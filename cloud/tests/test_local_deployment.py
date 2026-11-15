"""本地工作站部署模式：配置、初始化与现有 HTTP/WS 认证入口。"""

import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cloud"))

from app import middleware, startup
from app.api import auth
from app.main import app


class LocalDeploymentTests(unittest.TestCase):
    def test_cloud_default_and_local_loopback_configuration(self):
        for overrides, expected in [
            ({}, ("cloud", "0.0.0.0")),
            ({"DEPLOYMENT_MODE": "local", "API_HOST": "0.0.0.0"}, ("local", "127.0.0.1")),
        ]:
            with self.subTest(overrides=overrides):
                env = os.environ.copy()
                env.pop("DEPLOYMENT_MODE", None)
                env.update(overrides)
                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        "from app.core.config import DEPLOYMENT_MODE, API_HOST; "
                        "print(DEPLOYMENT_MODE, API_HOST)",
                    ],
                    cwd=ROOT / "cloud",
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(tuple(result.stdout.split()), expected)

    def test_local_initialization_does_not_create_demo_devices(self):
        with (
            patch.object(startup, "IS_LOCAL_DEPLOYMENT", True),
            patch.object(startup, "SessionLocal") as session_local,
        ):
            startup.create_initial_devices()
        session_local.assert_not_called()

    def test_http_authentication_only_changes_in_local_mode(self):
        client = TestClient(app)
        with patch.object(auth, "IS_LOCAL_DEPLOYMENT", False):
            self.assertEqual(client.get("/api/logs/?lines=1").status_code, 401)
        with patch.object(auth, "IS_LOCAL_DEPLOYMENT", True):
            response = client.get("/api/logs/?lines=1")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["code"], 200)

    def test_websockets_accept_local_connections_without_a_token(self):
        client = TestClient(app)
        with patch.object(auth, "IS_LOCAL_DEPLOYMENT", False):
            with self.assertRaises(WebSocketDisconnect) as denied:
                with client.websocket_connect("/ws/monitor"):
                    pass
            self.assertEqual(denied.exception.code, 1008)
        with patch.object(auth, "IS_LOCAL_DEPLOYMENT", True):
            with client.websocket_connect("/ws/monitor") as websocket:
                websocket.send_text("ping")
                self.assertEqual(websocket.receive_json(), {"type": "pong"})
            with client.websocket_connect("/ws/acquisition/sessions/missing/view"):
                pass

    def test_dc24_page_receives_backend_deployment_state(self):
        client = TestClient(app)
        with (
            patch.object(middleware, "DEPLOYMENT_MODE", "local"),
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "pathlib.Path.read_text", return_value="<html><head></head></html>"
            ),
        ):
            response = client.get("/dc24/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("window.__DEPLOYMENT_MODE__='local'", response.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
