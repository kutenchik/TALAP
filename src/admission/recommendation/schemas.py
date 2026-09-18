from typing import Literal

from admission.applicants.schemas import ApplicantContractModel, FinancialInput
from admission.assessment.schemas import InstitutionAssessment, InstitutionIdentity


RecommendationState = Literal[
    "recommended_for_review", "consider_with_actions", "insufficient_evidence", "excluded_by_applicant",
]
ActionCode = Literal[
    "retake_or_improve_english_test", "submit_compatible_english_score", "verify_current_english_policy",
    "verify_program_availability", "research_financial_aid", "provide_missing_academic_test_if_desired",
]
ReasonCode = Literal[
    "preferred_state", "excluded_state", "program_cip_observed", "program_evidence_partial",
    "program_evidence_unavailable", "program_not_evaluated_explore_mode",
    "english_minimum_met", "english_not_required", "english_no_minimum_published",
    "english_minimum_not_met", "english_score_missing", "english_policy_unavailable",
    "english_policy_not_found", "english_policy_conflicting", "english_applicability_unresolved",
    "english_conditional_policy_review_needed",
    "academic_above_reported_context", "academic_within_reported_context", "academic_below_reported_context",
    "academic_context_unavailable", "financial_review_needed", "sparse_data",
]


class RecommendationSignals(ApplicantContractModel):
    program: Literal["observed", "partial", "unavailable", "not_applicable"]
    english: Literal["usable", "action_needed", "uncertain", "conflicting"]
    academic: Literal["above_reported_context", "within_reported_context", "below_reported_context", "unavailable"]
    preference: Literal["preferred_state", "neutral", "excluded_state"]
    financial: Literal["unavailable"]
    data_quality: Literal["usable", "partial", "sparse", "conflicting"]


class UniversityRecommendation(ApplicantContractModel):
    seed_order: int
    institution: InstitutionIdentity
    recommendation_state: RecommendationState
    signals: RecommendationSignals
    action_codes: list[ActionCode]
    reason_codes: list[ReasonCode]
    assessment: InstitutionAssessment


class RecommendationSet(ApplicantContractModel):
    profile_key: str
    seed_order_start: int
    seed_order_end: int
    limit: int | None
    applicant_financial_context: FinancialInput
    recommendations: list[UniversityRecommendation]
