"""Application-service orchestration for the complete backend journey."""

from collections import Counter

from admission.applicants.diagnostics import diagnose_profile
from admission.journey.schemas import AdmissionJourney, JourneySummary
from admission.recommendation.services import recommend_for_profile
from admission.roadmap.services import build_roadmap


def _validate_scope(
    seed_order_start: int,
    seed_order_end: int,
    recommendation_limit: int | None,
) -> None:
    """Mirror the accepted service boundary for the no-recommendation branch."""
    if seed_order_start < 1 or seed_order_end > 100 or seed_order_start > seed_order_end:
        raise ValueError("seed order range must be inclusive within 1..100")
    if recommendation_limit is not None and (
        type(recommendation_limit) is not int or recommendation_limit <= 0
    ):
        raise ValueError("recommendation_limit must be a positive integer")


def build_admission_journey(
    profile_key: str,
    seed_order_start: int = 1,
    seed_order_end: int = 100,
    recommendation_limit: int | None = None,
) -> AdmissionJourney:
    """Run accepted services once and assemble one deterministic product result."""
    _validate_scope(seed_order_start, seed_order_end, recommendation_limit)
    diagnostic = diagnose_profile(profile_key)
    required_goal_missing = any(
        item.importance == "required_for_next_step" for item in diagnostic.missing_information
    )
    if required_goal_missing:
        roadmap = build_roadmap(
            diagnostic, None, seed_order_start, seed_order_end, recommendation_limit,
        )
        return AdmissionJourney(
            profile_key=profile_key,
            journey_state="profile_preparation",
            diagnostic=diagnostic,
            recommendations=None,
            roadmap=roadmap,
            summary=JourneySummary(
                candidate_count=0,
                recommended_for_review_count=0,
                consider_with_actions_count=0,
                insufficient_evidence_count=0,
                excluded_by_applicant_count=0,
                roadmap_item_count=len(roadmap.items),
            ),
        )

    # This is the only recommendation execution. The same returned object is
    # embedded below and supplied directly to pure roadmap grouping.
    recommendations = recommend_for_profile(
        profile_key, seed_order_start, seed_order_end, recommendation_limit,
    )
    roadmap = build_roadmap(
        diagnostic, recommendations, seed_order_start, seed_order_end, recommendation_limit,
    )
    counts = Counter(item.recommendation_state for item in recommendations.recommendations)
    return AdmissionJourney(
        profile_key=profile_key,
        journey_state="recommendations_ready",
        diagnostic=diagnostic,
        recommendations=recommendations,
        roadmap=roadmap,
        summary=JourneySummary(
            candidate_count=len(recommendations.recommendations),
            recommended_for_review_count=counts["recommended_for_review"],
            consider_with_actions_count=counts["consider_with_actions"],
            insufficient_evidence_count=counts["insufficient_evidence"],
            excluded_by_applicant_count=counts["excluded_by_applicant"],
            roadmap_item_count=len(roadmap.items),
        ),
    )
