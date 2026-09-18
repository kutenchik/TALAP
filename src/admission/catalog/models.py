from django.db import models


class SourceDocument(models.Model):
    """Provenance for structured imports and fetched official pages."""

    url = models.URLField()
    canonical_url = models.URLField(blank=True)
    institution = models.ForeignKey("Institution", null=True, blank=True, on_delete=models.SET_NULL, related_name="source_documents")
    publisher = models.CharField(max_length=200)
    source_type = models.CharField(max_length=100)
    data_year = models.CharField(max_length=20)
    retrieved_at = models.DateTimeField()
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    content_hash = models.CharField(max_length=64)
    page_title = models.CharField(max_length=500, blank=True)
    extraction_method = models.CharField(max_length=100, default="csv_import")
    model_name = models.CharField(max_length=100, blank=True)
    prompt_version = models.CharField(max_length=100, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["institution", "url"], name="unique_institution_source_url"),
        ]
        ordering = ["url"]


class Institution(models.Model):
    """Canonical IPEDS institution identity; names are not primary identity."""

    ipeds_unitid = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=300)
    state = models.CharField(max_length=2)
    city = models.CharField(max_length=150)
    country = models.CharField(max_length=2, default="US")
    ownership = models.CharField(max_length=32)
    official_website = models.URLField(blank=True)
    operating_status = models.CharField(max_length=32)
    bachelors_granting = models.BooleanField()
    bachelors_granting_evidence = models.CharField(max_length=200)
    source = models.ForeignKey(SourceDocument, on_delete=models.PROTECT, related_name="institutions")
    source_locator = models.CharField(max_length=200)

    class Meta:
        ordering = ["ipeds_unitid"]


class InstitutionAlias(models.Model):
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name="aliases")
    alias = models.CharField(max_length=300)
    alias_type = models.CharField(max_length=40, default="seed_name")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["institution", "alias", "alias_type"], name="unique_institution_alias"),
        ]
        ordering = ["institution__ipeds_unitid", "alias"]


class ProgramOffering(models.Model):
    """Bachelor's-level CIP coverage supported by IPEDS completions evidence."""

    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name="program_offerings")
    cip_code = models.CharField(max_length=7)
    cip_title = models.CharField(max_length=300)
    credential_level = models.CharField(max_length=40)
    award_level = models.PositiveSmallIntegerField()
    program_name = models.CharField(max_length=300, blank=True)
    completion_count = models.PositiveIntegerField()
    status = models.CharField(max_length=32)
    academic_year = models.CharField(max_length=20)
    source = models.ForeignKey(SourceDocument, on_delete=models.PROTECT, related_name="program_offerings")
    cip_title_source = models.ForeignKey(SourceDocument, on_delete=models.PROTECT, related_name="cip_titled_program_offerings")
    source_locator = models.CharField(max_length=300)
    evidence = models.TextField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["institution", "cip_code", "credential_level", "academic_year"],
                name="unique_program_offering_coverage",
            ),
        ]
        ordering = ["institution__ipeds_unitid", "cip_code"]


class AdmissionSnapshot(models.Model):
    """IPEDS Fall admissions/test-score context, never an applicant-level prediction or policy."""

    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name="admission_snapshots")
    data_year = models.CharField(max_length=20)
    term = models.CharField(max_length=20, default="fall")
    applicant_count = models.PositiveIntegerField(null=True, blank=True)
    admitted_count = models.PositiveIntegerField(null=True, blank=True)
    enrolled_count = models.PositiveIntegerField(null=True, blank=True)
    admission_rate = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    sat_ebrw_25 = models.PositiveSmallIntegerField(null=True, blank=True)
    sat_ebrw_75 = models.PositiveSmallIntegerField(null=True, blank=True)
    sat_math_25 = models.PositiveSmallIntegerField(null=True, blank=True)
    sat_math_75 = models.PositiveSmallIntegerField(null=True, blank=True)
    act_composite_25 = models.PositiveSmallIntegerField(null=True, blank=True)
    act_composite_75 = models.PositiveSmallIntegerField(null=True, blank=True)
    sat_submission_count = models.PositiveIntegerField(null=True, blank=True)
    sat_submission_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    act_submission_count = models.PositiveIntegerField(null=True, blank=True)
    act_submission_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    admissions_data_status = models.CharField(max_length=32)
    sat_data_status = models.CharField(max_length=32)
    act_data_status = models.CharField(max_length=32)
    test_data_status = models.CharField(max_length=32)
    source_flags = models.JSONField(default=dict)
    source = models.ForeignKey(SourceDocument, on_delete=models.PROTECT, related_name="admission_snapshots")
    dictionary_source = models.ForeignKey(SourceDocument, on_delete=models.PROTECT, related_name="admission_dictionary_snapshots")
    source_locator = models.CharField(max_length=200)
    evidence = models.TextField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["institution", "data_year", "term"], name="unique_admission_snapshot_term"),
        ]
        ordering = ["institution__ipeds_unitid", "data_year", "term"]


class EnglishRequirement(models.Model):
    """Official-page English-policy fact or explicitly qualified extraction state."""

    class TestType(models.TextChoices):
        IELTS = "ielts"
        TOEFL_IBT = "toefl_ibt"
        DUOLINGO_ENGLISH_TEST = "duolingo_english_test"

    class Status(models.TextChoices):
        VERIFIED = "verified"
        NO_MINIMUM_PUBLISHED = "no_minimum_published"
        NOT_FOUND = "not_found"
        NOT_REQUIRED = "not_required"
        CONFLICTING = "conflicting"
        UNVERIFIED = "unverified"
        EXTRACTION_FAILED = "extraction_failed"

    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name="english_requirements")
    applicant_scope = models.CharField(max_length=64, default="international_undergraduate")
    test_type = models.CharField(max_length=32, choices=TestType.choices)
    score_scale = models.CharField(max_length=32, blank=True)
    valid_for_tests_before = models.DateField(null=True, blank=True)
    valid_for_tests_on_or_after = models.DateField(null=True, blank=True)
    minimum_overall_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    subscore_requirements = models.JSONField(default=dict)
    waiver_text = models.TextField(blank=True)
    conditional_text = models.TextField(blank=True)
    policy_cycle = models.CharField(max_length=100, default="unspecified")
    status = models.CharField(max_length=32, choices=Status.choices)
    source = models.ForeignKey(SourceDocument, null=True, blank=True, on_delete=models.PROTECT, related_name="english_requirements")
    # Immutable binding to the exact source bytes that validated this fact.
    source_content_hash = models.CharField(max_length=64, blank=True, default="")
    evidence = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["institution", "test_type", "applicant_scope", "policy_cycle", "source", "score_scale", "valid_for_tests_before", "valid_for_tests_on_or_after"],
                name="unique_english_requirement_version",
            ),
        ]
        ordering = ["institution__ipeds_unitid", "test_type", "policy_cycle"]


class SeedInstitution(models.Model):
    """The reviewable 100-entry cohort and its explicit resolution state."""

    class Status(models.TextChoices):
        PENDING = "pending"
        RESOLVED = "resolved"
        AMBIGUOUS = "ambiguous"
        UNRESOLVED = "unresolved"

    seed_order = models.PositiveSmallIntegerField(unique=True)
    name = models.CharField(max_length=300)
    state = models.CharField(max_length=2)
    expected_ownership = models.CharField(max_length=32)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    institution = models.ForeignKey(Institution, null=True, blank=True, on_delete=models.SET_NULL, related_name="seed_entries")

    class Meta:
        ordering = ["seed_order"]


class DataIssue(models.Model):
    class IssueType(models.TextChoices):
        AMBIGUOUS_MATCH = "ambiguous_match"
        UNRESOLVED_MATCH = "unresolved_match"
        STATE_MISMATCH = "state_mismatch"
        OWNERSHIP_MISMATCH = "ownership_mismatch"
        DUPLICATE_UNITID = "duplicate_unitid"
        INVALID_PROGRAM_RECORD = "invalid_program_record"
        ZERO_BACHELOR_PROGRAMS = "zero_bachelor_programs"
        INVALID_ADMISSIONS_RECORD = "invalid_admissions_record"
        SOURCE_FETCH_FAILED = "source_fetch_failed"
        ENGLISH_EXTRACTION_REVIEW = "english_extraction_review"

    seed_entry = models.ForeignKey(SeedInstitution, on_delete=models.CASCADE, related_name="issues")
    issue_type = models.CharField(max_length=32, choices=IssueType.choices)
    # Empty for institution-wide issues; reviewed source URL for source-specific issues.
    issue_key = models.CharField(max_length=500, blank=True, default="")
    detail = models.TextField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["seed_entry", "issue_type", "issue_key"], name="unique_seed_issue_type_key"),
        ]
        ordering = ["seed_entry__seed_order", "issue_type"]
