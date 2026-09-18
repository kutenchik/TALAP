from datetime import date
from typing import Literal

from admission.applicants.schemas import ApplicantContractModel, JsonDecimal
from admission.assessment.academic import AcademicContext, EvidenceQuality


class InstitutionIdentity(ApplicantContractModel):
    ipeds_unitid: int
    name: str
    state: str


class ApplicantConstraintAssessment(ApplicantContractModel):
    excluded_by_applicant: bool
    reasons: list[Literal["excluded_state"]]


class CipEvidence(ApplicantContractModel):
    cip_code: str
    state: Literal["observed", "not_observed", "unavailable"]
    academic_years: list[str]


class ProgramAssessment(ApplicantContractModel):
    state: Literal["one_or_more_observed", "none_observed", "unavailable", "not_evaluated_explore_mode"]
    requested_cips: list[CipEvidence]


class RequirementEvidence(ApplicantContractModel):
    scale: str
    minimum_score: JsonDecimal
    valid_for_tests_before: date | None
    valid_for_tests_on_or_after: date | None
    policy_cycle: str


class SupportingAttempt(ApplicantContractModel):
    scale: str
    score: JsonDecimal
    taken_on: date | None


class EnglishTestAssessment(ApplicantContractModel):
    test_type: Literal["ielts", "toefl", "duolingo"]
    state: Literal[
        "meets_verified_minimum", "below_verified_minimum", "no_minimum_published", "not_required",
        "no_matching_applicant_score", "requirement_not_found", "requirement_conflicting",
        "requirement_unavailable", "applicability_ambiguous", "no_applicable_requirement",
    ]
    requirements: list[RequirementEvidence]
    supporting_attempts: list[SupportingAttempt]
    conditional_policy_present: bool


class EnglishAssessment(ApplicantContractModel):
    policy_state: Literal["not_required", "no_minimum_published", "verified_minimum", "conflicting", "reviewed_not_found", "unavailable"]
    tests: list[EnglishTestAssessment]


class DataAvailability(ApplicantContractModel):
    program_data_available: bool
    english_data_available: bool
    admissions_context_available: bool


class InstitutionAssessment(ApplicantContractModel):
    seed_order: int
    institution: InstitutionIdentity
    applicant_constraints: ApplicantConstraintAssessment
    program: ProgramAssessment
    english: EnglishAssessment
    data_availability: DataAvailability
    academic: AcademicContext
    evidence_quality: EvidenceQuality


class CandidateAssessmentSet(ApplicantContractModel):
    profile_key: str
    seed_order_start: int
    seed_order_end: int
    candidates: list[InstitutionAssessment]
