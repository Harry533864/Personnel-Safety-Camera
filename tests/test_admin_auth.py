import unittest
import os
from unittest.mock import patch

os.environ.setdefault("CAM_AUTO_START", "0")

from flask import Flask, jsonify

from app.auth import install_admin_auth


class AdminAuthTest(unittest.TestCase):
    def create_client(self):
        flask_app = Flask(__name__)
        install_admin_auth(flask_app)

        @flask_app.route("/api/stream/stop", methods=["POST"])
        def protected():
            return jsonify({"status": "success"})

        @flask_app.route("/api/runtime/status", methods=["GET"])
        def public():
            return jsonify({"status": "success"})

        return flask_app.test_client()

    def test_allows_public_status_without_token(self):
        with patch.dict("os.environ", {"CAM_ADMIN_TOKEN": "secret"}):
            response = self.create_client().get("/api/runtime/status")
        self.assertEqual(response.status_code, 200)

    def test_blocks_protected_route_without_token(self):
        with patch.dict("os.environ", {"CAM_ADMIN_TOKEN": "secret"}):
            response = self.create_client().post("/api/stream/stop")
        self.assertEqual(response.status_code, 401)

    def test_allows_protected_route_with_token(self):
        with patch.dict("os.environ", {"CAM_ADMIN_TOKEN": "secret"}):
            response = self.create_client().post(
                "/api/stream/stop",
                headers={"X-Admin-Token": "secret"},
            )
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
