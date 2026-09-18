import json
import tempfile
from decimal import Decimal
from pathlib import Path

from django.test import TestCase
from pydantic import ValidationError
from typer.testing import CliRunner

from admission.applicants.models import ApplicantProfile, ApplicantTestScore
from admission.applicants.schemas import ApplicantProfileInput
from admission.applicants.services import export_profile, import_profile, load_profile
from admission.cli.app import app


class ApplicantProfileTests(TestCase):
    def profile_data(self) -> dict:
        return {
            "profile_key": " student-001 ",
            "display_name": " Demo Student ",
            "citizenship_country_code": " kz ",
            "residence_country_code": " kz ",
            "school_country_code": " kz ",
            "graduation_year": 2027,
            "academics": {"gpa_value": 4.7, "gpa_scale": 5.0, "gpa_weighting": "unknown", "class_rank": 3, "class_size": 100},
            "tests": [
                {"test_type": "ielts", "scale": "ielts_0_9", "score": 6.5},
                {"test_type": "sat", "scale": "sat_total_400_1600", "score": 1420},
            ],
            "study_intent": {"mode": "known_major", "intended_cip_codes": [" 11.0701 ", "11.0701"], "interests": []},
            "financial": {"annual_budget_usd": 25000, "needs_financial_aid": True},
            "preferences": {"preferred_states": [" ca ", "MA", "CA"], "excluded_states": ["ny"]},
        }

    def payload(self, **updates: object) -> ApplicantProfileInput:
        data = self.profile_data()
        data.update(updates)
        return ApplicantProfileInput.model_validate(data)

    def test_valid_create_update_and_identical_reimport_are_idempotent(self) -> None:
        payload = self.payload()
        import_profile(payload)
        first_export = export_profile("student-001").model_dump(mode="json")
        self.assertEqual(ApplicantProfile.objects.count(), 1)
        self.assertEqual(ApplicantTestScore.objects.count(), 2)
        self.assertEqual(first_export["citizenship_country_code"], "KZ")
        self.assertEqual(first_export["preferences"]["preferred_states"], ["CA", "MA"])
        self.assertEqual(first_export["study_intent"]["intended_cip_codes"], ["11.0701"])

        import_profile(payload)
        self.assertEqual(ApplicantProfile.objects.count(), 1)
        self.assertEqual(ApplicantTestScore.objects.count(), 2)
        self.assertEqual(export_profile("student-001").model_dump(mode="json"), first_export)

        updated = self.profile_data()
        updated["display_name"] = "Updated Student"
        updated["tests"] = [{"test_type": "act", "scale": "act_composite_1_36", "score": 31}]
        import_profile(ApplicantProfileInput.model_validate(updated))
        self.assertEqual(ApplicantProfile.objects.get().display_name, "Updated Student")
        self.assertEqual(list(ApplicantTestScore.objects.values_list("test_type", flat=True)), ["act"])

    def test_invalid_profile_creates_no_partial_database_state(self) -> None:
        data = self.profile_data()
        data["academics"] = {"gpa_value": 4.7, "gpa_scale": None}
        with self.assertRaises(ValidationError):
            ApplicantProfileInput.model_validate(data)
        self.assertEqual(ApplicantProfile.objects.count(), 0)
        self.assertEqual(ApplicantTestScore.objects.count(), 0)

    def test_gpa_and_class_rank_validation(self) -> None:
        self.assertIsInstance(self.payload().academics.gpa_value, Decimal)
        for academics in (
            {"gpa_value": 5.1, "gpa_scale": 5.0},
            {"gpa_value": 4.0, "gpa_scale": None},
            {"gpa_value": None, "gpa_scale": 5.0},
            {"class_rank": 101, "class_size": 100},
            {"class_rank": 1, "class_size": None},
        ):
            data = self.profile_data()
            data["academics"] = academics
            with self.subTest(academics=academics), self.assertRaises(ValidationError):
                ApplicantProfileInput.model_validate(data)

    def test_decimal_fields_remain_internal_decimals_but_serialize_as_json_numbers(self) -> None:
        payload = self.payload()
        self.assertIsInstance(payload.academics.gpa_value, Decimal)
        self.assertIsInstance(payload.academics.gpa_scale, Decimal)
        self.assertIsInstance(payload.tests[0].score, Decimal)
        self.assertIsInstance(payload.financial.annual_budget_usd, Decimal)

        document = json.loads(payload.model_dump_json())
        for value in (
            document["academics"]["gpa_value"],
            document["academics"]["gpa_scale"],
            document["tests"][0]["score"],
            document["financial"]["annual_budget_usd"],
        ):
            self.assertIsInstance(value, (int, float))
            self.assertNotIsInstance(value, str)
        self.assertEqual(ApplicantProfileInput.model_validate(document), payload)

    def test_unknown_nested_contract_fields_fail_before_persistence(self) -> None:
        invalid_fields = (
            ("academics", {"gpa_value": 4.7, "gpa_scale": 5.0, "gpa_valeu": 4.8}),
            ("tests", [{"test_type": "ielts", "scale": "ielts_0_9", "score": 6.5, "socre": 7.0}]),
            ("study_intent", {"mode": "known_major", "intended_cip_codes": [], "unknown_field": True}),
            ("financial", {"annual_budget_usd": 25000, "annual_budegt_usd": 30000}),
            ("preferences", {"preferred_states": [], "excluded_states": [], "prefered_states": ["CA"]}),
        )
        for field_name, value in invalid_fields:
            data = self.profile_data()
            data[field_name] = value
            with self.subTest(field_name=field_name), self.assertRaises(ValidationError):
                ApplicantProfileInput.model_validate(data)
        self.assertEqual(ApplicantProfile.objects.count(), 0)

    def test_all_supported_score_scales_and_attempts_are_preserved(self) -> None:
        data = self.profile_data()
        data["tests"] = [
            {"test_type": "sat", "scale": "sat_total_400_1600", "score": 1600},
            {"test_type": "act", "scale": "act_composite_1_36", "score": 36},
            {"test_type": "ielts", "scale": "ielts_0_9", "score": 6.5},
            {"test_type": "toefl", "scale": "toefl_ibt_0_120", "score": 100},
            {"test_type": "toefl", "scale": "toefl_ibt_1_6", "score": 5.0},
            {"test_type": "duolingo", "scale": "det_10_160", "score": 120},
        ]
        import_profile(ApplicantProfileInput.model_validate(data))
        exported = export_profile("student-001")
        self.assertEqual([test.scale for test in exported.tests], [
            "sat_total_400_1600", "act_composite_1_36", "ielts_0_9", "toefl_ibt_0_120", "toefl_ibt_1_6", "det_10_160",
        ])
        self.assertEqual(ApplicantTestScore.objects.filter(test_type="toefl").count(), 2)

    def test_invalid_score_bounds_and_incompatible_scales_are_rejected(self) -> None:
        for test in (
            {"test_type": "sat", "scale": "sat_total_400_1600", "score": 399},
            {"test_type": "act", "scale": "act_composite_1_36", "score": 37},
            {"test_type": "ielts", "scale": "ielts_0_9", "score": 9.1},
            {"test_type": "toefl", "scale": "toefl_ibt_1_6", "score": 6.1},
            {"test_type": "duolingo", "scale": "det_10_160", "score": 9},
            {"test_type": "sat", "scale": "ielts_0_9", "score": 6.5},
        ):
            data = self.profile_data()
            data["tests"] = [test]
            with self.subTest(test=test), self.assertRaises(ValidationError):
                ApplicantProfileInput.model_validate(data)

    def test_study_financial_and_preference_rules(self) -> None:
        explore = self.profile_data()
        explore["study_intent"] = {"mode": "explore", "intended_cip_codes": [], "interests": [" computer science ", "computer science", "design"]}
        explore["financial"] = {"annual_budget_usd": 0, "needs_financial_aid": None}
        payload = ApplicantProfileInput.model_validate(explore)
        self.assertEqual(payload.study_intent.interests, ["computer science", "design"])
        self.assertEqual(payload.financial.annual_budget_usd, 0)
        self.assertEqual(payload.study_intent.intended_cip_codes, [])
        for financial, preferences in (
            ({"annual_budget_usd": -1}, {"preferred_states": [], "excluded_states": []}),
            ({"annual_budget_usd": 0}, {"preferred_states": ["CA"], "excluded_states": ["ca"]}),
        ):
            invalid = self.profile_data()
            invalid["financial"] = financial
            invalid["preferences"] = preferences
            with self.assertRaises(ValidationError):
                ApplicantProfileInput.model_validate(invalid)

    def test_cli_validate_import_show_and_example_round_trip(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "profile.json"
            path.write_text(json.dumps(self.profile_data()), encoding="utf-8")
            self.assertEqual(runner.invoke(app, ["profile", "validate", str(path)]).exit_code, 0)
            self.assertEqual(ApplicantProfile.objects.count(), 0)
            self.assertEqual(runner.invoke(app, ["profile", "import", str(path)]).exit_code, 0)
            shown = runner.invoke(app, ["profile", "show", "student-001"])
            self.assertEqual(shown.exit_code, 0)
            document = json.loads(shown.output)
            self.assertEqual(document["profile_key"], "student-001")
            for value in (
                document["academics"]["gpa_value"],
                document["academics"]["gpa_scale"],
                document["tests"][0]["score"],
                document["financial"]["annual_budget_usd"],
            ):
                self.assertIsInstance(value, (int, float))
                self.assertNotIsInstance(value, str)

        example = Path(__file__).resolve().parents[2] / "data" / "examples" / "applicant_profile.example.json"
        example_payload = load_profile(example)
        import_profile(example_payload)
        first = export_profile(example_payload.profile_key).model_dump_json()
        import_profile(ApplicantProfileInput.model_validate_json(first))
        second = export_profile(example_payload.profile_key).model_dump_json()
        self.assertEqual(json.loads(first), json.loads(second))
