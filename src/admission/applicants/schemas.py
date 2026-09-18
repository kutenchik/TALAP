import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator, model_validator


COUNTRY_CODE_PATTERN = re.compile(r"[A-Z]{2}")
STATE_CODE_PATTERN = re.compile(r"[A-Z]{2}")
TEST_SCALES = {
    "sat": ("sat_total_400_1600", Decimal("400"), Decimal("1600")),
    "act": ("act_composite_1_36", Decimal("1"), Decimal("36")),
    "ielts": ("ielts_0_9", Decimal("0"), Decimal("9")),
    "toefl": None,
    "duolingo": ("det_10_160", Decimal("10"), Decimal("160")),
}
TOEFL_SCALES = {
    "toefl_ibt_0_120": (Decimal("0"), Decimal("120")),
    "toefl_ibt_1_6": (Decimal("1"), Decimal("6")),
}
JsonDecimal = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class ApplicantContractModel(BaseModel):
    """Strict external contract that keeps Decimal values numeric in JSON."""

    model_config = ConfigDict(extra="forbid")


def _normalise_ordered(values: list[str], *, uppercase: bool = False) -> list[str]:
    normalised: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = value.strip()
        if uppercase:
            clean = clean.upper()
        if clean and clean not in seen:
            normalised.append(clean)
            seen.add(clean)
    return normalised


class AcademicsInput(ApplicantContractModel):
    gpa_value: JsonDecimal | None = None
    gpa_scale: JsonDecimal | None = None
    gpa_weighting: Literal["weighted", "unweighted", "unknown"] = "unknown"
    class_rank: int | None = None
    class_size: int | None = None

    @model_validator(mode="after")
    def validate_academics(self) -> "AcademicsInput":
        if (self.gpa_value is None) != (self.gpa_scale is None):
            raise ValueError("gpa_value and gpa_scale must be supplied together")
        if self.gpa_value is not None and (self.gpa_value <= 0 or self.gpa_scale is None or self.gpa_scale <= 0):
            raise ValueError("GPA value and scale must be positive")
        if self.gpa_value is not None and self.gpa_value > self.gpa_scale:
            raise ValueError("gpa_value cannot exceed gpa_scale")
        if (self.class_rank is None) != (self.class_size is None):
            raise ValueError("class_rank and class_size must be supplied together")
        if self.class_rank is not None and (self.class_rank <= 0 or self.class_size is None or self.class_size <= 0):
            raise ValueError("class rank and size must be positive")
        if self.class_rank is not None and self.class_rank > self.class_size:
            raise ValueError("class_rank cannot exceed class_size")
        return self


class ApplicantTestScoreInput(ApplicantContractModel):
    test_type: Literal["sat", "act", "ielts", "toefl", "duolingo"]
    scale: Literal["sat_total_400_1600", "act_composite_1_36", "ielts_0_9", "toefl_ibt_0_120", "toefl_ibt_1_6", "det_10_160"]
    score: JsonDecimal
    taken_on: date | None = None
    note: str | None = None

    @field_validator("note")
    @classmethod
    def trim_note(cls, value: str | None) -> str | None:
        return value.strip() if value else None

    @model_validator(mode="after")
    def validate_score_scale(self) -> "ApplicantTestScoreInput":
        if self.test_type == "toefl":
            bounds = TOEFL_SCALES.get(self.scale)
            if bounds is None:
                raise ValueError("TOEFL requires a TOEFL score scale")
        else:
            expected_scale, lower, upper = TEST_SCALES[self.test_type]  # type: ignore[misc]
            if self.scale != expected_scale:
                raise ValueError("test_type and scale are incompatible")
            bounds = (lower, upper)
        if not bounds[0] <= self.score <= bounds[1]:
            raise ValueError("score is outside the declared scale range")
        return self


class StudyIntentInput(ApplicantContractModel):
    mode: Literal["known_major", "explore"]
    intended_cip_codes: list[str] = Field(default_factory=list)
    interests: list[str] = Field(default_factory=list)

    @field_validator("intended_cip_codes", "interests")
    @classmethod
    def normalise_entries(cls, values: list[str]) -> list[str]:
        return _normalise_ordered(values)


class FinancialInput(ApplicantContractModel):
    annual_budget_usd: JsonDecimal | None = Field(default=None, ge=0)
    needs_financial_aid: bool | None = None


class PreferencesInput(ApplicantContractModel):
    preferred_states: list[str] = Field(default_factory=list)
    excluded_states: list[str] = Field(default_factory=list)

    @field_validator("preferred_states", "excluded_states")
    @classmethod
    def normalise_states(cls, values: list[str]) -> list[str]:
        normalised = _normalise_ordered(values, uppercase=True)
        if any(STATE_CODE_PATTERN.fullmatch(value) is None for value in normalised):
            raise ValueError("state codes must use two uppercase letters")
        return normalised

    @model_validator(mode="after")
    def reject_overlapping_states(self) -> "PreferencesInput":
        if set(self.preferred_states) & set(self.excluded_states):
            raise ValueError("a state cannot be both preferred and excluded")
        return self


class ApplicantProfileInput(ApplicantContractModel):

    profile_key: str = Field(min_length=1, max_length=120)
    display_name: str | None = None
    citizenship_country_code: str
    residence_country_code: str | None = None
    school_country_code: str | None = None
    graduation_year: int | None = Field(default=None, gt=0)
    academics: AcademicsInput = Field(default_factory=AcademicsInput)
    tests: list[ApplicantTestScoreInput] = Field(default_factory=list)
    study_intent: StudyIntentInput
    financial: FinancialInput = Field(default_factory=FinancialInput)
    preferences: PreferencesInput = Field(default_factory=PreferencesInput)

    @field_validator("profile_key")
    @classmethod
    def trim_profile_key(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("profile_key cannot be blank")
        return clean

    @field_validator("display_name")
    @classmethod
    def trim_display_name(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None

    @field_validator("citizenship_country_code", "residence_country_code", "school_country_code")
    @classmethod
    def normalise_country_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = value.strip().upper()
        if COUNTRY_CODE_PATTERN.fullmatch(clean) is None:
            raise ValueError("country codes must use two letters")
        return clean
