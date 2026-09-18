import re
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SeedManifestEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    seed_order: int = Field(ge=1)
    name: str = Field(min_length=1)
    state: str = Field(min_length=2, max_length=2)
    ownership: str
    country: str

    @field_validator("state", "country")
    @classmethod
    def uppercase(cls, value: str) -> str:
        return value.upper()


class SeedManifest(BaseModel):
    universities: list[SeedManifestEntry]


class IpedInstitutionRecord(BaseModel):
    unitid: int = Field(gt=0)
    name: str
    city: str
    state: str
    control: int
    website: str = ""
    cyactive: int
    ugoffer: int
    hloffer: int
    deggrant: int


class IpedBachelorCompletionRecord(BaseModel):
    unitid: int = Field(gt=0)
    cip_code: str
    cip_title: str = Field(min_length=1)
    award_level: int
    completion_count: int = Field(ge=0)
    major_number: int = Field(gt=0)

    @field_validator("cip_code")
    @classmethod
    def require_six_digit_cip_code(cls, value: str) -> str:
        if not re.fullmatch(r"\d{2}\.\d{4}", value):
            raise ValueError("CIP code must be a normalized six-digit CIP 2020 code")
        return value


class IpedAdmissionsRecord(BaseModel):
    unitid: int = Field(gt=0)
    applicant_count: int | None = Field(default=None, ge=0)
    admitted_count: int | None = Field(default=None, ge=0)
    enrolled_count: int | None = Field(default=None, ge=0)
    sat_ebrw_25: int | None = Field(default=None, ge=200, le=800)
    sat_ebrw_75: int | None = Field(default=None, ge=200, le=800)
    sat_math_25: int | None = Field(default=None, ge=200, le=800)
    sat_math_75: int | None = Field(default=None, ge=200, le=800)
    act_composite_25: int | None = Field(default=None, ge=1, le=36)
    act_composite_75: int | None = Field(default=None, ge=1, le=36)
    sat_submission_count: int | None = Field(default=None, ge=0)
    sat_submission_percent: int | None = Field(default=None, ge=0, le=100)
    act_submission_count: int | None = Field(default=None, ge=0)
    act_submission_percent: int | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def validate_relationships(self) -> "IpedAdmissionsRecord":
        if self.applicant_count is not None and self.admitted_count is not None and self.admitted_count > self.applicant_count:
            raise ValueError("admitted_count cannot exceed applicant_count")
        if self.admitted_count is not None and self.enrolled_count is not None and self.enrolled_count > self.admitted_count:
            raise ValueError("enrolled_count cannot exceed admitted_count")
        for lower, upper, label in (
            (self.sat_ebrw_25, self.sat_ebrw_75, "SAT EBRW"),
            (self.sat_math_25, self.sat_math_75, "SAT Math"),
            (self.act_composite_25, self.act_composite_75, "ACT Composite"),
        ):
            if lower is not None and upper is not None and lower > upper:
                raise ValueError(f"{label} 25th percentile cannot exceed 75th percentile")
        return self


class OfficialSourceSeed(BaseModel):
    """Reviewable official-page seed; search is only recorded as URL discovery."""

    institution_ipeds_unitid: int = Field(gt=0)
    institution_name: str = Field(min_length=1)
    url: str = Field(min_length=8)
    source_type: Literal["international_undergraduate_english"]
    discovery_method: Literal["search_engine_official_domain", "official_site_navigation", "manual_official_seed"]
    discovered_from: str = Field(min_length=1)
    allowed_hosts: list[str] = Field(min_length=1)


IELTS_MINIMUM_RANGE = (Decimal("0.0"), Decimal("9.0"))
TOEFL_IBT_MINIMUM_RANGE = (Decimal("0"), Decimal("120"))
TOEFL_IBT_NEW_MINIMUM_RANGE = (Decimal("1"), Decimal("6"))
DET_MINIMUM_RANGE = (Decimal("10"), Decimal("160"))
SUPPORTED_ENGLISH_TESTS = {"ielts", "toefl_ibt", "duolingo_english_test"}


class EnglishRequirementCandidate(BaseModel):
    """Gemma candidate only; evidence validation controls verified persistence."""

    test_type: Literal["ielts", "toefl_ibt", "duolingo_english_test"]
    minimum_score: Decimal | None = None
    score_scale: Literal["ielts_band_0_9", "toefl_ibt_0_120", "toefl_ibt_1_6", "det_10_160"] | None = None
    valid_for_tests_before: date | None = None
    valid_for_tests_on_or_after: date | None = None
    subscore_requirements: dict[str, Decimal] = Field(default_factory=dict)
    waiver_text: str | None = None
    conditional_text: str | None = None
    status: Literal["found", "no_minimum_published", "not_found", "not_required"]
    evidence: str = ""

    @model_validator(mode="after")
    def validate_score_for_test(self) -> "EnglishRequirementCandidate":
        if self.status == "found" and self.minimum_score is None:
            raise ValueError("found English requirement must include a minimum_score")
        if self.status != "found" and self.minimum_score is not None:
            raise ValueError("non-score English status must not include a minimum_score")
        expected_scales = {
            "ielts": {"ielts_band_0_9"},
            "toefl_ibt": {"toefl_ibt_0_120", "toefl_ibt_1_6"},
            "duolingo_english_test": {"det_10_160"},
        }[self.test_type]
        if self.score_scale is not None and self.score_scale not in expected_scales:
            raise ValueError("score_scale does not match test_type")
        if self.test_type == "toefl_ibt" and self.status == "found" and self.score_scale is None:
            raise ValueError("TOEFL minimum requires an explicit score_scale")
        if self.valid_for_tests_before and self.valid_for_tests_on_or_after and self.valid_for_tests_before >= self.valid_for_tests_on_or_after:
            raise ValueError("TOEFL applicability dates must not overlap")
        if self.minimum_score is None:
            return self
        lower, upper = {
            "ielts_band_0_9": IELTS_MINIMUM_RANGE,
            "toefl_ibt_0_120": TOEFL_IBT_MINIMUM_RANGE,
            "toefl_ibt_1_6": TOEFL_IBT_NEW_MINIMUM_RANGE,
            "det_10_160": DET_MINIMUM_RANGE,
        }.get(self.score_scale or {"ielts": "ielts_band_0_9", "duolingo_english_test": "det_10_160"}.get(self.test_type, ""), (Decimal("0"), Decimal("0")))
        if not lower <= self.minimum_score <= upper:
            raise ValueError(f"{self.test_type} score is outside its supported source-scale range")
        if self.score_scale == "toefl_ibt_1_6" and self.minimum_score * 2 != (self.minimum_score * 2).to_integral_value():
            raise ValueError("TOEFL iBT 1-6 scores must use 0.5 increments")
        return self


class EnglishExtractionResponse(BaseModel):
    requirements: list[EnglishRequirementCandidate]

    @model_validator(mode="after")
    def require_complete_unique_test_states(self) -> "EnglishExtractionResponse":
        seen: set[tuple[object, ...]] = set()
        tests = {candidate.test_type for candidate in self.requirements}
        if tests != SUPPORTED_ENGLISH_TESTS:
            missing = ", ".join(sorted(SUPPORTED_ENGLISH_TESTS - tests))
            raise ValueError(f"every supported test needs an explicit extraction state; missing: {missing}")
        for candidate in self.requirements:
            key = (candidate.test_type, candidate.score_scale, candidate.valid_for_tests_before, candidate.valid_for_tests_on_or_after)
            if key in seen:
                raise ValueError("duplicate logical extraction candidate")
            seen.add(key)
        return self
