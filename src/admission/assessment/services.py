from collections import defaultdict

from admission.applicants.schemas import ApplicantProfileInput, ApplicantTestScoreInput
from admission.applicants.services import export_profile
from admission.assessment.academic import EvidenceQuality, academic_evidence, build_academic_context
from admission.assessment.schemas import (
    ApplicantConstraintAssessment,
    CandidateAssessmentSet,
    CipEvidence,
    DataAvailability,
    EnglishAssessment,
    EnglishTestAssessment,
    InstitutionAssessment,
    InstitutionIdentity,
    ProgramAssessment,
    RequirementEvidence,
    SupportingAttempt,
)
from admission.catalog.models import AdmissionSnapshot, EnglishRequirement, Institution, ProgramOffering, SeedInstitution
from admission.catalog.services import ENGLISH_APPLICANT_SCOPE, _current_source_backed_english_requirements


TEST_MAP = {"ielts": "ielts", "toefl": "toefl_ibt", "duolingo": "duolingo_english_test"}
CATALOG_SCALE = {
    "ielts_0_9": "ielts_band_0_9",
    "toefl_ibt_0_120": "toefl_ibt_0_120",
    "toefl_ibt_1_6": "toefl_ibt_1_6",
    "det_10_160": "det_10_160",
}


def _attempt_applies(attempt: ApplicantTestScoreInput, requirement: EnglishRequirement) -> bool | None:
    if attempt.taken_on is None and (requirement.valid_for_tests_before or requirement.valid_for_tests_on_or_after):
        return None
    if requirement.valid_for_tests_before and attempt.taken_on is not None and attempt.taken_on >= requirement.valid_for_tests_before:
        return False
    if requirement.valid_for_tests_on_or_after and attempt.taken_on is not None and attempt.taken_on < requirement.valid_for_tests_on_or_after:
        return False
    return True


def _english_test_assessment(test_type: str, profile: ApplicantProfileInput, rows: list[EnglishRequirement]) -> EnglishTestAssessment:
    conditional = any(row.waiver_text or row.conditional_text for row in rows)
    common = {"test_type": test_type, "requirements": [], "supporting_attempts": [], "conditional_policy_present": conditional}
    if not rows:
        return EnglishTestAssessment(state="requirement_unavailable", **common)
    statuses = {row.status for row in rows}
    policy_meanings = statuses & {
        EnglishRequirement.Status.VERIFIED,
        EnglishRequirement.Status.NOT_REQUIRED,
        EnglishRequirement.Status.NO_MINIMUM_PUBLISHED,
    }
    if EnglishRequirement.Status.CONFLICTING in statuses or len(policy_meanings) > 1:
        return EnglishTestAssessment(state="requirement_conflicting", **common)
    if EnglishRequirement.Status.NOT_REQUIRED in statuses:
        return EnglishTestAssessment(state="not_required", **common)
    if EnglishRequirement.Status.NO_MINIMUM_PUBLISHED in statuses:
        return EnglishTestAssessment(state="no_minimum_published", **common)
    verified = [row for row in rows if row.status == EnglishRequirement.Status.VERIFIED and row.minimum_overall_score is not None]
    if not verified:
        if EnglishRequirement.Status.NOT_FOUND in statuses:
            return EnglishTestAssessment(state="requirement_not_found", **common)
        return EnglishTestAssessment(state="requirement_unavailable", **common)

    contexts: dict[tuple[object, ...], set[object]] = defaultdict(set)
    for row in verified:
        contexts[(row.score_scale, row.valid_for_tests_before, row.valid_for_tests_on_or_after)].add(row.minimum_overall_score)
    if any(len(values) > 1 for values in contexts.values()):
        return EnglishTestAssessment(state="requirement_conflicting", **common)

    evidence = [RequirementEvidence(
        scale=row.score_scale,
        minimum_score=row.minimum_overall_score,
        valid_for_tests_before=row.valid_for_tests_before,
        valid_for_tests_on_or_after=row.valid_for_tests_on_or_after,
        policy_cycle=row.policy_cycle,
    ) for row in verified]
    attempts = [test for test in profile.tests if test.test_type == test_type]
    compatible = [(attempt, row) for attempt in attempts for row in verified if CATALOG_SCALE[attempt.scale] == row.score_scale]
    if not compatible:
        return EnglishTestAssessment(test_type=test_type, state="no_matching_applicant_score", requirements=evidence, supporting_attempts=[], conditional_policy_present=conditional)

    applicable: list[tuple[ApplicantTestScoreInput, EnglishRequirement]] = []
    ambiguous = False
    for attempt in attempts:
        exact = [row for row in verified if row.score_scale == CATALOG_SCALE[attempt.scale]]
        if attempt.taken_on is None and len({(row.valid_for_tests_before, row.valid_for_tests_on_or_after) for row in exact}) > 1:
            ambiguous = True
            continue
        for row in exact:
            applies = _attempt_applies(attempt, row)
            ambiguous = ambiguous or applies is None
            if applies:
                applicable.append((attempt, row))
    if not applicable:
        state = "applicability_ambiguous" if ambiguous else "no_applicable_requirement"
        return EnglishTestAssessment(test_type=test_type, state=state, requirements=evidence, supporting_attempts=[], conditional_policy_present=conditional)
    supporting = [SupportingAttempt(scale=attempt.scale, score=attempt.score, taken_on=attempt.taken_on) for attempt, _row in applicable]
    if any(attempt.score >= row.minimum_overall_score for attempt, row in applicable):
        state = "meets_verified_minimum"
    elif ambiguous:
        state = "applicability_ambiguous"
    else:
        state = "below_verified_minimum"
    return EnglishTestAssessment(test_type=test_type, state=state, requirements=evidence, supporting_attempts=supporting, conditional_policy_present=conditional)


def assess_institution_for_profile(
    profile: ApplicantProfileInput,
    seed: SeedInstitution,
    programs: list[ProgramOffering],
    english_rows: list[EnglishRequirement],
    admissions_context_available: bool,
    admission_snapshots: list[AdmissionSnapshot] | None = None,
) -> InstitutionAssessment:
    institution = seed.institution
    assert institution is not None
    if profile.study_intent.mode == "explore":
        program = ProgramAssessment(state="not_evaluated_explore_mode", requested_cips=[])
    else:
        available = bool(programs)
        requested = []
        for cip in profile.study_intent.intended_cip_codes:
            matches = [row for row in programs if row.cip_code == cip and not row.cip_code.startswith("99.")]
            requested.append(CipEvidence(
                cip_code=cip,
                state="observed" if matches else ("not_observed" if available else "unavailable"),
                academic_years=list(dict.fromkeys(row.academic_year for row in matches)),
            ))
        program = ProgramAssessment(
            state="one_or_more_observed" if any(item.state == "observed" for item in requested) else ("none_observed" if available else "unavailable"),
            requested_cips=requested,
        )
    tests = [_english_test_assessment(test, profile, [row for row in english_rows if row.test_type == TEST_MAP[test]]) for test in ("ielts", "toefl", "duolingo")]
    policy_states = {test.state for test in tests}
    policy_state = (
        "conflicting" if "requirement_conflicting" in policy_states else
        "verified_minimum" if any(row.status == EnglishRequirement.Status.VERIFIED for row in english_rows) else
        "not_required" if "not_required" in policy_states else
        "no_minimum_published" if "no_minimum_published" in policy_states else
        "reviewed_not_found" if "requirement_not_found" in policy_states else "unavailable"
    )
    excluded = institution.state in profile.preferences.excluded_states
    academic = build_academic_context(profile, admission_snapshots or [])
    program_quality = {
        "one_or_more_observed": "verified", "none_observed": "partial",
        "unavailable": "unavailable", "not_evaluated_explore_mode": "not_applicable",
    }[program.state]
    if policy_state == "conflicting":
        english_quality = "conflicting"
    elif policy_state in {"verified_minimum", "not_required", "no_minimum_published"}:
        english_quality = "partial" if any(t.conditional_policy_present for t in tests) else "verified"
    elif policy_state == "reviewed_not_found":
        english_quality = "partial"
    else:
        english_quality = "unavailable"
    return InstitutionAssessment(
        seed_order=seed.seed_order,
        institution=InstitutionIdentity(ipeds_unitid=institution.ipeds_unitid, name=institution.name, state=institution.state),
        applicant_constraints=ApplicantConstraintAssessment(excluded_by_applicant=excluded, reasons=["excluded_state"] if excluded else []),
        program=program,
        english=EnglishAssessment(policy_state=policy_state, tests=tests),
        data_availability=DataAvailability(
            program_data_available=bool(programs),
            english_data_available=bool(english_rows),
            admissions_context_available=admissions_context_available,
        ),
        academic=academic,
        evidence_quality=EvidenceQuality(program=program_quality, english=english_quality, academic=academic_evidence(academic)),
    )


def assess_candidates(profile_key: str, seed_order_start: int = 1, seed_order_end: int = 100) -> CandidateAssessmentSet:
    return assess_candidates_for_profile(export_profile(profile_key), seed_order_start, seed_order_end)


def assess_candidates_for_profile(profile: ApplicantProfileInput, seed_order_start: int = 1, seed_order_end: int = 100) -> CandidateAssessmentSet:
    """Reuse an already loaded profile without repeating its ORM lookup."""
    if seed_order_start < 1 or seed_order_end > 100 or seed_order_start > seed_order_end:
        raise ValueError("seed order range must be inclusive within 1..100")
    seeds = list(SeedInstitution.objects.filter(seed_order__range=(seed_order_start, seed_order_end)).select_related("institution").order_by("seed_order"))
    expected = seed_order_end - seed_order_start + 1
    if len(seeds) != expected or any(seed.status != SeedInstitution.Status.RESOLVED or seed.institution is None for seed in seeds):
        raise ValueError("every selected seed row must exist and be resolved")
    unitids = [seed.institution.ipeds_unitid for seed in seeds if seed.institution]
    if len(unitids) != len(set(unitids)):
        raise ValueError("selected seed rows contain duplicate institution UNITIDs")
    institution_ids = [seed.institution_id for seed in seeds]
    programs_by_institution: dict[int, list[ProgramOffering]] = defaultdict(list)
    for row in ProgramOffering.objects.filter(institution_id__in=institution_ids, credential_level="bachelors_degree").order_by("institution_id", "cip_code", "academic_year"):
        programs_by_institution[row.institution_id].append(row)
    english_by_institution: dict[int, list[EnglishRequirement]] = defaultdict(list)
    for row in _current_source_backed_english_requirements().filter(institution_id__in=institution_ids, applicant_scope=ENGLISH_APPLICANT_SCOPE).select_related("source").order_by("institution_id", "test_type", "score_scale", "valid_for_tests_before", "valid_for_tests_on_or_after", "pk"):
        english_by_institution[row.institution_id].append(row)
    admissions_by_institution: dict[int, list[AdmissionSnapshot]] = defaultdict(list)
    for row in AdmissionSnapshot.objects.filter(institution_id__in=institution_ids).select_related("source").order_by("institution_id", "data_year", "term"):
        admissions_by_institution[row.institution_id].append(row)
    return CandidateAssessmentSet(
        profile_key=profile.profile_key,
        seed_order_start=seed_order_start,
        seed_order_end=seed_order_end,
        candidates=[assess_institution_for_profile(
            profile, seed, programs_by_institution[seed.institution_id], english_by_institution[seed.institution_id],
            bool(admissions_by_institution[seed.institution_id]), admissions_by_institution[seed.institution_id],
        ) for seed in seeds],
    )
