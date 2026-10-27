"""Offline contract tests: no Docker daemon, database or Meta connection."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "build" / "manage.sh"
FAKE_DOCKER = r"""#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
with open(os.environ["BUILD_TEST_CALLS"], "a") as stream:
    stream.write(json.dumps(args) + "\n")
if "ps" in args and "--services" in args:
    print(os.environ.get("BUILD_TEST_RUNNING", "api\nworker\npostgres\nredis"))
if "run" in args and "META_TEST_RECIPIENT_ID" in " ".join(args):
    if os.environ.get("BUILD_TEST_EMPTY_RECIPIENT") == "1":
        sys.exit(2)
if "apps.tools.reset_conversations" in " ".join(args):
    sys.exit(int(os.environ.get("BUILD_TEST_RESET_EXIT", "0")))
if "stop" in args:
    sys.exit(int(os.environ.get("BUILD_TEST_STOP_EXIT", "0")))
if "start" in args:
    sys.exit(int(os.environ.get("BUILD_TEST_START_EXIT", "0")))
"""


class BuildCommandsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="cfc-build-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project with spaces"
        (self.root / "build").mkdir(parents=True)
        shutil.copyfile(SCRIPT, self.root / "build" / "manage.sh")
        (self.root / "docker-compose.yml").write_text("services: {}\n")
        (self.root / ".env").write_text("# Not shell-sourced\n")
        binary = Path(self.temp.name) / "bin"
        binary.mkdir()
        docker = binary / "docker"
        docker.write_text(FAKE_DOCKER)
        docker.chmod(0o755)
        self.log = Path(self.temp.name) / "calls.jsonl"
        self.env = {
            **os.environ,
            "PATH": f"{binary}{os.pathsep}{os.environ['PATH']}",
            "BUILD_TEST_CALLS": str(self.log),
        }

    def run_command(self, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(self.root / "build" / "manage.sh"), *args],
            cwd=self.temp.name,
            env={**self.env, **env},
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_help_without_env_or_docker_calls(self) -> None:
        (self.root / ".env").unlink()
        result = self.run_command("help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("reset-chat --yes", result.stdout)
        self.assertEqual(self.calls(), [])

    def test_rejects_invalid_arguments_before_docker(self) -> None:
        for args in [
            ("unknown",),
            ("stop", "--volumes"),
            ("logs", "postgres"),
            ("reset-chat", "--sender-id", "123"),
            ("restart", "--all"),
        ]:
            with self.subTest(args=args):
                self.assertNotEqual(self.run_command(*args).returncode, 0)
                self.assertEqual(self.calls(), [])

    def test_reset_requires_explicit_confirmation(self) -> None:
        for args in [("reset-chat",), ("reset-chat", "--all")]:
            self.assertNotEqual(self.run_command(*args).returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_start_uses_correct_project_from_other_directory(self) -> None:
        result = self.run_command("start")
        self.assertEqual(result.returncode, 0, result.stderr)
        command = self.calls()[0]
        self.assertEqual(
            command[:7],
            [
                "compose",
                "--project-directory",
                str(self.root),
                "-f",
                str(self.root / "docker-compose.yml"),
                "--profile",
                "app",
            ],
        )
        self.assertEqual(command[7:], ["up", "-d", "--build", "api", "worker"])

    def test_restart_recreates_environment_without_reset(self) -> None:
        self.assertEqual(self.run_command("restart").returncode, 0)
        self.assertIn("--force-recreate", self.calls()[0])
        self.assertNotIn("reset_conversations", str(self.calls()))

    def test_stop_keeps_volumes_and_includes_optional_services(self) -> None:
        self.assertEqual(self.run_command("stop").returncode, 0)
        self.assertEqual(self.calls()[0][-3:], ["--profile", "*", "stop"])
        self.assertNotIn("down", self.calls()[0])
        self.assertNotIn("-v", self.calls()[0])

    def test_logs_are_bounded_and_service_scoped(self) -> None:
        self.assertEqual(self.run_command("logs", "worker").returncode, 0)
        self.assertEqual(
            self.calls()[0][-5:], ["logs", "--tail", "100", "--follow", "worker"]
        )

    def test_check_only_runs_read_only_preflight(self) -> None:
        self.assertEqual(self.run_command("check").returncode, 0)
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(
            self.calls()[0][-7:],
            [
                "exec",
                "-T",
                "worker",
                "python",
                "scripts/verify_go_live.py",
                "--api-url",
                "http://api:8000",
            ],
        )

    def test_missing_env_fails_before_docker(self) -> None:
        (self.root / ".env").unlink()
        self.assertNotEqual(self.run_command("start").returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_env_is_not_executed_as_shell(self) -> None:
        marker = self.root / "should-not-exist"
        (self.root / ".env").write_text(f'touch "{marker}"\n')
        self.assertEqual(self.run_command("status").returncode, 0)
        self.assertFalse(marker.exists())

    def test_reset_refuses_if_worker_not_running(self) -> None:
        result = self.run_command(
            "reset-chat", "--yes", BUILD_TEST_RUNNING="api\npostgres"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.calls()), 1)

    def test_empty_recipient_never_stops_or_resets(self) -> None:
        result = self.run_command("reset-chat", "--yes", BUILD_TEST_EMPTY_RECIPIENT="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any("stop" in call for call in self.calls()))
        self.assertNotIn("apps.tools.reset_conversations", str(self.calls()))

    def test_default_reset_is_scoped_and_restores_services(self) -> None:
        result = self.run_command("reset-chat", "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertEqual(calls[2][-3:], ["stop", "api", "worker"])
        self.assertIn('--sender-id "$META_TEST_RECIPIENT_ID"', calls[3][-1])
        self.assertNotIn("--all", calls[3][-1])
        self.assertEqual(calls[4][-3:], ["start", "api", "worker"])

    def test_all_reset_is_explicit(self) -> None:
        result = self.run_command("reset-chat", "--all", "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.calls()[2][-4:],
            ["python", "-m", "apps.tools.reset_conversations", "--all"],
        )

    def test_failed_reset_restores_only_previously_running_services(self) -> None:
        result = self.run_command(
            "reset-chat",
            "--yes",
            BUILD_TEST_RESET_EXIT="9",
            BUILD_TEST_RUNNING="worker\npostgres\nredis",
        )
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertEqual(self.calls()[-1][-2:], ["start", "worker"])
        self.assertNotIn("Chat state reset.", result.stdout)

    def test_stop_failure_does_not_reset_but_restores_services(self) -> None:
        result = self.run_command("reset-chat", "--yes", BUILD_TEST_STOP_EXIT="8")
        self.assertEqual(result.returncode, 8, result.stderr)
        self.assertNotIn("apps.tools.reset_conversations", str(self.calls()))
        self.assertEqual(self.calls()[-1][-3:], ["start", "api", "worker"])

    def test_restore_failure_returns_error(self) -> None:
        result = self.run_command("reset-chat", "--yes", BUILD_TEST_START_EXIT="7")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Could not restore services", result.stderr)


if __name__ == "__main__":
    unittest.main()
