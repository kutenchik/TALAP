import json
from decimal import Decimal

import pytest
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from pydantic import ValidationError
from typer.testing import CliRunner

from admission.applicants.schemas import ApplicantTestScoreInput
from admission.applicants.services import import_profile
from admission.assessment.academic import ReportedRange, position_attempts
from admission.assessment.services import assess_candidates
from admission.catalog.models import AdmissionSnapshot, EnglishRequirement
from admission.cli.app import app
from . import test_candidate_assessment as fixtures


@pytest.mark.parametrize("test_type,scale,lower,upper,scores,states", [
    ("sat", "sat_total_400_1600", 1400, 1500, [1390, 1400, 1450, 1500, 1510],
     ["below", "within", "within", "within", "above"]),
    ("act", "act_composite_1_36", 31, 34, [30, 31, 34, 35], ["below", "within", "within", "above"]),
])
def test_range_boundaries_preserve_independent_attempts(test_type, scale, lower, upper, scores, states):
    # SAT total context is synthetic ONLY: the ORM adapter cannot produce this range.
    attempts = [ApplicantTestScoreInput(test_type=test_type, scale=scale, score=n) for n in scores]
    context = ReportedRange(scale=scale, lower=lower, upper=upper)
    result = position_attempts(attempts, context)
    assert [item.state for item in result.attempts] == [f"{state}_reported_context" for state in states]
    assert [item.score for item in result.attempts] == scores
    assert result.state == "above_reported_context"
    assert position_attempts([], context).state == "applicant_score_missing"
    assert position_attempts(attempts, None).state == "context_unavailable"
    opposite = ReportedRange(scale="act_composite_1_36" if test_type == "sat" else "sat_total_400_1600", lower=lower, upper=upper)
    assert position_attempts(attempts, opposite).state == "context_not_comparable"


class AcademicAssessmentTests(TestCase):
    setUp = fixtures.CandidateAssessmentTests.setUp
    requirement = fixtures.CandidateAssessmentTests.requirement
    profile = fixtures.CandidateAssessmentTests.profile

    def test_raw_gpa_sections_not_totals_act_context_and_year(self):
        AdmissionSnapshot.objects.filter(institution=self.institutions[0]).update(
            sat_ebrw_25=700, sat_ebrw_75=750, sat_math_25=700, sat_math_75=750,
            act_composite_25=31, act_composite_75=34,
        )
        profile = self.profile(tests=[
            {"test_type": "sat", "scale": "sat_total_400_1600", "score": 1450},
            {"test_type": "act", "scale": "act_composite_1_36", "score": 30},
            {"test_type": "act", "scale": "act_composite_1_36", "score": 34},
        ])
        import_profile(profile)
        result = assess_candidates(profile.profile_key, 1, 1).candidates[0]
        academic = result.academic
        self.assertEqual(academic.gpa.state, "supplied_not_comparable")
        self.assertEqual((academic.gpa.gpa_value, academic.gpa.gpa_scale), (Decimal("4.7"), Decimal("5")))
        self.assertEqual(academic.sat.state, "context_not_comparable")
        self.assertIsNone(academic.sat.context)
        self.assertFalse(academic.sat_context_available)
        self.assertTrue(academic.act_context_available)
        self.assertEqual(academic.act.state, "within_reported_context")
        self.assertEqual([p.score for p in academic.act.attempts], [30, 34])
        self.assertEqual(academic.data_year, "2024")
        self.assertEqual(academic.source_url, self.source.url)
        self.assertEqual(result.evidence_quality.academic, "verified")
        self.assertEqual(profile.tests[0].score, 1450)

    def test_missing_and_partial_context_and_latest_year_no_backfill(self):
        import_profile(self.profile(academics={}, tests=[]))
        result = assess_candidates("student-001", 1, 4).candidates
        self.assertEqual(result[0].academic.gpa.state, "missing")
        self.assertEqual(result[0].academic.act.state, "applicant_score_missing")
        self.assertEqual(result[0].evidence_quality.academic, "partial")
        self.assertEqual(result[3].evidence_quality.academic, "unavailable")
        AdmissionSnapshot.objects.filter(institution=self.institutions[0]).update(act_composite_25=31, act_composite_75=34)
        self.assertEqual(assess_candidates("student-001", 1, 1).candidates[0].evidence_quality.academic, "partial")
        import_profile(self.profile(tests=[{"test_type": "act", "scale": "act_composite_1_36", "score": 32}]))
        snapshot = AdmissionSnapshot.objects.get(institution=self.institutions[0])
        snapshot.pk = None
        snapshot.data_year = "2025"
        snapshot.act_composite_25 = None
        snapshot.act_composite_75 = None
        snapshot.save()
        result = assess_candidates("student-001", 1, 1).candidates[0]
        self.assertEqual(result.academic.data_year, "2025")
        self.assertEqual(result.academic.act.state, "context_unavailable")
        self.assertEqual(result.evidence_quality.academic, "partial")

    def test_program_and_english_evidence_states(self):
        import_profile(self.profile())
        result = assess_candidates("student-001", 1, 4).candidates
        self.assertEqual([r.evidence_quality.program for r in result], ["verified", "partial", "unavailable", "unavailable"])
        # Unevaluated waiver text is explicitly partial.
        self.assertEqual(result[0].evidence_quality.english, "partial")
        self.assertEqual(result[1].evidence_quality.english, "verified")
        self.assertEqual(result[2].evidence_quality.english, "verified")
        self.assertEqual(result[3].evidence_quality.english, "unavailable")
        EnglishRequirement.objects.filter(institution=self.institutions[0]).update(waiver_text="")
        self.assertEqual(assess_candidates("student-001", 1, 1).candidates[0].evidence_quality.english, "verified")
        EnglishRequirement.objects.filter(institution=self.institutions[0]).update(status="not_found", minimum_overall_score=None)
        self.assertEqual(assess_candidates("student-001", 1, 1).candidates[0].evidence_quality.english, "partial")
        EnglishRequirement.objects.filter(institution=self.institutions[0]).update(status="conflicting")
        self.assertEqual(assess_candidates("student-001", 1, 1).candidates[0].evidence_quality.english, "conflicting")
        EnglishRequirement.objects.filter(institution=self.institutions[0]).update(applicant_scope="graduate")
        self.assertEqual(assess_candidates("student-001", 1, 1).candidates[0].evidence_quality.english, "unavailable")
        import_profile(self.profile(study_intent={"mode": "explore", "interests": ["design"]}))
        self.assertEqual(assess_candidates("student-001", 1, 1).candidates[0].evidence_quality.program, "not_applicable")

    def test_bulk_queries_cli_json_determinism_and_strict_schemas(self):
        import_profile(self.profile(tests=[{"test_type": "act", "scale": "act_composite_1_36", "score": 32}]))
        AdmissionSnapshot.objects.filter(institution=self.institutions[0]).update(act_composite_25=31, act_composite_75=34)
        with CaptureQueriesContext(connection) as small:
            assess_candidates("student-001", 1, 1)
        with CaptureQueriesContext(connection) as large:
            first = assess_candidates("student-001", 1, 4)
        self.assertEqual(len(small), len(large))
        self.assertTrue(all(q["sql"].lstrip().upper().startswith("SELECT") for q in large))
        self.assertEqual(first.model_dump_json(), assess_candidates("student-001", 1, 4).model_dump_json())
        self.assertEqual([r.seed_order for r in first.candidates], [1, 2, 3, 4])
        cli = CliRunner().invoke(app, ["assess", "candidates", "student-001", "--seed-order-end", "4"])
        self.assertEqual(cli.exit_code, 0, cli.output)
        document = json.loads(cli.output)
        context = document["candidates"][0]["academic"]["act"]["context"]
        self.assertIsInstance(context["lower"], int)
        self.assertIsInstance(document["candidates"][0]["academic"]["act"]["attempts"][0]["score"], (int, float))
        for schema in (first.candidates[0].academic, first.candidates[0].evidence_quality):
            with self.assertRaises(ValidationError):
                type(schema).model_validate({**schema.model_dump(), "unexpected": True})
        for forbidden in ("probability", "recommendation", "strong", "weak", "superscore"):
            self.assertNotIn(forbidden, cli.output)
