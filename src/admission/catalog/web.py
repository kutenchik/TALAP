"""Bounded, cache-backed retrieval and deterministic HTML text extraction."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura


DEFAULT_USER_AGENT = "PersonalAdmissionJourneyBot/0.1"


@dataclass(frozen=True)
class FetchResult:
    requested_url: str
    final_url: str
    http_status: int | None
    content: str | None
    content_hash: str
    from_cache: bool
    error: str = ""


@dataclass(frozen=True)
class ExtractedPage:
    title: str
    text: str
    method: str


class WebFetcher:
    """Fetch one reviewed page at a time; never performs general crawling."""

    def __init__(
        self,
        cache_root: Path = Path(".var/source_cache/web"),
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 20.0,
        retries: int = 2,
        user_agent: str = DEFAULT_USER_AGENT,
        respect_robots: bool = True,
    ) -> None:
        self.cache_root = cache_root
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.user_agent = user_agent
        self.respect_robots = respect_robots
        self.client = client or httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": user_agent},
        )

    @staticmethod
    def _key(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _cache_paths(self, url: str) -> tuple[Path, Path]:
        key = self._key(url)
        return self.cache_root / f"{key}.json", self.cache_root / f"{key}.html"

    def _load_cached(self, url: str) -> FetchResult | None:
        metadata_path, content_path = self._cache_paths(url)
        if not metadata_path.exists() or not content_path.exists():
            return None
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        return FetchResult(
            requested_url=url,
            final_url=metadata["final_url"],
            http_status=metadata["http_status"],
            content=content_path.read_text(encoding="utf-8"),
            content_hash=metadata["content_hash"],
            from_cache=True,
        )

    def _write_cache(self, result: FetchResult) -> None:
        metadata_path, content_path = self._cache_paths(result.requested_url)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        content_path.write_text(result.content or "", encoding="utf-8")
        metadata_path.write_text(
            json.dumps(
                {
                    "requested_url": result.requested_url,
                    "final_url": result.final_url,
                    "http_status": result.http_status,
                    "content_hash": result.content_hash,
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )

    def _robots_allowed(self, url: str) -> tuple[bool, str]:
        if not self.respect_robots:
            return True, "robots check disabled for injected test client"
        parts = urlsplit(url)
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        metadata_path, content_path = self._cache_paths(f"robots:{robots_url}")
        try:
            if content_path.exists():
                body = content_path.read_text(encoding="utf-8")
                status = json.loads(metadata_path.read_text(encoding="utf-8")).get("http_status", 200)
            else:
                response = self.client.get(robots_url)
                status = response.status_code
                body = response.text if response.status_code == 200 else ""
                metadata_path.parent.mkdir(parents=True, exist_ok=True)
                content_path.write_text(body, encoding="utf-8")
                metadata_path.write_text(json.dumps({"http_status": status}, sort_keys=True), encoding="utf-8")
        except httpx.HTTPError as exc:
            # A transient robots retrieval problem is recorded, not used to bypass a disallow.
            return False, f"robots retrieval failed: {exc.__class__.__name__}"
        if status != 200:
            return True, f"robots unavailable (HTTP {status}); no disallow document provided"
        parser = RobotFileParser()
        parser.parse(body.splitlines())
        if not parser.can_fetch(self.user_agent, url):
            return False, "robots.txt disallows this user agent"
        return True, "robots allowed"

    def fetch(self, url: str, *, refresh: bool = False) -> FetchResult:
        if not refresh:
            cached = self._load_cached(url)
            if cached is not None:
                return cached
        allowed, detail = self._robots_allowed(url)
        if not allowed:
            return FetchResult(url, url, None, None, "", False, detail)
        last_error = ""
        for _ in range(self.retries + 1):
            try:
                response = self.client.get(url)
                if 200 <= response.status_code < 300:
                    content = response.text
                    result = FetchResult(
                        requested_url=url,
                        final_url=str(response.url),
                        http_status=response.status_code,
                        content=content,
                        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                        from_cache=False,
                    )
                    self._write_cache(result)
                    return result
                last_error = f"HTTP {response.status_code}"
            except httpx.HTTPError as exc:
                last_error = f"{exc.__class__.__name__}: {exc}"
        return FetchResult(url, url, None, None, "", False, last_error or detail)


def extract_page(html: str) -> ExtractedPage:
    """Extract readable text while retaining table content whenever possible."""

    metadata = trafilatura.extract_metadata(html)
    title = metadata.title.strip() if metadata and metadata.title else ""
    text = trafilatura.extract(html, include_tables=True, include_links=False, favor_recall=True) or ""
    method = "trafilatura"
    if not text.strip():
        text = trafilatura.html2txt(html) or ""
        method = "trafilatura_html2txt"
    return ExtractedPage(title=title, text=text.strip(), method=method)


def select_english_relevance(text: str, *, context_lines: int = 4, max_characters: int = 12000) -> str:
    """Select deterministic local context rather than sending whole pages to a model."""

    keywords = (
        "ielts", "toefl", "duolingo", "english proficiency", "english language",
        "international applicant", "international student", "minimum score", "waiver", "exemption",
        "conditional admission",
    )
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    selected: set[int] = set()
    for index, line in enumerate(lines):
        if any(keyword in line.casefold() for keyword in keywords):
            selected.update(range(max(0, index - context_lines), min(len(lines), index + context_lines + 1)))
    if not selected:
        return ""
    material = "\n".join(lines[index] for index in sorted(selected))
    return material[:max_characters]
