from datetime import date
from typing import Literal

from admission.applicants.schemas import ApplicantContractModel, ApplicantProfileInput, ApplicantTestScoreInput, JsonDecimal
from admission.applicants.services import export_profile


class GoalDiagnostic(ApplicantContractModel):
    mode: Literal["known_major", "explore"]
    intended_cip_codes: list[str]
    interests: list[str]
    goal_supplied: bool


class GpaDiagnostic(ApplicantContractModel):
    state: Literal["provided", "missing"]
    gpa_value: JsonDecimal | None
    gpa_scale: JsonDecimal | None
    gpa_weighting: Literal["weighted", "unweighted", "unknown"]


class ClassRankDiagnostic(ApplicantContractModel):
    state: Literal["provided", "missing"]
    class_rank: int | None
    class_size: int | None


class AcademicDiagnostic(ApplicantContractModel):
    graduation_year: int | None
    gpa: GpaDiagnostic
    class_rank: ClassRankDiagnostic


class TestAttemptDiagnostic(ApplicantContractModel):
    test_type: Literal["sat", "act", "ielts", "toefl", "duolingo"]
    scale: Literal["sat_total_400_1600", "act_composite_1_36", "ielts_0_9", "toefl_ibt_0_120", "toefl_ibt_1_6", "det_10_160"]
    score: JsonDecimal
    taken_on: date | None


class TestingDiagnostic(ApplicantContractModel):
    state: Literal["scores_provided", "no_scores_provided"]
    attempts: list[TestAttemptDiagnostic]


class EnglishDiagnostic(ApplicantContractModel):
    state: Literal["scores_provided", "no_scores_provided"]
    attempts: list[TestAttemptDiagnostic]


class FinancialDiagnostic(ApplicantContractModel):
    budget_state: Literal["budget_provided", "budget_missing"]
    annual_budget_usd: JsonDecimal | None
    needs_financial_aid: bool | None


class PreferenceDiagnostic(ApplicantContractModel):
    preferred_states: list[str]
    excluded_states: list[str]


class ExplicitConstraint(ApplicantContractModel):
    constraint_type: Literal["excluded_state"]
    value: str
    hard: Literal[True]
    source: Literal["applicant_profile"]


class MissingInformation(ApplicantContractModel):
    code: Literal[
        "major_missing",
        "interests_missing",
        "graduation_year_missing",
        "gpa_missing",
        "class_rank_missing",
        "academic_test_scores_missing",
        "english_test_scores_missing",
        "annual_budget_missing",
    ]
    importance: Literal["required_for_next_step", "useful", "optional"]
    message: str


class ApplicantDiagnostic(ApplicantContractModel):
    profile_key: str
    goal: GoalDiagnostic
    academics: AcademicDiagnostic
    testing: TestingDiagnostic
    english: EnglishDiagnostic
    financial: FinancialDiagnostic
    preferences: PreferenceDiagnostic
    explicit_constraints: list[ExplicitConstraint]
    missing_information: list[MissingInformation]


def _attempt(test: ApplicantTestScoreInput) -> TestAttemptDiagnostic:
    return TestAttemptDiagnostic(
        test_type=test.test_type,
        scale=test.scale,
        score=test.score,
        taken_on=test.taken_on,
    )


def build_profile_diagnostic(profile: ApplicantProfileInput) -> ApplicantDiagnostic:
    """Build a factual diagnostic without university data, inference, or writes."""

    academic_attempts = [_attempt(test) for test in profile.tests if test.test_type in {"sat", "act"}]
    english_attempts = [_attempt(test) for test in profile.tests if test.test_type in {"ielts", "toefl", "duolingo"}]
    if profile.study_intent.mode == "known_major":
        goal_supplied = bool(profile.study_intent.intended_cip_codes)
    else:
        goal_supplied = bool(profile.study_intent.interests)

    missing: list[MissingInformation] = []
    if not goal_supplied:
        if profile.study_intent.mode == "known_major":
            missing.append(MissingInformation(
                code="major_missing",
                importance="required_for_next_step",
                message="No intended CIP code was supplied for known-major mode.",
            ))
        else:
            missing.append(MissingInformation(
                code="interests_missing",
                importance="required_for_next_step",
                message="No interest was supplied for explore mode.",
            ))
    if profile.graduation_year is None:
        missing.append(MissingInformation(code="graduation_year_missing", importance="useful", message="Graduation year was not supplied."))
    if profile.academics.gpa_value is None:
        missing.append(MissingInformation(code="gpa_missing", importance="useful", message="GPA was not supplied."))
    if profile.academics.class_rank is None:
        missing.append(MissingInformation(code="class_rank_missing", importance="optional", message="Class rank was not supplied."))
    if not academic_attempts:
        missing.append(MissingInformation(code="academic_test_scores_missing", importance="optional", message="No SAT or ACT attempt was supplied."))
    if not english_attempts:
        missing.append(MissingInformation(code="english_test_scores_missing", importance="useful", message="No English test attempt was supplied."))
    if profile.financial.annual_budget_usd is None:
        missing.append(MissingInformation(code="annual_budget_missing", importance="useful", message="Annual budget was not supplied."))

    return ApplicantDiagnostic(
        profile_key=profile.profile_key,
        goal=GoalDiagnostic(
            mode=profile.study_intent.mode,
            intended_cip_codes=profile.study_intent.intended_cip_codes,
            interests=profile.study_intent.interests,
            goal_supplied=goal_supplied,
        ),
        academics=AcademicDiagnostic(
            graduation_year=profile.graduation_year,
            gpa=GpaDiagnostic(
                state="provided" if profile.academics.gpa_value is not None else "missing",
                gpa_value=profile.academics.gpa_value,
                gpa_scale=profile.academics.gpa_scale,
                gpa_weighting=profile.academics.gpa_weighting,
            ),
            class_rank=ClassRankDiagnostic(
                state="provided" if profile.academics.class_rank is not None else "missing",
                class_rank=profile.academics.class_rank,
                class_size=profile.academics.class_size,
            ),
        ),
        testing=TestingDiagnostic(
            state="scores_provided" if academic_attempts else "no_scores_provided",
            attempts=academic_attempts,
        ),
        english=EnglishDiagnostic(
            state="scores_provided" if english_attempts else "no_scores_provided",
            attempts=english_attempts,
        ),
        financial=FinancialDiagnostic(
            budget_state="budget_provided" if profile.financial.annual_budget_usd is not None else "budget_missing",
            annual_budget_usd=profile.financial.annual_budget_usd,
            needs_financial_aid=profile.financial.needs_financial_aid,
        ),
        preferences=PreferenceDiagnostic(
            preferred_states=profile.preferences.preferred_states,
            excluded_states=profile.preferences.excluded_states,
        ),
        explicit_constraints=[
            ExplicitConstraint(constraint_type="excluded_state", value=state, hard=True, source="applicant_profile")
            for state in profile.preferences.excluded_states
        ],
        missing_information=missing,
    )


def diagnose_profile(profile_key: str) -> ApplicantDiagnostic:
    return build_profile_diagnostic(export_profile(profile_key))
