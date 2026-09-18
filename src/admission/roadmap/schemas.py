from typing import Literal

from admission.applicants.schemas import ApplicantContractModel


RoadmapState = Literal["profile_preparation", "university_actions", "no_blocking_actions"]
RoadmapCategory = Literal["profile", "academics", "english", "program", "financial", "research"]
RoadmapPriority = Literal["required", "high", "medium", "optional"]
RoadmapScope = Literal["profile", "institutions"]
RoadmapActionCode = Literal[
    "define_intended_major",
    "provide_academic_interests",
    "provide_graduation_year",
    "provide_gpa",
    "provide_class_rank_if_available",
    "provide_academic_test_if_desired",
    "provide_english_test_score",
    "provide_annual_budget",
    "retake_or_improve_english_test",
    "submit_compatible_english_score",
    "verify_current_english_policy",
    "verify_program_availability",
    "research_financial_aid",
    "provide_missing_academic_test_if_desired",
]
RoadmapReasonCode = Literal[
    "major_missing",
    "interests_missing",
    "graduation_year_missing",
    "gpa_missing",
    "class_rank_missing",
    "academic_test_scores_missing",
    "english_test_scores_missing",
    "annual_budget_missing",
    "english_minimum_not_met",
    "english_score_missing",
    "english_policy_unavailable",
    "english_policy_not_found",
    "english_policy_conflicting",
    "english_applicability_unresolved",
    "english_conditional_policy_review_needed",
    "program_evidence_partial",
    "program_evidence_unavailable",
    "financial_review_needed",
    "academic_context_unavailable",
]


class RoadmapItem(ApplicantContractModel):
    action_code: RoadmapActionCode
    category: RoadmapCategory
    priority: RoadmapPriority
    scope: RoadmapScope
    institution_unitids: list[int]
    reason_codes: list[RoadmapReasonCode]


class Roadmap(ApplicantContractModel):
    profile_key: str
    roadmap_state: RoadmapState
    seed_order_start: int
    seed_order_end: int
    recommendation_limit: int | None
    items: list[RoadmapItem]
