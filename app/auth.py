from __future__ import annotations

import hmac
import os
from collections.abc import Iterable

from flask import Request, jsonify, request


ADMIN_TOKEN_ENV = "CAM_ADMIN_TOKEN"

PROTECTED_RULES: tuple[tuple[str, set[str]], ...] = (
    ("/api/stream/start", {"GET", "POST"}),
    ("/api/stream/stop", {"GET", "POST"}),
    ("/api/stream/exposure", {"POST"}),
    ("/api/stream/gain", {"POST"}),
    ("/api/stream/white_balance", {"POST"}),
    ("/api/stream/power_line_frequency", {"POST"}),
    ("/api/stream/resolution", {"POST"}),
    ("/api/stream/fps", {"POST"}),
    ("/api/detection/detect", {"POST"}),
    ("/api/detection/save_regions", {"POST"}),
    ("/api/detection/exception_output", {"POST"}),
    ("/api/detection/exception_output/test", {"POST"}),
    ("/api/detection/exception_output/manual", {"POST"}),
    ("/api/models/upload", {"POST"}),
    ("/api/models/delete", {"POST"}),
    ("/api/record/config", {"POST"}),
    ("/api/record/delete", {"POST"}),
)


def _token_from_request(req: Request) -> str:
    header_token = req.headers.get("X-Admin-Token", "").strip()
    if header_token:
        return header_token

    auth_header = req.headers.get("Authorization", "").strip()
    prefix = "Bearer "
    if auth_header.startswith(prefix):
        return auth_header[len(prefix):].strip()

    return ""


def _matches_rule(path: str, method: str, rules: Iterable[tuple[str, set[str]]]) -> bool:
    return any(path == rule_path and method in methods for rule_path, methods in rules)


def install_admin_auth(app) -> None:
    """Protect write/control APIs when CAM_ADMIN_TOKEN is configured."""

    @app.before_request
    def require_admin_token():
        expected_token = os.environ.get(ADMIN_TOKEN_ENV, "").strip()
        if not expected_token:
            return None

        if not _matches_rule(request.path, request.method, PROTECTED_RULES):
            return None

        actual_token = _token_from_request(request)
        if hmac.compare_digest(actual_token, expected_token):
            return None

        return jsonify({
            "status": "error",
            "message": "admin token required",
        }), 401

