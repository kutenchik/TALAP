import json
from decimal import Decimal
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from typer.testing import CliRunner

from admission.applicants.diagnostics import build_profile_diagnostic, diagnose_profile
from admission.applicants.models import ApplicantProfile, ApplicantTestScore
from admission.applicants.schemas import ApplicantProfileInput
from admission.applicants.services import import_profile, load_profile
from admission.cli.app import app


def profile_payload(**overrides: object) -> ApplicantProfileInput:
    data = {
        "profile_key": "student-001",
        "display_name": "Diagnostic Student",
        "citizenship_country_code": "KZ",
        "residence_country_code": "KZ",
        "school_country_code": "KZ",
        "graduation_year": 2027,
        "academics": {"gpa_value": 4.7, "gpa_scale": 5.0, "gpa_weighting": "unknown", "class_rank": 4, "class_size": 80},
        "tests": [
            {"test_type": "sat", "scale": "sat_total_400_1600", "score": 1400, "taken_on": "2026-03-01"},
            {"test_type": "ielts", "scale": "ielts_0_9", "score": 6.5, "taken_on": "2026-04-01"},
        ],
        "study_intent": {"mode": "known_major", "intended_cip_codes": ["11.0701"], "interests": []},
        "financial": {"annual_budget_usd": 25000, "needs_financial_aid": True},
        "preferences": {"preferred_states": ["CA"], "excluded_states": ["NY"]},
    }
    data.update(overrides)
    return ApplicantProfileInput.model_validate(data)


class PureApplicantDiagnosticTests(SimpleTestCase):
    def test_known_major_and_explore_goal_states_and_required_missing_items(self) -> None:
        known = build_profile_diagnostic(profile_payload())
        self.assertTrue(known.goal.goal_supplied)
        self.assertEqual(known.goal.intended_cip_codes, ["11.0701"])

        known_missing = build_profile_diagnostic(profile_payload(
            study_intent={"mode": "known_major", "intended_cip_codes": [], "interests": []},
        ))
        self.assertFalse(known_missing.goal.goal_supplied)
        self.assertIn(("major_missing", "required_for_next_step"), [
            (item.code, item.importance) for item in known_missing.missing_information
        ])

        explore = build_profile_diagnostic(profile_payload(
            study_intent={"mode": "explore", "intended_cip_codes": [], "interests": ["robotics", "design"]},
        ))
        self.assertTrue(explore.goal.goal_supplied)
        self.assertEqual(explore.goal.interests, ["robotics", "design"])

        explore_missing = build_profile_diagnostic(profile_payload(
            study_intent={"mode": "explore", "intended_cip_codes": [], "interests": []},
        ))
        self.assertIn(("interests_missing", "required_for_next_step"), [
            (item.code, item.importance) for item in explore_missing.missing_information
        ])

    def test_academics_are_raw_and_missing_states_are_factual(self) -> None:
        diagnostic = build_profile_diagnostic(profile_payload())
        self.assertEqual(diagnostic.academics.gpa.state, "provided")
        self.assertEqual(diagnostic.academics.gpa.gpa_value, Decimal("4.7"))
        self.assertEqual(diagnostic.academics.gpa.gpa_scale, Decimal("5.0"))
        self.assertEqual((diagnostic.academics.class_rank.class_rank, diagnostic.academics.class_rank.class_size), (4, 80))

        missing = build_profile_diagnostic(profile_payload(academics={}))
        self.assertEqual(missing.academics.gpa.state, "missing")
        self.assertEqual(missing.academics.class_rank.state, "missing")
        codes = {item.code: item.importance for item in missing.missing_information}
        self.assertEqual(codes["gpa_missing"], "useful")
        self.assertEqual(codes["class_rank_missing"], "optional")

    def test_attempts_remain_ordered_separated_and_unconverted(self) -> None:
        tests = [
            {"test_type": "act", "scale": "act_composite_1_36", "score": 30},
            {"test_type": "toefl", "scale": "toefl_ibt_0_120", "score": 100},
            {"test_type": "sat", "scale": "sat_total_400_1600", "score": 1450},
            {"test_type": "toefl", "scale": "toefl_ibt_1_6", "score": 5.0},
            {"test_type": "ielts", "scale": "ielts_0_9", "score": 7.0},
        ]
        diagnostic = build_profile_diagnostic(profile_payload(tests=tests))
        self.assertEqual([attempt.test_type for attempt in diagnostic.testing.attempts], ["act", "sat"])
        self.assertEqual([attempt.scale for attempt in diagnostic.english.attempts], ["toefl_ibt_0_120", "toefl_ibt_1_6", "ielts_0_9"])
        self.assertEqual([attempt.score for attempt in diagnostic.english.attempts[:2]], [Decimal("100"), Decimal("5.0")])
        self.assertNotIn("best", diagnostic.model_dump_json())

    def test_budget_preferences_and_explicit_constraints_preserve_semantics(self) -> None:
        diagnostic = build_profile_diagnostic(profile_payload(
            financial={"annual_budget_usd": 0, "needs_financial_aid": True},
            preferences={"preferred_states": ["CA", "MA"], "excluded_states": ["NY", "TX"]},
        ))
        self.assertEqual(diagnostic.financial.budget_state, "budget_provided")
        self.assertEqual(diagnostic.financial.annual_budget_usd, Decimal("0"))
        self.assertEqual([item.value for item in diagnostic.explicit_constraints], ["NY", "TX"])
        self.assertTrue(all(item.hard and item.constraint_type == "excluded_state" for item in diagnostic.explicit_constraints))
        self.assertNotIn("CA", [item.value for item in diagnostic.explicit_constraints])
        self.assertFalse(any(item.constraint_type == "annual_budget_usd" for item in diagnostic.explicit_constraints))

        missing = build_profile_diagnostic(profile_payload(financial={"annual_budget_usd": None, "needs_financial_aid": None}))
        self.assertEqual(missing.financial.budget_state, "budget_missing")
        self.assertIn(("annual_budget_missing", "useful"), [(item.code, item.importance) for item in missing.missing_information])

    def test_missing_codes_and_serialization_are_deterministic_and_unique(self) -> None:
        payload = profile_payload(
            graduation_year=None,
            academics={},
            tests=[],
            study_intent={"mode": "known_major", "intended_cip_codes": [], "interests": []},
            financial={"annual_budget_usd": None, "needs_financial_aid": None},
        )
        first = build_profile_diagnostic(payload)
        second = build_profile_diagnostic(payload)
        codes = [item.code for item in first.missing_information]
        self.assertEqual(codes, [
            "major_missing", "graduation_year_missing", "gpa_missing", "class_rank_missing",
            "academic_test_scores_missing", "english_test_scores_missing", "annual_budget_missing",
        ])
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(first.model_dump_json(), second.model_dump_json())


class StoredApplicantDiagnosticTests(TestCase):
    def test_service_and_cli_are_deterministic_numeric_read_only_and_unknown_is_explicit(self) -> None:
        import_profile(profile_payload())
        profile_count = ApplicantProfile.objects.count()
        score_count = ApplicantTestScore.objects.count()
        first = diagnose_profile("student-001").model_dump_json()
        second = diagnose_profile("student-001").model_dump_json()
        self.assertEqual(first, second)

        runner = CliRunner()
        result = runner.invoke(app, ["profile", "diagnose", "student-001"])
        self.assertEqual(result.exit_code, 0)
        document = json.loads(result.output)
        for value in (
            document["academics"]["gpa"]["gpa_value"],
            document["academics"]["gpa"]["gpa_scale"],
            document["testing"]["attempts"][0]["score"],
            document["english"]["attempts"][0]["score"],
            document["financial"]["annual_budget_usd"],
        ):
            self.assertIsInstance(value, (int, float))
            self.assertNotIsInstance(value, str)
        self.assertEqual(ApplicantProfile.objects.count(), profile_count)
        self.assertEqual(ApplicantTestScore.objects.count(), score_count)

        unknown = runner.invoke(app, ["profile", "diagnose", "missing-profile"])
        self.assertNotEqual(unknown.exit_code, 0)
        self.assertIn("unknown profile_key", unknown.output)

    def test_fictional_example_imports_and_diagnoses(self) -> None:
        example = Path(__file__).resolve().parents[2] / "data" / "examples" / "applicant_profile.example.json"
        payload = load_profile(example)
        import_profile(payload)
        diagnostic = diagnose_profile(payload.profile_key)
        self.assertTrue(diagnostic.goal.goal_supplied)
        self.assertEqual(diagnostic.academics.gpa.state, "provided")
        self.assertEqual(diagnostic.testing.state, "scores_provided")
        self.assertEqual(diagnostic.english.state, "scores_provided")
        self.assertEqual(diagnostic.financial.budget_state, "budget_provided")
