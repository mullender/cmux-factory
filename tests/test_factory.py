import argparse
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import factory


class FactoryTests(unittest.TestCase):
    def init_project(self, root: Path) -> None:
        code = factory.command_init(argparse.Namespace(directory=str(root)))
        self.assertEqual(code, 0)

    def register_factory(self, root: Path, *, active: bool = True) -> None:
        registry = {
            "active": active,
            "project": str(root),
            "workspace_id": "WORKSPACE",
            "lead": "lead",
            "agents": {
                "lead": {
                    "surface_id": "LEAD",
                    "generation": 1,
                    "state": "ready",
                    "current": True,
                },
                "builder": {
                    "surface_id": "BUILDER",
                    "generation": 1,
                    "state": "ready",
                    "current": False,
                },
            },
            "watchdog": {"surface_id": "WATCHDOG", "state": "ready"},
        }
        factory.with_registry(root, lambda target: (target.clear(), target.update(registry)))

    def test_init_creates_readable_project_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            config = factory.load_config(root)
            self.assertEqual(config["version"], 1)
            self.assertEqual(config["name"], root.name)
            self.assertTrue((root / ".factory/config/OPERATING_RULES.md").is_file())
            self.assertTrue((root / ".factory/brain/NOW.md").is_file())

    def test_init_is_idempotent_and_does_not_replace_existing_factory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            facts = root / ".factory/brain/FACTS.md"
            facts.write_text("keep this fact\n")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.init_project(root)
            self.assertEqual(facts.read_text(), "keep this fact\n")
            self.assertIn(f"READY {root.resolve() / '.factory'}", output.getvalue())

    def test_init_uses_git_root_from_a_subdirectory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            nested = root / "src" / "feature"
            nested.mkdir(parents=True)
            self.init_project(nested)
            self.assertTrue((root / ".factory/factory.toml").is_file())
            self.assertFalse((nested / ".factory").exists())

    def test_init_prints_manual_and_command_line_next_steps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.init_project(root)
            receipt = output.getvalue()
            self.assertIn("FROM A NORMAL TERMINAL", receipt)
            self.assertIn("cmux new-workspace", receipt)
            self.assertIn("codex /start-factory", receipt)
            self.assertIn("claude /start-factory", receipt)
            self.assertIn("Run factory doctor --project", receipt)

    def test_init_rejects_an_unrecognized_factory_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".factory").mkdir()
            with self.assertRaises(factory.FactoryError):
                self.init_project(root)

    def test_init_rejects_an_incomplete_existing_factory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            (root / ".factory/config/STYLE.md").unlink()
            with self.assertRaisesRegex(factory.FactoryError, "STYLE.md"):
                self.init_project(root)

    def test_compose_prompt_has_common_and_role_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            config = factory.load_config(root)
            prompt = factory.compose_prompt(root, "builder", config["agents"]["builder"])
            self.assertIn("Use the smallest change", prompt)
            self.assertIn("only agent that can edit project source", prompt)
            self.assertIn("You implement one bounded assignment", prompt)
            self.assertIn("factory check-in builder", prompt)

    def test_cmux_parses_json_and_rejects_invalid_output(self) -> None:
        completed = subprocess.CompletedProcess(["cmux"], 0, stdout='{"ok": true}\n', stderr="")
        with (
            mock.patch.object(factory, "cmux_bin", return_value="/mock/cmux"),
            mock.patch.object(factory, "run_text", return_value=completed),
        ):
            self.assertEqual(factory.cmux("identify"), {"ok": True})

        invalid = subprocess.CompletedProcess(["cmux"], 0, stdout="not json\n", stderr="")
        with (
            mock.patch.object(factory, "cmux_bin", return_value="/mock/cmux"),
            mock.patch.object(factory, "run_text", return_value=invalid),
            self.assertRaises(factory.FactoryError),
        ):
            factory.cmux("identify")

    def test_find_value_searches_nested_receipts(self) -> None:
        receipt = {"result": [{"surface": {"id": "SURFACE"}}]}
        self.assertEqual(factory.find_value(receipt, {"id"}), "SURFACE")
        self.assertIsNone(factory.find_value(receipt, {"missing"}))

    def test_send_turn_waits_for_queued_text_before_enter(self) -> None:
        calls: list[tuple[str, ...]] = []

        def fake_cmux(*arguments: str):
            calls.append(arguments)
            if arguments[0] == "send":
                return {"queued": True}
            if arguments[0] == "read-screen":
                return {"text": "run the factory"}
            return {"ok": True}

        with mock.patch.object(factory, "cmux", side_effect=fake_cmux):
            factory.send_turn("WORKSPACE", "SURFACE", "run the factory")

        self.assertEqual([call[0] for call in calls], ["send", "read-screen", "send-key"])

    def test_run_text_reports_failed_commands(self) -> None:
        failed = subprocess.CompletedProcess(["tool"], 2, stdout="", stderr="bad input\n")
        with (
            mock.patch.object(factory.subprocess, "run", return_value=failed),
            self.assertRaisesRegex(factory.FactoryError, "bad input"),
        ):
            factory.run_text(["tool", "argument"])

    def test_start_builds_tabs_and_records_exact_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            surface_ids = iter(["BUILDER-SURFACE", "REVIEWER-SURFACE", "WATCHDOG-SURFACE"])
            sent: list[tuple[str, ...]] = []

            def fake_cmux(*arguments: str):
                sent.append(arguments)
                if arguments == ("identify",):
                    return {
                        "caller": {
                            "workspace_id": "WORKSPACE",
                            "window_id": "WINDOW",
                            "pane_id": "PANE",
                            "surface_id": "LEAD-SURFACE",
                        }
                    }
                if arguments[0] == "new-surface":
                    return {"surface_id": next(surface_ids)}
                return {"ok": True}

            with mock.patch.object(factory, "cmux", side_effect=fake_cmux):
                code = factory.command_start(argparse.Namespace(project=str(root)))

            self.assertEqual(code, 0)
            registry = json.loads((root / ".factory/run/registry.json").read_text())
            self.assertEqual(registry["agents"]["lead"]["surface_id"], "LEAD-SURFACE")
            self.assertEqual(registry["agents"]["builder"]["surface_id"], "BUILDER-SURFACE")
            self.assertEqual(registry["agents"]["reviewer"]["surface_id"], "REVIEWER-SURFACE")
            self.assertEqual(registry["watchdog"]["surface_id"], "WATCHDOG-SURFACE")
            self.assertTrue(any(call[0] == "rename-tab" for call in sent))
            self.assertFalse(any("--working-directory" in call for call in sent))
            rename_calls = [call for call in sent if call[0] == "rename-tab"]
            self.assertTrue(all("--title" not in call for call in rename_calls))
            self.assertTrue(
                any(
                    call[0] == "send"
                    and call[-1].startswith("cd -- ")
                    and "claude" in call[-1]
                    for call in sent
                )
            )

    def test_closed_surface_is_explained_and_not_restarted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            registry = {
                "active": True,
                "workspace_id": "WORKSPACE",
                "lead": "lead",
                "agents": {
                    "lead": {"surface_id": "LEAD", "generation": 1},
                    "builder": {"surface_id": "BUILDER", "generation": 1},
                },
            }
            factory.with_registry(root, lambda target: (target.clear(), target.update(registry)))
            calls: list[tuple[str, ...]] = []

            def fake_cmux(*arguments: str):
                calls.append(arguments)
                return {"ok": True}

            event = {
                "type": "event",
                "name": "surface.closed",
                "id": "EVENT-1",
                "workspace_id": "WORKSPACE",
                "surface_id": "BUILDER",
            }
            with mock.patch.object(factory, "cmux", side_effect=fake_cmux):
                factory.handle_watch_event(root, event)

            updated, _ = factory.with_registry(root)
            self.assertEqual(updated["agents"]["builder"]["state"], "needs-attention")
            journal = (root / ".factory/run/watchdog.jsonl").read_text()
            self.assertIn("automatic restart is disabled", journal)
            self.assertTrue(any(call[0] == "notify" for call in calls))
            self.assertFalse(any(call[0] == "new-surface" for call in calls))

    def test_agent_hooks_update_registered_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            self.register_factory(root)

            factory.handle_watch_event(
                root,
                {
                    "type": "event",
                    "name": "agent.hook.PreToolUse",
                    "workspace_id": "WORKSPACE",
                    "surface_id": "BUILDER",
                },
            )
            working, _ = factory.with_registry(root)
            self.assertEqual(working["agents"]["builder"]["state"], "working")

            factory.handle_watch_event(
                root,
                {
                    "type": "event",
                    "name": "agent.hook.Stop",
                    "workspace_id": "WORKSPACE",
                    "surface_id": "BUILDER",
                },
            )
            idle, _ = factory.with_registry(root)
            self.assertEqual(idle["agents"]["builder"]["state"], "idle")

    def test_status_json_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            factory.with_registry(
                root,
                lambda target: target.update(
                    {
                        "active": False,
                        "project": str(root),
                        "agents": {"lead": {"generation": 1, "state": "ready"}},
                    }
                ),
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = factory.command_status(argparse.Namespace(project=str(root), json=True))
            self.assertEqual(code, 0)
            data = json.loads(output.getvalue())
            self.assertEqual(data["agents"]["lead"]["state"], "ready")

    def test_status_human_output_includes_health_and_last_watchdog_action(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            self.register_factory(root)
            factory.journal(root, "RESULT", "Lead notified", agent="builder")
            output = io.StringIO()
            with (
                mock.patch.object(factory, "live_surface_ids", return_value={"LEAD"}),
                contextlib.redirect_stdout(output),
            ):
                code = factory.command_status(argparse.Namespace(project=str(root), json=False))
            self.assertEqual(code, 0)
            text = output.getvalue()
            self.assertIn("FACTORY", text)
            self.assertIn("builder", text)
            self.assertIn("WATCHDOG", text)

    def test_check_in_and_note_write_durable_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            self.register_factory(root)

            code = factory.command_check_in(
                argparse.Namespace(
                    project=str(root),
                    agent="builder",
                    state="working",
                    summary="Implement the bounded task",
                )
            )
            self.assertEqual(code, 0)
            status = json.loads((root / ".factory/agents/builder/STATUS.json").read_text())
            self.assertEqual(status["state"], "working")

            code = factory.command_note(argparse.Namespace(project=str(root), text="Keep changes small"))
            self.assertEqual(code, 0)
            feedback = (root / ".factory/brain/FEEDBACK.jsonl").read_text()
            self.assertIn("Keep changes small", feedback)

    def test_check_in_rejects_an_unknown_agent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            self.register_factory(root)
            with self.assertRaises(factory.FactoryError):
                factory.command_check_in(
                    argparse.Namespace(project=str(root), agent="unknown", state="idle", summary="done")
                )

    def test_stop_interrupts_workers_and_keeps_the_lead_tab(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            self.register_factory(root)
            calls: list[tuple[str, ...]] = []

            with mock.patch.object(factory, "cmux", side_effect=lambda *args: calls.append(args)):
                code = factory.command_stop(argparse.Namespace(project=str(root)))

            self.assertEqual(code, 0)
            stopped, _ = factory.with_registry(root)
            self.assertFalse(stopped["active"])
            self.assertEqual(stopped["agents"]["builder"]["state"], "stopped")
            surfaces = {call[4] for call in calls if call[0] == "send-key"}
            self.assertEqual(surfaces, {"BUILDER", "WATCHDOG"})

    def test_doctor_reports_machine_and_project_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            output = io.StringIO()

            def fake_run(command: list[str], *, check: bool = True):
                return subprocess.CompletedProcess(command, 0, stdout="PONG\n", stderr="")

            def fake_which(command: str):
                return f"/mock/bin/{command}"

            with (
                mock.patch.object(factory, "run_text", side_effect=fake_run),
                mock.patch.object(factory.shutil, "which", side_effect=fake_which),
                contextlib.redirect_stdout(output),
            ):
                code = factory.command_doctor(argparse.Namespace(project=str(root)))

            self.assertEqual(code, 0)
            self.assertIn("PASS  cmux binary", output.getvalue())
            self.assertIn("PASS  project config", output.getvalue())

    def test_main_turns_factory_errors_into_a_clear_exit_code(self) -> None:
        error = io.StringIO()
        with (
            mock.patch.object(factory, "command_status", side_effect=factory.FactoryError("broken registry")),
            contextlib.redirect_stderr(error),
        ):
            code = factory.main(["status"])
        self.assertEqual(code, 1)
        self.assertIn("ERROR broken registry", error.getvalue())


if __name__ == "__main__":
    unittest.main()
