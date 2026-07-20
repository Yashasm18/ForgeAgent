import json
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path


class ControlPlaneApiServerTests(unittest.TestCase):
    """Exercise the HTTP boundary exactly as a local judge would."""

    @staticmethod
    def _free_port() -> int:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            return int(probe.getsockname()[1])

    @staticmethod
    def _json_request(url: str, method: str = "GET", payload: dict[str, object] | None = None, token: str | None = None) -> tuple[int, dict[str, object]]:
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=1) as response:
            return response.status, json.load(response)

    def test_fresh_api_process_creates_project_and_reads_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            port = self._free_port()
            main = Path(__file__).resolve().parents[1] / "main.py"
            process = subprocess.Popen(
                [sys.executable, str(main), "--api", "--api-port", str(port)],
                cwd=root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            base = f"http://127.0.0.1:{port}"
            try:
                for _ in range(30):
                    try:
                        status, health = self._json_request(f"{base}/healthz")
                        if status == 200 and health["status"] == "ok":
                            break
                    except OSError:
                        time.sleep(0.1)
                else:
                    self.fail("control-plane API did not become healthy")

                status, created = self._json_request(
                    f"{base}/v1/projects",
                    method="POST",
                    payload={"project_id": "judge/api", "owner": "judge"},
                )
                self.assertEqual(status, 201)
                self.assertEqual(created["project_id"], "judge/api")
                token = created["bootstrap_token"]
                self.assertTrue(token)

                status, snapshot = self._json_request(
                    f"{base}/v1/projects/judge/api/snapshot",
                    token=str(token),
                )
                self.assertEqual(status, 200)
                self.assertEqual(snapshot["project_id"], "judge/api")
                self.assertEqual(snapshot["members"][0]["subject"], "judge")
            finally:
                process.terminate()
                process.wait(timeout=5)

    def test_api_feedback_quarantines_a_reproduced_contract_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            port = self._free_port()
            main = Path(__file__).resolve().parents[1] / "main.py"
            process = subprocess.Popen(
                [sys.executable, str(main), "--api", "--api-port", str(port)],
                cwd=root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            base = f"http://127.0.0.1:{port}"
            try:
                for _ in range(30):
                    try:
                        if self._json_request(f"{base}/healthz")[0] == 200:
                            break
                    except OSError:
                        time.sleep(0.1)
                else:
                    self.fail("control-plane API did not become healthy")

                _, created = self._json_request(
                    f"{base}/v1/projects", method="POST",
                    payload={"project_id": "judge/maintenance", "owner": "judge"},
                )
                token = str(created["bootstrap_token"])
                _, requested = self._json_request(
                    f"{base}/v1/projects/judge/maintenance/capability-requests",
                    method="POST",
                    token=token,
                    payload={"task": "Extract invoice IDs from billing logs", "payload": {"text": "INV-2048"}},
                )
                capability_id = str(requested["memory_record"]["id"])
                self._json_request(
                    f"{base}/v1/projects/judge/maintenance/capabilities/{capability_id}:decision",
                    method="POST", token=token,
                    payload={"decision": "approved", "reason": "Reviewed deterministic proof evidence and source."},
                )
                _, feedback = self._json_request(
                    f"{base}/v1/projects/judge/maintenance/capabilities/{capability_id}/feedback",
                    method="POST", token=token,
                    payload={
                        "verdict": "incorrect",
                        "summary": "Downstream contract requires only the primary invoice identifier.",
                        "payload": {"text": "INV-2048 and INV-9"},
                        "expected_output": ["INV-2048"],
                    },
                )
                self.assertTrue(feedback["quarantined"])
                _, snapshot = self._json_request(
                    f"{base}/v1/projects/judge/maintenance/snapshot", token=token,
                )
                self.assertEqual(snapshot["receipt"]["capabilities"][0]["state"], "quarantined")
            finally:
                process.terminate()
                process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
