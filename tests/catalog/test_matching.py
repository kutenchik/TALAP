from admission.catalog.matching import exact_state_matches, fuzzy_candidates, is_bachelors_granting, ownership_from_control
from admission.catalog.schemas import IpedInstitutionRecord


def record(unitid: int, name: str, state: str) -> IpedInstitutionRecord:
    return IpedInstitutionRecord(
        unitid=unitid, name=name, city="Test City", state=state, control=1,
        cyactive=1, ugoffer=1, hloffer=9, deggrant=1,
    )


def test_exact_match_requires_state() -> None:
    records = [record(1, "Example University", "CA"), record(2, "Example University", "NY")]
    assert [candidate.unitid for candidate in exact_state_matches("Example University", "CA", records)] == [1]


def test_fuzzy_candidates_are_only_suggestions() -> None:
    records = [record(1, "Example University", "CA")]
    assert [candidate.unitid for candidate in fuzzy_candidates("Example Univ", "CA", records)] == [1]


def test_ipeds_control_and_degree_evidence_are_interpreted_conservatively() -> None:
    bachelors = record(1, "Example University", "CA")
    assert ownership_from_control(2) == "private_nonprofit"
    assert is_bachelors_granting(bachelors.model_copy(update={"hloffer": 3})) is False
    assert is_bachelors_granting(bachelors.model_copy(update={"hloffer": 4})) is False
    assert is_bachelors_granting(bachelors.model_copy(update={"hloffer": 5})) is True
    assert is_bachelors_granting(bachelors.model_copy(update={"hloffer": 9})) is True
    assert is_bachelors_granting(bachelors.model_copy(update={"ugoffer": 0})) is False
    assert is_bachelors_granting(bachelors.model_copy(update={"deggrant": 0})) is False
