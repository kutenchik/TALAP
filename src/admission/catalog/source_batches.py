"""Offline seed-order selection and audit of the curated English source list."""

import json
from pathlib import Path
from typing import Literal, TypedDict
from urllib.parse import urlparse

from admission.catalog.models import SeedInstitution
from admission.catalog.services import load_official_source_seeds


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
