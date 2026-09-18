import json

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from pydantic import ValidationError
from typer.testing import CliRunner

from admission.applicants.schemas import ApplicantProfileInput, ApplicantTestScoreInput
from admission.assessment.academic import ReportedRange, position_attempts
from admission.applicants.services import import_profile
from admission.assessment.services import assess_candidates
from admission.catalog.models import AdmissionSnapshot, EnglishRequirement, Institution, ProgramOffering, SeedInstitution, SourceDocument
from admission.cli.app import app
from admission.recommendation.schemas import RecommendationSet
from admission.recommendation.services import MissingApplicantGoal, priority_key, recommend_assessment, recommend_for_profile


class RecommendationTests(TestCase):
    def setUp(self):
        self.source = SourceDocument.objects.create(
            url="https://example.edu/fixture", publisher="fixture", source_type="fixture", data_year="2024",
            retrieved_at="2026-01-01T00:00:00Z", content_hash="a" * 64,
        )
        self.institutions = []
        for order, state in enumerate(["MA", "CA", "TX", "FL", "NY"], 1):
            institution = Institution.objects.create(
                ipeds_unitid=900000+order, name=f"Fixture {order}", state=state, city="Fixture", country="US",
                ownership="private", operating_status="active", bachelors_granting=True,
                bachelors_granting_evidence="fixture", source=self.source, source_locator="fixture",
            )
            self.institutions.append(institution)
            SeedInstitution.objects.create(seed_order=order, name=institution.name, state=state,
                expected_ownership="private", status="resolved", institution=institution)
            if order == 4:
                continue
            ProgramOffering.objects.create(institution=institution, cip_code="11.0701", cip_title="Computer Science",
                credential_level="bachelors_degree", award_level=5, completion_count=10, status="reported",
                academic_year="2024", source=self.source, cip_title_source=self.source, source_locator="fixture", evidence="fixture")
            EnglishRequirement.objects.create(institution=institution, applicant_scope="international_undergraduate",
                test_type="ielts", score_scale="ielts_band_0_9", minimum_overall_score=8 if order == 3 else 6.5,
                status="verified", source=self.source, source_content_hash=self.source.content_hash, evidence="fixture")
            AdmissionSnapshot.objects.create(institution=institution, data_year="2024", term="fall",
                act_composite_25=31, act_composite_75=34, admissions_data_status="reported", sat_data_status="not_reported",
                act_data_status="reported", test_data_status="reported", source=self.source, dictionary_source=self.source,
                source_locator="fixture", evidence="Historical undergraduate context")
        self.profile = ApplicantProfileInput.model_validate({
            "profile_key": "student-001", "citizenship_country_code": "KZ",
            "academics": {"gpa_value": 4.7, "gpa_scale": 5},
            "study_intent": {"mode": "known_major", "intended_cip_codes": ["11.0701"]},
            "tests": [{"test_type": "ielts", "scale": "ielts_0_9", "score": 7},
                      {"test_type": "act", "scale": "act_composite_1_36", "score": 32}],
            "financial": {"annual_budget_usd": 0, "needs_financial_aid": True},
            "preferences": {"preferred_states": ["CA"], "excluded_states": ["NY"]},
        })
        import_profile(self.profile)

    def rows(self):
        return recommend_for_profile("student-001", 1, 5).recommendations

    def test_review_buckets_order_preference_limit_and_reasons(self):
        rows = self.rows()
        self.assertEqual([r.seed_order for r in rows], [2, 1, 3, 4, 5])
        self.assertEqual([r.recommendation_state for r in rows], [
            "recommended_for_review", "recommended_for_review", "consider_with_actions",
            "insufficient_evidence", "excluded_by_applicant",
        ])
        self.assertIn("preferred_state", rows[0].reason_codes)
        self.assertIn("retake_or_improve_english_test", rows[2].action_codes)
        self.assertIn("verify_current_english_policy", rows[3].action_codes)
        self.assertIn("excluded_state", rows[-1].reason_codes)
        self.assertEqual([r.seed_order for r in recommend_for_profile("student-001", 1, 5, 2).recommendations], [2, 1])
        self.assertEqual(recommend_for_profile("student-001", 1, 5).model_dump_json(), recommend_for_profile("student-001", 1, 5).model_dump_json())

    def test_missing_english_score_conflict_uncertainty_and_alternatives(self):
        institution = self.institutions[0]
        for status, expected, action in (
            ("conflicting", "consider_with_actions", "verify_current_english_policy"),
            ("not_found", "insufficient_evidence", "verify_current_english_policy"),
            ("unverified", "insufficient_evidence", "verify_current_english_policy"),
            ("not_required", "recommended_for_review", None),
            ("no_minimum_published", "recommended_for_review", None),
        ):
            with self.subTest(status=status):
                EnglishRequirement.objects.filter(institution=institution).update(status=status, minimum_overall_score=None)
                row = recommend_for_profile("student-001", 1, 1).recommendations[0]
                self.assertEqual(row.recommendation_state, expected)
                if action:
                    self.assertIn(action, row.action_codes)
                else:
                    self.assertNotIn("verify_current_english_policy", row.action_codes)
                    self.assertNotIn("submit_compatible_english_score", row.action_codes)
        EnglishRequirement.objects.filter(institution=institution).update(status="verified", minimum_overall_score=6.5)
        # IELTS met is a usable route, despite unavailable TOEFL and DET policy.
        self.assertNotIn("verify_current_english_policy", recommend_for_profile("student-001", 1, 1).recommendations[0].action_codes)
        self.profile.tests = self.profile.tests[1:]
        import_profile(self.profile)
        row = recommend_for_profile("student-001", 1, 1).recommendations[0]
        self.assertEqual(row.recommendation_state, "consider_with_actions")
        self.assertIn("submit_compatible_english_score", row.action_codes)

    def test_applicability_and_conditional_review_actions(self):
        for state in ("no_applicable_requirement", "applicability_ambiguous"):
            with self.subTest(state=state):
                assessment = assess_candidates("student-001", 1, 1).candidates[0]
                assessment.english.tests[0].state = state
                row = recommend_assessment(self.profile, assessment)
                self.assertEqual(row.recommendation_state, "consider_with_actions")
                self.assertIn("verify_current_english_policy", row.action_codes)
                self.assertNotIn("retake_or_improve_english_test", row.action_codes)
        EnglishRequirement.objects.filter(institution=self.institutions[0]).update(waiver_text="Conditional waiver policy")
        row = recommend_for_profile("student-001", 1, 1).recommendations[0]
        self.assertEqual(row.recommendation_state, "consider_with_actions")
        self.assertIn("english_conditional_policy_review_needed", row.reason_codes)

    def test_program_absence_and_explore_are_not_exclusions(self):
        ProgramOffering.objects.filter(institution=self.institutions[0]).update(cip_code="14.0901")
        row = recommend_for_profile("student-001", 1, 1).recommendations[0]
        self.assertEqual(row.signals.program, "partial")
        self.assertEqual(row.recommendation_state, "insufficient_evidence")
        self.assertIn("verify_program_availability", row.action_codes)
        self.assertFalse(row.assessment.applicant_constraints.excluded_by_applicant)
        self.profile.study_intent.mode = "explore"
        self.profile.study_intent.intended_cip_codes = []
        self.profile.study_intent.interests = ["robots"]
        import_profile(self.profile)
        row = recommend_for_profile("student-001", 1, 1).recommendations[0]
        self.assertEqual(row.recommendation_state, "recommended_for_review")
        self.assertEqual(row.signals.program, "not_applicable")
        self.assertNotIn("verify_program_availability", row.action_codes)

    def test_academic_order_below_never_blocks_and_seed_breaks_ties(self):
        self.profile.preferences.preferred_states = []
        import_profile(self.profile)
        EnglishRequirement.objects.filter(institution=self.institutions[2]).update(minimum_overall_score=6.5)
        AdmissionSnapshot.objects.filter(institution=self.institutions[0]).update(act_composite_25=33, act_composite_75=35)
        AdmissionSnapshot.objects.filter(institution=self.institutions[2]).update(act_composite_25=28, act_composite_75=30)
        rows = recommend_for_profile("student-001", 1, 3).recommendations
        self.assertEqual([r.seed_order for r in rows], [3, 2, 1])
        self.assertTrue(all(r.recommendation_state == "recommended_for_review" for r in rows))
        self.assertEqual(rows[-1].signals.academic, "below_reported_context")
        self.assertEqual(rows[-1].action_codes, ["research_financial_aid"])
        AdmissionSnapshot.objects.update(act_composite_25=31, act_composite_75=34)
        self.assertEqual([r.seed_order for r in recommend_for_profile("student-001", 1, 3).recommendations], [1, 2, 3])
        # Missing academic scores do not cause a service error or an English action.
        self.profile.tests = self.profile.tests[:1]
        import_profile(self.profile)
        row = recommend_for_profile("student-001", 1, 1).recommendations[0]
        self.assertEqual(row.recommendation_state, "recommended_for_review")
        self.assertIn("provide_missing_academic_test_if_desired", row.action_codes)

    def test_financial_is_context_only_and_no_penalty_or_cutoff(self):
        original = self.rows()
        self.assertTrue(all(row.signals.financial == "unavailable" for row in original))
        self.assertTrue(all("research_financial_aid" in row.action_codes for row in original))
        self.profile.financial.annual_budget_usd = 999999
        self.profile.financial.needs_financial_aid = False
        import_profile(self.profile)
        updated = self.rows()
        self.assertEqual([(r.seed_order, r.recommendation_state) for r in original], [(r.seed_order, r.recommendation_state) for r in updated])
        self.assertTrue(all("research_financial_aid" not in r.action_codes for r in updated))

    def test_strongest_submitted_context_is_one_signal_without_double_counting(self):
        assessment = assess_candidates("student-001", 1, 1).candidates[0]
        # Exercise the pure heuristic with explicit synthetic total context;
        # the production ADM adapter never derives SAT totals from sections.
        assessment.academic.sat = position_attempts([
            ApplicantTestScoreInput(test_type="sat", scale="sat_total_400_1600", score=1510),
        ], ReportedRange(scale="sat_total_400_1600", lower=1400, upper=1500))
        one_above = recommend_assessment(self.profile, assessment)
        self.assertEqual(one_above.signals.academic, "above_reported_context")
        assessment.academic.act = position_attempts([
            ApplicantTestScoreInput(test_type="act", scale="act_composite_1_36", score=35),
        ], ReportedRange(scale="act_composite_1_36", lower=31, upper=34))
        both_above = recommend_assessment(self.profile, assessment)
        self.assertEqual(priority_key(one_above), priority_key(both_above))
        self.assertEqual(both_above.reason_codes.count("academic_above_reported_context"), 1)
        self.assertEqual(len(both_above.assessment.academic.sat.attempts), 1)
        self.assertEqual(len(both_above.assessment.academic.act.attempts), 1)

    def test_missing_goal_errors_for_both_modes(self):
        for mode, code in (("known_major", "major_missing"), ("explore", "interests_missing")):
            self.profile.study_intent.mode = mode
            self.profile.study_intent.intended_cip_codes = []
            self.profile.study_intent.interests = []
            import_profile(self.profile)
            with self.assertRaisesRegex(MissingApplicantGoal, code):
                recommend_for_profile("student-001", 1, 5)
            cli = CliRunner().invoke(app, ["recommend", "universities", "student-001", "--seed-order-end", "5"])
            self.assertNotEqual(cli.exit_code, 0)
            self.assertIn(code, cli.output)

    def test_cli_json_errors_read_only_strict_and_forbidden_fields(self):
        runner = CliRunner()
        args = ["recommend", "universities", "student-001", "--seed-order-end", "5"]
        with CaptureQueriesContext(connection) as queries:
            first = runner.invoke(app, args)
        self.assertEqual(first.exit_code, 0, first.output)
        self.assertTrue(all(q["sql"].lstrip().upper().startswith("SELECT") for q in queries))
        self.assertEqual(first.output, runner.invoke(app, args).output)
        document = json.loads(first.output)
        self.assertEqual([row["seed_order"] for row in document["recommendations"]], [2, 1, 3, 4, 5])
        self.assertIsInstance(document["recommendations"][0]["assessment"]["academic"]["gpa"]["gpa_value"], (int, float))
        self.assertEqual(len(json.loads(runner.invoke(app, args + ["--limit", "2"]).output)["recommendations"]), 2)
        for arguments in (
            ["recommend", "universities", "unknown"], args + ["--limit", "0"],
            args + ["--limit", "-1"], args + ["--seed-order-start", "6"],
        ):
            self.assertNotEqual(runner.invoke(app, arguments).exit_code, 0)
        with self.assertRaises(ValidationError):
            RecommendationSet.model_validate({**document, "unexpected": True})
        forbidden = {"admission_probability", "acceptance_probability", "admission_chance", "chance_percent", "reach", "target", "safety"}
        def assert_no_forbidden(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden & value.keys())
                for child in value.values():
                    assert_no_forbidden(child)
            elif isinstance(value, list):
                for child in value:
                    assert_no_forbidden(child)
        assert_no_forbidden(document)
        assert_no_forbidden(RecommendationSet.model_json_schema())
