from pathlib import Path

from django.db import transaction

from admission.applicants.models import ApplicantProfile, ApplicantTestScore
from admission.applicants.schemas import (
    AcademicsInput,
    ApplicantProfileInput,
    ApplicantTestScoreInput,
    FinancialInput,
    PreferencesInput,
    StudyIntentInput,
)


def load_profile(path: Path) -> ApplicantProfileInput:
    return ApplicantProfileInput.model_validate_json(path.read_text(encoding="utf-8"))


@transaction.atomic
def import_profile(payload: ApplicantProfileInput) -> ApplicantProfile:
    academics = payload.academics
    financial = payload.financial
    profile, _created = ApplicantProfile.objects.update_or_create(
        profile_key=payload.profile_key,
        defaults={
            "display_name": payload.display_name or "",
            "citizenship_country_code": payload.citizenship_country_code,
            "residence_country_code": payload.residence_country_code or "",
            "school_country_code": payload.school_country_code or "",
            "graduation_year": payload.graduation_year,
            "gpa_value": academics.gpa_value,
            "gpa_scale": academics.gpa_scale,
            "gpa_weighting": academics.gpa_weighting,
            "class_rank": academics.class_rank,
            "class_size": academics.class_size,
            "study_mode": payload.study_intent.mode,
            "intended_cip_codes": payload.study_intent.intended_cip_codes,
            "interests": payload.study_intent.interests,
            "annual_budget_usd": financial.annual_budget_usd,
            "needs_financial_aid": financial.needs_financial_aid,
            "preferred_states": payload.preferences.preferred_states,
            "excluded_states": payload.preferences.excluded_states,
        },
    )
    profile.test_scores.all().delete()
    ApplicantTestScore.objects.bulk_create([
        ApplicantTestScore(
            profile=profile,
            position=position,
            test_type=test.test_type,
            scale=test.scale,
            score=test.score,
            taken_on=test.taken_on,
            note=test.note or "",
        )
        for position, test in enumerate(payload.tests)
    ])
    return profile


def export_profile(profile_key: str) -> ApplicantProfileInput:
    profile = ApplicantProfile.objects.prefetch_related("test_scores").get(profile_key=profile_key)
    return ApplicantProfileInput(
        profile_key=profile.profile_key,
        display_name=profile.display_name or None,
        citizenship_country_code=profile.citizenship_country_code,
        residence_country_code=profile.residence_country_code or None,
        school_country_code=profile.school_country_code or None,
        graduation_year=profile.graduation_year,
        academics=AcademicsInput(
            gpa_value=profile.gpa_value,
            gpa_scale=profile.gpa_scale,
            gpa_weighting=profile.gpa_weighting,
            class_rank=profile.class_rank,
            class_size=profile.class_size,
        ),
        tests=[
            ApplicantTestScoreInput(
                test_type=test.test_type,
                scale=test.scale,
                score=test.score,
                taken_on=test.taken_on,
                note=test.note or None,
            )
            for test in profile.test_scores.all()
        ],
        study_intent=StudyIntentInput(
            mode=profile.study_mode,
            intended_cip_codes=profile.intended_cip_codes,
            interests=profile.interests,
        ),
        financial=FinancialInput(
            annual_budget_usd=profile.annual_budget_usd,
            needs_financial_aid=profile.needs_financial_aid,
        ),
        preferences=PreferencesInput(
            preferred_states=profile.preferred_states,
            excluded_states=profile.excluded_states,
        ),
    )
