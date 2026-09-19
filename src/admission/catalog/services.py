"""Application services for TASK-001 catalog resolution and export."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from django.db import models, transaction
from django.db.models import F, Q

from admission.llm.alem import EnglishExtractionClient, LLMUnavailable

from .matching import exact_state_matches, fuzzy_candidates, is_bachelors_granting, normalize_name, ownership_from_control
from .models import AdmissionSnapshot, DataIssue, EnglishRequirement, Institution, InstitutionAlias, ProgramOffering, SeedInstitution, SourceDocument
from .schemas import EnglishExtractionResponse, EnglishRequirementCandidate, IpedAdmissionsRecord, IpedBachelorCompletionRecord, IpedInstitutionRecord, OfficialSourceSeed, SeedManifest
from .web import WebFetcher, extract_page, select_english_relevance

IPEDS_HD_2024_URL = "https://nces.ed.gov/ipeds/datacenter/data/HD2024.zip"
IPEDS_HD_2024_YEAR = "2024"
IPEDS_C2024_A_URL = "https://nces.ed.gov/ipeds/datacenter/data/C2024_A.zip"
IPEDS_C2024_A_YEAR = "2024"
CIP_2020_RESOURCE_URL = "https://nces.ed.gov/ipeds/cipcode/resources.aspx?y=56"
CIP_2020_YEAR = "2020"
BACHELOR_AWARD_LEVEL = 5
KNOWN_AWARD_LEVELS = frozenset({1, 2, 3, 4, 5, 6, 7, 8, 17, 18, 19, 20, 21})
# C2024_A encodes its Summary Grand Totals row as "99"; some IPEDS exports render it as "99.0000".
IPEDS_SUMMARY_CIP_CODES = frozenset({"99", "99.0000"})
IPEDS_ADM2024_URL = "https://nces.ed.gov/ipeds/complete-data-files/ADM2024.zip"
IPEDS_ADM2024_DICTIONARY_URL = "https://nces.ed.gov/ipeds/complete-data-files/ADM2024_Dict.zip"
IPEDS_ADM2024_YEAR = "2024"
IPEDS_ADM2024_TERM = "fall"
# ADM2024_Dict.xlsx, "Imputation values": these codes apply to each ADM
# continuous variable used below.  Keep this release-specific mapping here
# rather than applying a guessed cross-survey IPEDS flag set.
ADM2024_FLAG_STATUSES = {
    "A": "not_applicable",  # Not applicable
    "B": "not_reported",  # Institution left item blank
    "C": "reported",  # Analyst corrected reported value
    "D": "unknown",  # Do not know
    "G": "imputed",  # Data generated from other data values
    "H": "unavailable",  # Value not derived - data not usable
    "J": "imputed",  # Logical imputation
    "K": "imputed",  # Ratio adjustment
    "L": "imputed",  # Imputed using the Group Median procedure
    "N": "imputed",  # Imputed using Nearest Neighbor procedure
    "P": "imputed",  # Imputed using Carry Forward procedure
    "R": "reported",  # Reported
    "Z": "implied_zero",  # Implied zero
}
ADM2024_VALUE_FLAGS = frozenset({"C", "G", "J", "K", "L", "N", "P", "R"})


def load_seed_manifest(path: Path) -> SeedManifest:
    return SeedManifest.model_validate_json(path.read_text(encoding="utf-8"))


@transaction.atomic
def seed_manifest(path: Path) -> int:
    manifest = load_seed_manifest(path)
    if len(manifest.universities) != 100:
        raise ValueError(f"Expected exactly 100 seed entries, found {len(manifest.universities)}")
    orders = [entry.seed_order for entry in manifest.universities]
    if len(set(orders)) != len(orders):
        raise ValueError("Seed manifest contains duplicate seed_order values")
    for entry in manifest.universities:
        SeedInstitution.objects.update_or_create(
            seed_order=entry.seed_order,
            defaults={
                "name": entry.name,
                "state": entry.state,
                "expected_ownership": entry.ownership,
            },
        )
    return len(manifest.universities)


def _website(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    return value if urlparse(value).scheme else f"https://{value}"


def load_ipeds_records(path: Path) -> list[IpedInstitutionRecord]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    records: list[IpedInstitutionRecord] = []
    for row in rows:
        try:
            records.append(
                IpedInstitutionRecord(
                    unitid=int(row["UNITID"]), name=row["INSTNM"].strip(), city=row["CITY"].strip(),
                    state=row["STABBR"].strip(), control=int(row["CONTROL"]), website=row.get("WEBADDR", ""),
                    cyactive=int(row["CYACTIVE"]), ugoffer=int(row["UGOFFER"]), hloffer=int(row["HLOFFER"]),
                    deggrant=int(row["DEGGRANT"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    if not records:
        raise ValueError(f"No usable IPEDS records found in {path}")
    return records


def _upsert_issue(seed: SeedInstitution, issue_type: str, detail: str, *, issue_key: str = "") -> None:
    """Upsert a review item without making different reviewed URLs collide."""

    DataIssue.objects.update_or_create(
        seed_entry=seed,
        issue_type=issue_type,
        issue_key=issue_key,
        defaults={"detail": detail},
    )


@transaction.atomic
def import_ipeds(path: Path, source_url: str = IPEDS_HD_2024_URL, data_year: str = IPEDS_HD_2024_YEAR) -> dict[str, int]:
    records = load_ipeds_records(path)
    content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    source, created = SourceDocument.objects.get_or_create(
        url=source_url,
        defaults={
            "publisher": "National Center for Education Statistics (IPEDS)",
            "source_type": "institutional_characteristics",
            "data_year": data_year,
            "retrieved_at": datetime.now(timezone.utc),
            "content_hash": content_hash,
            "extraction_method": "csv_import",
        },
    )
    if not created and source.content_hash != content_hash:
        source.data_year = data_year
        source.retrieved_at = datetime.now(timezone.utc)
        source.content_hash = content_hash
        source.save(update_fields=["data_year", "retrieved_at", "content_hash"])
    state_name_index: dict[tuple[str, str], list[IpedInstitutionRecord]] = {}
    name_index: dict[str, list[IpedInstitutionRecord]] = {}
    for record in records:
        state_name_index.setdefault((record.state, normalize_name(record.name)), []).append(record)
        name_index.setdefault(normalize_name(record.name), []).append(record)

    counts = {"resolved": 0, "ambiguous": 0, "unresolved": 0, "state_mismatch": 0, "ownership_mismatch": 0}
    used_unitids: dict[int, int] = {}
    for seed in SeedInstitution.objects.order_by("seed_order"):
        DataIssue.objects.filter(
            seed_entry=seed,
            issue_type__in=[
                DataIssue.IssueType.AMBIGUOUS_MATCH,
                DataIssue.IssueType.UNRESOLVED_MATCH,
                DataIssue.IssueType.STATE_MISMATCH,
                DataIssue.IssueType.OWNERSHIP_MISMATCH,
                DataIssue.IssueType.DUPLICATE_UNITID,
            ],
        ).delete()
        matches = state_name_index.get((seed.state, normalize_name(seed.name)), [])
        if len(matches) == 1:
            candidate = matches[0]
            if candidate.unitid in used_unitids:
                seed.status = SeedInstitution.Status.AMBIGUOUS
                seed.institution = None
                seed.save(update_fields=["status", "institution"])
                _upsert_issue(seed, DataIssue.IssueType.DUPLICATE_UNITID, f"UNITID {candidate.unitid} was already assigned to seed order {used_unitids[candidate.unitid]}.")
                counts["ambiguous"] += 1
                continue
            ownership = ownership_from_control(candidate.control)
            expected = "private_nonprofit" if seed.expected_ownership == "private" else seed.expected_ownership
            if ownership != expected:
                seed.status = SeedInstitution.Status.UNRESOLVED
                seed.institution = None
                seed.save(update_fields=["status", "institution"])
                _upsert_issue(seed, DataIssue.IssueType.OWNERSHIP_MISMATCH, f"Seed expects {expected}; IPEDS CONTROL={candidate.control} maps to {ownership}.")
                counts["unresolved"] += 1
                counts["ownership_mismatch"] += 1
                continue
            institution, _ = Institution.objects.update_or_create(
                ipeds_unitid=candidate.unitid,
                defaults={
                    "name": candidate.name, "state": candidate.state, "city": candidate.city, "country": "US",
                    "ownership": ownership, "official_website": _website(candidate.website),
                    "operating_status": "active" if candidate.cyactive == 1 else "not_active",
                    "bachelors_granting": is_bachelors_granting(candidate),
                    "bachelors_granting_evidence": f"UGOFFER={candidate.ugoffer}; HLOFFER={candidate.hloffer}; DEGGRANT={candidate.deggrant}",
                    "source": source, "source_locator": f"HD{data_year}.csv UNITID {candidate.unitid}",
                },
            )
            InstitutionAlias.objects.update_or_create(institution=institution, alias=seed.name, alias_type="seed_name")
            seed.status = SeedInstitution.Status.RESOLVED
            seed.institution = institution
            seed.save(update_fields=["status", "institution"])
            used_unitids[candidate.unitid] = seed.seed_order
            counts["resolved"] += 1
        elif len(matches) > 1:
            seed.status = SeedInstitution.Status.AMBIGUOUS
            seed.institution = None
            seed.save(update_fields=["status", "institution"])
            _upsert_issue(seed, DataIssue.IssueType.AMBIGUOUS_MATCH, f"Exact state/name match produced UNITIDs: {', '.join(str(match.unitid) for match in matches)}")
            counts["ambiguous"] += 1
        else:
            seed.status = SeedInstitution.Status.UNRESOLVED
            seed.institution = None
            seed.save(update_fields=["status", "institution"])
            same_name = name_index.get(normalize_name(seed.name), [])
            if same_name:
                _upsert_issue(seed, DataIssue.IssueType.STATE_MISMATCH, f"Name matches only in state(s): {', '.join(sorted({match.state for match in same_name}))}; seed state is {seed.state}.")
                counts["state_mismatch"] += 1
            else:
                suggestions = fuzzy_candidates(seed.name, seed.state, records)
                description = ", ".join(f"{match.name} ({match.unitid})" for match in suggestions) or "no state-local candidates"
                _upsert_issue(seed, DataIssue.IssueType.UNRESOLVED_MATCH, f"No exact state/name match. Non-final fuzzy suggestions: {description}.")
            counts["unresolved"] += 1
    return counts


def status_counts() -> dict[str, int]:
    return {
        "total": SeedInstitution.objects.count(),
        "resolved": SeedInstitution.objects.filter(status=SeedInstitution.Status.RESOLVED).count(),
        "ambiguous": SeedInstitution.objects.filter(status=SeedInstitution.Status.AMBIGUOUS).count(),
        "unresolved": SeedInstitution.objects.filter(status=SeedInstitution.Status.UNRESOLVED).count(),
        "pending": SeedInstitution.objects.filter(status=SeedInstitution.Status.PENDING).count(),
    }


def status_rows() -> list[dict[str, object]]:
    rows = []
    for seed in SeedInstitution.objects.select_related("institution").prefetch_related("issues").order_by("seed_order"):
        rows.append({
            "seed_order": seed.seed_order, "seed_name": seed.name, "state": seed.state, "status": seed.status,
            "ipeds_unitid": seed.institution.ipeds_unitid if seed.institution else None,
            "canonical_name": seed.institution.name if seed.institution else None,
            "issues": [issue.issue_type for issue in seed.issues.all()],
        })
    return rows


def export_institutions(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for institution in Institution.objects.select_related("source").prefetch_related("aliases").order_by("ipeds_unitid"):
        records.append({
            "bachelors_granting": institution.bachelors_granting,
            "bachelors_granting_evidence": institution.bachelors_granting_evidence,
            "city": institution.city,
            "country": institution.country,
            "ipeds_unitid": institution.ipeds_unitid,
            "name": institution.name,
            "official_website": institution.official_website or None,
            "operating_status": institution.operating_status,
            "ownership": institution.ownership,
            "seed_aliases": sorted(alias.alias for alias in institution.aliases.filter(alias_type="seed_name")),
            "source": {
                "data_year": institution.source.data_year,
                "content_hash": institution.source.content_hash,
                "extraction_method": institution.source.extraction_method,
                "publisher": institution.source.publisher,
                "retrieved_at": institution.source.retrieved_at.isoformat(),
                "source_locator": institution.source_locator,
                "url": institution.source.url,
            },
            "state": institution.state,
        })
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
    return len(records)


def _normalize_cip_code(value: str) -> str:
    value = value.strip()
    if value.startswith('="') and value.endswith('"'):
        value = value[2:-1]
    return value


def _is_ipeds_summary_cip_code(value: str) -> bool:
    return _normalize_cip_code(value) in IPEDS_SUMMARY_CIP_CODES


def load_cip_titles(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = csv.DictReader(handle)
        titles = {
            _normalize_cip_code(row.get("CIPCode", "")): row.get("CIPTitle", "").strip()
            for row in rows
            if _normalize_cip_code(row.get("CIPCode", "")) and row.get("CIPTitle", "").strip()
        }
    if not titles:
        raise ValueError(f"No CIP 2020 titles found in {path}")
    return titles


def _source_document(
    url: str,
    publisher: str,
    source_type: str,
    data_year: str,
    path: Path,
    extraction_method: str = "csv_import",
) -> SourceDocument:
    content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    source, created = SourceDocument.objects.get_or_create(
        url=url,
        institution__isnull=True,
        defaults={
            "publisher": publisher,
            "source_type": source_type,
            "data_year": data_year,
            "retrieved_at": datetime.now(timezone.utc),
            "content_hash": content_hash,
            "extraction_method": extraction_method,
        },
    )
    if not created and (source.content_hash != content_hash or source.extraction_method != extraction_method):
        update_fields = ["data_year", "extraction_method"]
        source.data_year = data_year
        source.extraction_method = extraction_method
        if source.content_hash != content_hash:
            source.retrieved_at = datetime.now(timezone.utc)
            source.content_hash = content_hash
            update_fields.extend(["retrieved_at", "content_hash"])
        source.save(update_fields=update_fields)
    return source


def _completion_record(row: dict[str, str], cip_titles: dict[str, str]) -> IpedBachelorCompletionRecord:
    cip_code = _normalize_cip_code(row.get("CIPCODE", ""))
    return IpedBachelorCompletionRecord(
        unitid=int(row["UNITID"]),
        cip_code=cip_code,
        cip_title=cip_titles.get(cip_code, ""),
        award_level=int(row["AWLEVEL"]),
        completion_count=int(row["CTOTALT"]),
        major_number=int(row["MAJORNUM"]),
    )


@transaction.atomic
def import_bachelors_programs(
    completions_path: Path,
    cip_titles_path: Path,
    source_url: str = IPEDS_C2024_A_URL,
    data_year: str = IPEDS_C2024_A_YEAR,
    cip_source_url: str = CIP_2020_RESOURCE_URL,
) -> dict[str, int]:
    """Import aggregate CIP coverage only when IPEDS reports bachelor's awards."""

    cip_titles = load_cip_titles(cip_titles_path)
    completions_source = _source_document(
        source_url,
        "National Center for Education Statistics (IPEDS)",
        "completions_program_awards",
        data_year,
        completions_path,
    )
    cip_source = _source_document(
        cip_source_url,
        "National Center for Education Statistics (CIP 2020)",
        "cip_classification",
        CIP_2020_YEAR,
        cip_titles_path,
    )
    institutions = {institution.ipeds_unitid: institution for institution in Institution.objects.order_by("ipeds_unitid")}
    institution_ids = {institution.id for institution in institutions.values()}
    seed_by_institution = {
        seed.institution_id: seed for seed in SeedInstitution.objects.filter(institution__isnull=False).select_related("institution")
    }
    if len(institutions) != 100 or len(seed_by_institution) != 100:
        raise ValueError("TASK-002 requires exactly 100 resolved canonical institutions")

    program_issue_types = [DataIssue.IssueType.INVALID_PROGRAM_RECORD, DataIssue.IssueType.ZERO_BACHELOR_PROGRAMS]
    DataIssue.objects.filter(seed_entry__institution_id__in=institution_ids, issue_type__in=program_issue_types).delete()
    aggregated: dict[tuple[int, str], dict[str, object]] = {}
    invalid_by_unitid: dict[int, list[str]] = {}
    summary_rows_ignored = 0
    with completions_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            try:
                unitid = int(row.get("UNITID", ""))
            except ValueError:
                continue
            if unitid not in institutions:
                continue
            try:
                award_level = int(row.get("AWLEVEL", ""))
            except ValueError:
                invalid_by_unitid.setdefault(unitid, []).append("missing or non-numeric AWLEVEL")
                continue
            if award_level not in KNOWN_AWARD_LEVELS:
                invalid_by_unitid.setdefault(unitid, []).append(f"unknown AWLEVEL={award_level}")
                continue
            if award_level != BACHELOR_AWARD_LEVEL:
                continue
            if _is_ipeds_summary_cip_code(row.get("CIPCODE", "")):
                summary_rows_ignored += 1
                continue
            try:
                record = _completion_record(row, cip_titles)
            except (KeyError, TypeError, ValueError):
                invalid_by_unitid.setdefault(unitid, []).append(
                    f"invalid bachelor's row CIPCODE={row.get('CIPCODE', '')!r} MAJORNUM={row.get('MAJORNUM', '')!r}"
                )
                continue
            if record.completion_count == 0:
                continue
            key = (record.unitid, record.cip_code)
            entry = aggregated.setdefault(
                key,
                {"cip_title": record.cip_title, "completion_count": 0, "major_numbers": []},
            )
            entry["completion_count"] = int(entry["completion_count"]) + record.completion_count
            entry["major_numbers"].append(record.major_number)

    for unitid, details in invalid_by_unitid.items():
        _upsert_issue(
            seed_by_institution[institutions[unitid].id],
            DataIssue.IssueType.INVALID_PROGRAM_RECORD,
            "; ".join(sorted(set(details))),
        )

    program_counts: dict[int, int] = {unitid: 0 for unitid in institutions}
    for (unitid, cip_code), entry in sorted(aggregated.items()):
        institution = institutions[unitid]
        major_numbers = sorted(set(entry["major_numbers"]))
        source_locator = (
            f"C{data_year}_A.csv UNITID {unitid}; CIPCODE {cip_code}; AWLEVEL={BACHELOR_AWARD_LEVEL}; "
            f"MAJORNUM={','.join(str(number) for number in major_numbers)}"
        )
        completion_count = int(entry["completion_count"])
        ProgramOffering.objects.update_or_create(
            institution=institution,
            cip_code=cip_code,
            credential_level="bachelors_degree",
            academic_year=data_year,
            defaults={
                "cip_title": str(entry["cip_title"]),
                "award_level": BACHELOR_AWARD_LEVEL,
                "program_name": "",
                "completion_count": completion_count,
                "status": "verified",
                "source": completions_source,
                "cip_title_source": cip_source,
                "source_locator": source_locator,
                "evidence": f"IPEDS reported {completion_count} bachelor's award completion(s) across MAJORNUM {','.join(str(number) for number in major_numbers)}.",
            },
        )
        program_counts[unitid] += 1

    for unitid, count in program_counts.items():
        institution = institutions[unitid]
        seed = seed_by_institution[institution.id]
        if count == 0:
            _upsert_issue(
                seed,
                DataIssue.IssueType.ZERO_BACHELOR_PROGRAMS,
                f"No positive AWLEVEL={BACHELOR_AWARD_LEVEL} completions evidence found in C{data_year}_A for UNITID {unitid}.",
            )
        else:
            institution.bachelors_granting = True
            institution.bachelors_granting_evidence = (
                f"C{data_year}_A bachelor's completions evidence: {count} CIP record(s), AWLEVEL={BACHELOR_AWARD_LEVEL}."
            )
            institution.save(update_fields=["bachelors_granting", "bachelors_granting_evidence"])

    total_records = ProgramOffering.objects.filter(institution_id__in=institution_ids, academic_year=data_year, credential_level="bachelors_degree").count()
    duplicate_records = sum(
        group["count"] - 1
        for group in ProgramOffering.objects.filter(institution_id__in=institution_ids, academic_year=data_year)
        .values("institution_id", "cip_code", "credential_level", "academic_year")
        .annotate(count=models.Count("id"))
        .filter(count__gt=1)
    )
    return {
        "institutions_processed": len(institutions),
        "institutions_with_programs": sum(count > 0 for count in program_counts.values()),
        "institutions_zero_programs": sum(count == 0 for count in program_counts.values()),
        "program_records": total_records,
        "unique_cip_codes": len({cip_code for _, cip_code in aggregated}),
        "duplicate_records": duplicate_records,
        "invalid_records": sum(len(set(details)) for details in invalid_by_unitid.values()),
        "summary_rows_ignored": summary_rows_ignored,
    }


def export_programs(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for program in ProgramOffering.objects.select_related("institution", "source", "cip_title_source").order_by("institution__ipeds_unitid", "cip_code"):
        records.append({
            "academic_year": program.academic_year,
            "award_level": program.award_level,
            "cip_code": program.cip_code,
            "cip_title": program.cip_title,
            "cip_title_source": {
                "content_hash": program.cip_title_source.content_hash,
                "data_year": program.cip_title_source.data_year,
                "extraction_method": program.cip_title_source.extraction_method,
                "publisher": program.cip_title_source.publisher,
                "retrieved_at": program.cip_title_source.retrieved_at.isoformat(),
                "url": program.cip_title_source.url,
            },
            "completion_count": program.completion_count,
            "credential_level": program.credential_level,
            "evidence": program.evidence,
            "institution_ipeds_unitid": program.institution.ipeds_unitid,
            "program_name": program.program_name or None,
            "source": {
                "content_hash": program.source.content_hash,
                "data_year": program.source.data_year,
                "publisher": program.source.publisher,
                "retrieved_at": program.source.retrieved_at.isoformat(),
                "source_locator": program.source_locator,
                "url": program.source.url,
            },
            "status": program.status,
        })
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
    return len(records)


def program_status() -> dict[str, int]:
    institutions = Institution.objects.count()
    zero_issues = DataIssue.objects.filter(issue_type=DataIssue.IssueType.ZERO_BACHELOR_PROGRAMS).count()
    duplicate_records = sum(
        group["count"] - 1
        for group in ProgramOffering.objects.values("institution_id", "cip_code", "credential_level", "academic_year")
        .annotate(count=models.Count("id"))
        .filter(count__gt=1)
    )
    return {
        "institutions_processed": institutions,
        "institutions_with_programs": Institution.objects.filter(program_offerings__credential_level="bachelors_degree").distinct().count(),
        "institutions_zero_programs": zero_issues,
        "program_records": ProgramOffering.objects.count(),
        "unique_cip_codes": ProgramOffering.objects.values("cip_code").distinct().count(),
        "duplicate_records": duplicate_records,
    }


def _field_value(row: dict[str, str], field: str, *, score: bool = False) -> tuple[int | None, str, str, bool]:
    """Map an ADM2024 continuous value and its documented imputation flag."""

    raw_value = row.get(field, "").strip()
    flag = row.get(f"X{field}", "").strip()
    status = ADM2024_FLAG_STATUSES.get(flag)
    if status is None:
        # ADM2024 defines a flag for every imported continuous field. A blank
        # or unfamiliar flag paired with a row is source-malformed, not reported.
        return None, "unknown", flag, True
    if flag == "Z":
        # An implied zero is meaningful for counts/percentages but cannot be a
        # valid SAT/ACT percentile score. Preserve the raw flag either way.
        if raw_value and raw_value != "0":
            return None, "unknown", flag, True
        if score:
            return None, "unavailable", flag, False
        return 0, status, flag, False
    if flag in ADM2024_VALUE_FLAGS:
        if not raw_value:
            return None, "unknown", flag, True
        return int(raw_value), status, flag, False
    # A, B, D, and H are documented legitimate non-numeric source states.
    return None, status, flag, False


def _group_status(items: list[tuple[int | None, str, str, bool]]) -> str:
    values = [item for item in items if item[0] is not None]
    if values:
        if any(item[1] == "reported" for item in values):
            return "reported"
        if any(item[1] == "imputed" for item in values):
            return "imputed"
        return "implied_zero"
    statuses = {item[1] for item in items}
    if statuses == {"not_applicable"}:
        return "not_applicable"
    if statuses <= {"not_reported"}:
        return "not_reported"
    if statuses <= {"unknown"}:
        return "unknown"
    return "unavailable"


def _combined_test_status(sat_status: str, act_status: str) -> str:
    if "reported" in {sat_status, act_status}:
        return "reported"
    if "imputed" in {sat_status, act_status}:
        return "imputed"
    if sat_status == act_status == "not_applicable":
        return "not_applicable"
    if sat_status == act_status == "not_reported":
        return "not_reported"
    if sat_status == act_status == "unknown":
        return "unknown"
    if sat_status == act_status == "implied_zero":
        return "implied_zero"
    return "unavailable"


def _empty_admission_defaults(source: SourceDocument, dictionary_source: SourceDocument, data_year: str, term: str, locator: str) -> dict[str, object]:
    return {
        "applicant_count": None,
        "admitted_count": None,
        "enrolled_count": None,
        "admission_rate": None,
        "sat_ebrw_25": None,
        "sat_ebrw_75": None,
        "sat_math_25": None,
        "sat_math_75": None,
        "act_composite_25": None,
        "act_composite_75": None,
        "sat_submission_count": None,
        "sat_submission_percent": None,
        "act_submission_count": None,
        "act_submission_percent": None,
        "admissions_data_status": "unavailable",
        "sat_data_status": "unavailable",
        "act_data_status": "unavailable",
        "test_data_status": "unavailable",
        "source_flags": {},
        "source": source,
        "dictionary_source": dictionary_source,
        "source_locator": locator,
        "evidence": "No ADM2024 row was available for this canonical UNITID.",
    }


@transaction.atomic
def import_admissions(
    admissions_path: Path,
    dictionary_path: Path,
    source_url: str = IPEDS_ADM2024_URL,
    dictionary_url: str = IPEDS_ADM2024_DICTIONARY_URL,
    data_year: str = IPEDS_ADM2024_YEAR,
    term: str = IPEDS_ADM2024_TERM,
) -> dict[str, int]:
    """Import Fall IPEDS admissions/test-score context; never infer test policy or applicant outcomes."""

    source = _source_document(
        source_url,
        "National Center for Education Statistics (IPEDS)",
        "admissions_and_test_scores",
        data_year,
        admissions_path,
    )
    dictionary_source = _source_document(
        dictionary_url,
        "National Center for Education Statistics (IPEDS)",
        "admissions_data_dictionary",
        data_year,
        dictionary_path,
        extraction_method="xlsx_dictionary",
    )
    institutions = {institution.ipeds_unitid: institution for institution in Institution.objects.order_by("ipeds_unitid")}
    institution_ids = {institution.id for institution in institutions.values()}
    seeds = {seed.institution_id: seed for seed in SeedInstitution.objects.filter(institution__isnull=False)}
    if len(institutions) != 100 or len(seeds) != 100:
        raise ValueError("TASK-003 requires exactly 100 resolved canonical institutions")

    DataIssue.objects.filter(
        seed_entry__institution_id__in=institution_ids,
        issue_type=DataIssue.IssueType.INVALID_ADMISSIONS_RECORD,
    ).delete()
    rows_by_unitid: dict[int, dict[str, str]] = {}
    duplicate_source_rows: set[int] = set()
    with admissions_path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            try:
                unitid = int(row.get("UNITID", ""))
            except ValueError:
                continue
            if unitid not in institutions:
                continue
            if unitid in rows_by_unitid:
                duplicate_source_rows.add(unitid)
                continue
            rows_by_unitid[unitid] = row

    invalid_records = 0
    for unitid, institution in institutions.items():
        locator = f"ADM{data_year}.csv UNITID {unitid}"
        row = rows_by_unitid.get(unitid)
        if row is None:
            AdmissionSnapshot.objects.update_or_create(
                institution=institution,
                data_year=data_year,
                term=term,
                defaults=_empty_admission_defaults(source, dictionary_source, data_year, term, locator),
            )
            continue
        if unitid in duplicate_source_rows:
            invalid_records += 1
            _upsert_issue(seeds[institution.id], DataIssue.IssueType.INVALID_ADMISSIONS_RECORD, "Duplicate ADM2024 source rows for canonical UNITID.")
            AdmissionSnapshot.objects.filter(institution=institution, data_year=data_year, term=term).delete()
            continue
        try:
            values = {
                "applicant_count": _field_value(row, "APPLCN"),
                "admitted_count": _field_value(row, "ADMSSN"),
                "enrolled_count": _field_value(row, "ENRLT"),
                "sat_submission_count": _field_value(row, "SATNUM"),
                "sat_submission_percent": _field_value(row, "SATPCT"),
                "act_submission_count": _field_value(row, "ACTNUM"),
                "act_submission_percent": _field_value(row, "ACTPCT"),
                "sat_ebrw_25": _field_value(row, "SATVR25", score=True),
                "sat_ebrw_75": _field_value(row, "SATVR75", score=True),
                "sat_math_25": _field_value(row, "SATMT25", score=True),
                "sat_math_75": _field_value(row, "SATMT75", score=True),
                "act_composite_25": _field_value(row, "ACTCM25", score=True),
                "act_composite_75": _field_value(row, "ACTCM75", score=True),
            }
            unknown_flags = [f"{field}={value[2] or '<blank>'}" for field, value in values.items() if value[3]]
            if unknown_flags:
                raise ValueError(f"Undocumented or inconsistent ADM2024 imputation flag(s): {', '.join(unknown_flags)}")
            record = IpedAdmissionsRecord(unitid=unitid, **{field: value[0] for field, value in values.items()})
        except (KeyError, TypeError, ValueError) as exc:
            invalid_records += 1
            _upsert_issue(seeds[institution.id], DataIssue.IssueType.INVALID_ADMISSIONS_RECORD, str(exc))
            AdmissionSnapshot.objects.filter(institution=institution, data_year=data_year, term=term).delete()
            continue

        admissions_status = _group_status([values[field] for field in ("applicant_count", "admitted_count", "enrolled_count")])
        sat_status = _group_status([values[field] for field in ("sat_submission_count", "sat_submission_percent", "sat_ebrw_25", "sat_ebrw_75", "sat_math_25", "sat_math_75")])
        act_status = _group_status([values[field] for field in ("act_submission_count", "act_submission_percent", "act_composite_25", "act_composite_75")])
        admission_rate = None
        if record.applicant_count is not None and record.admitted_count is not None and record.applicant_count > 0:
            admission_rate = (Decimal(record.admitted_count) / Decimal(record.applicant_count)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        source_flags = {field: value[2] for field, value in values.items()}
        AdmissionSnapshot.objects.update_or_create(
            institution=institution,
            data_year=data_year,
            term=term,
            defaults={
                **{field: getattr(record, field) for field in values},
                "admission_rate": admission_rate,
                "admissions_data_status": admissions_status,
                "sat_data_status": sat_status,
                "act_data_status": act_status,
                "test_data_status": _combined_test_status(sat_status, act_status),
                "source_flags": source_flags,
                "source": source,
                "dictionary_source": dictionary_source,
                "source_locator": locator,
                "evidence": "IPEDS ADM2024 Fall 2024 context for first-time degree/certificate-seeking undergraduate applicants/enrollees; score percentiles are distributions, not requirements or policy.",
            },
        )

    snapshots = AdmissionSnapshot.objects.filter(institution_id__in=institution_ids, data_year=data_year, term=term)
    duplicate_records = sum(
        group["count"] - 1
        for group in snapshots.values("institution_id", "data_year", "term").annotate(count=models.Count("id")).filter(count__gt=1)
    )
    return {
        "institutions_processed": len(institutions),
        "institutions_with_admissions_records": snapshots.count(),
        "institutions_without_applicable_or_reported_admissions_data": snapshots.exclude(admissions_data_status__in=["reported", "imputed"]).count(),
        "institutions_with_admission_rate": snapshots.filter(admission_rate__isnull=False).count(),
        "institutions_with_sat_percentiles": snapshots.filter(sat_ebrw_25__isnull=False).count(),
        "institutions_with_act_percentiles": snapshots.filter(act_composite_25__isnull=False).count(),
        "invalid_records": invalid_records,
        "duplicate_records": duplicate_records,
    }


def export_admissions(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for snapshot in AdmissionSnapshot.objects.select_related("institution", "source", "dictionary_source").order_by("institution__ipeds_unitid", "data_year", "term"):
        records.append({
            "act_composite_25": snapshot.act_composite_25,
            "act_composite_75": snapshot.act_composite_75,
            "act_data_status": snapshot.act_data_status,
            "act_submission_count": snapshot.act_submission_count,
            "act_submission_percent": snapshot.act_submission_percent,
            "admission_rate": str(snapshot.admission_rate) if snapshot.admission_rate is not None else None,
            "admissions_data_status": snapshot.admissions_data_status,
            "admitted_count": snapshot.admitted_count,
            "applicant_count": snapshot.applicant_count,
            "data_year": snapshot.data_year,
            "dictionary_source": {
                "content_hash": snapshot.dictionary_source.content_hash,
                "data_year": snapshot.dictionary_source.data_year,
                "extraction_method": snapshot.dictionary_source.extraction_method,
                "publisher": snapshot.dictionary_source.publisher,
                "retrieved_at": snapshot.dictionary_source.retrieved_at.isoformat(),
                "url": snapshot.dictionary_source.url,
            },
            "enrolled_count": snapshot.enrolled_count,
            "evidence": snapshot.evidence,
            "institution_ipeds_unitid": snapshot.institution.ipeds_unitid,
            "sat_data_status": snapshot.sat_data_status,
            "sat_ebrw_25": snapshot.sat_ebrw_25,
            "sat_ebrw_75": snapshot.sat_ebrw_75,
            "sat_math_25": snapshot.sat_math_25,
            "sat_math_75": snapshot.sat_math_75,
            "sat_submission_count": snapshot.sat_submission_count,
            "sat_submission_percent": snapshot.sat_submission_percent,
            "source": {
                "content_hash": snapshot.source.content_hash,
                "data_year": snapshot.source.data_year,
                "publisher": snapshot.source.publisher,
                "retrieved_at": snapshot.source.retrieved_at.isoformat(),
                "source_locator": snapshot.source_locator,
                "url": snapshot.source.url,
            },
            "source_flags": snapshot.source_flags,
            "term": snapshot.term,
            "test_data_status": snapshot.test_data_status,
        })
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
    return len(records)


def admissions_status() -> dict[str, int]:
    snapshots = AdmissionSnapshot.objects.all()
    duplicate_records = sum(
        group["count"] - 1
        for group in snapshots.values("institution_id", "data_year", "term").annotate(count=models.Count("id")).filter(count__gt=1)
    )
    return {
        "institutions_processed": Institution.objects.count(),
        "institutions_with_admissions_records": snapshots.count(),
        "institutions_without_applicable_or_reported_admissions_data": snapshots.exclude(admissions_data_status__in=["reported", "imputed"]).count(),
        "institutions_with_admission_rate": snapshots.filter(admission_rate__isnull=False).count(),
        "institutions_with_sat_percentiles": snapshots.filter(sat_ebrw_25__isnull=False).count(),
        "institutions_with_act_percentiles": snapshots.filter(act_composite_25__isnull=False).count(),
        "invalid_records": DataIssue.objects.filter(issue_type=DataIssue.IssueType.INVALID_ADMISSIONS_RECORD).count(),
        "duplicate_records": duplicate_records,
    }


PILOT_ENGLISH_SOURCE_TYPE = "official_english_policy_page"
ENGLISH_APPLICANT_SCOPE = "international_undergraduate"
ENGLISH_PROMPT_VERSION = "english-policy-v2"
ENGLISH_TEST_TERMS = {
    "ielts": ("ielts", "international english language testing system"),
    "toefl_ibt": ("toefl", "test of english as a foreign language"),
    "duolingo_english_test": ("duolingo", "det", "duolingo english test"),
}
MAX_ENGLISH_SECTION_DISTANCE = 1500
# Cached MIT structured content places its new-scale TOEFL minimum 325
# characters after the applicability marker; 600 retains a bounded interval
# while allowing this table/annotation flattening without making ownership
# page-wide.
MAX_TOEFL_APPLICABILITY_DISTANCE = 600
MAX_TOEFL_POST_SCORE_QUALIFIER_DISTANCE = 120
# A preceding table/section heading may qualify a score row after flattened
# HTML. Keep this much smaller than a test section so unrelated page prose
# cannot poison a binding score.
MAX_NONBINDING_SCORE_HEADING_DISTANCE = 350
MAX_NONBINDING_SCORE_FOLLOWING_DISTANCE = 120
_TEST_CONTEXT_PATTERNS = {
    test_type: tuple(re.compile(rf"(?<!\\w){re.escape(alias)}(?!\\w)", re.IGNORECASE) for alias in aliases)
    for test_type, aliases in ENGLISH_TEST_TERMS.items()
}


def load_official_source_seeds(path: Path) -> list[OfficialSourceSeed]:
    seeds = [OfficialSourceSeed.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not seeds:
        raise ValueError(f"No source seeds found in {path}")
    pairs = [(seed.institution_ipeds_unitid, seed.url) for seed in seeds]
    if len(pairs) != len(set(pairs)):
        raise ValueError("Source seeds contain a duplicate institution UNITID + URL pair")
    return sorted(seeds, key=lambda seed: (seed.institution_ipeds_unitid, seed.url))


def _selected_source_seeds(path: Path, unitids: set[int] | list[int] | None) -> list[OfficialSourceSeed]:
    seeds = load_official_source_seeds(path)
    selected = [seed for seed in seeds if unitids is None or seed.institution_ipeds_unitid in unitids]
    missing = set(unitids or []) - {seed.institution_ipeds_unitid for seed in selected}
    if missing:
        raise ValueError("Requested UNITID is not present in the reviewed official source seeds: " + ", ".join(map(str, sorted(missing))))
    if isinstance(unitids, list):
        order = {unitid: index for index, unitid in enumerate(unitids)}
        selected.sort(key=lambda seed: (order[seed.institution_ipeds_unitid], seed.url))
    return selected


def discover_official_sources(path: Path, unitids: set[int] | list[int] | None = None) -> list[OfficialSourceSeed]:
    """Return reviewed, deterministic official URL seeds; discovery itself is auditable data."""

    seeds = _selected_source_seeds(path, unitids)
    institutions = {row.ipeds_unitid: row for row in Institution.objects.filter(ipeds_unitid__in=[seed.institution_ipeds_unitid for seed in seeds])}
    if len(institutions) != len({seed.institution_ipeds_unitid for seed in seeds}):
        raise ValueError("Every official source seed must resolve to an existing canonical institution")
    for seed in seeds:
        if institutions[seed.institution_ipeds_unitid].name != seed.institution_name:
            raise ValueError(f"Source seed institution name does not match canonical UNITID {seed.institution_ipeds_unitid}")
    return seeds


def _seed_for_institution(institution_id: int) -> SeedInstitution:
    return SeedInstitution.objects.get(institution_id=institution_id)


def _normalised_text(value: str) -> str:
    return " ".join(value.split())


def _allowed_final_host(url: str, allowed_hosts: list[str]) -> bool:
    host = (urlparse(url).hostname or "").casefold()
    return any(host == allowed.casefold() or host.endswith(f".{allowed.casefold()}") for allowed in allowed_hosts)


def fetch_official_sources(
    seed_path: Path,
    *,
    unitids: set[int] | list[int] | None = None,
    fetcher: WebFetcher | None = None,
    refresh: bool = False,
) -> dict[str, int]:
    """Fetch a reviewed pilot subset while persisting only metadata/provenance in the database."""

    seeds = discover_official_sources(seed_path, unitids)
    fetcher = fetcher or WebFetcher()
    counts = {"attempted": 0, "fetched": 0, "failed": 0, "from_cache": 0, "extracted": 0}
    for seed in seeds:
        institution = Institution.objects.get(ipeds_unitid=seed.institution_ipeds_unitid)
        source_seed = _seed_for_institution(institution.id)
        other_active_urls = [s.url for s in seeds if s.institution_ipeds_unitid == seed.institution_ipeds_unitid and s.url != seed.url]
        DataIssue.objects.filter(seed_entry=source_seed, issue_type=DataIssue.IssueType.SOURCE_FETCH_FAILED).exclude(issue_key__in=other_active_urls).delete()
        counts["attempted"] += 1
        result = fetcher.fetch(seed.url, refresh=refresh)
        if not result.content or result.http_status is None or not _allowed_final_host(result.final_url, seed.allowed_hosts):
            detail = result.error or f"Redirected to unapproved host {urlparse(result.final_url).hostname!r}."
            _upsert_issue(source_seed, DataIssue.IssueType.SOURCE_FETCH_FAILED, detail, issue_key=seed.url)
            counts["failed"] += 1
            source = SourceDocument.objects.filter(institution=institution, url=seed.url, source_type=PILOT_ENGLISH_SOURCE_TYPE).first()
            if source is not None:
                source.http_status = result.http_status
                source.content_hash = ""
                source.retrieved_at = datetime.now(timezone.utc)
                source.save(update_fields=["http_status", "content_hash", "retrieved_at"])
            continue
        page = extract_page(result.content)
        source_defaults = {
            "canonical_url": result.final_url,
            "publisher": institution.name,
            "source_type": PILOT_ENGLISH_SOURCE_TYPE,
            "data_year": "current",
            "retrieved_at": datetime.now(timezone.utc),
            "http_status": result.http_status,
            "content_hash": result.content_hash,
            "page_title": page.title,
            "extraction_method": page.method,
            "model_name": "",
            "prompt_version": "",
        }
        source, created = SourceDocument.objects.get_or_create(
            institution=institution,
            url=seed.url,
            defaults=source_defaults,
        )
        if not created and (
            source.content_hash != result.content_hash
            or source.canonical_url != result.final_url
            or source.http_status != result.http_status
            or source.page_title != page.title
            or source.extraction_method != page.method
        ):
            source.canonical_url = result.final_url
            source.publisher = institution.name
            source.source_type = PILOT_ENGLISH_SOURCE_TYPE
            source.data_year = "current"
            source.retrieved_at = datetime.now(timezone.utc)
            source.http_status = result.http_status
            source.content_hash = result.content_hash
            source.page_title = page.title
            source.extraction_method = page.method
            source.save(update_fields=["canonical_url", "publisher", "source_type", "data_year", "retrieved_at", "http_status", "content_hash", "page_title", "extraction_method"])
        counts["fetched"] += 1
        counts["from_cache"] += int(result.from_cache)
        counts["extracted"] += int(bool(page.text))
    return counts


def build_english_prompt(*, source_url: str, institution_name: str, source_text: str) -> str:
    return f"""Extract only international undergraduate English-proficiency facts from the supplied SOURCE_TEXT.

Institution: {institution_name}
Applicant scope: {ENGLISH_APPLICANT_SCOPE}
Source URL: {source_url}

Use only SOURCE_TEXT. Do not use model memory, outside knowledge, or guesses. Do not merge graduate, transfer, program-specific, or other applicant categories into international undergraduate facts. Return unknown/not_found when unsupported. Evidence must be copied exactly from SOURCE_TEXT.

Return one JSON candidate for IELTS, TOEFL iBT, and Duolingo English Test, even when the inspected source has no support for a test. Multiple TOEFL candidates are allowed only for different scales or applicability date windows.

Use status "found" only for an explicit minimum. Use "no_minimum_published" only when SOURCE_TEXT explicitly says there is no minimum/cutoff. Use "not_required" only for a global rule for the entire stated applicant scope. A waiver conditional on English-medium study is not global not_required: preserve it in waiver_text/conditional_text and use the actual test state separately. Use "not_found" when the inspected source does not support the test policy.

For a found requirement, return a contiguous evidence span that includes the test name or heading when practical. If a score is structurally under a heading/table and repeating the test name in the exact score row is impossible, return the exact score evidence; deterministic source-context validation will associate it. Do not fabricate a test name into quoted evidence. For TOEFL found candidates set score_scale to "toefl_ibt_0_120" or "toefl_ibt_1_6" and include valid_for_tests_before and/or valid_for_tests_on_or_after when SOURCE_TEXT states an effective rule. Do not treat score ranges or middle-50% data as minimums. Recommended minimums, competitive or successful-applicant benchmarks, expected scores, and typical scores are not binding minimums. Use no_minimum_published only for an explicit no-minimum statement; otherwise use not_found for the hard minimum, preserving supported policy text.

Return JSON only in this exact shape:
{{"requirements":[{{"test_type":"ielts|toefl_ibt|duolingo_english_test","minimum_score":number|null,"score_scale":"ielts_band_0_9|toefl_ibt_0_120|toefl_ibt_1_6|det_10_160|null","valid_for_tests_before":"YYYY-MM-DD|null","valid_for_tests_on_or_after":"YYYY-MM-DD|null","subscore_requirements":{{}},"waiver_text":string|null,"conditional_text":string|null,"status":"found|no_minimum_published|not_found|not_required","evidence":string}}]}}

Return ONLY the JSON object. Do not wrap the response in Markdown or ```json code fences. Do not include explanation before or after the JSON.

SOURCE_TEXT:
{source_text}
"""


def _score_occurrences(candidate: EnglishRequirementCandidate, text: str) -> list[re.Match[str]]:
    """Locate complete numeric tokens that exactly equal the candidate score.

    Decimal comparison intentionally permits harmless trailing-zero formatting
    (for example, ``3.5`` and ``3.50``), but never a numeric prefix such as
    ``5`` in ``5.5`` or ``80`` in ``80.5``.
    """

    if candidate.minimum_score is None:
        return []
    return [
        match
        for match in re.finditer(r"(?<!\d)(?<!\d\.)\d+(?:\.\d+)?(?!\d)(?!\.\d)", text)
        if Decimal(match.group()) == candidate.minimum_score
    ]


def _score_appears_in_evidence(candidate: EnglishRequirementCandidate) -> bool:
    return candidate.minimum_score is None or bool(_score_occurrences(candidate, _normalised_text(candidate.evidence)))


def _evidence_span(source_text: str, evidence: str) -> re.Match[str] | None:
    """Find literal evidence while allowing only whitespace representation differences."""

    tokens = evidence.split()
    if not tokens:
        return None
    return re.search(r"\s+".join(re.escape(token) for token in tokens), source_text)


def _english_test_anchors(source_text: str) -> list[tuple[int, int, str]]:
    """Return non-overlapping test-name anchors in original flattened source order."""

    matches: list[tuple[int, int, str]] = []
    for test_type, patterns in _TEST_CONTEXT_PATTERNS.items():
        for pattern in patterns:
            matches.extend((match.start(), match.end(), test_type) for match in pattern.finditer(source_text))
    # Aliases overlap (for example, "Duolingo" inside "Duolingo English Test").
    # Keep the longest anchor at a position; otherwise section ownership would be artificial.
    anchors: list[tuple[int, int, str]] = []
    for start, end, test_type in sorted(matches, key=lambda item: (item[0], -(item[1] - item[0]), item[2])):
        if anchors and start < anchors[-1][1]:
            continue
        anchors.append((start, end, test_type))
    return anchors


def _section_context_for_evidence(
    candidate: EnglishRequirementCandidate,
    source_text: str,
    evidence_match: re.Match[str],
    *,
    allow_multiple_test_policy: bool = False,
) -> tuple[str, int, int] | None:
    """Assign evidence to one bounded, unambiguous test section in original text."""

    anchors = _english_test_anchors(source_text)
    evidence_anchors = [test_type for start, end, test_type in anchors if start >= evidence_match.start() and end <= evidence_match.end()]
    if evidence_anchors and (
        set(evidence_anchors) == {candidate.test_type}
        or (allow_multiple_test_policy and candidate.test_type in evidence_anchors)
    ):
        section_start = max(0, evidence_match.start() - MAX_ENGLISH_SECTION_DISTANCE)
        section_end = min(len(source_text), evidence_match.end() + MAX_ENGLISH_SECTION_DISTANCE)
    else:
        preceding = [anchor for anchor in anchors if anchor[1] <= evidence_match.start()]
        following = [anchor for anchor in anchors if anchor[0] >= evidence_match.end()]
        owner: tuple[int, int, str] | None = None
        if preceding and evidence_match.start() - preceding[-1][1] <= MAX_ENGLISH_SECTION_DISTANCE:
            owner = preceding[-1]
        elif not preceding or evidence_match.start() - preceding[-1][1] > MAX_ENGLISH_SECTION_DISTANCE:
            if following and following[0][0] - evidence_match.end() <= MAX_ENGLISH_SECTION_DISTANCE:
                owner = following[0]
                if len(following) > 1 and following[1][0] - evidence_match.end() <= MAX_ENGLISH_SECTION_DISTANCE:
                    return None
        if owner is None or owner[2] != candidate.test_type:
            return None
        if owner[0] < evidence_match.start():
            section_start = owner[0]
            next_other = next((anchor for anchor in following if anchor[2] != candidate.test_type), None)
            section_end = next_other[0] if next_other else min(len(source_text), owner[0] + MAX_ENGLISH_SECTION_DISTANCE)
        else:
            section_start = max(0, owner[0] - MAX_ENGLISH_SECTION_DISTANCE)
            section_end = owner[1]
    if not section_start <= evidence_match.start() <= evidence_match.end() <= section_end:
        return None
    return (
        source_text[section_start:section_end],
        evidence_match.start() - section_start,
        evidence_match.end() - section_start,
    )


def _date_markers(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    year = value.year
    month = value.month
    day = value.day
    month_name = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")[month - 1]
    return (value.isoformat(), f"{month}/{day}/{year}", f"{month}/{day}/{str(year)[-2:]}", f"{month_name} {day}, {year}", f"{month_name} {year}")


def _validate_toefl_applicability(candidate: EnglishRequirementCandidate, context: str, evidence_start: int, evidence_end: int) -> tuple[bool, str]:
    expected_kind = None
    date_value = None
    if candidate.valid_for_tests_before:
        expected_kind = "before"
        date_value = candidate.valid_for_tests_before
    elif candidate.valid_for_tests_on_or_after:
        expected_kind = "on_or_after"
        date_value = candidate.valid_for_tests_on_or_after
    else:
        return True, "no TOEFL applicability supplied"
    if not any(marker.casefold() in context.casefold() for marker in _date_markers(date_value)):
        return False, "TOEFL applicability date is not supported by bounded local context"
    applicability_markers = [
        ("before", match)
        for match in re.finditer(r"\b(before|prior to)\b", context, re.IGNORECASE)
    ] + [
        ("on_or_after", match)
        for match in re.finditer(r"\b(on or after|effective)\b", context, re.IGNORECASE)
    ]
    if not applicability_markers:
        return False, f"TOEFL {expected_kind} applicability is not supported by bounded local context"
    applicability_markers.sort(key=lambda item: item[1].start())
    score_matches = _score_occurrences(candidate, context[evidence_start:evidence_end])
    if not score_matches:
        return False, "TOEFL candidate score is not present in literal evidence"
    score_kinds: set[str] = set()
    for score_match in score_matches:
        score_start = evidence_start + score_match.start()
        score_end = evidence_start + score_match.end()
        # A qualifier immediately following a score can own it in direct prose,
        # such as "minimum score is 90 before January 21, 2026". Sentence
        # boundaries are used only for this local look-ahead; they do not end
        # the structured-text interval owned by a preceding applicability rule.
        following = [
            item
            for item in applicability_markers
            if score_end <= item[1].start() <= score_end + MAX_TOEFL_POST_SCORE_QUALIFIER_DISTANCE
            and not re.search(r"(?:[!?;]|\.(?=\s|$)|\n)", context[score_end:item[1].start()])
        ]
        if following:
            following_kinds = {item[0] for item in following}
            if len(following_kinds) == 1:
                score_kinds.update(following_kinds)
                continue
            return False, "TOEFL candidate score has conflicting following applicability qualifiers"

        # A preceding marker owns subsequent flattened table/section content
        # until the next marker or a deliberately small, explicit maximum.
        # Punctuation, URLs, and newlines are not semantic interval ends.
        preceding = [
            (index, item)
            for index, item in enumerate(applicability_markers)
            if item[1].start() <= score_start
        ]
        if preceding:
            marker_index, (marker_kind, marker) = preceding[-1]
            next_marker = (
                applicability_markers[marker_index + 1][1]
                if marker_index + 1 < len(applicability_markers)
                else None
            )
            marker_distance = score_start - marker.end()
            if (
                marker_distance <= MAX_TOEFL_APPLICABILITY_DISTANCE
                and (next_marker is None or score_start < next_marker.start())
            ):
                score_kinds.add(marker_kind)
                continue
        return False, "TOEFL candidate score is outside an applicability clause"
    if score_kinds != {expected_kind}:
        observed = ", ".join(sorted(score_kinds)) or "none"
        return False, f"TOEFL evidence score is associated with {observed} applicability, not {expected_kind}"
    return True, "TOEFL applicability validated"


_NONBINDING_SCORE_GROUP_PATTERNS = (
    re.compile(r"\b(?:strongly\s+)?recommend(?:ed|s|ing)?\b(?:\s+\w+){0,5}\s+\b(?:scores?|minimums?|benchmark)\b", re.IGNORECASE),
    re.compile(r"\b(?:minimum\s+)?scores?\b.{0,60}\b(?:is|are)\s+(?:strongly\s+)?recommended\b", re.IGNORECASE),
    re.compile(r"\b(?:most\s+)?competitive\s+applicants?\b.{0,80}\b(?:generally|typically|usually|often|should|suggested|score|earn|have)\b", re.IGNORECASE),
    re.compile(r"\b(?:most\s+)?successful\s+applicants?\b.{0,80}\b(?:generally|typically|usually|often|should|score|earn|have)\b", re.IGNORECASE),
    re.compile(r"\b(?:scores?|score\s+requirements?)\b.{0,80}\b(?:competitive|successful)\b", re.IGNORECASE),
    re.compile(r"\bto\s+(?:be|remain)\s+(?:most\s+)?competitive\b.{0,100}\bapplicants?\s+(?:should|are\s+encouraged|ought)\b", re.IGNORECASE),
    re.compile(r"\bapplicants?\s+(?:should|are\s+encouraged|ought)\b.{0,80}\b(?:score|earn|have)\b.{0,80}\bto\s+(?:be|remain)\s+(?:most\s+)?competitive\b", re.IGNORECASE),
    re.compile(r"\b(?:expected|typical)\s+(?:minimum\s+)?scores?\b", re.IGNORECASE),
    re.compile(r"\b(?:minimum\s+)?scores?\s+(?:expected|typical)\b", re.IGNORECASE),
    re.compile(r"\b(?:the\s+)?following\s+(?:minimum\s+)?scores?\b.{0,60}\b(?:are\s+)?(?:generally\s+|typically\s+)?expected\b", re.IGNORECASE),
    re.compile(r"\b(?:minimum\s+)?scores?\b.{0,60}\b(?:are\s+)?(?:generally\s+|typically\s+)?expected(?:\s+in\s+most\s+cases)?\b", re.IGNORECASE),
    re.compile(r"\b(?:students?|applicants?|candidates?)\s+(?:who\s+are|considered)\s+(?:the\s+)?(?:most\s+)?competitive(?:\s+for\s+admission)?\b.{0,100}\b(?:will|tend\s+to|generally|typically|usually|often)\b.{0,50}\b(?:score|earn|have)\b", re.IGNORECASE),
    re.compile(r"\bnot\s+(?:a\s+)?strict\s+cutoff\b", re.IGNORECASE),
    re.compile(r"\bapplicants?\s+below\b.{0,80}\b(?:admissible|admitted)\b", re.IGNORECASE),
)
_NONBINDING_POST_SCORE_PATTERNS = (
    re.compile(r"\b(?:is|are)\s+(?:strongly\s+)?recommended\b", re.IGNORECASE),
    re.compile(r"\bconsidered\s+competitive\b", re.IGNORECASE),
)


def _has_nonbinding_score_group_language(value: str) -> bool:
    return any(pattern.search(value) for pattern in _NONBINDING_SCORE_GROUP_PATTERNS)


def _is_nonbinding_score_benchmark(candidate: EnglishRequirementCandidate, source_text: str, evidence_match: re.Match[str]) -> bool:
    """Identify advisory score language only when it owns this bounded score group."""

    evidence = source_text[evidence_match.start():evidence_match.end()]
    for score_match in _score_occurrences(candidate, evidence):
        score_start = evidence_match.start() + score_match.start()
        score_end = evidence_match.start() + score_match.end()
        heading_start = max(0, score_start - MAX_NONBINDING_SCORE_HEADING_DISTANCE)
        preceding_heading = source_text[heading_start:score_start]
        if _has_nonbinding_score_group_language(preceding_heading):
            return True

        preceding_phrase = source_text[heading_start:score_start]
        sentence_start = re.search(r"(?:[!?;]|\.(?=\s|$)|\n)\s*$", preceding_phrase)
        if sentence_start is not None:
            preceding_phrase = preceding_phrase[sentence_start.end():]
        following = source_text[score_end:score_end + MAX_NONBINDING_SCORE_FOLLOWING_DISTANCE]
        sentence_end = re.search(r"(?:[!?;]|\.(?=\s|$)|\n)", following)
        if sentence_end is not None:
            following = following[:sentence_end.start()]
        score_phrase = preceding_phrase + score_match.group() + following
        if _has_nonbinding_score_group_language(score_phrase):
            return True
        if any(pattern.search(score_phrase) for pattern in _NONBINDING_POST_SCORE_PATTERNS):
            return True
    return False


_EXPLICIT_NOT_REQUIRED_PATTERNS = (
    re.compile(r"\b(?:is|are)\s+not\s+required\b", re.IGNORECASE),
    re.compile(r"\b(?:do|does)\s+not\s+require\b", re.IGNORECASE),
    re.compile(r"\b(?:is|are)\s+optional\b", re.IGNORECASE),
)
_CONDITIONAL_WAIVER_PATTERN = re.compile(
    r"\b(?:if|unless|except|when|who|whose)\b|\b(?:completed|english-medium|native\s+english|years\s+in\s+english|waiv)\w*\b",
    re.IGNORECASE,
)
_GENERIC_ENGLISH_TEST_PATTERN = re.compile(
    r"\benglish(?:\s+language)?\s+(?:proficiency\s+)?(?:exam|exams|test|tests|testing)\b",
    re.IGNORECASE,
)
_NO_MINIMUM_PUBLISHED_PATTERNS = (
    re.compile(r"\bno\s+(?:required\s+)?minimum(?:\s+scores?)?\b", re.IGNORECASE),
    re.compile(r"\bno\s+score\s+minimums?\b", re.IGNORECASE),
    re.compile(r"\b(?:does|do)\s+not\s+have\s+(?:a\s+)?minimum(?:\s+scores?)?\b", re.IGNORECASE),
    re.compile(r"\bno\s+(?:score\s+)?cutoff\b", re.IGNORECASE),
)


def _mentions_candidate_english_test(candidate: EnglishRequirementCandidate, evidence: str) -> bool:
    return (
        any(pattern.search(evidence) for pattern in _TEST_CONTEXT_PATTERNS[candidate.test_type])
        or _GENERIC_ENGLISH_TEST_PATTERN.search(evidence) is not None
    )


def _supports_explicit_not_required(candidate: EnglishRequirementCandidate, evidence: str) -> bool:
    """Accept only an explicit, unconditional English-test non-requirement."""

    return (
        any(pattern.search(evidence) for pattern in _EXPLICIT_NOT_REQUIRED_PATTERNS)
        and _mentions_candidate_english_test(candidate, evidence)
        and _CONDITIONAL_WAIVER_PATTERN.search(evidence) is None
    )


def _supports_explicit_no_minimum(evidence: str) -> bool:
    return any(pattern.search(evidence) for pattern in _NO_MINIMUM_PUBLISHED_PATTERNS)


def validate_english_evidence(candidate: EnglishRequirementCandidate, source_text: str) -> tuple[bool, str]:
    """Evidence must be literal source content and substantiate the requested test/scope."""

    evidence = _normalised_text(candidate.evidence)
    source = _normalised_text(source_text)
    if candidate.status == "not_found":
        return True, "not_found is an explicit candidate absence state; no score is persisted"
    evidence_match = _evidence_span(source_text, evidence)
    if not evidence or evidence_match is None:
        return False, "candidate evidence is not present in extracted source text"
    section_context = _section_context_for_evidence(
        candidate,
        source_text,
        evidence_match,
        allow_multiple_test_policy=candidate.status in {"no_minimum_published", "not_required"},
    )
    if section_context is None:
        return False, "candidate evidence does not establish the claimed test in a bounded source section"
    local_context, local_evidence_start, local_evidence_end = section_context
    evidence_lower = evidence.casefold()
    if candidate.status == "no_minimum_published" and not _supports_explicit_no_minimum(evidence):
        return False, "no_minimum_published requires explicit no-minimum/cutoff evidence"
    if candidate.status == "not_required":
        if not _supports_explicit_not_required(candidate, evidence):
            return False, "not_required requires explicit unconditional English-test evidence"
    if candidate.status == "found" and not _score_appears_in_evidence(candidate):
        return False, "candidate score is not supported by its evidence"
    if candidate.status == "found" and any(marker in evidence_lower for marker in ("middle 50", "middle-50", "percentile range", "typical range")):
        return False, "score-range evidence is not a published minimum"
    if candidate.status == "found" and _is_nonbinding_score_benchmark(candidate, source_text, evidence_match):
        return False, "non-binding benchmark evidence is not a published hard minimum"
    if candidate.test_type == "toefl_ibt" and candidate.status == "found" and candidate.score_scale is None:
        return False, "TOEFL evidence requires a score scale"
    if candidate.test_type == "toefl_ibt" and candidate.status == "found":
        valid_applicability, applicability_detail = _validate_toefl_applicability(candidate, local_context, local_evidence_start, local_evidence_end)
        if not valid_applicability:
            return False, applicability_detail
    context = local_context.casefold()
    if "graduate" in context and "undergraduate" not in context:
        return False, "graduate-only evidence cannot validate an undergraduate fact"
    return True, "evidence validated"


_SINGLE_FENCED_RESPONSE = re.compile(
    r"```(?:[ \t]*json)?[ \t]*\r?\n(?P<body>.*?)\r?\n```[ \t]*",
    re.IGNORECASE | re.DOTALL,
)


def _normalise_llm_json_response(response: str) -> str:
    """Accept raw JSON or one complete JSON/generic Markdown fence, and nothing around it."""

    stripped = response.strip()
    match = _SINGLE_FENCED_RESPONSE.fullmatch(stripped)
    if match is None:
        return stripped
    body = match.group("body")
    if re.search(r"(?m)^[ \t]*```", body):
        # A second fence is never part of the allowed single-block transport form.
        return stripped
    return body


def _parse_llm_response(client: EnglishExtractionClient, prompt: str, retries: int = 1) -> EnglishExtractionResponse:
    last_error: Exception | None = None
    current_prompt = prompt
    for attempt in range(retries + 1):
        try:
            return EnglishExtractionResponse.model_validate_json(_normalise_llm_json_response(client.extract(current_prompt)))
        except (ValueError, TypeError) as exc:
            last_error = exc
            if attempt < retries:
                safe_error = str(exc).replace("SOURCE_TEXT", "source text")[:2000]
                current_prompt = f"{prompt}\n\nPrevious response failed schema validation:\n{safe_error}\nReturn corrected JSON using only the same SOURCE_TEXT. Return raw JSON only, without Markdown fences."
    raise ValueError(f"LLM response could not be parsed/validated after {retries + 1} attempts: {last_error}")


_PERSISTED_ENGLISH_STATUSES = {
    EnglishRequirement.Status.VERIFIED: "found",
    EnglishRequirement.Status.NO_MINIMUM_PUBLISHED: "no_minimum_published",
    EnglishRequirement.Status.NOT_FOUND: "not_found",
    EnglishRequirement.Status.NOT_REQUIRED: "not_required",
}
_ENGLISH_COUNT_KEY = {
    "found": "verified",
    "no_minimum_published": "no_minimum_published",
    "not_found": "not_found",
    "not_required": "not_required",
}


def _sanitize_optional_candidate_text(candidate: EnglishRequirementCandidate, source_text: str) -> tuple[EnglishRequirementCandidate, int]:
    """Discard unsupported adjunct text without weakening core-fact checks."""

    source = _normalised_text(source_text)
    updates: dict[str, None] = {}
    for field_name in ("waiver_text", "conditional_text"):
        value = getattr(candidate, field_name)
        if value and _normalised_text(value) not in source:
            updates[field_name] = None
    return candidate.model_copy(update=updates), len(updates)


def _candidate_from_requirement(requirement: EnglishRequirement) -> EnglishRequirementCandidate | None:
    candidate_status = _PERSISTED_ENGLISH_STATUSES.get(requirement.status)
    if candidate_status is None:
        return None
    return EnglishRequirementCandidate(
        test_type=requirement.test_type,
        minimum_score=requirement.minimum_overall_score,
        score_scale=requirement.score_scale or None,
        valid_for_tests_before=requirement.valid_for_tests_before,
        valid_for_tests_on_or_after=requirement.valid_for_tests_on_or_after,
        subscore_requirements=requirement.subscore_requirements,
        waiver_text=requirement.waiver_text or None,
        conditional_text=requirement.conditional_text or None,
        status=candidate_status,
        evidence=requirement.evidence,
    )


def _reusable_english_requirements(source: SourceDocument, source_text: str) -> tuple[list[EnglishRequirement] | None, int]:
    """Revalidate source-hash-matched rows; bind only valid legacy pilot rows."""

    current_hash = source.content_hash
    if not current_hash:
        return None, 0
    rows = list(EnglishRequirement.objects.filter(source=source, source_content_hash__in=["", current_hash]).order_by("pk"))
    if not rows or EnglishRequirement.objects.filter(source=source, source_content_hash=current_hash, status=EnglishRequirement.Status.CONFLICTING).exists():
        return None, 0

    reusable: list[EnglishRequirement] = []
    optional_text_dropped = 0
    for requirement in rows:
        candidate = _candidate_from_requirement(requirement)
        if candidate is None:
            return None, optional_text_dropped
        candidate, dropped = _sanitize_optional_candidate_text(candidate, source_text)
        optional_text_dropped += dropped
        valid, _detail = validate_english_evidence(candidate, source_text)
        if not valid:
            return None, optional_text_dropped
        update_fields: list[str] = []
        for field_name in ("waiver_text", "conditional_text"):
            sanitized = getattr(candidate, field_name) or ""
            if getattr(requirement, field_name) != sanitized:
                setattr(requirement, field_name, sanitized)
                update_fields.append(field_name)
        if not requirement.source_content_hash:
            requirement.source_content_hash = current_hash
            update_fields.append("source_content_hash")
        if update_fields:
            requirement.save(update_fields=update_fields)
        reusable.append(requirement)

    covered_tests = {requirement.test_type for requirement in reusable}
    if covered_tests != set(EnglishRequirement.TestType.values):
        return None, optional_text_dropped
    return reusable, optional_text_dropped


@transaction.atomic
def enrich_english_requirements(
    seed_path: Path,
    client: EnglishExtractionClient,
    *,
    unitids: set[int] | list[int] | None = None,
    fetcher: WebFetcher | None = None,
) -> dict[str, int]:
    """Turn bounded source text into verified facts only after deterministic validation."""

    seeds = discover_official_sources(seed_path, unitids)
    fetcher = fetcher or WebFetcher()
    counts = {"attempted": 0, "llm_calls": 0, "reused_sources": 0, "reused_facts": 0, "optional_text_dropped": 0, "verified": 0, "no_minimum_published": 0, "not_found": 0, "not_required": 0, "conflicting": 0, "extraction_failed": 0, "review_issues": 0}
    for seed in seeds:
        institution = Institution.objects.get(ipeds_unitid=seed.institution_ipeds_unitid)
        source_seed = _seed_for_institution(institution.id)
        # TASK-004 predated source keys; clear only its stale unscoped extraction issue.
        DataIssue.objects.filter(seed_entry=source_seed, issue_type=DataIssue.IssueType.ENGLISH_EXTRACTION_REVIEW, issue_key="").delete()
        DataIssue.objects.filter(seed_entry=source_seed, issue_type=DataIssue.IssueType.ENGLISH_EXTRACTION_REVIEW, issue_key=seed.url).delete()
        counts["attempted"] += 1
        source = SourceDocument.objects.filter(institution=institution, url=seed.url, source_type=PILOT_ENGLISH_SOURCE_TYPE).first()
        fetched = fetcher.fetch(seed.url)
        if source is None or not fetched.content:
            _upsert_issue(source_seed, DataIssue.IssueType.ENGLISH_EXTRACTION_REVIEW, "No fetched official source content is available for English extraction.", issue_key=seed.url)
            counts["extraction_failed"] += 1
            counts["review_issues"] += 1
            continue
        if source.content_hash != fetched.content_hash:
            source.content_hash = fetched.content_hash
            source.retrieved_at = datetime.now(timezone.utc)
            source.save(update_fields=["content_hash", "retrieved_at"])
        page = extract_page(fetched.content)
        relevant_text = select_english_relevance(page.text)
        if not relevant_text:
            _upsert_issue(source_seed, DataIssue.IssueType.ENGLISH_EXTRACTION_REVIEW, "No English-proficiency context was selected from extracted official text.", issue_key=seed.url)
            counts["extraction_failed"] += 1
            counts["review_issues"] += 1
            continue
        reusable, optional_dropped = _reusable_english_requirements(source, relevant_text)
        counts["optional_text_dropped"] += optional_dropped
        if reusable is not None:
            counts["reused_sources"] += 1
            counts["reused_facts"] += len(reusable)
            for requirement in reusable:
                counts[_ENGLISH_COUNT_KEY[_PERSISTED_ENGLISH_STATUSES[requirement.status]]] += 1
            continue
        try:
            # Count the bounded extraction request even if the remote service rejects it.
            counts["llm_calls"] += 1
            response = _parse_llm_response(client, build_english_prompt(source_url=source.canonical_url or source.url, institution_name=institution.name, source_text=relevant_text))
        except (LLMUnavailable, ValueError) as exc:
            _upsert_issue(source_seed, DataIssue.IssueType.ENGLISH_EXTRACTION_REVIEW, str(exc), issue_key=seed.url)
            counts["extraction_failed"] += 1
            counts["review_issues"] += 1
            continue
        source.model_name = client.model_name
        source.prompt_version = ENGLISH_PROMPT_VERSION
        source.save(update_fields=["model_name", "prompt_version"])
        for candidate in response.requirements:
            candidate, optional_dropped = _sanitize_optional_candidate_text(candidate, relevant_text)
            counts["optional_text_dropped"] += optional_dropped
            valid, detail = validate_english_evidence(candidate, relevant_text)
            if not valid:
                _upsert_issue(source_seed, DataIssue.IssueType.ENGLISH_EXTRACTION_REVIEW, detail, issue_key=seed.url)
                counts["review_issues"] += 1
                continue
            existing = EnglishRequirement.objects.filter(
                institution=institution,
                applicant_scope=ENGLISH_APPLICANT_SCOPE,
                test_type=candidate.test_type,
                policy_cycle="unspecified",
                source=source,
                score_scale=candidate.score_scale or "",
                valid_for_tests_before=candidate.valid_for_tests_before,
                valid_for_tests_on_or_after=candidate.valid_for_tests_on_or_after,
            ).first()
            if existing and existing.source_content_hash == source.content_hash and existing.status == EnglishRequirement.Status.VERIFIED and candidate.status == "found" and existing.minimum_overall_score != candidate.minimum_score:
                existing.status = EnglishRequirement.Status.CONFLICTING
                existing.evidence = f"Existing verified value {existing.minimum_overall_score}; new candidate evidence: {candidate.evidence}"
                existing.save(update_fields=["status", "evidence"])
                _upsert_issue(source_seed, DataIssue.IssueType.ENGLISH_EXTRACTION_REVIEW, "Conflicting English minimum from official-source extraction.", issue_key=seed.url)
                counts["conflicting"] += 1
                counts["review_issues"] += 1
                continue
            status = {
                "found": EnglishRequirement.Status.VERIFIED,
                "no_minimum_published": EnglishRequirement.Status.NO_MINIMUM_PUBLISHED,
                "not_found": EnglishRequirement.Status.NOT_FOUND,
                "not_required": EnglishRequirement.Status.NOT_REQUIRED,
            }[candidate.status]
            EnglishRequirement.objects.update_or_create(
                institution=institution,
                applicant_scope=ENGLISH_APPLICANT_SCOPE,
                test_type=candidate.test_type,
                policy_cycle="unspecified",
                source=source,
                score_scale=candidate.score_scale or "",
                valid_for_tests_before=candidate.valid_for_tests_before,
                valid_for_tests_on_or_after=candidate.valid_for_tests_on_or_after,
                defaults={
                    "minimum_overall_score": candidate.minimum_score,
                    "subscore_requirements": {key: str(value) for key, value in candidate.subscore_requirements.items()},
                    "waiver_text": candidate.waiver_text or "",
                    "conditional_text": candidate.conditional_text or "",
                    "status": status,
                    "evidence": "" if candidate.status == "not_found" else candidate.evidence,
                    "source_content_hash": source.content_hash,
                },
            )
            counts[_ENGLISH_COUNT_KEY[candidate.status]] += 1
    if not seeds:
        counts["review_issues"] = 0
        return counts
    active_issue_pairs = Q()
    for seed in seeds:
        active_issue_pairs |= Q(seed_entry__institution__ipeds_unitid=seed.institution_ipeds_unitid, issue_key=seed.url)
    counts["review_issues"] = DataIssue.objects.filter(
        issue_type=DataIssue.IssueType.ENGLISH_EXTRACTION_REVIEW,
    ).filter(active_issue_pairs).count()
    return counts


def _current_source_backed_english_requirements():
    """Return only facts validated against their source's current bytes."""

    return EnglishRequirement.objects.filter(
        source__isnull=False,
        source_content_hash__gt="",
        source_content_hash=F("source__content_hash"),
    )


def export_english_requirements(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for requirement in _current_source_backed_english_requirements().select_related("institution", "source").order_by("institution__ipeds_unitid", "test_type", "score_scale", "valid_for_tests_before", "valid_for_tests_on_or_after", "policy_cycle", "source__url"):
        records.append({
            "applicant_scope": requirement.applicant_scope,
            "conditional_text": requirement.conditional_text or None,
            "evidence": requirement.evidence or None,
            "institution_ipeds_unitid": requirement.institution.ipeds_unitid,
            "minimum_overall_score": str(requirement.minimum_overall_score) if requirement.minimum_overall_score is not None else None,
            "policy_cycle": requirement.policy_cycle,
            "score_scale": requirement.score_scale or None,
            "source": None if requirement.source is None else {"canonical_url": requirement.source.canonical_url or None, "content_hash": requirement.source.content_hash, "url": requirement.source.url},
            "source_content_hash": requirement.source_content_hash or None,
            "status": requirement.status,
            "subscore_requirements": requirement.subscore_requirements,
            "test_type": requirement.test_type,
            "valid_for_tests_before": requirement.valid_for_tests_before.isoformat() if requirement.valid_for_tests_before else None,
            "valid_for_tests_on_or_after": requirement.valid_for_tests_on_or_after.isoformat() if requirement.valid_for_tests_on_or_after else None,
            "waiver_text": requirement.waiver_text or None,
        })
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
    return len(records)


def export_sources(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    sources = SourceDocument.objects.filter(
        source_type=PILOT_ENGLISH_SOURCE_TYPE,
        content_hash__gt="",
        http_status=200,
    ).select_related("institution").order_by("institution__ipeds_unitid", "url")
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for source in sources:
            record = {
                "canonical_url": source.canonical_url or None,
                "content_hash": source.content_hash,
                "extraction_method": source.extraction_method,
                "http_status": source.http_status,
                "institution_ipeds_unitid": source.institution.ipeds_unitid if source.institution else None,
                "model_name": source.model_name or None,
                "page_title": source.page_title or None,
                "prompt_version": source.prompt_version or None,
                "publisher": source.publisher,
                "retrieved_at": source.retrieved_at.isoformat(),
                "source_type": source.source_type,
                "url": source.url,
            }
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n")
    return sources.count()
