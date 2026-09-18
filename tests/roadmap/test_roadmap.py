import json
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from pydantic import ValidationError
from typer.testing import CliRunner

from admission.applicants.diagnostics import build_profile_diagnostic
from admission.applicants.schemas import ApplicantProfileInput, ApplicantTestScoreInput
from admission.applicants.services import import_profile
from admission.catalog.models import AdmissionSnapshot, EnglishRequirement, ProgramOffering
from admission.cli.app import app
from admission.recommendation.services import recommend_for_profile
from admission.roadmap.schemas import Roadmap
from admission.roadmap.services import build_roadmap, build_roadmap_for_profile
from tests.recommendation import test_recommendations as fixtures


class RoadmapTests(TestCase):
    setUp = fixtures.RecommendationTests.setUp

    def item(self, roadmap, action_code):
        return next(item for item in roadmap.items if item.action_code == action_code)

    def test_profile_preparation_maps_all_missing_information_without_recommendation(self):
        self.profile.study_intent.intended_cip_codes = []
        self.profile.graduation_year = None
        self.profile.academics.gpa_value = None
        self.profile.academics.gpa_scale = None
        self.profile.academics.class_rank = None
        self.profile.academics.class_size = None
        self.profile.tests = []
        self.profile.financial.annual_budget_usd = None
        import_profile(self.profile)
        with patch("admission.roadmap.services.recommend_for_profile") as recommend:
            roadmap = build_roadmap_for_profile("student-001", 1, 5)
        recommend.assert_not_called()
        self.assertEqual(roadmap.roadmap_state, "profile_preparation")
        self.assertEqual([(item.action_code, item.priority) for item in roadmap.items], [
            ("define_intended_major", "required"),
            ("provide_graduation_year", "medium"),
            ("provide_gpa", "medium"),
            ("provide_english_test_score", "medium"),
            ("provide_annual_budget", "medium"),
            ("provide_academic_test_if_desired", "optional"),
            ("provide_class_rank_if_available", "optional"),
        ])
        self.assertTrue(all(item.scope == "profile" and item.institution_unitids == [] for item in roadmap.items))
        self.assertEqual(self.item(roadmap, "provide_academic_test_if_desired").reason_codes,
                         ["academic_test_scores_missing"])

        self.profile.study_intent.mode = "explore"
        self.profile.study_intent.interests = []
        import_profile(self.profile)
        roadmap = build_roadmap_for_profile("student-001", 1, 5)
        self.assertEqual(roadmap.items[0].action_code, "provide_academic_interests")
        self.assertEqual(roadmap.items[0].priority, "required")

    def test_grouping_deduplicates_actions_reasons_and_excludes_applicant_exclusions(self):
        first = build_roadmap_for_profile("student-001", 1, 5)
        second = build_roadmap_for_profile("student-001", 1, 5)
        self.assertEqual(first.model_dump_json(), second.model_dump_json())
        self.assertEqual(len(first.items), len({item.action_code for item in first.items}))
        financial = self.item(first, "research_financial_aid")
        self.assertEqual(financial.institution_unitids, [900001, 900002, 900003, 900004])
        self.assertEqual(financial.reason_codes, ["financial_review_needed"])
        self.assertNotIn(900005, [unitid for item in first.items for unitid in item.institution_unitids])
        verify_program = self.item(first, "verify_program_availability")
        self.assertEqual(verify_program.institution_unitids, [900004])
        self.assertEqual(verify_program.reason_codes, ["program_evidence_unavailable"])
        self.assertEqual(first.roadmap_state, "university_actions")

    def test_english_actions_remain_separate_with_exact_priorities_and_reasons(self):
        roadmap = build_roadmap_for_profile("student-001", 1, 4)
        retake = self.item(roadmap, "retake_or_improve_english_test")
        self.assertEqual((retake.priority, retake.institution_unitids, retake.reason_codes),
                         ("high", [900003], ["english_minimum_not_met"]))
        verify = self.item(roadmap, "verify_current_english_policy")
        self.assertEqual((verify.priority, verify.institution_unitids), ("medium", [900003, 900004]))
        self.assertEqual(verify.reason_codes, ["english_policy_unavailable"])
        self.assertNotIn(900001, verify.institution_unitids)

        EnglishRequirement.objects.filter(institution=self.institutions[0]).update(
            waiver_text="Conditional policy requires review",
        )
        conditional = self.item(build_roadmap_for_profile("student-001", 1, 1),
                                "verify_current_english_policy")
        self.assertEqual(conditional.institution_unitids, [900001])
        self.assertEqual(conditional.reason_codes, ["english_conditional_policy_review_needed"])
        EnglishRequirement.objects.filter(institution=self.institutions[0]).update(waiver_text="")

        self.profile.tests = self.profile.tests[1:]
        import_profile(self.profile)
        missing_score = build_roadmap_for_profile("student-001", 1, 1)
        submit = self.item(missing_score, "submit_compatible_english_score")
        self.assertEqual((submit.priority, submit.reason_codes), ("high", ["english_score_missing"]))

        self.profile.tests = ApplicantProfileInput.model_validate({
            **self.profile.model_dump(),
            "tests": [{"test_type": "ielts", "scale": "ielts_0_9", "score": 7},
                      {"test_type": "act", "scale": "act_composite_1_36", "score": 32}],
        }).tests
        import_profile(self.profile)
        for status, reason in (
            ("conflicting", "english_policy_conflicting"),
            ("not_found", "english_policy_not_found"),
            ("unverified", "english_policy_unavailable"),
        ):
            with self.subTest(status=status):
                EnglishRequirement.objects.filter(institution=self.institutions[0]).update(
                    status=status, minimum_overall_score=None,
                )
                item = self.item(build_roadmap_for_profile("student-001", 1, 1),
                                 "verify_current_english_policy")
                self.assertIn(reason, item.reason_codes)

        recommendations = recommend_for_profile("student-001", 1, 1)
        row = recommendations.recommendations[0]
        row.action_codes = ["verify_current_english_policy"]
        row.reason_codes = ["english_applicability_unresolved", "english_applicability_unresolved"]
        diagnostic = build_profile_diagnostic(self.profile)
        item = self.item(build_roadmap(diagnostic, recommendations, 1, 1, None),
                         "verify_current_english_policy")
        self.assertEqual(item.reason_codes, ["english_applicability_unresolved"])

    def test_program_financial_and_academic_rules_are_conservative(self):
        ProgramOffering.objects.filter(institution=self.institutions[0]).update(cip_code="14.0901")
        roadmap = build_roadmap_for_profile("student-001", 1, 1)
        program = self.item(roadmap, "verify_program_availability")
        self.assertEqual((program.priority, program.reason_codes), ("medium", ["program_evidence_partial"]))

        self.profile.study_intent.mode = "explore"
        self.profile.study_intent.intended_cip_codes = []
        self.profile.study_intent.interests = ["robots"]
        import_profile(self.profile)
        explore = build_roadmap_for_profile("student-001", 1, 1)
        self.assertNotIn("verify_program_availability", [item.action_code for item in explore.items])

        self.profile.study_intent.mode = "known_major"
        self.profile.study_intent.intended_cip_codes = ["11.0701"]
        self.profile.study_intent.interests = []
        self.profile.financial.needs_financial_aid = False
        ProgramOffering.objects.filter(institution=self.institutions[0]).update(cip_code="11.0701")
        self.profile.tests = self.profile.tests[:1]
        import_profile(self.profile)
        optional = build_roadmap_for_profile("student-001", 1, 1)
        academic = self.item(optional, "provide_missing_academic_test_if_desired")
        self.assertEqual((academic.priority, academic.category), ("optional", "academics"))

        self.profile.tests.append(ApplicantTestScoreInput(
            test_type="act", scale="act_composite_1_36", score=30,
        ))
        import_profile(self.profile)
        AdmissionSnapshot.objects.filter(institution=self.institutions[0]).update(
            act_composite_25=31, act_composite_75=34,
        )
        below = build_roadmap_for_profile("student-001", 1, 1)
        self.assertNotIn("provide_missing_academic_test_if_desired", [item.action_code for item in below.items])
        self.assertNotIn("retake_or_improve_academic_test", [item.action_code for item in below.items])
        self.assertEqual(below.roadmap_state, "no_blocking_actions")

    def test_limit_applies_before_grouping_and_cli_is_read_only_and_explicit(self):
        limited = build_roadmap_for_profile("student-001", 1, 5, 2)
        self.assertEqual(self.item(limited, "research_financial_aid").institution_unitids, [900001, 900002])
        runner = CliRunner()
        args = ["roadmap", "build", "student-001", "--seed-order-end", "5"]
        with CaptureQueriesContext(connection) as queries:
            first = runner.invoke(app, args)
        self.assertEqual(first.exit_code, 0, first.output)
        self.assertTrue(all(query["sql"].lstrip().upper().startswith("SELECT") for query in queries))
        self.assertEqual(first.output, runner.invoke(app, args).output)
        document = json.loads(first.output)
        self.assertIsInstance(document["items"][0]["institution_unitids"][0], int)
        limited_cli = json.loads(runner.invoke(app, args + ["--recommendation-limit", "2"]).output)
        self.assertEqual(limited_cli["recommendation_limit"], 2)
        for arguments in (
            ["roadmap", "build", "unknown"],
            args + ["--seed-order-start", "6"],
            args + ["--recommendation-limit", "0"],
            args + ["--recommendation-limit", "-1"],
        ):
            self.assertNotEqual(runner.invoke(app, arguments).exit_code, 0)

    def test_profile_preparation_cli_success_strict_schema_and_forbidden_content(self):
        self.profile.study_intent.intended_cip_codes = []
        import_profile(self.profile)
        result = CliRunner().invoke(app, ["roadmap", "build", "student-001", "--seed-order-end", "5"])
        self.assertEqual(result.exit_code, 0, result.output)
        document = json.loads(result.output)
        self.assertEqual(document["roadmap_state"], "profile_preparation")
        with self.assertRaises(ValidationError):
            Roadmap.model_validate({**document, "unexpected": True})
        forbidden = {
            "admission_probability", "acceptance_probability", "chance_percent", "reach", "target", "safety",
            "due_date", "deadline", "days_remaining", "scholarship_amount", "cost_estimate",
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
        assert_clean(Roadmap.model_json_schema())
