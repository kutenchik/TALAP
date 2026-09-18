"""Deterministic roadmap construction from diagnostics and recommendations."""

from collections import defaultdict

from admission.applicants.diagnostics import ApplicantDiagnostic, diagnose_profile
from admission.recommendation.schemas import RecommendationSet, UniversityRecommendation
from admission.recommendation.services import recommend_for_profile
from admission.roadmap.schemas import Roadmap, RoadmapItem


PROFILE_ACTIONS = {
    "major_missing": ("define_intended_major", "profile", "required"),
    "interests_missing": ("provide_academic_interests", "profile", "required"),
    "graduation_year_missing": ("provide_graduation_year", "profile", "medium"),
    "gpa_missing": ("provide_gpa", "academics", "medium"),
    "class_rank_missing": ("provide_class_rank_if_available", "academics", "optional"),
    "academic_test_scores_missing": ("provide_academic_test_if_desired", "academics", "optional"),
    "english_test_scores_missing": ("provide_english_test_score", "english", "medium"),
    "annual_budget_missing": ("provide_annual_budget", "financial", "medium"),
}
RECOMMENDATION_ACTIONS = {
    "retake_or_improve_english_test": ("english", "high"),
    "submit_compatible_english_score": ("english", "high"),
    "verify_current_english_policy": ("english", "medium"),
    "verify_program_availability": ("program", "medium"),
    "research_financial_aid": ("financial", "medium"),
    "provide_missing_academic_test_if_desired": ("academics", "optional"),
}
ACTION_REASONS = {
    "retake_or_improve_english_test": {"english_minimum_not_met"},
    "submit_compatible_english_score": {"english_score_missing"},
    "verify_current_english_policy": {
        "english_policy_unavailable", "english_policy_not_found", "english_policy_conflicting",
        "english_applicability_unresolved", "english_conditional_policy_review_needed",
    },
    "verify_program_availability": {"program_evidence_partial", "program_evidence_unavailable"},
    "research_financial_aid": {"financial_review_needed"},
    "provide_missing_academic_test_if_desired": {"academic_context_unavailable"},
}
PRIORITY_ORDER = {"required": 0, "high": 1, "medium": 2, "optional": 3}
CATEGORY_ORDER = {"profile": 0, "academics": 1, "english": 2, "program": 3, "financial": 4, "research": 5}
# These are actionable university evidence gaps. Financial research and an
# optional academic score remain visible without making the roadmap blocking.
UNIVERSITY_FOLLOW_UP_ACTIONS = {
    "retake_or_improve_english_test", "submit_compatible_english_score",
    "verify_current_english_policy", "verify_program_availability",
}


def _sort_items(items: list[RoadmapItem]) -> list[RoadmapItem]:
    return sorted(items, key=lambda item: (
        PRIORITY_ORDER[item.priority], CATEGORY_ORDER[item.category], item.action_code,
    ))


def _profile_items(diagnostic: ApplicantDiagnostic) -> list[RoadmapItem]:
    return [
        RoadmapItem(
            action_code=PROFILE_ACTIONS[missing.code][0],
            category=PROFILE_ACTIONS[missing.code][1],
            priority=PROFILE_ACTIONS[missing.code][2],
            scope="profile",
            institution_unitids=[],
            reason_codes=[missing.code],
        )
        for missing in diagnostic.missing_information
    ]


def _recommendation_items(recommendations: list[UniversityRecommendation]) -> list[RoadmapItem]:
    unitids: dict[str, set[int]] = defaultdict(set)
    reasons: dict[str, list[str]] = defaultdict(list)
    for recommendation in recommendations:
        if recommendation.recommendation_state == "excluded_by_applicant":
            continue
        for action_code in recommendation.action_codes:
            unitids[action_code].add(recommendation.institution.ipeds_unitid)
            allowed = ACTION_REASONS[action_code]
            for reason_code in recommendation.reason_codes:
                if reason_code in allowed and reason_code not in reasons[action_code]:
                    reasons[action_code].append(reason_code)
    return [
        RoadmapItem(
            action_code=action_code,
            category=RECOMMENDATION_ACTIONS[action_code][0],
            priority=RECOMMENDATION_ACTIONS[action_code][1],
            scope="institutions",
            institution_unitids=sorted(action_unitids),
            reason_codes=reasons[action_code],
        )
        for action_code, action_unitids in unitids.items()
    ]


def build_roadmap(
    diagnostic: ApplicantDiagnostic,
    recommendations: RecommendationSet | None,
    seed_order_start: int,
    seed_order_end: int,
    recommendation_limit: int | None,
) -> Roadmap:
    """Purely group diagnostic and recommendation action codes into a roadmap."""
    items = _profile_items(diagnostic)
    required_goal_missing = any(
        item.importance == "required_for_next_step" for item in diagnostic.missing_information
    )
    if required_goal_missing:
        state = "profile_preparation"
    else:
        if recommendations is None:
            raise ValueError("recommendations are required when the applicant goal is usable")
        recommendation_items = _recommendation_items(recommendations.recommendations)
        items.extend(recommendation_items)
        state = "university_actions" if any(
            item.action_code in UNIVERSITY_FOLLOW_UP_ACTIONS for item in recommendation_items
        ) else "no_blocking_actions"
    return Roadmap(
        profile_key=diagnostic.profile_key,
        roadmap_state=state,
        seed_order_start=seed_order_start,
        seed_order_end=seed_order_end,
        recommendation_limit=recommendation_limit,
        items=_sort_items(items),
    )


def build_roadmap_for_profile(
    profile_key: str,
    seed_order_start: int = 1,
    seed_order_end: int = 100,
    recommendation_limit: int | None = None,
) -> Roadmap:
    if seed_order_start < 1 or seed_order_end > 100 or seed_order_start > seed_order_end:
        raise ValueError("seed order range must be inclusive within 1..100")
    if recommendation_limit is not None and (
        type(recommendation_limit) is not int or recommendation_limit <= 0
    ):
        raise ValueError("recommendation_limit must be a positive integer")
    diagnostic = diagnose_profile(profile_key)
    required_goal_missing = any(
        item.importance == "required_for_next_step" for item in diagnostic.missing_information
    )
    recommendations = None if required_goal_missing else recommend_for_profile(
        profile_key, seed_order_start, seed_order_end, recommendation_limit,
    )
    return build_roadmap(
        diagnostic, recommendations, seed_order_start, seed_order_end, recommendation_limit,
    )
