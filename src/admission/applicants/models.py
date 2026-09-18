from django.db import models


class ApplicantProfile(models.Model):
    class GpaWeighting(models.TextChoices):
        WEIGHTED = "weighted"
        UNWEIGHTED = "unweighted"
        UNKNOWN = "unknown"

    class StudyMode(models.TextChoices):
        KNOWN_MAJOR = "known_major"
        EXPLORE = "explore"

    profile_key = models.CharField(max_length=120, unique=True)
    display_name = models.CharField(max_length=200, blank=True)
    citizenship_country_code = models.CharField(max_length=2)
    residence_country_code = models.CharField(max_length=2, blank=True)
    school_country_code = models.CharField(max_length=2, blank=True)
    graduation_year = models.PositiveSmallIntegerField(null=True, blank=True)
    gpa_value = models.DecimalField(max_digits=7, decimal_places=3, null=True, blank=True)
    gpa_scale = models.DecimalField(max_digits=7, decimal_places=3, null=True, blank=True)
    gpa_weighting = models.CharField(max_length=12, choices=GpaWeighting.choices, default=GpaWeighting.UNKNOWN)
    class_rank = models.PositiveIntegerField(null=True, blank=True)
    class_size = models.PositiveIntegerField(null=True, blank=True)
    study_mode = models.CharField(max_length=16, choices=StudyMode.choices)
    intended_cip_codes = models.JSONField(default=list)
    interests = models.JSONField(default=list)
    annual_budget_usd = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    needs_financial_aid = models.BooleanField(null=True, blank=True)
    preferred_states = models.JSONField(default=list)
    excluded_states = models.JSONField(default=list)

    class Meta:
        ordering = ["profile_key"]


class ApplicantTestScore(models.Model):
    class TestType(models.TextChoices):
        SAT = "sat"
        ACT = "act"
        IELTS = "ielts"
        TOEFL = "toefl"
        DUOLINGO = "duolingo"

    profile = models.ForeignKey(ApplicantProfile, on_delete=models.CASCADE, related_name="test_scores")
    position = models.PositiveSmallIntegerField()
    test_type = models.CharField(max_length=12, choices=TestType.choices)
    scale = models.CharField(max_length=24)
    score = models.DecimalField(max_digits=7, decimal_places=3)
    taken_on = models.DateField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["profile", "position"], name="unique_applicant_test_position"),
        ]
        ordering = ["profile__profile_key", "position"]
