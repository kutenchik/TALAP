"""Offline seed-order selection and audit of the curated English source list."""

import json
from pathlib import Path
from typing import Literal, TypedDict
from urllib.parse import urlparse

from admission.catalog.models import DataIssue, EnglishRequirement, SeedInstitution, SourceDocument
from admission.catalog.services import PILOT_ENGLISH_SOURCE_TYPE, load_official_source_seeds


class SourceGap(TypedDict):
    seed_order: int
    institution_ipeds_unitid: int
    institution_name: str
    active_official_source_urls: list[str]
    source_status: Literal["ready", "missing"]
    notes: str | None


def select_seed_batch(start: int, end: int) -> list[SeedInstitution]:
    """Require every inclusive seed order to resolve to a distinct institution."""
    if start < 1 or end < start:
        raise ValueError("Seed-order range must satisfy 1 <= start <= end")
    entries = list(
        SeedInstitution.objects.filter(seed_order__range=(start, end))
        .select_related("institution").order_by("seed_order")
    )
    orders = [entry.seed_order for entry in entries]
    if len(entries) != end - start + 1 or len(set(orders)) != len(orders):
        raise ValueError("Seed-order range is incomplete or contains duplicate seed orders")
    if any(entry.status != SeedInstitution.Status.RESOLVED or entry.institution_id is None for entry in entries):
        raise ValueError("Every selected seed must resolve to a canonical institution")
    unitids = [entry.institution.ipeds_unitid for entry in entries]
    if len(set(unitids)) != len(unitids):
        raise ValueError("Seed-order range contains duplicate institution UNITIDs")
    return entries


def resolve_source_selection(
    unitids: list[int], start: int | None, end: int | None,
) -> set[int] | list[int] | None:
    if start is None and end is None:
        return set(unitids) or None
    if start is None or end is None:
        raise ValueError("Both --seed-order-start and --seed-order-end are required")
    if unitids:
        raise ValueError("Use --unitid or a seed-order range, not both")
    return [entry.institution.ipeds_unitid for entry in select_seed_batch(start, end)]


def source_gap_rows(source_path: Path, start: int, end: int) -> list[SourceGap]:
    """Audit reviewed seeds locally; list membership is TASK-004's active contract.

    This is a curated-seed audit, not live verification or automated URL discovery.
    Historical SourceDocuments and issues do not activate an absent URL.
    """
    entries = select_seed_batch(start, end)
    seeds = load_official_source_seeds(source_path)
    rows: list[SourceGap] = []
    for entry in entries:
        institution = entry.institution
        selected = [seed for seed in seeds if seed.institution_ipeds_unitid == institution.ipeds_unitid]
        for seed in selected:
            if seed.institution_name != institution.name:
                raise ValueError(f"Source seed name differs from canonical UNITID {institution.ipeds_unitid}")
            url = urlparse(seed.url)
            host = (url.hostname or "").casefold()
            if url.scheme not in {"https", "http"} or not any(
                host == allowed.casefold() or host.endswith("." + allowed.casefold())
                for allowed in seed.allowed_hosts
            ):
                raise ValueError(f"Source URL is outside reviewed allowed hosts for UNITID {institution.ipeds_unitid}")
        urls = sorted(seed.url for seed in selected)
        rows.append({
            "seed_order": entry.seed_order,
            "institution_ipeds_unitid": institution.ipeds_unitid,
            "institution_name": institution.name,
            "active_official_source_urls": urls,
            "source_status": "ready" if urls else "missing",
            "notes": None if urls else "No active reviewed international undergraduate English source seed.",
        })
    return rows


def export_source_gaps(source_path: Path, output: Path, start: int, end: int) -> dict[str, int]:
    rows = source_gap_rows(source_path, start, end)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ready = sum(row["source_status"] == "ready" for row in rows)
    return {"batch_size": len(rows), "source_ready": ready, "source_missing": len(rows) - ready}


class BatchStatusRow(TypedDict):
    seed_order: int
    institution_ipeds_unitid: int
    institution_name: str
    official_source_url: str | None
    source_status: Literal["ready", "missing"]
    fetch_status: Literal["fetched", "failed", "not_attempted"]
    english_status: Literal[
        "verified",
        "no_minimum_published",
        "not_found",
        "not_required",
        "conflicting",
        "extraction_failed",
        "not_attempted",
    ]
    unresolved_reasons: list[str]


def batch_status_rows(source_path: Path, start: int, end: int) -> list[BatchStatusRow]:
    entries = select_seed_batch(start, end)
    seeds = load_official_source_seeds(source_path)
    rows: list[BatchStatusRow] = []
    for entry in entries:
        institution = entry.institution
        selected = [seed for seed in seeds if seed.institution_ipeds_unitid == institution.ipeds_unitid]
        if not selected:
            rows.append({
                "seed_order": entry.seed_order,
                "institution_ipeds_unitid": institution.ipeds_unitid,
                "institution_name": institution.name,
                "official_source_url": None,
                "source_status": "missing",
                "fetch_status": "not_attempted",
                "english_status": "not_attempted",
                "unresolved_reasons": ["source_not_found"],
            })
            continue

        seed = selected[0]
        source = SourceDocument.objects.filter(
            institution=institution,
            url=seed.url,
            source_type=PILOT_ENGLISH_SOURCE_TYPE,
        ).first()

        fetch_failed = (
            source is None
            or not source.content_hash
            or source.http_status != 200
        )

        if fetch_failed:
            rows.append({
                "seed_order": entry.seed_order,
                "institution_ipeds_unitid": institution.ipeds_unitid,
                "institution_name": institution.name,
                "official_source_url": seed.url,
                "source_status": "ready",
                "fetch_status": "failed",
                "english_status": "extraction_failed",
                "unresolved_reasons": ["source_fetch_failed"],
            })
            continue

        reqs = list(EnglishRequirement.objects.filter(
            institution=institution,
            source=source,
            source_content_hash=source.content_hash,
        ))

        if any(r.status == EnglishRequirement.Status.VERIFIED for r in reqs):
            english_status = "verified"
            unresolved_reasons = []
        elif any(r.status == EnglishRequirement.Status.NO_MINIMUM_PUBLISHED for r in reqs):
            english_status = "no_minimum_published"
            unresolved_reasons = []
        elif any(r.status == EnglishRequirement.Status.NOT_REQUIRED for r in reqs):
            english_status = "not_required"
            unresolved_reasons = []
        elif any(r.status == EnglishRequirement.Status.NOT_FOUND for r in reqs):
            english_status = "not_found"
            unresolved_reasons = []
        elif any(r.status == EnglishRequirement.Status.CONFLICTING for r in reqs):
            english_status = "conflicting"
            unresolved_reasons = ["conflicting_official_sources"]
        else:
            english_status = "extraction_failed"
            issues = list(DataIssue.objects.filter(
                seed_entry=entry,
                issue_type=DataIssue.IssueType.ENGLISH_EXTRACTION_REVIEW,
            ))
            if any("evidence" in iss.detail.lower() or "candidate" in iss.detail.lower() for iss in issues):
                unresolved_reasons = ["evidence_validation_failed"]
            else:
                unresolved_reasons = ["extraction_failed"]

        rows.append({
            "seed_order": entry.seed_order,
            "institution_ipeds_unitid": institution.ipeds_unitid,
            "institution_name": institution.name,
            "official_source_url": seed.url,
            "source_status": "ready",
            "fetch_status": "fetched",
            "english_status": english_status,
            "unresolved_reasons": unresolved_reasons,
        })
    return rows


def export_batch_status(source_path: Path, output: Path, start: int, end: int) -> dict[str, int]:
    rows = batch_status_rows(source_path, start, end)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    verified = sum(row["english_status"] == "verified" for row in rows)
    fetched = sum(row["fetch_status"] == "fetched" for row in rows)
    unresolved = sum(bool(row["unresolved_reasons"]) for row in rows)
    return {"batch_size": len(rows), "fetched": fetched, "verified": verified, "unresolved": unresolved}
