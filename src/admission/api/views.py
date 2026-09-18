import json
import re
from json import JSONDecodeError
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.middleware.csrf import get_token
from pydantic import ValidationError

from admission.applicants.diagnostics import diagnose_profile
from admission.applicants.models import ApplicantProfile
from admission.applicants.schemas import ApplicantProfileInput
from admission.applicants.services import export_profile, import_profile
from admission.journey.services import build_admission_journey


_INTEGER_PATTERN = re.compile(r"-?[0-9]+")
_JOURNEY_QUERY_NAMES = {"seed_order_start", "seed_order_end", "recommendation_limit"}


def _error(
    code: str,
    message: str,
    status: int,
    details: list[dict[str, Any]] | None = None,
) -> JsonResponse:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return JsonResponse({"error": error}, status=status)


def _method_not_allowed() -> JsonResponse:
    return _error("method_not_allowed", "Method not allowed.", 405)


def _model_response(model: Any) -> JsonResponse:
    return JsonResponse(model.model_dump(mode="json"))


def _safe_validation_details(exc: ValidationError) -> list[dict[str, Any]]:
    return [
        {
            "location": list(error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors(include_url=False, include_context=False, include_input=False)
    ]


def _parse_profile(request: HttpRequest) -> ApplicantProfileInput | JsonResponse:
    if request.content_type != "application/json":
        return _error("invalid_json", "Content-Type must be application/json.", 400)
    try:
        document = json.loads(request.body.decode("utf-8"))
    except (JSONDecodeError, UnicodeDecodeError):
        return _error("invalid_json", "Request body must contain valid UTF-8 JSON.", 400)
    if not isinstance(document, dict):
        return _error("invalid_json", "Request body must be a JSON object.", 400)
    try:
        return ApplicantProfileInput.model_validate(document)
    except ValidationError as exc:
        return _error(
            "validation_error",
            "Profile validation failed.",
            400,
            _safe_validation_details(exc),
        )


def _profile_not_found() -> JsonResponse:
    return _error("profile_not_found", "Profile not found.", 404)


def _journey_query(request: HttpRequest) -> tuple[int, int, int | None] | JsonResponse:
    unknown = sorted(set(request.GET) - _JOURNEY_QUERY_NAMES)
    if unknown:
        return _error("invalid_query", "Unknown journey query parameter.", 400)
    if any(len(request.GET.getlist(name)) != 1 for name in request.GET):
        return _error("invalid_query", "Journey query parameters cannot be repeated.", 400)

    parsed: dict[str, int] = {}
    for name in _JOURNEY_QUERY_NAMES:
        if name not in request.GET:
            continue
        raw = request.GET[name]
        if _INTEGER_PATTERN.fullmatch(raw) is None:
            return _error("invalid_query", "Journey query parameters must be integers.", 400)
        parsed[name] = int(raw)
    return (
        parsed.get("seed_order_start", 1),
        parsed.get("seed_order_end", 100),
        parsed.get("recommendation_limit"),
    )


def health(request: HttpRequest) -> JsonResponse:
    if request.method != "GET":
        return _method_not_allowed()
    return JsonResponse({"status": "ok"})


def csrf(request: HttpRequest) -> JsonResponse:
    if request.method != "GET":
        return _method_not_allowed()
    response = JsonResponse({"csrfToken": get_token(request)})
    response["Cache-Control"] = "no-store"
    return response


def validate_profile(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return _method_not_allowed()
    profile = _parse_profile(request)
    if isinstance(profile, JsonResponse):
        return profile
    return _model_response(profile)


def upsert_profile(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return _method_not_allowed()
    profile = _parse_profile(request)
    if isinstance(profile, JsonResponse):
        return profile
    import_profile(profile)
    return _model_response(export_profile(profile.profile_key))


def get_profile(request: HttpRequest, profile_key: str) -> JsonResponse:
    if request.method != "GET":
        return _method_not_allowed()
    try:
        profile = export_profile(profile_key)
    except ApplicantProfile.DoesNotExist:
        return _profile_not_found()
    return _model_response(profile)


def get_diagnostic(request: HttpRequest, profile_key: str) -> JsonResponse:
    if request.method != "GET":
        return _method_not_allowed()
    try:
        diagnostic = diagnose_profile(profile_key)
    except ApplicantProfile.DoesNotExist:
        return _profile_not_found()
    return _model_response(diagnostic)


def get_journey(request: HttpRequest, profile_key: str) -> JsonResponse:
    if request.method != "GET":
        return _method_not_allowed()
    query = _journey_query(request)
    if isinstance(query, JsonResponse):
        return query
    try:
        journey = build_admission_journey(profile_key, *query)
    except ApplicantProfile.DoesNotExist:
        return _profile_not_found()
    except ValueError:
        return _error("invalid_query", "Journey query parameters are outside the supported range.", 400)
    return _model_response(journey)
