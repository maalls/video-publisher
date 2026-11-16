from datetime import date
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from video_publisher.ci import ci_arguments

DAY = "2026-11-17"


class CITests(unittest.TestCase):
    def test_manual_demo(self):
        self.assertEqual(ci_arguments("workflow_dispatch", "demo", DAY),
                         ["--date", DAY, "--demo"])

    def test_manual_render_ignores_public_flag(self):
        self.assertEqual(ci_arguments("workflow_dispatch", "render", DAY, True, True),
                         ["--date", DAY])

    def test_manual_private_only(self):
        self.assertEqual(ci_arguments("workflow_dispatch", "private-test", DAY, True, True),
                         ["--date", DAY, "--publish-youtube", "--private-test"])

    def test_manual_cannot_schedule_or_use_old_boolean(self):
        for mode in ("scheduled", "", "true", "false"):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                ci_arguments("workflow_dispatch", mode, DAY, True, True)

    def test_cron_disabled_even_when_public_enabled(self):
        with self.assertRaises(ValueError):
            ci_arguments("schedule", "", DAY, False, True)

    def test_cron_render(self):
        self.assertEqual(ci_arguments("schedule", "", DAY, True, False), ["--date", DAY])

    def test_cron_public_requires_both_flags(self):
        self.assertEqual(ci_arguments("schedule", "", DAY, True, True),
                         ["--date", DAY, "--publish-youtube"])

    def test_unknown_event_and_invalid_date(self):
        with self.assertRaises(ValueError):
            ci_arguments("push", "demo", DAY)
        with self.assertRaises(ValueError):
            ci_arguments("workflow_dispatch", "demo", "invalid")

    def test_runner_private_sets_only_child_env(self):
        spec = importlib.util.spec_from_file_location("run_ci", Path(__file__).parents[1] / "scripts/run_ci.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        env = {"GITHUB_EVENT_NAME": "workflow_dispatch", "INPUT_MODE": "private-test",
               "RUN_DATE": DAY, "ENABLE_YOUTUBE": "false"}
        with patch.dict(os.environ, env, clear=True), patch.object(module.subprocess, "run") as run:
            module.main()
            self.assertEqual(os.environ["ENABLE_YOUTUBE"], "false")
            self.assertEqual(run.call_args.kwargs["env"]["ENABLE_YOUTUBE"], "true")
            self.assertIn("--private-test", run.call_args.args[0])
            self.assertTrue(run.call_args.kwargs["check"])

    def test_runner_render_never_uploads(self):
        spec = importlib.util.spec_from_file_location("run_ci", Path(__file__).parents[1] / "scripts/run_ci.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        env = {"GITHUB_EVENT_NAME": "workflow_dispatch", "INPUT_MODE": "render",
               "RUN_DATE": DAY, "ENABLE_YOUTUBE": "true"}
        with patch.dict(os.environ, env, clear=True), patch.object(module.subprocess, "run") as run:
            module.main()
            self.assertEqual(run.call_args.args[0], ["video-publisher", "--date", DAY])
            self.assertEqual(run.call_args.kwargs["env"]["ENABLE_YOUTUBE"], "false")


class WorkflowWiringTests(unittest.TestCase):
    def test_workflow_has_opt_in_job_and_explicit_modes(self):
        text = (Path(__file__).parents[1] / ".github/workflows/daily.yml").read_text()
        self.assertIn("if: github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'", text)
        self.assertNotIn("  schedule:", text)
        self.assertIn("type: choice", text)
        self.assertIn("default: demo", text)
        for mode in ("demo", "render", "private-test"):
            self.assertIn(f"          - {mode}", text)
        self.assertIn("run: python scripts/run_ci.py", text)
        self.assertNotIn("inputs.demo", text)
