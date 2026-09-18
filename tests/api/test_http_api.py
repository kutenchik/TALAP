import inspect
import json
from copy import deepcopy
from unittest.mock import patch

from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext

from admission.api import views
from admission.applicants.diagnostics import diagnose_profile
from admission.applicants.models import ApplicantProfile, ApplicantTestScore
from admission.applicants.services import export_profile, import_profile
from admission.journey.services import build_admission_journey
from tests.recommendation import test_recommendations as fixtures


class HttpApiTests(TestCase):
    setUp = fixtures.RecommendationTests.setUp

    def post_json(self, path, document):
        return self.client.post(path, data=json.dumps(document), content_type="application/json")

    def assert_json_error(self, response, status, code):
        self.assertEqual(response.status_code, status)
        self.assertEqual(response.headers["Content-Type"], "application/json")
        self.assertEqual(response.json()["error"]["code"], code)

    def assert_read_only(self, queries):
        mutating = ("INSERT", "UPDATE", "DELETE")
        self.assertFalse(any(query["sql"].lstrip().upper().startswith(mutating) for query in queries))

    def test_health_and_method_errors_are_exact_json_without_cors(self):
        response = self.client.get("/api/v1/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/json")
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)
        self.assert_json_error(self.client.post("/api/v1/health/"), 405, "method_not_allowed")

    def test_validate_profile_normalizes_without_writes_and_sanitizes_errors(self):
        payload = self.profile.model_dump(mode="json")
        payload["preferences"]["preferred_states"] = ["ca"]
        with CaptureQueriesContext(connection) as queries:
            response = self.post_json("/api/v1/profiles/validate/", payload)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["preferences"]["preferred_states"], ["CA"])
        self.assertIsInstance(response.json()["academics"]["gpa_value"], (int, float))
        self.assert_read_only(queries)

        invalid_cases = []
        typo = deepcopy(payload)
        typo["academics"]["gpa_typo"] = 4.7
        invalid_cases.append(typo)
        bad_gpa = deepcopy(payload)
        bad_gpa["academics"].update({"gpa_value": 6, "gpa_scale": 5})
        invalid_cases.append(bad_gpa)
        bad_scale = deepcopy(payload)
        bad_scale["tests"][0].update({"test_type": "ielts", "scale": "act_composite_1_36"})
        invalid_cases.append(bad_scale)
        for invalid in invalid_cases:
            with self.subTest(invalid=invalid):
                error = self.post_json("/api/v1/profiles/validate/", invalid)
                self.assert_json_error(error, 400, "validation_error")
                detail = error.json()["error"]["details"][0]
                self.assertEqual(set(detail), {"location", "message", "type"})

        self.assert_json_error(
            self.client.post("/api/v1/profiles/validate/", data="{", content_type="application/json"),
            400, "invalid_json",
        )
        self.assert_json_error(self.post_json("/api/v1/profiles/validate/", []), 400, "invalid_json")
        self.assert_json_error(
            self.client.post("/api/v1/profiles/validate/", data="{}", content_type="text/plain"),
            400, "invalid_json",
        )
        self.assert_json_error(self.client.get("/api/v1/profiles/validate/"), 405, "method_not_allowed")

    def test_profile_upsert_reuses_atomic_service_and_get_contract(self):
        payload = self.profile.model_dump(mode="json")
        payload["profile_key"] = "api-student"
        first = self.post_json("/api/v1/profiles/", payload)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json(), export_profile("api-student").model_dump(mode="json"))
        second = self.post_json("/api/v1/profiles/", payload)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(ApplicantProfile.objects.filter(profile_key="api-student").count(), 1)

        payload["display_name"] = "Updated Student"
        payload["tests"] = [{"test_type": "toefl", "scale": "toefl_ibt_0_120", "score": 105}]
        updated = self.post_json("/api/v1/profiles/", payload)
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["display_name"], "Updated Student")
        self.assertEqual(updated.json(), export_profile("api-student").model_dump(mode="json"))
        self.assertEqual(updated.json()["tests"][0]["test_type"], "toefl")
        self.assertEqual(updated.json()["tests"][0]["score"], 105)
        self.assertEqual(ApplicantTestScore.objects.filter(profile__profile_key="api-student").count(), 1)

        before = updated.json()
        invalid = deepcopy(payload)
        invalid["academics"].update({"gpa_value": 9, "gpa_scale": 5})
        self.assert_json_error(self.post_json("/api/v1/profiles/", invalid), 400, "validation_error")
        self.assertEqual(export_profile("api-student").model_dump(mode="json"), before)

        get_response = self.client.get("/api/v1/profiles/api-student/")
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json(), export_profile("api-student").model_dump(mode="json"))
        self.assert_json_error(self.client.get("/api/v1/profiles/unknown/"), 404, "profile_not_found")
        self.assert_json_error(self.client.delete("/api/v1/profiles/api-student/"), 405, "method_not_allowed")

    def test_diagnostic_contract_not_found_method_and_read_only(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/api/v1/profiles/student-001/diagnostic/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), diagnose_profile("student-001").model_dump(mode="json"))
        self.assert_read_only(queries)
        self.assert_json_error(
            self.client.get("/api/v1/profiles/unknown/diagnostic/"), 404, "profile_not_found",
        )
        self.assert_json_error(
            self.client.post("/api/v1/profiles/student-001/diagnostic/"), 405, "method_not_allowed",
        )

    def test_journey_contract_limit_profile_preparation_and_query_errors(self):
        path = (
            "/api/v1/profiles/student-001/journey/"
            "?seed_order_start=1&seed_order_end=5&recommendation_limit=2"
        )
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, response.content)
        expected = build_admission_journey("student-001", 1, 5, 2).model_dump(mode="json")
        self.assertEqual(response.json(), expected)

        self.profile.study_intent.intended_cip_codes = []
        import_profile(self.profile)
        preparation = self.client.get("/api/v1/profiles/student-001/journey/?seed_order_end=5")
        self.assertEqual(preparation.status_code, 200)
        self.assertEqual(preparation.json()["journey_state"], "profile_preparation")
        self.assertIsNone(preparation.json()["recommendations"])

        self.assert_json_error(
            self.client.get("/api/v1/profiles/unknown/journey/?seed_order_end=5"),
            404, "profile_not_found",
        )
        invalid_queries = (
            "seed_order_start=abc&seed_order_end=5",
            "seed_order_end=101",
            "seed_order_start=5&seed_order_end=1",
            "seed_order_end=5&recommendation_limit=0",
            "seed_order_start=1&seed_order_start=5&seed_order_end=5",
            "seed_order_end=5&recomendation_limit=2",
            "seed_order_end=5&recommendation_limit=1.5",
        )
        for query in invalid_queries:
            with self.subTest(query=query):
                self.assert_json_error(
                    self.client.get(f"/api/v1/profiles/student-001/journey/?{query}"),
                    400, "invalid_query",
                )
        self.assert_json_error(
            self.client.post("/api/v1/profiles/student-001/journey/"), 405, "method_not_allowed",
        )

    def test_journey_calls_application_service_once_and_views_stay_thin(self):
        original = views.build_admission_journey
        with patch("admission.api.views.build_admission_journey", wraps=original) as service:
            response = self.client.get(
                "/api/v1/profiles/student-001/journey/?seed_order_end=5&recommendation_limit=2"
            )
        self.assertEqual(response.status_code, 200)
        service.assert_called_once_with("student-001", 1, 5, 2)
        source = inspect.getsource(views)
        for forbidden in (
            "ProgramOffering", "EnglishRequirement", "recommend_for_profile", "build_roadmap",
            "assess_candidates",
        ):
            self.assertNotIn(forbidden, source)

    def test_journey_http_numbers_remain_numbers(self):
        response = self.client.get("/api/v1/profiles/student-001/journey/?seed_order_end=5")
        self.assertEqual(response.status_code, 200)
        document = response.json()
        recommendation = document["recommendations"]["recommendations"][0]
        values = (
            document["diagnostic"]["academics"]["gpa"]["gpa_value"],
            document["diagnostic"]["testing"]["attempts"][0]["score"],
            document["diagnostic"]["english"]["attempts"][0]["score"],
            document["diagnostic"]["financial"]["annual_budget_usd"],
            recommendation["assessment"]["english"]["tests"][0]["requirements"][0]["minimum_score"],
            recommendation["assessment"]["academic"]["act"]["context"]["lower"],
        )
        self.assertTrue(all(isinstance(value, (int, float)) and not isinstance(value, str) for value in values))

    def test_get_profile_journey_and_validate_are_read_only_and_csrf_is_enabled(self):
        requests = (
            lambda: self.client.get("/api/v1/profiles/student-001/"),
            lambda: self.client.get("/api/v1/profiles/student-001/diagnostic/"),
            lambda: self.client.get("/api/v1/profiles/student-001/journey/?seed_order_end=5"),
            lambda: self.post_json("/api/v1/profiles/validate/", self.profile.model_dump(mode="json")),
        )
        for request in requests:
            with CaptureQueriesContext(connection) as queries:
                response = request()
            self.assertEqual(response.status_code, 200, response.content)
            self.assert_read_only(queries)

        csrf_client = Client(enforce_csrf_checks=True)
        protected = csrf_client.post(
            "/api/v1/profiles/",
            data=json.dumps(self.profile.model_dump(mode="json")),
            content_type="application/json",
        )
        self.assertEqual(protected.status_code, 403)

    def test_csrf_bootstrap_get_is_json_sets_cookie_and_does_not_write(self):
        client = Client(enforce_csrf_checks=True)
        with CaptureQueriesContext(connection) as queries:
            response = client.get('/api/v1/csrf/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'application/json')
        self.assertTrue(response.json()['csrfToken'])
        self.assertTrue(response.cookies['csrftoken'].value)
        self.assertIn('Cookie', response.headers['Vary'])
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertNotIn('Access-Control-Allow-Origin', response.headers)
        self.assert_read_only(queries)

    def test_csrf_bootstrap_method_errors_and_protection(self):
        self.assert_json_error(self.client.post('/api/v1/csrf/'), 405, 'method_not_allowed')
        self.assertEqual(self.client.head('/api/v1/csrf/').status_code, 405)
        client = Client(enforce_csrf_checks=True)
        token = client.get('/api/v1/csrf/').json()['csrfToken']
        with CaptureQueriesContext(connection) as queries:
            response = client.post('/api/v1/csrf/', HTTP_X_CSRFTOKEN=token)
        self.assert_json_error(response, 405, 'method_not_allowed')
        self.assert_read_only(queries)
        # Unsafe requests without CSRF still fail at middleware before method dispatch.
        self.assertEqual(Client(enforce_csrf_checks=True).post('/api/v1/csrf/').status_code, 403)
        self.assertFalse(getattr(views.csrf, 'csrf_exempt', False))

    def test_browser_csrf_validate_save_and_reload_with_same_origin(self):
        client = Client(enforce_csrf_checks=True)
        token = client.get('/api/v1/csrf/').json()['csrfToken']
        payload = self.profile.model_dump(mode='json')
        payload['profile_key'] = 'talap-local-csrf-test'
        headers = {'HTTP_X_CSRFTOKEN': token, 'HTTP_ORIGIN': 'http://testserver'}
        with CaptureQueriesContext(connection) as queries:
            validation = client.post('/api/v1/profiles/validate/', json.dumps(payload), content_type='application/json', **headers)
        self.assertEqual(validation.status_code, 200)
        self.assert_read_only(queries)
        saved = client.post('/api/v1/profiles/', json.dumps(validation.json()), content_type='application/json', **headers)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(client.get('/api/v1/profiles/talap-local-csrf-test/').json(), saved.json())
        rejected = client.post('/api/v1/profiles/', json.dumps(payload), content_type='application/json', HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN='https://untrusted.invalid')
        self.assertEqual(rejected.status_code, 403)
