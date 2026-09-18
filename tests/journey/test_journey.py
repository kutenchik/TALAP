import json
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from pydantic import ValidationError
from typer.testing import CliRunner

from admission.applicants.services import import_profile
from admission.cli.app import app
from admission.journey.schemas import AdmissionJourney
from admission.journey.services import build_admission_journey
from admission.recommendation.services import recommend_for_profile
from admission.journey import services as journey_services
from tests.recommendation import test_recommendations as fixtures


class AdmissionJourneyTests(TestCase):
    setUp = fixtures.RecommendationTests.setUp

    def test_required_goal_gaps_return_profile_preparation_without_candidates(self):
        for mode, expected_action in (
            ("known_major", "define_intended_major"),
            ("explore", "provide_academic_interests"),
        ):
            with self.subTest(mode=mode):
                self.profile.study_intent.mode = mode
                self.profile.study_intent.intended_cip_codes = []
                self.profile.study_intent.interests = []
                import_profile(self.profile)
                with (
                    patch("admission.journey.services.recommend_for_profile") as recommendation,
                    patch("admission.assessment.services.assess_candidates_for_profile") as assessment,
                ):
                    result = build_admission_journey("student-001", 1, 5)
                recommendation.assert_not_called()
                assessment.assert_not_called()
                self.assertEqual(result.journey_state, "profile_preparation")
                self.assertIsNone(result.recommendations)
                self.assertEqual(result.summary.candidate_count, 0)
                self.assertEqual(result.roadmap.roadmap_state, "profile_preparation")
                self.assertIn(expected_action, [item.action_code for item in result.roadmap.items])
                self.assertTrue(all(not item.institution_unitids for item in result.roadmap.items))

    def test_full_flow_summary_all_states_exclusions_and_determinism(self):
        first = build_admission_journey("student-001", 1, 5)
        second = build_admission_journey("student-001", 1, 5)
        self.assertEqual(first.journey_state, "recommendations_ready")
        self.assertEqual(first.diagnostic.profile_key, "student-001")
        self.assertIsNotNone(first.recommendations)
        self.assertEqual(first.model_dump_json(), second.model_dump_json())
        self.assertEqual(first.summary.model_dump(), {
            "candidate_count": 5,
            "recommended_for_review_count": 2,
            "consider_with_actions_count": 1,
            "insufficient_evidence_count": 1,
            "excluded_by_applicant_count": 1,
            "roadmap_item_count": len(first.roadmap.items),
        })
        state_total = sum((
            first.summary.recommended_for_review_count,
            first.summary.consider_with_actions_count,
            first.summary.insufficient_evidence_count,
            first.summary.excluded_by_applicant_count,
        ))
        self.assertEqual(state_total, first.summary.candidate_count)
        excluded = next(
            item for item in first.recommendations.recommendations
            if item.recommendation_state == "excluded_by_applicant"
        )
        roadmap_unitids = {
            unitid for item in first.roadmap.items for unitid in item.institution_unitids
        }
        self.assertNotIn(excluded.institution.ipeds_unitid, roadmap_unitids)

    def test_recommendation_executes_once_and_same_object_builds_roadmap(self):
        original_recommend = journey_services.recommend_for_profile
        original_build_roadmap = journey_services.build_roadmap
        generated = []
        roadmap_inputs = []

        def recommend_once(*args, **kwargs):
            result = original_recommend(*args, **kwargs)
            generated.append(result)
            return result

        def capture_roadmap(diagnostic, recommendations, *args, **kwargs):
            roadmap_inputs.append(recommendations)
            return original_build_roadmap(diagnostic, recommendations, *args, **kwargs)

        with (
            patch.object(journey_services, "recommend_for_profile", side_effect=recommend_once) as recommendation,
            patch.object(journey_services, "build_roadmap", side_effect=capture_roadmap) as roadmap,
        ):
            result = journey_services.build_admission_journey("student-001", 1, 5)
        recommendation.assert_called_once_with("student-001", 1, 5, None)
        roadmap.assert_called_once()
        self.assertIs(roadmap_inputs[0], generated[0])
        self.assertIs(result.recommendations, generated[0])

    def test_limit_uses_exact_returned_recommendations_and_bounds_roadmap(self):
        journey = build_admission_journey("student-001", 1, 5, 2)
        direct = recommend_for_profile("student-001", 1, 5, 2)
        self.assertEqual(journey.recommendations.model_dump(), direct.model_dump())
        self.assertEqual(len(journey.recommendations.recommendations), 2)
        self.assertEqual(journey.summary.candidate_count, 2)
        returned_unitids = {
            item.institution.ipeds_unitid for item in journey.recommendations.recommendations
        }
        roadmap_unitids = {
            unitid for item in journey.roadmap.items for unitid in item.institution_unitids
        }
        self.assertTrue(roadmap_unitids <= returned_unitids)
        self.assertEqual(journey.roadmap.seed_order_start, 1)
        self.assertEqual(journey.roadmap.seed_order_end, 5)
        self.assertEqual(journey.roadmap.recommendation_limit, 2)

    def test_cli_numeric_types_read_only_errors_and_profile_preparation_success(self):
        runner = CliRunner()
        arguments = ["journey", "run", "student-001", "--seed-order-end", "5"]
        with CaptureQueriesContext(connection) as queries:
            result = runner.invoke(app, arguments)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue(all(query["sql"].lstrip().upper().startswith("SELECT") for query in queries))
        document = json.loads(result.output)
        recommendation = document["recommendations"]["recommendations"][0]
        numeric_values = (
            document["diagnostic"]["academics"]["gpa"]["gpa_value"],
            document["diagnostic"]["testing"]["attempts"][0]["score"],
            document["diagnostic"]["english"]["attempts"][0]["score"],
            document["diagnostic"]["financial"]["annual_budget_usd"],
            recommendation["assessment"]["english"]["tests"][0]["requirements"][0]["minimum_score"],
            recommendation["assessment"]["academic"]["act"]["context"]["lower"],
        )
        self.assertTrue(all(isinstance(value, (int, float)) and not isinstance(value, str) for value in numeric_values))
        self.assertEqual(result.output, runner.invoke(app, arguments).output)

        self.profile.study_intent.intended_cip_codes = []
        import_profile(self.profile)
        preparation = runner.invoke(app, arguments)
        self.assertEqual(preparation.exit_code, 0, preparation.output)
        self.assertEqual(json.loads(preparation.output)["journey_state"], "profile_preparation")

        for invalid in (
            ["journey", "run", "unknown", "--seed-order-end", "5"],
            arguments + ["--seed-order-start", "6"],
            arguments + ["--recommendation-limit", "0"],
            arguments + ["--recommendation-limit", "-1"],
        ):
            self.assertNotEqual(runner.invoke(app, invalid).exit_code, 0)
        with self.assertRaisesRegex(ValueError, "positive integer"):
            build_admission_journey("student-001", 1, 5, True)

    def test_existing_cli_commands_remain_compatible(self):
        runner = CliRunner()
        commands = (
            ["profile", "diagnose", "student-001"],
            ["assess", "candidates", "student-001", "--seed-order-end", "5"],
            ["recommend", "universities", "student-001", "--seed-order-end", "5"],
            ["roadmap", "build", "student-001", "--seed-order-end", "5"],
        )
        for command in commands:
            with self.subTest(command=command):
                result = runner.invoke(app, command)
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertIsInstance(json.loads(result.output), dict)

    def test_strict_contract_and_forbidden_output(self):
        result = build_admission_journey("student-001", 1, 5)
        document = result.model_dump(mode="json")
        with self.assertRaises(ValidationError):
            AdmissionJourney.model_validate({**document, "unexpected": True})
        forbidden = {
            "admission_probability", "acceptance_probability", "chance_percent", "likely_admitted",
            "reach", "target", "safety", "scholarship_amount", "invented_cost", "invented_deadline",
        }

        def assert_clean(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden & value.keys())
                for child in value.values():
                    assert_clean(child)
            elif isinstance(value, list):
                for child in value:
                    assert_clean(child)

        assert_clean(document)
        assert_clean(AdmissionJourney.model_json_schema())
