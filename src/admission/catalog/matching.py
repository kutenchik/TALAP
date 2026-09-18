"""Pure deterministic matching helpers for seed-to-IPEDS resolution."""

from collections.abc import Iterable
from difflib import SequenceMatcher
import re

from .schemas import IpedInstitutionRecord


def normalize_name(value: str) -> str:
    value = value.casefold().replace("&", " and ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def exact_state_matches(seed_name: str, state: str, records: Iterable[IpedInstitutionRecord]) -> list[IpedInstitutionRecord]:
    normalized = normalize_name(seed_name)
    return [record for record in records if record.state == state and normalize_name(record.name) == normalized]


def fuzzy_candidates(seed_name: str, state: str, records: Iterable[IpedInstitutionRecord], limit: int = 3) -> list[IpedInstitutionRecord]:
    """Return suggestions only; callers must never resolve based on this result."""

    normalized = normalize_name(seed_name)
    ranked = sorted(
        ((SequenceMatcher(None, normalized, normalize_name(record.name)).ratio(), record) for record in records if record.state == state),
        key=lambda item: (-item[0], item[1].unitid),
    )
    return [record for score, record in ranked[:limit] if score >= 0.65]


def ownership_from_control(control: int) -> str:
    return {1: "public", 2: "private_nonprofit", 3: "private_forprofit"}.get(control, "unknown")


def is_bachelors_granting(record: IpedInstitutionRecord) -> bool:
    # In IPEDS HLOFFER coding, 5 is bachelor's degree; values 3 and 4 are sub-baccalaureate.
    return record.ugoffer == 1 and record.hloffer >= 5 and record.deggrant == 1
