"""Documented ordinal review priority; no admission outcome model."""

from admission.applicants.diagnostics import build_profile_diagnostic
from admission.applicants.schemas import ApplicantProfileInput
from admission.applicants.services import export_profile
from admission.assessment.schemas import InstitutionAssessment
from admission.assessment.services import assess_candidates_for_profile
from admission.recommendation.schemas import RecommendationSet, RecommendationSignals, UniversityRecommendation


class MissingApplicantGoal(ValueError):
    """A product goal is required before prioritizing universities."""


BUCKET_ORDER = {"recommended_for_review": 0, "consider_with_actions": 1, "insufficient_evidence": 2, "excluded_by_applicant": 3}
PROGRAM_ORDER = {"observed": 0, "not_applicable": 0, "partial": 1, "unavailable": 2}
ENGLISH_ORDER = {"usable": 0, "action_needed": 1, "uncertain": 2, "conflicting": 3}
# Unknown academic context occupies the neutral (within-context) sorting slot.
ACADEMIC_ORDER = {"above_reported_context": 0, "within_reported_context": 1, "unavailable": 1, "below_reported_context": 2}
QUALITY_ORDER = {"usable": 0, "partial": 1, "sparse": 2, "conflicting": 3}


def priority_key(item: UniversityRecommendation) -> tuple[int, ...]:
    return (
        BUCKET_ORDER[item.recommendation_state],
        0 if item.signals.preference == "preferred_state" else 1,
        PROGRAM_ORDER[item.signals.program], ENGLISH_ORDER[item.signals.english],
        ACADEMIC_ORDER[item.signals.academic], QUALITY_ORDER[item.signals.data_quality], item.seed_order,
    )


def recommend_assessment(profile: ApplicantProfileInput, assessment: InstitutionAssessment) -> UniversityRecommendation:
    reasons = []
    actions = []
    excluded = assessment.applicant_constraints.excluded_by_applicant
    preference = "excluded_state" if excluded else (
        "preferred_state" if assessment.institution.state in profile.preferences.preferred_states else "neutral"
    )
    if preference != "neutral":
        reasons.append(preference)

    program, program_reason = {
        "one_or_more_observed": ("observed", "program_cip_observed"),
        "none_observed": ("partial", "program_evidence_partial"),
        "unavailable": ("unavailable", "program_evidence_unavailable"),
        "not_evaluated_explore_mode": ("not_applicable", "program_not_evaluated_explore_mode"),
    }[assessment.program.state]
    reasons.append(program_reason)
    if program in {"partial", "unavailable"}:
        actions.append("verify_program_availability")

    tests = assessment.english.tests
    states = {test.state for test in tests}
    positive = {
        "meets_verified_minimum": "english_minimum_met",
        "not_required": "english_not_required",
        "no_minimum_published": "english_no_minimum_published",
    }
    concrete_english_action = False
    if "requirement_conflicting" in states:
        english = "conflicting"
        reasons.append("english_policy_conflicting")
        actions.append("verify_current_english_policy")
        concrete_english_action = True
    elif states & positive.keys():
        # Tests are alternative submitted routes: do not demand all three exams.
        english = "usable"
        reasons.extend(reason for state, reason in positive.items() if state in states)
        if any(test.conditional_policy_present for test in tests):
            english = "uncertain"
            reasons.append("english_conditional_policy_review_needed")
            actions.append("verify_current_english_policy")
            concrete_english_action = True
    else:
        english = "uncertain"
        if "below_verified_minimum" in states:
            english = "action_needed"
            reasons.append("english_minimum_not_met")
            actions.append("retake_or_improve_english_test")
            concrete_english_action = True
        if "no_matching_applicant_score" in states:
            english = "action_needed"
            reasons.append("english_score_missing")
            actions.append("submit_compatible_english_score")
            concrete_english_action = True
        if states & {"applicability_ambiguous", "no_applicable_requirement"}:
            reasons.append("english_applicability_unresolved")
            actions.append("verify_current_english_policy")
            concrete_english_action = True
        if "requirement_not_found" in states:
            reasons.append("english_policy_not_found")
            actions.append("verify_current_english_policy")
        if "requirement_unavailable" in states:
            reasons.append("english_policy_unavailable")
            actions.append("verify_current_english_policy")

    academic_states = {assessment.academic.sat.state, assessment.academic.act.state}
    academic = next((state for state in (
        "above_reported_context", "within_reported_context", "below_reported_context",
    ) if state in academic_states), "unavailable")
    reasons.append(f"academic_{academic}" if academic != "unavailable" else "academic_context_unavailable")
    if not assessment.academic.sat.attempts and not assessment.academic.act.attempts:
        actions.append("provide_missing_academic_test_if_desired")

    qualities = assessment.evidence_quality
    applicable = [state for state in (qualities.program, qualities.english, qualities.academic) if state != "not_applicable"]
    if "conflicting" in applicable:
        quality = "conflicting"
    elif all(state == "verified" for state in applicable):
        quality = "usable"
    elif "verified" in applicable:
        quality = "partial"
    else:
        quality = "sparse"
        reasons.append("sparse_data")

    # Known major needs observed CIP + usable English; explore needs usable
    # English + comparable academic evidence. SAT/ACT absence never blocks service.
    supported_review = english == "usable" and (
        program == "observed" or (program == "not_applicable" and qualities.academic == "verified")
    )
    state = (
        "excluded_by_applicant" if excluded else
        "consider_with_actions" if concrete_english_action else
        "recommended_for_review" if supported_review else "insufficient_evidence"
    )
    if profile.financial.needs_financial_aid is True:
        reasons.append("financial_review_needed")
        actions.append("research_financial_aid")
    return UniversityRecommendation(
        seed_order=assessment.seed_order, institution=assessment.institution, recommendation_state=state,
        signals=RecommendationSignals(program=program, english=english, academic=academic, preference=preference,
                                      financial="unavailable", data_quality=quality),
        action_codes=list(dict.fromkeys(actions)), reason_codes=list(dict.fromkeys(reasons)), assessment=assessment,
    )


def recommend_for_profile(
    profile_key: str, seed_order_start: int = 1, seed_order_end: int = 100, limit: int | None = None,
) -> RecommendationSet:
    if limit is not None and (type(limit) is not int or limit <= 0):
        raise ValueError("limit must be a positive integer")
    profile = export_profile(profile_key)
    diagnostic = build_profile_diagnostic(profile)
    missing = [item.code for item in diagnostic.missing_information if item.importance == "required_for_next_step"]
    if missing:
        raise MissingApplicantGoal("A usable applicant goal is required: " + ", ".join(missing))
    assessment = assess_candidates_for_profile(profile, seed_order_start, seed_order_end)
    ordered = sorted((recommend_assessment(profile, item) for item in assessment.candidates), key=priority_key)
    return RecommendationSet(
        profile_key=profile.profile_key, seed_order_start=seed_order_start, seed_order_end=seed_order_end, limit=limit,
        applicant_financial_context=profile.financial, recommendations=ordered if limit is None else ordered[:limit],
    )
