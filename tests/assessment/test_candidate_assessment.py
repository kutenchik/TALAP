import json
from datetime import date

from django.test import TestCase
from typer.testing import CliRunner

from admission.applicants.models import ApplicantProfile, ApplicantTestScore
from admission.applicants.schemas import ApplicantProfileInput
from admission.applicants.services import import_profile
from admission.assessment.services import assess_candidates
from admission.catalog.models import AdmissionSnapshot, EnglishRequirement, Institution, ProgramOffering, SeedInstitution, SourceDocument
from admission.cli.app import app


class CandidateAssessmentTests(TestCase):
    def setUp(self) -> None:
        self.source = SourceDocument.objects.create(
            url="https://example.edu/source", publisher="fixture", source_type="fixture", data_year="2024",
            retrieved_at="2026-01-01T00:00:00Z", content_hash="a" * 64,
        )
        self.dictionary_source = SourceDocument.objects.create(
            url="https://example.edu/dict", publisher="fixture", source_type="fixture", data_year="2024",
            retrieved_at="2026-01-01T00:00:00Z", content_hash="d" * 64,
        )
        states = ["MA", "NY", "CA", "TX"]
        self.institutions = []
        for order, state in enumerate(states, 1):
            institution = Institution.objects.create(
                ipeds_unitid=900000 + order, name=f"Fixture University {order}", state=state, city="Fixture", country="US",
                ownership="private", official_website="https://example.edu", operating_status="active", bachelors_granting=True,
                bachelors_granting_evidence="fixture", source=self.source, source_locator="fixture",
            )
            SeedInstitution.objects.create(
                seed_order=order, name=institution.name, state=state, expected_ownership="private",
                status=SeedInstitution.Status.RESOLVED, institution=institution,
            )
            self.institutions.append(institution)
        ProgramOffering.objects.create(
            institution=self.institutions[0], cip_code="11.0701", cip_title="Computer Science", credential_level="bachelors_degree",
            award_level=5, program_name="", completion_count=10, status="reported", academic_year="2024",
            source=self.source, cip_title_source=self.dictionary_source, source_locator="fixture", evidence="fixture",
        )
        ProgramOffering.objects.create(
            institution=self.institutions[1], cip_code="99.0000", cip_title="Summary", credential_level="bachelors_degree",
            award_level=5, program_name="", completion_count=1, status="reported", academic_year="2024",
            source=self.source, cip_title_source=self.dictionary_source, source_locator="fixture", evidence="fixture",
        )
        AdmissionSnapshot.objects.create(
            institution=self.institutions[0], data_year="2024", term="fall", admissions_data_status="reported",
            sat_data_status="not_reported", act_data_status="not_reported", test_data_status="not_reported", source_flags={},
            source=self.source, dictionary_source=self.dictionary_source, source_locator="fixture", evidence="fixture",
        )
        self.requirement(0, "ielts", "ielts_band_0_9", "6.5", EnglishRequirement.Status.VERIFIED, waiver_text="Waiver may apply.")
        self.requirement(0, "toefl_ibt", "toefl_ibt_0_120", "90", EnglishRequirement.Status.VERIFIED, before=date(2026, 1, 21))
        self.requirement(0, "toefl_ibt", "toefl_ibt_1_6", "4.5", EnglishRequirement.Status.VERIFIED, on_or_after=date(2026, 1, 21))
        self.requirement(1, "ielts", "ielts_band_0_9", None, EnglishRequirement.Status.NO_MINIMUM_PUBLISHED)
        self.requirement(2, "ielts", "ielts_band_0_9", None, EnglishRequirement.Status.NOT_REQUIRED)
        self.requirement(2, "toefl_ibt", "toefl_ibt_0_120", None, EnglishRequirement.Status.NOT_FOUND)
        stale = self.requirement(3, "ielts", "ielts_band_0_9", "6.0", EnglishRequirement.Status.VERIFIED)
        stale.source_content_hash = "stale"
        stale.save(update_fields=["source_content_hash"])

    def requirement(self, index, test_type, scale, minimum, status, before=None, on_or_after=None, waiver_text=""):
        return EnglishRequirement.objects.create(
            institution=self.institutions[index], applicant_scope="international_undergraduate", test_type=test_type,
            score_scale=scale, valid_for_tests_before=before, valid_for_tests_on_or_after=on_or_after,
            minimum_overall_score=minimum, subscore_requirements={}, waiver_text=waiver_text, conditional_text="",
            policy_cycle=f"fixture-{index}-{test_type}-{scale}", status=status, source=self.source,
            source_content_hash=self.source.content_hash, evidence="fixture",
        )

    def test_other_applicant_scopes_do_not_affect_policy_or_availability(self) -> None:
        import_profile(self.profile())
        for index in (0, 3):
            row = self.requirement(index, "ielts", "ielts_band_0_9", "8.0", EnglishRequirement.Status.VERIFIED)
            row.applicant_scope = "graduate"
            row.save(update_fields=["applicant_scope"])
        candidates = assess_candidates("student-001", 1, 4).candidates
        ielts = candidates[0].english.tests[0]
        self.assertEqual(ielts.state, "meets_verified_minimum")
        self.assertEqual([float(item.minimum_score) for item in ielts.requirements], [6.5])
        self.assertEqual(candidates[0].english.policy_state, "verified_minimum")
        self.assertEqual(candidates[3].english.tests[0].state, "requirement_unavailable")
        self.assertEqual(candidates[3].english.policy_state, "unavailable")
        self.assertFalse(candidates[3].data_availability.english_data_available)
        self.assertEqual(EnglishRequirement.objects.filter(applicant_scope="graduate").count(), 2)

    def test_compatible_attempt_dates_distinguish_no_applicable_requirement(self) -> None:
        for scale, score, taken_on, expected in (
            ("toefl_ibt_0_120", 100, "2025-12-01", "meets_verified_minimum"),
            ("toefl_ibt_0_120", 100, "2026-02-01", "no_applicable_requirement"),
            ("toefl_ibt_1_6", 5, "2026-02-01", "meets_verified_minimum"),
            ("toefl_ibt_1_6", 5, "2025-12-01", "no_applicable_requirement"),
            ("toefl_ibt_0_120", 100, "2026-01-21", "no_applicable_requirement"),
            ("toefl_ibt_1_6", 5, "2026-01-21", "meets_verified_minimum"),
        ):
            with self.subTest(scale=scale, taken_on=taken_on):
                import_profile(self.profile(tests=[{
                    "test_type": "toefl", "scale": scale, "score": score, "taken_on": taken_on,
                }]))
                result = assess_candidates("student-001", 1, 1).candidates[0].english.tests[1]
                self.assertEqual(result.state, expected)
        import_profile(self.profile(tests=[]))
        self.assertEqual(assess_candidates("student-001", 1, 1).candidates[0].english.tests[1].state, "no_matching_applicant_score")

    def test_mixed_current_policy_meanings_conflict_but_absence_does_not(self) -> None:
        import_profile(self.profile())
        status = EnglishRequirement.Status
        for left, right, expected in (
            (status.VERIFIED, status.NOT_REQUIRED, "requirement_conflicting"),
            (status.VERIFIED, status.NO_MINIMUM_PUBLISHED, "requirement_conflicting"),
            (status.NOT_REQUIRED, status.NO_MINIMUM_PUBLISHED, "requirement_conflicting"),
            (status.VERIFIED, status.NOT_FOUND, "meets_verified_minimum"),
            (status.NO_MINIMUM_PUBLISHED, status.NOT_FOUND, "no_minimum_published"),
            (status.NOT_REQUIRED, status.NOT_FOUND, "not_required"),
            (status.VERIFIED, status.UNVERIFIED, "meets_verified_minimum"),
            (status.VERIFIED, status.EXTRACTION_FAILED, "meets_verified_minimum"),
            (status.VERIFIED, status.CONFLICTING, "requirement_conflicting"),
        ):
            with self.subTest(left=left, right=right):
                EnglishRequirement.objects.filter(institution=self.institutions[3]).delete()
                first = self.requirement(3, "ielts", "ielts_band_0_9", "6.5" if left == status.VERIFIED else None, left)
                second = self.requirement(3, "ielts", "ielts_band_0_9", None, right)
                second.source = self.dictionary_source
                second.source_content_hash = self.dictionary_source.content_hash
                second.save(update_fields=["source", "source_content_hash"])
                result = assess_candidates("student-001", 4, 4).candidates[0]
                self.assertEqual(result.english.tests[0].state, expected)
                self.assertTrue(result.data_availability.english_data_available)
                if expected == "requirement_conflicting":
                    self.assertEqual(result.english.policy_state, "conflicting")

    def profile(self, **updates):
        data = {
            "profile_key": "student-001", "citizenship_country_code": "KZ", "graduation_year": 2027,
            "academics": {"gpa_value": 4.7, "gpa_scale": 5.0},
            "tests": [
                {"test_type": "ielts", "scale": "ielts_0_9", "score": 7.0},
                {"test_type": "toefl", "scale": "toefl_ibt_0_120", "score": 85, "taken_on": "2025-12-01"},
                {"test_type": "toefl", "scale": "toefl_ibt_1_6", "score": 5.0, "taken_on": "2026-02-01"},
            ],
            "study_intent": {"mode": "known_major", "intended_cip_codes": ["11.0701", "14.0901"], "interests": []},
            "financial": {"annual_budget_usd": 25000, "needs_financial_aid": True},
            "preferences": {"preferred_states": ["MA"], "excluded_states": ["NY"]},
        }
        data.update(updates)
        return ApplicantProfileInput.model_validate(data)

    def test_selection_constraints_program_evidence_and_availability(self) -> None:
        import_profile(self.profile())
        result = assess_candidates("student-001", 1, 4)
        self.assertEqual([row.seed_order for row in result.candidates], [1, 2, 3, 4])
        self.assertFalse(result.candidates[0].applicant_constraints.excluded_by_applicant)
        self.assertTrue(result.candidates[1].applicant_constraints.excluded_by_applicant)
        self.assertEqual([item.state for item in result.candidates[0].program.requested_cips], ["observed", "not_observed"])
        self.assertEqual(result.candidates[1].program.state, "none_observed")
        self.assertFalse(result.candidates[1].applicant_constraints.reasons == ["excluded_state", "program_not_offered"])
        self.assertEqual(result.candidates[2].program.state, "unavailable")
        self.assertEqual(result.candidates[0].data_availability.model_dump(), {
            "program_data_available": True, "english_data_available": True, "admissions_context_available": True,
        })
        self.assertFalse(result.candidates[3].data_availability.english_data_available)
        self.assertNotIn("confidence", result.model_dump_json())

    def test_english_exact_scales_states_dates_freshness_and_conditionals(self) -> None:
        import_profile(self.profile())
        candidates = assess_candidates("student-001", 1, 4).candidates
        first = candidates[0]
        by_test = {row.test_type: row for row in first.english.tests}
        self.assertEqual(by_test["ielts"].state, "meets_verified_minimum")
        self.assertTrue(by_test["ielts"].conditional_policy_present)
        self.assertEqual(by_test["toefl"].state, "meets_verified_minimum")
        self.assertEqual([item.scale for item in by_test["toefl"].supporting_attempts], ["toefl_ibt_0_120", "toefl_ibt_1_6"])
        self.assertEqual({row.test_type: row.state for row in candidates[1].english.tests}["ielts"], "no_minimum_published")
        third = {row.test_type: row.state for row in candidates[2].english.tests}
        self.assertEqual(third["ielts"], "not_required")
        self.assertEqual(third["toefl"], "requirement_not_found")
        self.assertEqual(candidates[3].english.policy_state, "unavailable")

        below = self.profile(tests=[{"test_type": "ielts", "scale": "ielts_0_9", "score": 6.0}])
        import_profile(below)
        self.assertEqual({row.test_type: row.state for row in assess_candidates("student-001", 1, 1).candidates[0].english.tests}["ielts"], "below_verified_minimum")
        import_profile(self.profile(tests=[]))
        self.assertEqual({row.test_type: row.state for row in assess_candidates("student-001", 1, 1).candidates[0].english.tests}["ielts"], "no_matching_applicant_score")

    def test_ambiguity_conflict_explore_and_fail_closed_candidate_selection(self) -> None:
        import_profile(self.profile(tests=[{"test_type": "toefl", "scale": "toefl_ibt_0_120", "score": 100}]))
        self.requirement(0, "toefl_ibt", "toefl_ibt_0_120", "95", EnglishRequirement.Status.VERIFIED, on_or_after=date(2026, 1, 21))
        states = {row.test_type: row.state for row in assess_candidates("student-001", 1, 1).candidates[0].english.tests}
        self.assertEqual(states["toefl"], "applicability_ambiguous")

        conflict_source = SourceDocument.objects.create(
            url="https://example.edu/conflict", publisher="fixture", source_type="fixture", data_year="2024",
            retrieved_at="2026-01-01T00:00:00Z", content_hash="c" * 64,
        )
        EnglishRequirement.objects.create(
            institution=self.institutions[0], applicant_scope="international_undergraduate", test_type="ielts",
            score_scale="ielts_band_0_9", minimum_overall_score="7.0", subscore_requirements={}, waiver_text="",
            conditional_text="", policy_cycle="conflict", status=EnglishRequirement.Status.VERIFIED,
            source=conflict_source, source_content_hash=conflict_source.content_hash, evidence="fixture",
        )
        import_profile(self.profile())
        conflict_states = {row.test_type: row.state for row in assess_candidates("student-001", 1, 1).candidates[0].english.tests}
        self.assertEqual(conflict_states["ielts"], "requirement_conflicting")

        import_profile(self.profile(study_intent={"mode": "explore", "intended_cip_codes": [], "interests": ["robotics"]}))
        self.assertEqual(assess_candidates("student-001", 1, 1).candidates[0].program.state, "not_evaluated_explore_mode")
        with self.assertRaises(ValueError):
            assess_candidates("student-001", 0, 2)
        SeedInstitution.objects.filter(seed_order=2).update(institution=self.institutions[0])
        with self.assertRaises(ValueError):
            assess_candidates("student-001", 1, 2)
        SeedInstitution.objects.filter(seed_order=4).update(status=SeedInstitution.Status.UNRESOLVED, institution=None)
        with self.assertRaises(ValueError):
            assess_candidates("student-001", 1, 4)

    def test_cli_json_numeric_order_visibility_errors_and_no_persistence(self) -> None:
        import_profile(self.profile())
        counts = (ApplicantProfile.objects.count(), ApplicantTestScore.objects.count())
        runner = CliRunner()
        result = runner.invoke(app, ["assess", "candidates", "student-001", "--seed-order-start", "1", "--seed-order-end", "2"])
        self.assertEqual(result.exit_code, 0)
        document = json.loads(result.output)
        self.assertEqual([row["seed_order"] for row in document["candidates"]], [1, 2])
        self.assertTrue(document["candidates"][1]["applicant_constraints"]["excluded_by_applicant"])
        minimum = document["candidates"][0]["english"]["tests"][0]["requirements"][0]["minimum_score"]
        self.assertIsInstance(minimum, (int, float))
        self.assertEqual((ApplicantProfile.objects.count(), ApplicantTestScore.objects.count()), counts)
        self.assertNotEqual(runner.invoke(app, ["assess", "candidates", "missing", "--seed-order-end", "1"]).exit_code, 0)
        self.assertNotEqual(runner.invoke(app, ["assess", "candidates", "student-001", "--seed-order-start", "3", "--seed-order-end", "2"]).exit_code, 0)
