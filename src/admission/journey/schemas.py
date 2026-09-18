from typing import Literal

from pydantic import Field, model_validator

from admission.applicants.diagnostics import ApplicantDiagnostic
from admission.applicants.schemas import ApplicantContractModel
from admission.recommendation.schemas import RecommendationSet
from admission.roadmap.schemas import Roadmap


JourneyState = Literal["profile_preparation", "recommendations_ready"]


class JourneySummary(ApplicantContractModel):
    candidate_count: int = Field(ge=0)
    recommended_for_review_count: int = Field(ge=0)
    consider_with_actions_count: int = Field(ge=0)
    insufficient_evidence_count: int = Field(ge=0)
    excluded_by_applicant_count: int = Field(ge=0)
    roadmap_item_count: int = Field(ge=0)


class AdmissionJourney(ApplicantContractModel):
    profile_key: str
    journey_state: JourneyState
    diagnostic: ApplicantDiagnostic
    recommendations: RecommendationSet | None
    roadmap: Roadmap
    summary: JourneySummary

    @model_validator(mode="after")
    def validate_consistent_result(self) -> "AdmissionJourney":
        if self.diagnostic.profile_key != self.profile_key or self.roadmap.profile_key != self.profile_key:
            raise ValueError("journey components must use the same profile_key")
        state_total = (
            self.summary.recommended_for_review_count
            + self.summary.consider_with_actions_count
            + self.summary.insufficient_evidence_count
            + self.summary.excluded_by_applicant_count
        )
        if state_total != self.summary.candidate_count:
            raise ValueError("recommendation-state counts must sum to candidate_count")
        if self.summary.roadmap_item_count != len(self.roadmap.items):
            raise ValueError("roadmap_item_count must match the returned roadmap")
        if self.journey_state == "profile_preparation":
            if self.recommendations is not None or self.summary.candidate_count != 0:
                raise ValueError("profile preparation cannot contain recommendations")
            if self.roadmap.roadmap_state != "profile_preparation":
                raise ValueError("profile preparation requires a profile-preparation roadmap")
            if any(item.institution_unitids for item in self.roadmap.items):
                raise ValueError("profile preparation cannot contain institution actions")
            return self
        if self.recommendations is None:
            raise ValueError("recommendations_ready requires recommendations")
        if self.recommendations.profile_key != self.profile_key:
            raise ValueError("recommendations must use the journey profile_key")
        if (
            self.roadmap.seed_order_start != self.recommendations.seed_order_start
            or self.roadmap.seed_order_end != self.recommendations.seed_order_end
            or self.roadmap.recommendation_limit != self.recommendations.limit
        ):
            raise ValueError("roadmap scope must match recommendation scope")
        recommendation_unitids = {
            item.institution.ipeds_unitid for item in self.recommendations.recommendations
        }
        roadmap_unitids = {
            unitid for item in self.roadmap.items for unitid in item.institution_unitids
        }
        if not roadmap_unitids <= recommendation_unitids:
            raise ValueError("roadmap institutions must come from returned recommendations")
        if self.summary.candidate_count != len(self.recommendations.recommendations):
            raise ValueError("candidate_count must count returned recommendations")
        return self
