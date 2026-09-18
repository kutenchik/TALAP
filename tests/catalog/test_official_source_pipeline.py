import json
from pathlib import Path
import tempfile
from types import SimpleNamespace

import httpx
from django.test import TestCase
from pydantic import ValidationError

from admission.catalog.models import DataIssue, EnglishRequirement, Institution, SeedInstitution, SourceDocument
from admission.catalog.schemas import EnglishExtractionResponse, EnglishRequirementCandidate
from admission.catalog.services import (
    MAX_TOEFL_APPLICABILITY_DISTANCE,
    _normalise_llm_json_response,
    _parse_llm_response,
    discover_official_sources,
    enrich_english_requirements,
    export_english_requirements,
    fetch_official_sources,
    load_official_source_seeds,
    validate_english_evidence,
)
from admission.catalog.web import WebFetcher, extract_page, select_english_relevance
from admission.llm.alem import AlemGemmaClient, LLMUnavailable


HTML = """
<html><head><title>International undergraduate English</title></head><body>
<h1>International undergraduate English proficiency</h1>
<p>International undergraduate applicants need an IELTS minimum score of 6.5.</p>
<p>International undergraduate applicants need a TOEFL iBT minimum score of 80.</p>
<p>International undergraduate applicants need a Duolingo English Test minimum score of 110.</p>
</body></html>
"""


class FakeEnglishClient:
    model_name = "fake-gemma4"

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.prompts: list[str] = []

    def extract(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.responses.pop(0)


class OfficialSourcePipelineTests(TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.seed_path = self.root / "official_urls.jsonl"
        source = SourceDocument.objects.create(
            url="https://nces.example/HD2024.zip", publisher="IPEDS", source_type="institutional_characteristics",
            data_year="2024", retrieved_at="2024-01-01T00:00:00Z", content_hash="a" * 64,
        )
        self.institution = Institution.objects.create(
            ipeds_unitid=999001, name="Example University", state="CA", city="Example", country="US",
            ownership="public", official_website="https://example.edu", operating_status="active",
            bachelors_granting=True, bachelors_granting_evidence="fixture", source=source, source_locator="fixture",
        )
        self.seed = SeedInstitution.objects.create(
            seed_order=1, name=self.institution.name, state="CA", expected_ownership="public",
            status=SeedInstitution.Status.RESOLVED, institution=self.institution,
        )
        self.write_seeds()

    def write_seeds(self, additional: list[dict] | None = None) -> None:
        rows = [{
            "institution_ipeds_unitid": self.institution.ipeds_unitid,
            "institution_name": self.institution.name,
            "url": "https://example.edu/english",
            "source_type": "international_undergraduate_english",
            "discovery_method": "search_engine_official_domain",
            "discovered_from": "fixture official-domain search",
            "allowed_hosts": ["example.edu"],
        }]
        rows.extend(additional or [])
        self.seed_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def fetcher(self, handler) -> WebFetcher:
        return WebFetcher(
            cache_root=self.root / "cache",
            client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True),
            respect_robots=False,
            retries=0,
        )

    def success_handler(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=HTML, request=request)

    def seed_and_fetch(self, handler=None) -> WebFetcher:
        fetcher = self.fetcher(handler or self.success_handler)
        result = fetch_official_sources(self.seed_path, fetcher=fetcher)
        self.assertEqual(result["fetched"], 1)
        return fetcher

    def valid_response(self) -> str:
        return json.dumps({"requirements": [
            {"test_type": "ielts", "minimum_score": 6.5, "score_scale": "ielts_band_0_9", "subscore_requirements": {}, "waiver_text": None, "conditional_text": None, "status": "found", "evidence": "International undergraduate applicants need an IELTS minimum score of 6.5."},
            {"test_type": "toefl_ibt", "minimum_score": 80, "score_scale": "toefl_ibt_0_120", "subscore_requirements": {}, "waiver_text": None, "conditional_text": None, "status": "found", "evidence": "International undergraduate applicants need a TOEFL iBT minimum score of 80."},
            {"test_type": "duolingo_english_test", "minimum_score": 110, "score_scale": "det_10_160", "subscore_requirements": {}, "waiver_text": None, "conditional_text": None, "status": "found", "evidence": "International undergraduate applicants need a Duolingo English Test minimum score of 110."},
        ]})

    def not_found_response(self) -> str:
        return json.dumps({"requirements": [
            {"test_type": test_type, "minimum_score": None, "subscore_requirements": {}, "waiver_text": None, "conditional_text": None, "status": "not_found", "evidence": ""}
            for test_type in ("ielts", "toefl_ibt", "duolingo_english_test")
        ]})

    def test_successful_fetch_persists_source_and_redirect_final_url(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/english":
                return httpx.Response(302, headers={"Location": "https://example.edu/final"}, request=request)
            return httpx.Response(200, text=HTML, request=request)

        result = fetch_official_sources(self.seed_path, fetcher=self.fetcher(handler))
        source = SourceDocument.objects.get(institution=self.institution, url="https://example.edu/english")

        self.assertEqual((result["fetched"], result["failed"]), (1, 0))
        self.assertEqual(source.canonical_url, "https://example.edu/final")
        self.assertEqual(source.http_status, 200)
        self.assertTrue(source.content_hash)

    def test_timeout_fetch_failure_creates_explicit_issue(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("fixture timeout", request=request)

        result = fetch_official_sources(self.seed_path, fetcher=self.fetcher(handler))

        self.assertEqual(result["failed"], 1)
        self.assertTrue(DataIssue.objects.filter(seed_entry=self.seed, issue_type=DataIssue.IssueType.SOURCE_FETCH_FAILED).exists())

    def test_cache_prevents_repeat_download(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, text=HTML, request=request)

        fetcher = self.fetcher(handler)
        first = fetcher.fetch("https://example.edu/english")
        second = fetcher.fetch("https://example.edu/english")

        self.assertFalse(first.from_cache)
        self.assertTrue(second.from_cache)
        self.assertEqual(calls, 1)

    def test_trafilatura_extraction_and_relevance_keep_test_context(self) -> None:
        page = extract_page(HTML)
        relevant = select_english_relevance(page.text)

        self.assertTrue(page.text)
        self.assertIn("IELTS", relevant)
        self.assertIn("TOEFL", relevant)
        self.assertIn("Duolingo", relevant)

    def test_adapter_uses_configured_model_and_base_url_without_key_output(self) -> None:
        calls = []

        class Completions:
            def create(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])

        fake_sdk = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
        client = AlemGemmaClient("not-a-real-key", base_url="https://alem.example/v1", model_name="gemma4-test", client=fake_sdk)

        self.assertEqual(client.extract("SOURCE_TEXT"), "{}")
        self.assertEqual(client.base_url, "https://alem.example/v1")
        self.assertEqual(calls[0]["model"], "gemma4-test")

    def test_adapter_converts_live_transport_failures_to_safe_unavailable_error(self) -> None:
        class Completions:
            def create(self, **kwargs):
                from openai import APIConnectionError
                raise APIConnectionError(request=httpx.Request("POST", "https://alem.example/v1/chat/completions"))

        fake_sdk = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
        with self.assertRaisesRegex(LLMUnavailable, "APIConnectionError"):
            AlemGemmaClient("not-a-real-key", client=fake_sdk).extract("SOURCE_TEXT")

    def test_valid_structured_extraction_and_evidence_persist(self) -> None:
        fetcher = self.seed_and_fetch()
        client = FakeEnglishClient([self.valid_response()])

        result = enrich_english_requirements(self.seed_path, client, fetcher=fetcher)
        requirement = EnglishRequirement.objects.get(institution=self.institution, test_type="ielts")

        self.assertEqual((result["verified"], result["llm_calls"]), (3, 1))
        self.assertEqual(str(requirement.minimum_overall_score), "6.50")
        self.assertEqual(requirement.status, EnglishRequirement.Status.VERIFIED)
        self.assertEqual(requirement.source_content_hash, requirement.source.content_hash)
        self.assertIn("SOURCE_TEXT", client.prompts[0])
        self.assertIn("Do not use model memory", client.prompts[0])

    def test_unsupported_optional_text_drops_without_blocking_core_fact(self) -> None:
        fetcher = self.seed_and_fetch()
        payload = json.loads(self.valid_response())
        payload["requirements"][0]["conditional_text"] = "Hallucinated conditional path."
        payload["requirements"][1]["waiver_text"] = "Hallucinated waiver path."
        payload["requirements"][2]["conditional_text"] = "Another unsupported conditional path."

        result = enrich_english_requirements(self.seed_path, FakeEnglishClient([json.dumps(payload)]), fetcher=fetcher)

        self.assertEqual((result["verified"], result["optional_text_dropped"], result["review_issues"]), (3, 3, 0))
        self.assertFalse(EnglishRequirement.objects.exclude(waiver_text="").exists())
        self.assertFalse(EnglishRequirement.objects.exclude(conditional_text="").exists())

    def test_supported_optional_conditional_text_remains_stored(self) -> None:
        supported_text = "Conditional admission is available."
        html = HTML.replace("</body>", f"<p>{supported_text}</p></body>")
        fetcher = self.seed_and_fetch(lambda request: httpx.Response(200, text=html, request=request))
        payload = json.loads(self.valid_response())
        payload["requirements"][0]["conditional_text"] = supported_text

        result = enrich_english_requirements(self.seed_path, FakeEnglishClient([json.dumps(payload)]), fetcher=fetcher)

        requirement = EnglishRequirement.objects.get(institution=self.institution, test_type="ielts")
        self.assertEqual((requirement.conditional_text, result["optional_text_dropped"], result["review_issues"]), (supported_text, 0, 0))

    def test_malformed_json_is_retried_in_bounded_fashion(self) -> None:
        fetcher = self.seed_and_fetch()
        client = FakeEnglishClient(["not json", "still not json"])

        result = enrich_english_requirements(self.seed_path, client, fetcher=fetcher)

        self.assertEqual(len(client.prompts), 2)
        self.assertEqual(result["extraction_failed"], 1)
        self.assertTrue(DataIssue.objects.filter(seed_entry=self.seed, issue_type=DataIssue.IssueType.ENGLISH_EXTRACTION_REVIEW).exists())

    def test_fenced_json_normalization_is_strict_and_does_not_consume_a_retry(self) -> None:
        raw = self.valid_response()
        for response in (raw, f"```json\n{raw}\n```", f"```JSON\n{raw}\n```", f"```\n{raw}\n```", f" \n```json\n{raw}\n```\n "):
            self.assertEqual(_normalise_llm_json_response(response), raw)
        for response in (f"Explanation\n```json\n{raw}\n```", f"```json\n{raw}\n```\nExplanation", f"```json\n{raw}\n```\n```\n{{}}\n```"):
            with self.assertRaises(ValueError):
                _parse_llm_response(FakeEnglishClient([response]), "SOURCE_TEXT: fixture", retries=0)
        with self.assertRaises(ValueError):
            _parse_llm_response(FakeEnglishClient(["```json\n{\n```"]), "SOURCE_TEXT: fixture", retries=0)
        with self.assertRaises(ValidationError):
            EnglishExtractionResponse.model_validate_json(_normalise_llm_json_response("```json\n{\"requirements\": []}\n```"))
        client = FakeEnglishClient([f"```json\n{raw}\n```"])
        self.assertEqual(len(_parse_llm_response(client, "SOURCE_TEXT: fixture").requirements), 3)
        self.assertEqual(len(client.prompts), 1)

    def test_retry_prompt_requires_raw_json_without_markdown_fences(self) -> None:
        client = FakeEnglishClient(["not json", self.valid_response()])
        _parse_llm_response(client, "SOURCE_TEXT: fixture")
        self.assertIn("Previous response failed schema validation", client.prompts[1])
        self.assertIn("Return raw JSON only, without Markdown fences.", client.prompts[1])

    def test_enrichment_removes_only_legacy_blank_key_review_issue(self) -> None:
        fetcher = self.seed_and_fetch()
        DataIssue.objects.create(seed_entry=self.seed, issue_type=DataIssue.IssueType.ENGLISH_EXTRACTION_REVIEW, issue_key="", detail="legacy")
        current = DataIssue.objects.create(seed_entry=self.seed, issue_type=DataIssue.IssueType.ENGLISH_EXTRACTION_REVIEW, issue_key="https://example.edu/other", detail="current")
        other_type = DataIssue.objects.create(seed_entry=self.seed, issue_type=DataIssue.IssueType.SOURCE_FETCH_FAILED, issue_key="", detail="other type")

        enrich_english_requirements(self.seed_path, FakeEnglishClient([self.valid_response()]), fetcher=fetcher)
        enrich_english_requirements(self.seed_path, FakeEnglishClient([self.valid_response()]), fetcher=fetcher)

        self.assertFalse(DataIssue.objects.filter(seed_entry=self.seed, issue_type=DataIssue.IssueType.ENGLISH_EXTRACTION_REVIEW, issue_key="").exists())
        self.assertTrue(DataIssue.objects.filter(pk=current.pk).exists())
        self.assertTrue(DataIssue.objects.filter(pk=other_type.pk).exists())

    def test_not_found_remains_null_not_invented(self) -> None:
        fetcher = self.seed_and_fetch()
        response = json.dumps({"requirements": [
            {"test_type": "ielts", "minimum_score": None, "subscore_requirements": {}, "waiver_text": None, "conditional_text": None, "status": "not_found", "evidence": ""},
            {"test_type": "toefl_ibt", "minimum_score": None, "subscore_requirements": {}, "waiver_text": None, "conditional_text": None, "status": "not_found", "evidence": ""},
            {"test_type": "duolingo_english_test", "minimum_score": None, "subscore_requirements": {}, "waiver_text": None, "conditional_text": None, "status": "not_found", "evidence": ""},
        ]})

        result = enrich_english_requirements(self.seed_path, FakeEnglishClient([response]), fetcher=fetcher)
        requirement = EnglishRequirement.objects.get(institution=self.institution, test_type="toefl_ibt")

        self.assertEqual(result["not_found"], 3)
        self.assertIsNone(requirement.minimum_overall_score)
        self.assertEqual(requirement.status, EnglishRequirement.Status.NOT_FOUND)

    def test_conditional_waiver_cannot_be_stored_as_global_not_required(self) -> None:
        source_text = "International undergraduate applicants: IELTS is not required for applicants who completed four years in English."
        candidate = EnglishRequirementCandidate(test_type="ielts", minimum_score=None, status="not_required", evidence="IELTS is not required for applicants who completed four years in English.")

        self.assertFalse(validate_english_evidence(candidate, source_text)[0])

    def test_explicit_global_not_required_can_be_stored(self) -> None:
        source_text = "For international undergraduate applicants, IELTS is not required."
        candidate = EnglishRequirementCandidate(test_type="ielts", minimum_score=None, status="not_required", evidence=source_text)
        self.assertEqual(validate_english_evidence(candidate, source_text), (True, "evidence validated"))

    def test_explicit_not_required_variants_validate_without_conditional_waivers(self) -> None:
        def candidate(evidence: str) -> EnglishRequirementCandidate:
            return EnglishRequirementCandidate(
                test_type="toefl_ibt", minimum_score=None, status="not_required", evidence=evidence,
            )

        examples = (
            "We do not require any English proficiency exams.",
            "English proficiency testing is not required.",
            "The university does not require TOEFL, IELTS, or DET.",
            "English proficiency testing is optional.",
        )
        for evidence in examples:
            with self.subTest(evidence=evidence):
                self.assertTrue(validate_english_evidence(candidate(evidence), f"TOEFL\n{evidence}")[0])

        conditional_examples = (
            "You are not required to submit a test if you studied in English for three years.",
            "Applicants who are native English speakers do not require this exam.",
            "The requirement may be waived for eligible applicants.",
        )
        for evidence in conditional_examples:
            with self.subTest(evidence=evidence):
                self.assertFalse(validate_english_evidence(candidate(evidence), f"TOEFL\n{evidence}")[0])

    def test_explicit_no_minimum_is_distinct_from_not_found(self) -> None:
        source_text = "Northeastern does not have minimum score requirements for the TOEFL."
        candidate = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=None, status="no_minimum_published", evidence=source_text)
        self.assertEqual(validate_english_evidence(candidate, source_text), (True, "evidence validated"))

    def test_explicit_no_minimum_variants_reject_advisory_and_binding_score_language(self) -> None:
        def candidate(evidence: str, status: str = "no_minimum_published") -> EnglishRequirementCandidate:
            return EnglishRequirementCandidate(
                test_type="toefl_ibt", minimum_score=None, status=status, evidence=evidence,
            )

        explicit_examples = (
            "There is no minimum score required.",
            "We have no score minimums.",
            "The university does not have minimum scores.",
            "There is no score cutoff.",
        )
        for evidence in explicit_examples:
            with self.subTest(evidence=evidence):
                self.assertTrue(validate_english_evidence(candidate(evidence), f"TOEFL\n{evidence}")[0])

        for evidence in (
            "Recommended score: 100.",
            "Competitive applicants generally score 100.",
            "Applicants must score at least 100.",
        ):
            with self.subTest(evidence=evidence):
                self.assertFalse(validate_english_evidence(candidate(evidence), f"TOEFL\n{evidence}")[0])
        binding_evidence = "Applicants must score at least 100."
        self.assertFalse(validate_english_evidence(candidate(binding_evidence, "not_required"), f"TOEFL\n{binding_evidence}")[0])

    def test_bounded_heading_context_validates_generic_score_evidence(self) -> None:
        source_text = """International undergraduate English requirements
IELTS
For general requirement programs, the minimum score is 6.0.
TOEFL
For general requirement programs, the minimum score is 61 (iBT).
Duolingo English Test
For general requirement programs, the minimum score is 95."""
        candidates = (
            EnglishRequirementCandidate(test_type="ielts", minimum_score=6.0, status="found", evidence="For general requirement programs, the minimum score is 6.0."),
            EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=61, score_scale="toefl_ibt_0_120", status="found", evidence="For general requirement programs, the minimum score is 61 (iBT)."),
            EnglishRequirementCandidate(test_type="duolingo_english_test", minimum_score=95, status="found", evidence="For general requirement programs, the minimum score is 95."),
        )
        for candidate in candidates:
            self.assertEqual(validate_english_evidence(candidate, source_text), (True, "evidence validated"))

    def test_section_boundaries_and_direct_test_evidence_keep_ownership_strict(self) -> None:
        source_text = """TOEFL
The minimum score is 80.
IELTS
The minimum score is 6.5.
Duolingo English Test
The minimum score is 115."""
        direct_toefl = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=80, score_scale="toefl_ibt_0_120", status="found", evidence="TOEFL\nThe minimum score is 80.")
        generic_toefl = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=80, score_scale="toefl_ibt_0_120", status="found", evidence="The minimum score is 80.")
        misplaced_toefl = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=6.5, score_scale="toefl_ibt_0_120", status="found", evidence="The minimum score is 6.5.")
        self.assertTrue(validate_english_evidence(direct_toefl, source_text)[0])
        self.assertTrue(validate_english_evidence(generic_toefl, source_text)[0])
        self.assertFalse(validate_english_evidence(misplaced_toefl, source_text)[0])

    def test_ambiguous_following_headings_fail_closed(self) -> None:
        source_text = "The minimum score is 80.\nTOEFL\nIELTS"
        candidate = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=80, score_scale="toefl_ibt_0_120", status="found", evidence="The minimum score is 80.")
        self.assertFalse(validate_english_evidence(candidate, source_text)[0])

    def test_bounded_context_rejects_wrong_or_distant_test_association(self) -> None:
        wrong_section = "IELTS\nFor general requirement programs, the minimum score is 80."
        wrong_candidate = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=80, score_scale="toefl_ibt_0_120", status="found", evidence="For general requirement programs, the minimum score is 80.")
        self.assertFalse(validate_english_evidence(wrong_candidate, wrong_section)[0])
        distant_section = "IELTS" + (" unrelated" * 250) + "\nFor general requirement programs, the minimum score is 6.0."
        distant_candidate = EnglishRequirementCandidate(test_type="ielts", minimum_score=6.0, status="found", evidence="For general requirement programs, the minimum score is 6.0.")
        self.assertFalse(validate_english_evidence(distant_candidate, distant_section)[0])

    def test_toefl_versions_remain_bound_to_their_local_date_rules(self) -> None:
        source_text = """TOEFL iBT
For tests before January 21, 2026, the minimum score is 80.
For tests effective January 2026, the minimum overall score is 4.5."""
        old = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=80, score_scale="toefl_ibt_0_120", valid_for_tests_before="2026-01-21", status="found", evidence="For tests before January 21, 2026, the minimum score is 80.")
        new = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=4.5, score_scale="toefl_ibt_1_6", valid_for_tests_on_or_after="2026-01-21", status="found", evidence="For tests effective January 2026, the minimum overall score is 4.5.")
        self.assertTrue(validate_english_evidence(old, source_text)[0])
        self.assertTrue(validate_english_evidence(new, source_text)[0])

    def test_combined_uc_style_evidence_assigns_each_score_to_its_own_clause(self) -> None:
        source_text = """TOEFL
Internet-based test (iBT) or iBT Home Edition: Effective January 2026 a minimum score of 4.5 or better. Prior to January 2026 a minimum score of 80 or better."""
        combined = "Internet-based test (iBT) or iBT Home Edition: Effective January 2026 a minimum score of 4.5 or better. Prior to January 2026 a minimum score of 80 or better."
        new = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=4.5, score_scale="toefl_ibt_1_6", valid_for_tests_on_or_after="2026-01-01", status="found", evidence=combined)
        old = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=80, score_scale="toefl_ibt_0_120", valid_for_tests_before="2026-01-01", status="found", evidence=combined)
        self.assertTrue(validate_english_evidence(new, source_text)[0])
        self.assertTrue(validate_english_evidence(old, source_text)[0])

    def test_combined_toefl_evidence_rejects_opposite_clause_and_missing_score(self) -> None:
        source_text = """TOEFL
Effective January 2026 minimum 4.5. Prior to January 2026 minimum 80."""
        combined = "Effective January 2026 minimum 4.5. Prior to January 2026 minimum 80."
        new_as_old = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=4.5, score_scale="toefl_ibt_1_6", valid_for_tests_before="2026-01-01", status="found", evidence=combined)
        old_as_new = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=80, score_scale="toefl_ibt_0_120", valid_for_tests_on_or_after="2026-01-01", status="found", evidence=combined)
        absent_score = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=80, score_scale="toefl_ibt_0_120", valid_for_tests_before="2026-01-01", status="found", evidence="Effective January 2026 minimum 4.5.")
        self.assertFalse(validate_english_evidence(new_as_old, source_text)[0])
        self.assertFalse(validate_english_evidence(old_as_new, source_text)[0])
        self.assertFalse(validate_english_evidence(absent_score, source_text)[0])

    def test_toefl_score_token_boundaries_and_conflicting_identical_scores_fail_closed(self) -> None:
        token_source = "TOEFL\nEffective January 2026 minimum 95."
        token_candidate = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=5, score_scale="toefl_ibt_1_6", valid_for_tests_on_or_after="2026-01-01", status="found", evidence="Effective January 2026 minimum 95.")
        ambiguous_source = "TOEFL\nEffective January 2026 minimum 5. Prior to January 2026 minimum 5."
        ambiguous_candidate = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=5, score_scale="toefl_ibt_1_6", valid_for_tests_on_or_after="2026-01-01", status="found", evidence="Effective January 2026 minimum 5. Prior to January 2026 minimum 5.")
        self.assertFalse(validate_english_evidence(token_candidate, token_source)[0])
        self.assertFalse(validate_english_evidence(ambiguous_candidate, ambiguous_source)[0])

    def test_exact_decimal_score_tokens_allow_only_equivalent_trailing_zero_forms(self) -> None:
        def validates(candidate_score: object, evidence_score: str) -> bool:
            source_text = f"TOEFL\nThe minimum score is {evidence_score}."
            candidate = EnglishRequirementCandidate(
                test_type="toefl_ibt", minimum_score=candidate_score,
                score_scale="toefl_ibt_0_120" if float(candidate_score) > 6 else "toefl_ibt_1_6", status="found",
                evidence=f"The minimum score is {evidence_score}.",
            )
            return validate_english_evidence(candidate, source_text)[0]

        self.assertTrue(validates(5, "5"))
        self.assertTrue(validates(5, "5.0"))
        self.assertTrue(validates(5, "5.00"))
        self.assertFalse(validates(5, "5.5"))
        self.assertFalse(validates(5, "95"))
        self.assertFalse(validates(5, "50"))
        self.assertTrue(validates(80, "80"))
        self.assertTrue(validates(80, "80.0"))
        self.assertFalse(validates(80, "80.5"))
        self.assertFalse(validates(80, "180"))
        self.assertTrue(validates(3.5, "3.5"))
        self.assertTrue(validates(3.5, "3.50"))
        self.assertFalse(validates(3.5, "13.5"))
        self.assertFalse(validates(3.5, "3.55"))

    def test_score_before_same_sentence_qualifier_beats_previous_sentence_marker(self) -> None:
        source_text = """TOEFL
Prior to January 2026 minimum 80.
Minimum 4.5 effective January 2026."""
        evidence = "Prior to January 2026 minimum 80.\nMinimum 4.5 effective January 2026."
        old = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=80, score_scale="toefl_ibt_0_120", valid_for_tests_before="2026-01-01", status="found", evidence=evidence)
        new = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=4.5, score_scale="toefl_ibt_1_6", valid_for_tests_on_or_after="2026-01-01", status="found", evidence=evidence)
        self.assertTrue(validate_english_evidence(old, source_text)[0])
        self.assertTrue(validate_english_evidence(new, source_text)[0])

    def test_structured_marker_intervals_cover_mit_style_table_rows(self) -> None:
        source_text = """TOEFL
TOEFL (Taken before 1/21/26) | Minimum: 90 |
TOEFL (Taken on or after 1/21/26) Effective January 21, 2026, TOEFL will adopt a 1-6 score scale. Visit https://example.org/scores.html for more information. | Minimum: 5 |"""
        old = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=90, score_scale="toefl_ibt_0_120", valid_for_tests_before="2026-01-21", status="found", evidence="TOEFL (Taken before 1/21/26) | Minimum: 90 |")
        new = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=5, score_scale="toefl_ibt_1_6", valid_for_tests_on_or_after="2026-01-21", status="found", evidence="TOEFL (Taken on or after 1/21/26) Effective January 21, 2026, TOEFL will adopt a 1-6 score scale. Visit https://example.org/scores.html for more information. | Minimum: 5 |")
        self.assertTrue(validate_english_evidence(old, source_text)[0])
        self.assertTrue(validate_english_evidence(new, source_text)[0])

    def test_structured_marker_intervals_cover_asu_style_flattened_rows(self) -> None:
        source_text = """TOEFL
For exams taken before January 21, 2026:
For the general requirement programs, the minimum score is 61 (iBT).
For exams taken on or after January 21, 2026:
For the general requirement programs, the minimum overall score is 3.5."""
        old = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=61, score_scale="toefl_ibt_0_120", valid_for_tests_before="2026-01-21", status="found", evidence="For the general requirement programs, the minimum score is 61 (iBT).")
        new = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=3.5, score_scale="toefl_ibt_1_6", valid_for_tests_on_or_after="2026-01-21", status="found", evidence="For the general requirement programs, the minimum overall score is 3.5.")
        self.assertTrue(validate_english_evidence(old, source_text)[0])
        self.assertTrue(validate_english_evidence(new, source_text)[0])

    def test_marker_intervals_remain_bounded_and_fail_closed(self) -> None:
        distant_source = "TOEFL\nEffective January 21, 2026" + (" filler" * ((MAX_TOEFL_APPLICABILITY_DISTANCE // 6) + 1)) + " minimum 5."
        distant = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=5, score_scale="toefl_ibt_1_6", valid_for_tests_on_or_after="2026-01-21", status="found", evidence=distant_source.removeprefix("TOEFL\n"))
        ambiguous_source = "TOEFL minimum 5 before January 21, 2026, effective January 21, 2026."
        ambiguous = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=5, score_scale="toefl_ibt_1_6", valid_for_tests_on_or_after="2026-01-21", status="found", evidence=ambiguous_source)
        unsupported_date = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=5, score_scale="toefl_ibt_1_6", valid_for_tests_on_or_after="2026-01-21", status="found", evidence="Effective January 2025 minimum 5.")
        self.assertEqual(
            validate_english_evidence(distant, distant_source),
            (False, "TOEFL candidate score is outside an applicability clause"),
        )
        self.assertFalse(validate_english_evidence(ambiguous, ambiguous_source)[0])
        self.assertFalse(validate_english_evidence(unsupported_date, "TOEFL\nEffective January 2025 minimum 5.")[0])

    def test_direct_mit_style_score_before_applicability_qualifier_still_passes(self) -> None:
        source_text = "TOEFL minimum score is 90 before January 21, 2026."
        candidate = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=90, score_scale="toefl_ibt_0_120", valid_for_tests_before="2026-01-21", status="found", evidence=source_text)
        self.assertTrue(validate_english_evidence(candidate, source_text)[0])

    def test_toefl_scales_cannot_validate_against_the_other_applicability_rule(self) -> None:
        source_text = """TOEFL
For tests before January 21, 2026, the minimum score is 4.5.
For tests effective January 2026, the minimum overall score is 80."""
        old_with_new_rule = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=80, score_scale="toefl_ibt_0_120", valid_for_tests_before="2026-01-21", status="found", evidence="For tests effective January 2026, the minimum overall score is 80.")
        new_with_old_rule = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=4.5, score_scale="toefl_ibt_1_6", valid_for_tests_on_or_after="2026-01-21", status="found", evidence="For tests before January 21, 2026, the minimum score is 4.5.")
        self.assertFalse(validate_english_evidence(old_with_new_rule, source_text)[0])
        self.assertFalse(validate_english_evidence(new_with_old_rule, source_text)[0])

    def test_not_found_persists_and_exports_without_fake_evidence(self) -> None:
        fetcher = self.seed_and_fetch()
        response = json.dumps({"requirements": [
            {"test_type": test_type, "minimum_score": None, "subscore_requirements": {}, "waiver_text": None, "conditional_text": None, "status": "not_found", "evidence": "not_found"}
            for test_type in ("ielts", "toefl_ibt", "duolingo_english_test")
        ]})
        enrich_english_requirements(self.seed_path, FakeEnglishClient([response]), fetcher=fetcher)
        self.assertFalse(EnglishRequirement.objects.exclude(evidence="").exists())
        exported = self.root / "not-found.jsonl"
        export_english_requirements(exported)
        self.assertTrue(all(json.loads(line)["evidence"] is None for line in exported.read_text(encoding="utf-8").splitlines()))

    def test_successful_source_processing_clears_only_its_current_review_issue(self) -> None:
        fetcher = self.seed_and_fetch()
        current = DataIssue.objects.create(seed_entry=self.seed, issue_type=DataIssue.IssueType.ENGLISH_EXTRACTION_REVIEW, issue_key="https://example.edu/english", detail="old failure")
        other = DataIssue.objects.create(seed_entry=self.seed, issue_type=DataIssue.IssueType.ENGLISH_EXTRACTION_REVIEW, issue_key="https://example.edu/other", detail="other source")
        enrich_english_requirements(self.seed_path, FakeEnglishClient([self.valid_response()]), fetcher=fetcher)
        enrich_english_requirements(self.seed_path, FakeEnglishClient([self.valid_response()]), fetcher=fetcher)
        self.assertFalse(DataIssue.objects.filter(pk=current.pk).exists())
        self.assertTrue(DataIssue.objects.filter(pk=other.pk).exists())

    def test_current_run_issue_count_excludes_inactive_historical_source(self) -> None:
        fetcher = self.seed_and_fetch()
        historical = DataIssue.objects.create(seed_entry=self.seed, issue_type=DataIssue.IssueType.ENGLISH_EXTRACTION_REVIEW, issue_key="https://example.edu/inactive", detail="historical")
        result = enrich_english_requirements(self.seed_path, FakeEnglishClient([self.valid_response()]), fetcher=fetcher)
        self.assertTrue(DataIssue.objects.filter(pk=historical.pk).exists())
        self.assertEqual(result["review_issues"], 0)

    def test_unicode_evidence_round_trips_as_deterministic_utf8_export(self) -> None:
        source = SourceDocument.objects.create(url="https://example.edu/unicode", institution=self.institution, publisher="Example", source_type="official_english_policy_page", data_year="current", retrieved_at="2026-01-21T00:00:00Z", content_hash="d" * 64)
        EnglishRequirement.objects.create(institution=self.institution, applicant_scope="international_undergraduate", test_type="ielts", score_scale="ielts_band_0_9", policy_cycle="unicode", minimum_overall_score=6.5, status=EnglishRequirement.Status.VERIFIED, source=source, source_content_hash=source.content_hash, evidence="If you’ve scored 6.5, the 1–6 scale note still applies.")
        first = self.root / "unicode-one.jsonl"
        second = self.root / "unicode-two.jsonl"
        export_english_requirements(first)
        export_english_requirements(second)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertIn("you’ve scored 6.5, the 1–6 scale", first.read_bytes().decode("utf-8"))

    def test_fabricated_evidence_fails_and_whitespace_difference_passes(self) -> None:
        candidate = EnglishRequirementCandidate(test_type="ielts", minimum_score=6.5, status="found", evidence="IELTS minimum score is 6.5")

        self.assertFalse(validate_english_evidence(candidate, "International undergraduate applicants need IELTS 7.0.")[0])
        self.assertTrue(validate_english_evidence(candidate, "International undergraduate applicants need IELTS   minimum\nscore is 6.5.")[0])

    def test_test_score_ranges_are_validated(self) -> None:
        with self.assertRaises(ValidationError):
            EnglishRequirementCandidate(test_type="ielts", minimum_score=9.5, status="found", evidence="IELTS 9.5")
        with self.assertRaises(ValidationError):
            EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=121, score_scale="toefl_ibt_0_120", status="found", evidence="TOEFL 121")
        with self.assertRaises(ValidationError):
            EnglishRequirementCandidate(test_type="duolingo_english_test", minimum_score=9, status="found", evidence="Duolingo 9")

    def test_graduate_only_evidence_cannot_validate_undergraduate_fact(self) -> None:
        candidate = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=100, score_scale="toefl_ibt_0_120", status="found", evidence="Graduate applicants need a TOEFL minimum score of 100.")

        self.assertFalse(validate_english_evidence(candidate, "Graduate applicants need a TOEFL minimum score of 100.")[0])

    def test_one_failed_institution_does_not_abort_batch(self) -> None:
        second_source = SourceDocument.objects.create(url="https://nces.example/HD2024-2.zip", publisher="IPEDS", source_type="identity", data_year="2024", retrieved_at="2024-01-01T00:00:00Z", content_hash="b" * 64)
        second = Institution.objects.create(ipeds_unitid=999002, name="Second University", state="CA", city="Example", country="US", ownership="public", official_website="https://second.example.edu", operating_status="active", bachelors_granting=True, bachelors_granting_evidence="fixture", source=second_source, source_locator="fixture")
        SeedInstitution.objects.create(seed_order=2, name=second.name, state="CA", expected_ownership="public", status=SeedInstitution.Status.RESOLVED, institution=second)
        self.write_seeds([{"institution_ipeds_unitid": 999002, "institution_name": second.name, "url": "https://second.example.edu/english", "source_type": "international_undergraduate_english", "discovery_method": "search_engine_official_domain", "discovered_from": "fixture", "allowed_hosts": ["second.example.edu"]}])

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "second.example.edu":
                raise httpx.ReadTimeout("fixture", request=request)
            return httpx.Response(200, text=HTML, request=request)

        result = fetch_official_sources(self.seed_path, fetcher=self.fetcher(handler))
        self.assertEqual((result["fetched"], result["failed"]), (1, 1))

    def test_reimport_is_idempotent_and_export_is_deterministic(self) -> None:
        fetcher = self.seed_and_fetch()
        first = enrich_english_requirements(self.seed_path, FakeEnglishClient([self.valid_response()]), fetcher=fetcher)
        second = enrich_english_requirements(self.seed_path, FakeEnglishClient([self.valid_response()]), fetcher=fetcher)
        export_one = self.root / "english-one.jsonl"
        export_two = self.root / "english-two.jsonl"

        self.assertEqual((first["verified"], second["verified"]), (3, 3))
        self.assertEqual(EnglishRequirement.objects.count(), 3)
        export_english_requirements(export_one)
        export_english_requirements(export_two)
        self.assertEqual(export_one.read_bytes(), export_two.read_bytes())
        first_record = json.loads(export_one.read_text(encoding="utf-8").splitlines()[0])
        self.assertTrue(first_record["source_content_hash"])

    def test_identical_hash_reuses_validated_facts_without_llm_calls(self) -> None:
        fetcher = self.seed_and_fetch()
        first = enrich_english_requirements(self.seed_path, FakeEnglishClient([self.valid_response()]), fetcher=fetcher)
        second_client = FakeEnglishClient([])
        second = enrich_english_requirements(self.seed_path, second_client, fetcher=fetcher)
        third = enrich_english_requirements(self.seed_path, FakeEnglishClient([]), fetcher=fetcher)

        self.assertEqual((first["verified"], first["llm_calls"]), (3, 1))
        self.assertEqual((second["verified"], second["llm_calls"], second["reused_sources"], second["reused_facts"]), (3, 0, 1, 3))
        self.assertEqual((third["verified"], third["llm_calls"], third["reused_sources"]), (3, 0, 1))
        self.assertEqual(second_client.prompts, [])

    def test_changed_source_hash_forces_llm_and_rebinds_facts(self) -> None:
        fetcher = self.seed_and_fetch()
        enrich_english_requirements(self.seed_path, FakeEnglishClient([self.valid_response()]), fetcher=fetcher)
        source = SourceDocument.objects.get(institution=self.institution, url="https://example.edu/english")
        old_hash = source.content_hash
        changed_fetcher = WebFetcher(
            cache_root=self.root / "changed-cache",
            client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=HTML.replace("</body>", "<p>Updated source bytes.</p></body>"), request=request))),
            respect_robots=False,
            retries=0,
        )

        result = enrich_english_requirements(self.seed_path, FakeEnglishClient([self.valid_response()]), fetcher=changed_fetcher)

        source.refresh_from_db()
        self.assertNotEqual(source.content_hash, old_hash)
        self.assertEqual((result["llm_calls"], result["reused_sources"], result["verified"]), (1, 0, 3))
        self.assertFalse(EnglishRequirement.objects.exclude(source_content_hash=source.content_hash).exists())

    def test_partial_changed_source_excludes_stale_fact_from_current_export(self) -> None:
        fetcher = self.seed_and_fetch()
        enrich_english_requirements(self.seed_path, FakeEnglishClient([self.valid_response()]), fetcher=fetcher)
        source = SourceDocument.objects.get(institution=self.institution, url="https://example.edu/english")
        old_hash = source.content_hash
        payload = json.loads(self.valid_response())
        payload["requirements"][1]["evidence"] = "Unsupported TOEFL evidence from the changed source."
        changed_fetcher = WebFetcher(
            cache_root=self.root / "partial-changed-cache",
            client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=HTML.replace("</body>", "<p>Changed bytes.</p></body>"), request=request))),
            respect_robots=False,
            retries=0,
        )

        result = enrich_english_requirements(self.seed_path, FakeEnglishClient([json.dumps(payload)]), fetcher=changed_fetcher)
        source.refresh_from_db()
        exported = self.root / "partial-current.jsonl"
        export_english_requirements(exported)
        records = [json.loads(line) for line in exported.read_text(encoding="utf-8").splitlines()]
        stale_toefl = EnglishRequirement.objects.get(institution=self.institution, test_type="toefl_ibt")

        self.assertNotEqual(source.content_hash, old_hash)
        self.assertEqual((result["llm_calls"], result["verified"]), (1, 2))
        self.assertEqual(stale_toefl.source_content_hash, old_hash)
        self.assertEqual({record["test_type"] for record in records}, {"ielts", "duolingo_english_test"})
        self.assertTrue(all(record["source_content_hash"] == record["source"]["content_hash"] for record in records))

    def test_unbound_legacy_rows_do_not_export_until_revalidated(self) -> None:
        fetcher = self.seed_and_fetch()
        enrich_english_requirements(self.seed_path, FakeEnglishClient([self.valid_response()]), fetcher=fetcher)
        legacy = EnglishRequirement.objects.get(institution=self.institution, test_type="toefl_ibt")
        legacy.source_content_hash = ""
        legacy.save(update_fields=["source_content_hash"])
        before_bootstrap = self.root / "unbound-before.jsonl"
        export_english_requirements(before_bootstrap)

        result = enrich_english_requirements(self.seed_path, FakeEnglishClient([]), fetcher=fetcher)
        after_bootstrap = self.root / "unbound-after.jsonl"
        export_english_requirements(after_bootstrap)

        before_types = {json.loads(line)["test_type"] for line in before_bootstrap.read_text(encoding="utf-8").splitlines()}
        after_records = [json.loads(line) for line in after_bootstrap.read_text(encoding="utf-8").splitlines()]
        self.assertNotIn("toefl_ibt", before_types)
        self.assertEqual((result["llm_calls"], result["reused_sources"], len(after_records)), (0, 1, 3))
        self.assertTrue(all(record["source_content_hash"] == record["source"]["content_hash"] for record in after_records))

    def test_legacy_rows_are_bound_only_after_revalidation(self) -> None:
        fetcher = self.seed_and_fetch()
        enrich_english_requirements(self.seed_path, FakeEnglishClient([self.valid_response()]), fetcher=fetcher)
        EnglishRequirement.objects.update(source_content_hash="")

        result = enrich_english_requirements(self.seed_path, FakeEnglishClient([]), fetcher=fetcher)
        source = SourceDocument.objects.get(institution=self.institution, url="https://example.edu/english")

        self.assertEqual((result["llm_calls"], result["reused_sources"], result["reused_facts"]), (0, 1, 3))
        self.assertFalse(EnglishRequirement.objects.exclude(source_content_hash=source.content_hash).exists())

    def test_invalid_legacy_or_current_evidence_is_not_reused(self) -> None:
        fetcher = self.seed_and_fetch()
        enrich_english_requirements(self.seed_path, FakeEnglishClient([self.valid_response()]), fetcher=fetcher)
        stale = EnglishRequirement.objects.get(institution=self.institution, test_type="ielts")
        stale.evidence = "Unsupported prior evidence."
        stale.source_content_hash = ""
        stale.save(update_fields=["evidence", "source_content_hash"])

        result = enrich_english_requirements(self.seed_path, FakeEnglishClient([self.valid_response()]), fetcher=fetcher)

        self.assertEqual((result["llm_calls"], result["reused_sources"], result["verified"]), (1, 0, 3))
        stale.refresh_from_db()
        self.assertTrue(stale.source_content_hash)
        self.assertIn("IELTS minimum score", stale.evidence)

    def test_not_found_legacy_rows_can_reuse_the_same_hash(self) -> None:
        fetcher = self.seed_and_fetch()
        enrich_english_requirements(self.seed_path, FakeEnglishClient([self.not_found_response()]), fetcher=fetcher)
        EnglishRequirement.objects.update(source_content_hash="")

        result = enrich_english_requirements(self.seed_path, FakeEnglishClient([]), fetcher=fetcher)

        self.assertEqual((result["llm_calls"], result["reused_sources"], result["not_found"]), (0, 1, 3))

    def test_conflicting_current_fact_prevents_reuse(self) -> None:
        fetcher = self.seed_and_fetch()
        enrich_english_requirements(self.seed_path, FakeEnglishClient([self.valid_response()]), fetcher=fetcher)
        EnglishRequirement.objects.filter(institution=self.institution, test_type="ielts").update(status=EnglishRequirement.Status.CONFLICTING)

        result = enrich_english_requirements(self.seed_path, FakeEnglishClient([self.valid_response()]), fetcher=fetcher)

        self.assertEqual((result["llm_calls"], result["reused_sources"], result["verified"]), (1, 0, 3))

    def test_multiple_toefl_versions_reuse_together(self) -> None:
        html = """<html><body>
<p>International undergraduate applicants need an IELTS minimum score of 6.5.</p>
<p>International undergraduate applicants need a Duolingo English Test minimum score of 110.</p>
<p>TOEFL iBT minimum score is 80 before January 21, 2026.</p>
<p>TOEFL iBT minimum score is 4.5 effective January 21, 2026.</p>
</body></html>"""
        fetcher = self.seed_and_fetch(lambda request: httpx.Response(200, text=html, request=request))
        response = json.dumps({"requirements": [
            {"test_type": "ielts", "minimum_score": 6.5, "score_scale": "ielts_band_0_9", "subscore_requirements": {}, "waiver_text": None, "conditional_text": None, "status": "found", "evidence": "International undergraduate applicants need an IELTS minimum score of 6.5."},
            {"test_type": "duolingo_english_test", "minimum_score": 110, "score_scale": "det_10_160", "subscore_requirements": {}, "waiver_text": None, "conditional_text": None, "status": "found", "evidence": "International undergraduate applicants need a Duolingo English Test minimum score of 110."},
            {"test_type": "toefl_ibt", "minimum_score": 80, "score_scale": "toefl_ibt_0_120", "valid_for_tests_before": "2026-01-21", "subscore_requirements": {}, "waiver_text": None, "conditional_text": None, "status": "found", "evidence": "TOEFL iBT minimum score is 80 before January 21, 2026."},
            {"test_type": "toefl_ibt", "minimum_score": 4.5, "score_scale": "toefl_ibt_1_6", "valid_for_tests_on_or_after": "2026-01-21", "subscore_requirements": {}, "waiver_text": None, "conditional_text": None, "status": "found", "evidence": "TOEFL iBT minimum score is 4.5 effective January 21, 2026."},
        ]})
        enrich_english_requirements(self.seed_path, FakeEnglishClient([response]), fetcher=fetcher)

        result = enrich_english_requirements(self.seed_path, FakeEnglishClient([]), fetcher=fetcher)

        self.assertEqual((result["llm_calls"], result["reused_sources"], result["reused_facts"], result["verified"]), (0, 1, 4, 4))
        self.assertEqual(EnglishRequirement.objects.filter(institution=self.institution, test_type="toefl_ibt").count(), 2)

    def test_issue_count_uses_exact_institution_url_pairs(self) -> None:
        foundation_source = SourceDocument.objects.create(
            url="https://nces.example/second.zip", publisher="IPEDS", source_type="institutional_characteristics",
            data_year="2024", retrieved_at="2024-01-01T00:00:00Z", content_hash="b" * 64,
        )
        second = Institution.objects.create(
            ipeds_unitid=999002, name="Second Example University", state="CA", city="Example", country="US",
            ownership="public", official_website="https://second.example.edu", operating_status="active",
            bachelors_granting=True, bachelors_granting_evidence="fixture", source=foundation_source, source_locator="fixture",
        )
        SeedInstitution.objects.create(seed_order=2, name=second.name, state="CA", expected_ownership="public", status=SeedInstitution.Status.RESOLVED, institution=second)
        second_url = "https://second.example.edu/english"
        self.write_seeds(additional=[{
            "institution_ipeds_unitid": second.ipeds_unitid,
            "institution_name": second.name,
            "url": second_url,
            "source_type": "international_undergraduate_english",
            "discovery_method": "search_engine_official_domain",
            "discovered_from": "fixture official-domain search",
            "allowed_hosts": ["second.example.edu"],
        }])
        fetcher = self.fetcher(self.success_handler)
        self.assertEqual(fetch_official_sources(self.seed_path, fetcher=fetcher)["fetched"], 2)
        enrich_english_requirements(self.seed_path, FakeEnglishClient([self.valid_response(), self.valid_response()]), fetcher=fetcher)
        DataIssue.objects.create(seed_entry=self.seed, issue_type=DataIssue.IssueType.ENGLISH_EXTRACTION_REVIEW, issue_key=second_url, detail="wrong institution/url pair")

        result = enrich_english_requirements(self.seed_path, FakeEnglishClient([]), fetcher=fetcher)

        self.assertEqual(result["review_issues"], 0)

    def test_empty_selected_seed_set_has_no_active_review_issues(self) -> None:
        DataIssue.objects.create(
            seed_entry=self.seed,
            issue_type=DataIssue.IssueType.ENGLISH_EXTRACTION_REVIEW,
            issue_key="https://example.edu/english",
            detail="unrelated stored issue",
        )

        result = enrich_english_requirements(self.seed_path, FakeEnglishClient([]), unitids=set(), fetcher=self.fetcher(self.success_handler))

        self.assertEqual((result["attempted"], result["review_issues"]), (0, 0))

    def test_multiple_urls_for_one_institution_are_selected_and_duplicates_fail(self) -> None:
        extra = {"institution_ipeds_unitid": self.institution.ipeds_unitid, "institution_name": self.institution.name, "url": "https://example.edu/waiver", "source_type": "international_undergraduate_english", "discovery_method": "official_site_navigation", "discovered_from": "fixture", "allowed_hosts": ["example.edu"]}
        self.write_seeds([extra])
        self.assertEqual(len(discover_official_sources(self.seed_path, {self.institution.ipeds_unitid})), 2)
        self.write_seeds([extra, extra])
        with self.assertRaises(ValueError):
            load_official_source_seeds(self.seed_path)

    def test_source_specific_fetch_issues_coexist_and_rerun_is_idempotent(self) -> None:
        extra = {"institution_ipeds_unitid": self.institution.ipeds_unitid, "institution_name": self.institution.name, "url": "https://example.edu/waiver", "source_type": "international_undergraduate_english", "discovery_method": "official_site_navigation", "discovered_from": "fixture", "allowed_hosts": ["example.edu"]}
        self.write_seeds([extra])
        result = fetch_official_sources(self.seed_path, fetcher=self.fetcher(lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("fixture", request=request))))
        self.assertEqual(result["failed"], 2)
        self.assertEqual(DataIssue.objects.filter(seed_entry=self.seed, issue_type=DataIssue.IssueType.SOURCE_FETCH_FAILED).count(), 2)
        fetch_official_sources(self.seed_path, fetcher=self.fetcher(lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("fixture", request=request))))
        self.assertEqual(DataIssue.objects.filter(seed_entry=self.seed, issue_type=DataIssue.IssueType.SOURCE_FETCH_FAILED).count(), 2)

    def test_toefl_versions_validate_and_can_coexist(self) -> None:
        old = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=90, score_scale="toefl_ibt_0_120", valid_for_tests_before="2026-01-21", status="found", evidence="TOEFL minimum score is 90 before January 21, 2026.")
        new = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=4.5, score_scale="toefl_ibt_1_6", valid_for_tests_on_or_after="2026-01-21", status="found", evidence="TOEFL minimum score is 4.5 on or after January 21, 2026.")
        self.assertEqual(old.score_scale, "toefl_ibt_0_120")
        self.assertEqual(new.score_scale, "toefl_ibt_1_6")
        with self.assertRaises(ValidationError):
            EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=4.3, score_scale="toefl_ibt_1_6", status="found", evidence="TOEFL 4.3")
        source = SourceDocument.objects.create(url="https://example.edu/toefl", institution=self.institution, publisher="Example", source_type="official_english_policy_page", data_year="current", retrieved_at="2026-01-21T00:00:00Z", content_hash="c" * 64)
        for candidate in (old, new):
            EnglishRequirement.objects.create(institution=self.institution, applicant_scope="international_undergraduate", test_type="toefl_ibt", score_scale=candidate.score_scale, valid_for_tests_before=candidate.valid_for_tests_before, valid_for_tests_on_or_after=candidate.valid_for_tests_on_or_after, policy_cycle="unspecified", minimum_overall_score=candidate.minimum_score, status=EnglishRequirement.Status.VERIFIED, source=source, source_content_hash=source.content_hash, evidence=candidate.evidence)
        exported = self.root / "toefl.jsonl"
        export_english_requirements(exported)
        self.assertIn('"toefl_ibt_0_120"', exported.read_text(encoding="utf-8"))
        self.assertIn('"toefl_ibt_1_6"', exported.read_text(encoding="utf-8"))

    def test_complete_state_and_retry_correction_are_required(self) -> None:
        with self.assertRaises(ValidationError):
            EnglishExtractionResponse.model_validate({"requirements": [{"test_type": "ielts", "status": "not_found"}]})
        client = FakeEnglishClient(["not json", self.valid_response()])
        response = _parse_llm_response(client, "SOURCE_TEXT: fixture")
        self.assertEqual(len(response.requirements), 3)
        self.assertIn("Previous response failed schema validation", client.prompts[1])


    def add_batch_institution(self, order: int, unitid: int) -> Institution:
        institution = Institution.objects.create(
            ipeds_unitid=unitid, name=f"Batch University {order}", state="CA", city="Example",
            country="US", ownership="public", official_website="https://example.edu",
            operating_status="active", bachelors_granting=True, bachelors_granting_evidence="fixture",
            source=self.institution.source, source_locator="fixture",
        )
        SeedInstitution.objects.create(
            seed_order=order, name=institution.name, state="CA", expected_ownership="public",
            status=SeedInstitution.Status.RESOLVED, institution=institution,
        )
        return institution

    def test_seed_batch_selects_exactly_25_in_seed_order(self) -> None:
        from admission.catalog.source_batches import select_seed_batch, resolve_source_selection

        for order in range(2, 27):
            self.add_batch_institution(order, 900000 - order)
        entries = select_seed_batch(1, 25)
        self.assertEqual([entry.seed_order for entry in entries], list(range(1, 26)))
        self.assertEqual(len({entry.institution.ipeds_unitid for entry in entries}), 25)
        self.assertEqual(
            resolve_source_selection([], 1, 25),
            [entry.institution.ipeds_unitid for entry in entries],
        )
        self.assertEqual([entry.seed_order for entry in select_seed_batch(25, 25)], [25])

    def test_seed_batch_rejects_invalid_incomplete_unresolved_and_duplicate_membership(self) -> None:
        from admission.catalog.source_batches import select_seed_batch, resolve_source_selection

        for start, end in ((0, 1), (2, 1), (1, 2), (27, 28)):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                select_seed_batch(start, end)
        for unitids, start, end in (([], 1, None), ([], None, 1), ([999001], 1, 1)):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                resolve_source_selection(unitids, start, end)
        second = SeedInstitution.objects.create(
            seed_order=2, name="Unresolved", state="CA", expected_ownership="public",
        )
        with self.assertRaisesRegex(ValueError, "resolve"):
            select_seed_batch(1, 2)
        second.status = SeedInstitution.Status.RESOLVED
        second.institution = self.institution
        second.save()
        with self.assertRaisesRegex(ValueError, "duplicate institution UNITIDs"):
            select_seed_batch(1, 2)

    def test_source_gap_manifest_is_stable_retains_multiple_urls_and_excludes_history(self) -> None:
        from admission.catalog.source_batches import export_source_gaps

        missing = self.add_batch_institution(2, 999002)
        self.add_batch_institution(3, 999003)
        SourceDocument.objects.create(
            institution=missing, url="https://example.edu/historical",
            publisher=missing.name, source_type="official_english_policy_page",
            data_year="current", retrieved_at="2024-01-01T00:00:00Z", content_hash="b" * 64,
        )
        extra = json.loads(self.seed_path.read_text(encoding="utf-8").splitlines()[0])
        extra["url"] = "https://example.edu/waivers"
        self.write_seeds([extra])
        output = self.root / "review" / "gaps.json"
        first = export_source_gaps(self.seed_path, output, 1, 2)
        before = output.read_bytes()
        self.assertEqual(export_source_gaps(self.seed_path, output, 1, 2), first)
        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(first, {"batch_size": 2, "source_ready": 1, "source_missing": 1})
        rows = json.loads(before)
        self.assertEqual([row["seed_order"] for row in rows], [1, 2])
        self.assertEqual(rows[0]["active_official_source_urls"], [
            "https://example.edu/english", "https://example.edu/waivers",
        ])
        self.assertEqual(rows[1]["source_status"], "missing")
        self.assertEqual(rows[1]["active_official_source_urls"], [])
        self.assertNotIn("minimum_overall_score", rows[0])

    def test_source_gap_rejects_wrong_name_and_unapproved_url_host(self) -> None:
        from admission.catalog.source_batches import source_gap_rows

        row = json.loads(self.seed_path.read_text(encoding="utf-8"))
        for changed in ({**row, "institution_name": "Wrong"}, {**row, "url": "https://third-party.example/english"}):
            self.seed_path.write_text(json.dumps(changed) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                source_gap_rows(self.seed_path, 1, 1)

    def test_ordered_source_selection_keeps_seed_order_and_missing_sources_fail_before_fetch(self) -> None:
        from unittest.mock import Mock

        second = self.add_batch_institution(2, 900002)
        row = json.loads(self.seed_path.read_text(encoding="utf-8"))
        row.update(institution_ipeds_unitid=second.ipeds_unitid, institution_name=second.name)
        self.write_seeds([row])
        selected = discover_official_sources(self.seed_path, [999001, 900002])
        self.assertEqual([seed.institution_ipeds_unitid for seed in selected], [999001, 900002])
        self.write_seeds()
        fetcher = Mock()
        with self.assertRaisesRegex(ValueError, "900002"):
            fetch_official_sources(self.seed_path, unitids=[999001, 900002], fetcher=fetcher)
        fetcher.fetch.assert_not_called()

    def test_batch_cli_selectors_and_repeated_unitid_are_preserved(self) -> None:
        from unittest.mock import patch
        from typer.testing import CliRunner
        from admission.cli.app import app

        self.add_batch_institution(2, 900002)
        for command, service in (("fetch-sources", "fetch_official_sources"), ("enrich-english", "enrich_english_requirements")):
            for options, expected in (
                (["--seed-order-start", "1", "--seed-order-end", "2"], [999001, 900002]),
                (["--unitid", "900002", "--unitid", "999001"], {999001, 900002}),
                ([], None),
            ):
                with self.subTest(command=command, options=options), patch(
                    f"admission.cli.app.{service}", return_value={"attempted": 2},
                ) as call, patch("admission.cli.app.AlemGemmaClient.from_environment", return_value=FakeEnglishClient([])):
                    result = CliRunner().invoke(app, ["data", command, "--source-seeds", str(self.seed_path), *options])
                    self.assertEqual(result.exit_code, 0, result.output)
                    self.assertEqual(call.call_args.kwargs["unitids"], expected)

    def test_batch_cli_invalid_range_never_starts_pipeline(self) -> None:
        from unittest.mock import patch
        from typer.testing import CliRunner
        from admission.cli.app import app

        for command in ("fetch-sources", "enrich-english"):
            for options in (
                ["--seed-order-start", "1"],
                ["--seed-order-start", "2", "--seed-order-end", "1"],
                ["--seed-order-start", "0", "--seed-order-end", "1"],
                ["--seed-order-start", "1", "--seed-order-end", "2"],
                ["--seed-order-start", "1", "--seed-order-end", "1", "--unitid", "999001"],
            ):
                with self.subTest(command=command, options=options), patch(
                    "admission.cli.app.fetch_official_sources",
                ) as fetch, patch("admission.cli.app.enrich_english_requirements") as enrich, patch(
                    "admission.cli.app.AlemGemmaClient.from_environment",
                ) as client:
                    result = CliRunner().invoke(app, ["data", command, "--source-seeds", str(self.seed_path), *options])
                    self.assertEqual(result.exit_code, 2, result.output)
                    fetch.assert_not_called()
                    enrich.assert_not_called()
                    client.assert_not_called()

    def test_source_gap_cli_is_offline_and_reports_counts(self) -> None:
        from unittest.mock import patch
        from typer.testing import CliRunner
        from admission.cli.app import app

        self.add_batch_institution(2, 900002)
        with patch("admission.catalog.web.WebFetcher.fetch", side_effect=AssertionError("No network")), patch(
            "admission.cli.app.AlemGemmaClient.from_environment", side_effect=AssertionError("No LLM"),
        ):
            result = CliRunner().invoke(app, [
                "data", "source-gaps", "--source-seeds", str(self.seed_path),
                "--seed-order-start", "1", "--seed-order-end", "2",
                "--path", str(self.root / "gaps.json"),
            ])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("batch_size=2 source_ready=1 source_missing=1", result.output)

    def test_batch_cli_reuses_unchanged_validated_source_without_llm(self) -> None:
        from unittest.mock import patch
        from typer.testing import CliRunner
        from admission.cli.app import app

        fetcher = self.seed_and_fetch()
        enrich_english_requirements(self.seed_path, FakeEnglishClient([self.valid_response()]), fetcher=fetcher)
        client = FakeEnglishClient([])
        with patch("admission.catalog.services.WebFetcher", return_value=fetcher), patch(
            "admission.cli.app.AlemGemmaClient.from_environment", return_value=client,
        ):
            result = CliRunner().invoke(app, [
                "data", "enrich-english", "--source-seeds", str(self.seed_path),
                "--seed-order-start", "1", "--seed-order-end", "1",
            ])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("llm_calls=0 reused_sources=1 reused_facts=3", result.output)
        self.assertEqual(client.prompts, [])

    def test_nonbinding_benchmarks_cannot_be_verified_hard_minimums(self) -> None:
        for evidence in (
            "IELTS recommended minimum score of 6.5.",
            "IELTS competitive applicants generally score 6.5.",
            "IELTS most successful applicants score 6.5.",
            "IELTS expected score of 6.5.",
            "IELTS typical score of 6.5.",
        ):
            candidate = EnglishRequirementCandidate(
                test_type="ielts", minimum_score=6.5, status="found", evidence=evidence,
            )
            with self.subTest(evidence=evidence):
                self.assertFalse(validate_english_evidence(candidate, evidence)[0])
        clipped = EnglishRequirementCandidate(
            test_type="ielts", minimum_score=6.5, status="found", evidence="6.5",
        )
        self.assertFalse(validate_english_evidence(clipped, "IELTS\nRecommended minimum\n6.5")[0])
        no_minimum = EnglishRequirementCandidate(
            test_type="ielts", status="no_minimum_published",
            evidence="IELTS has no minimum; typical score is 6.5.",
        )
        self.assertTrue(validate_english_evidence(no_minimum, no_minimum.evidence)[0])

    def test_nonbinding_score_benchmark_forms_reject_found_toefl_candidates(self) -> None:
        def candidate(score: float, evidence: str) -> EnglishRequirementCandidate:
            return EnglishRequirementCandidate(
                test_type="toefl_ibt", minimum_score=score,
                score_scale="toefl_ibt_1_6" if score <= 6 else "toefl_ibt_0_120",
                status="found", evidence=evidence,
            )

        examples = (
            (100, "TOEFL\nFor exams taken prior to January 21, 2026, a minimum score of 100 is recommended."),
            (5.0, "TOEFL\nFor exams taken on January 21, 2026 or later, a minimum score of 5.0 is recommended."),
            (100, "TOEFL\nWe strongly recommend the following scores:\nTOEFL\n100 minimum overall score"),
            (100, "TOEFL\nMost competitive applicants typically earn 100."),
            (100, "TOEFL\nScore requirements to be most competitive:\nTOEFL 100"),
            (100, "TOEFL\nMinimum score expected: 100."),
            (100, "TOEFL\nExpected score: 100; this is not a strict cutoff."),
            (100, "TOEFL\nRecommended minimums; applicants below them may still be admissible.\nTOEFL 100"),
            (100, "TOEFL\nScores of 100 or above are considered competitive."),
            (100, "TOEFL\nSuccessful applicants typically score 100."),
            (100, "TOEFL\nTo be most competitive, applicants should score 100."),
            (100, "TOEFL\nTo be competitive, applicants should score 100."),
            (100, "TOEFL\nApplicants should score 100 to be competitive."),
            (100, "TOEFL\nTo remain competitive, applicants should have a score of 100."),
            (100, "TOEFL\nFor the most competitive applicants, a score of 100 is suggested."),
            (105, "TOEFL\nThe following minimum scores are expected in most cases:\nTOEFL minimum score 105."),
            (105, "TOEFL\nTOEFL scores of 105 are expected in most cases."),
            (100, "TOEFL\nStudents who are most competitive for admission will have a score of 100."),
            (100, "TOEFL\nApplicants who are most competitive tend to have a score of 100."),
            (100, "TOEFL\nCandidates who are most competitive generally score 100."),
            (100, "TOEFL\nStudents considered most competitive usually score 100."),
        )
        for score, source_text in examples:
            with self.subTest(source_text=source_text):
                self.assertFalse(validate_english_evidence(candidate(score, source_text), source_text)[0])

        ielts_source = "IELTS\nThe following scores are typically expected:\nIELTS 8.0."
        ielts_candidate = EnglishRequirementCandidate(
            test_type="ielts", minimum_score=8.0, status="found", evidence=ielts_source,
        )
        self.assertFalse(validate_english_evidence(ielts_candidate, ielts_source)[0])

    def test_nonbinding_headings_are_bounded_and_do_not_poison_hard_minima(self) -> None:
        row_source = "TOEFL\nWe strongly recommend the following scores:\nTOEFL\n100 minimum overall score"
        row_candidate = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=100, score_scale="toefl_ibt_0_120", status="found", evidence="100 minimum overall score")
        distant_source = "TOEFL\nWe strongly recommend the following scores:" + (" filler" * 51) + "\nApplicants must score at least 100."
        distant_candidate = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=100, score_scale="toefl_ibt_0_120", status="found", evidence="Applicants must score at least 100.")

        self.assertFalse(validate_english_evidence(row_candidate, row_source)[0])
        self.assertTrue(validate_english_evidence(distant_candidate, distant_source)[0])

    def test_binding_minimums_remain_valid_despite_unrelated_recommendations(self) -> None:
        examples = (
            "TOEFL\nMinimum Score\nTOEFL 100",
            "TOEFL minimum score of 90.",
            "TOEFL\nApplicants must achieve a score of at least 100.",
            "TOEFL\nApplicants are required to score 100 or higher.",
            "TOEFL\nApplicants must score at least 100. We recommend taking the examination early.",
            "TOEFL\nWe recommend TOEFL as one way to demonstrate proficiency. Applicants using TOEFL must achieve at least 100.",
            "TOEFL\nApplicants must score at least 100. Higher scores may make an applicant more competitive.",
            "TOEFL\nApplicants need at least 100 for admission; competitive applicants often score higher.",
            "TOEFL\nApplicants are required to score 100 or higher.",
            "TOEFL\nApplicants must score at least 100. Most competitive applicants score 110 or higher.",
            "TOEFL\nMinimum score: 100. Students with stronger scores may be more competitive.",
        )
        for source_text in examples:
            score = 90 if "90" in source_text else 100
            candidate = EnglishRequirementCandidate(test_type="toefl_ibt", minimum_score=score, score_scale="toefl_ibt_0_120", status="found", evidence=source_text)
            with self.subTest(source_text=source_text):
                self.assertTrue(validate_english_evidence(candidate, source_text)[0])
