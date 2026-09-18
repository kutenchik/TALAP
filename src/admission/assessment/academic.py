"""Historical score positioning. Section percentiles are never summed."""

from datetime import date
from typing import Literal

from admission.applicants.schemas import ApplicantContractModel, ApplicantProfileInput, ApplicantTestScoreInput, JsonDecimal
from admission.catalog.models import AdmissionSnapshot


PositionState = Literal[
    "above_reported_context", "within_reported_context", "below_reported_context",
    "context_unavailable", "applicant_score_missing", "context_not_comparable",
]
EvidenceState = Literal["verified", "partial", "conflicting", "unavailable", "not_applicable"]


class ReportedRange(ApplicantContractModel):
    scale: Literal["sat_total_400_1600", "act_composite_1_36"]
    lower: int
    upper: int


class AttemptPosition(ApplicantContractModel):
    scale: str
    score: JsonDecimal
    taken_on: date | None
    state: PositionState


class TestPosition(ApplicantContractModel):
    state: PositionState
    context: ReportedRange | None
    attempts: list[AttemptPosition]


class RawGpa(ApplicantContractModel):
    state: Literal["supplied_not_comparable", "missing"]
    gpa_value: JsonDecimal | None
    gpa_scale: JsonDecimal | None
    gpa_weighting: Literal["weighted", "unweighted", "unknown"]


class AcademicContext(ApplicantContractModel):
    snapshot_available: bool
    sat_context_available: bool
    act_context_available: bool
    data_year: str | None
    source_data_year: str | None
    term: str | None
    source_url: str | None
    source_locator: str | None
    gpa: RawGpa
    sat: TestPosition
    act: TestPosition


class EvidenceQuality(ApplicantContractModel):
    program: EvidenceState
    english: EvidenceState
    academic: EvidenceState


def position_attempts(
    attempts: list[ApplicantTestScoreInput],
    context: ReportedRange | None,
    unavailable_state: Literal["context_unavailable", "context_not_comparable"] = "context_unavailable",
) -> TestPosition:
    """Compare each attempt on the same scale; summary is above > within > below."""
    positions = []
    for attempt in attempts:
        state = unavailable_state
        if context is not None:
            if attempt.scale != context.scale or context.lower > context.upper:
                state = "context_not_comparable"
            elif attempt.score < context.lower:
                state = "below_reported_context"
            elif attempt.score > context.upper:
                state = "above_reported_context"
            else:
                state = "within_reported_context"
        positions.append(AttemptPosition(scale=attempt.scale, score=attempt.score, taken_on=attempt.taken_on, state=state))
    states = {item.state for item in positions}
    summary = next((state for state in (
        "above_reported_context", "within_reported_context", "below_reported_context",
        "context_not_comparable", "context_unavailable",
    ) if state in states), "applicant_score_missing")
    return TestPosition(state=summary, context=context, attempts=positions)


def build_academic_context(profile: ApplicantProfileInput, snapshots: list[AdmissionSnapshot]) -> AcademicContext:
    # Latest stored Fall year only; never backfill missing percentiles from older years.
    fall = [row for row in snapshots if row.term == "fall"]
    snapshot = max(fall, key=lambda row: row.data_year) if fall else None
    act_range = None
    sat_sections = False
    if snapshot is not None:
        sat_sections = any(getattr(snapshot, field) is not None for field in (
            "sat_ebrw_25", "sat_ebrw_75", "sat_math_25", "sat_math_75",
        ))
        lower, upper = snapshot.act_composite_25, snapshot.act_composite_75
        if lower is not None and upper is not None and 1 <= lower <= upper <= 36:
            act_range = ReportedRange(scale="act_composite_1_36", lower=lower, upper=upper)
    return AcademicContext(
        snapshot_available=bool(snapshots),
        sat_context_available=False,  # ADM supplies section percentiles, not total percentiles.
        act_context_available=act_range is not None,
        data_year=snapshot.data_year if snapshot else None,
        source_data_year=snapshot.source.data_year if snapshot else None,
        term=snapshot.term if snapshot else None,
        source_url=snapshot.source.url if snapshot else None,
        source_locator=snapshot.source_locator if snapshot else None,
        gpa=RawGpa(
            state="supplied_not_comparable" if profile.academics.gpa_value is not None else "missing",
            gpa_value=profile.academics.gpa_value, gpa_scale=profile.academics.gpa_scale,
            gpa_weighting=profile.academics.gpa_weighting,
        ),
        sat=position_attempts([t for t in profile.tests if t.test_type == "sat"], None,
                             "context_not_comparable" if sat_sections else "context_unavailable"),
        act=position_attempts([t for t in profile.tests if t.test_type == "act"], act_range),
    )


def academic_evidence(context: AcademicContext) -> EvidenceState:
    if any(test.state in {"above_reported_context", "within_reported_context", "below_reported_context"}
           for test in (context.sat, context.act)):
        return "verified"
    return "partial" if context.snapshot_available else "unavailable"
