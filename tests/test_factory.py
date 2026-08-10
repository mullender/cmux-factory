import argparse
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import factory


class FactoryTests(unittest.TestCase):
    def init_project(self, root: Path) -> None:
        code = factory.command_init(argparse.Namespace(directory=str(root)))
        self.assertEqual(code, 0)

    def init_git_project(self, root: Path) -> str:
        self.init_project(root)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(
            [
                "git", "-C", str(root),
                "-c", "user.name=Factory Test",
                "-c", "user.email=factory@example.invalid",
                "commit", "-qm", "Initial project",
            ],
            check=True,
        )
        return factory.git_head(root)

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
            self.assertIn("worktrees/", (root / ".factory/.gitignore").read_text().splitlines())
            state = json.loads((root / ".factory/template-state.json").read_text())
            self.assertEqual(state["format"], 1)
            self.assertIn("roles/reviewer.md", state["files"])

    def test_update_replaces_an_unchanged_managed_rule(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "project"
            root.mkdir()
            self.init_project(root)
            template = base / "template"
            shutil.copytree(factory.TEMPLATE_ROOT, template)
            reviewer = template / "roles/reviewer.md"
            reviewer.write_text(reviewer.read_text() + "\n- New upstream rule.\n")

            result = factory.sync_project_templates(root, template)

            self.assertIn("roles/reviewer.md", result["updated"])
            self.assertIn("New upstream rule", (root / ".factory/roles/reviewer.md").read_text())
            self.assertEqual(result["review"], [])

    def test_update_preserves_a_local_rule_and_writes_the_new_template_for_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "project"
            root.mkdir()
            self.init_project(root)
            project_rule = root / ".factory/roles/reviewer.md"
            project_rule.write_text(project_rule.read_text() + "\n- Local project rule.\n")
            template = base / "template"
            shutil.copytree(factory.TEMPLATE_ROOT, template)
            upstream_rule = template / "roles/reviewer.md"
            upstream_rule.write_text(upstream_rule.read_text() + "\n- New upstream rule.\n")

            result = factory.sync_project_templates(root, template)

            self.assertIn("roles/reviewer.md", result["review"])
            self.assertIn("Local project rule", project_rule.read_text())
            review = root / ".factory/update/roles/reviewer.md.new"
            self.assertIn("New upstream rule", review.read_text())

            accepted = factory.accept_current_templates(root, ["roles/reviewer.md"], template)
            resolved = factory.sync_project_templates(root, template)

            self.assertEqual(accepted, ["roles/reviewer.md"])
            self.assertFalse(review.exists())
            self.assertIn("roles/reviewer.md", resolved["local"])
            self.assertEqual(resolved["review"], [])

    def test_update_keeps_a_local_rule_when_the_template_did_not_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            project_rule = root / ".factory/roles/reviewer.md"
            project_rule.write_text(project_rule.read_text() + "\n- Local project rule.\n")

            result = factory.sync_project_templates(root)

            self.assertIn("roles/reviewer.md", result["local"])
            self.assertEqual(result["review"], [])
            self.assertIn("Local project rule", project_rule.read_text())

    def test_update_can_replace_all_reviewed_rules_with_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "project"
            root.mkdir()
            self.init_project(root)
            project_rule = root / ".factory/roles/reviewer.md"
            project_rule.write_text(project_rule.read_text() + "\n- Local project rule.\n")
            template = base / "template"
            shutil.copytree(factory.TEMPLATE_ROOT, template)
            upstream_rule = template / "roles/reviewer.md"
            upstream_rule.write_text(upstream_rule.read_text() + "\n- New upstream rule.\n")

            result = factory.sync_project_templates(root, template, use_upstream=True)

            self.assertIn("roles/reviewer.md", result["updated"])
            self.assertEqual(result["review"], [])
            self.assertIn("New upstream rule", project_rule.read_text())
            self.assertNotIn("Local project rule", project_rule.read_text())
            self.assertFalse((root / ".factory/update/roles/reviewer.md.new").exists())

    def test_update_does_not_guess_when_an_existing_project_has_no_template_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            (root / ".factory/template-state.json").unlink()
            project_rule = root / ".factory/roles/reviewer.md"
            project_rule.write_text(project_rule.read_text() + "\n- Existing project rule.\n")

            result = factory.sync_project_templates(root)

            self.assertIn("roles/reviewer.md", result["review"])
            self.assertIn("Existing project rule", project_rule.read_text())

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

    def test_project_root_uses_the_launch_environment_from_a_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            nested = root / ".factory" / "worktrees" / "builder"
            nested.mkdir(parents=True)
            with (
                mock.patch.dict(factory.os.environ, {"FACTORY_PROJECT_ROOT": str(root)}),
                mock.patch.object(factory.Path, "cwd", return_value=nested),
            ):
                self.assertEqual(factory.project_root(None), root.resolve())

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
            self.assertIn("factory inbox builder", prompt)
            self.assertIn("Never poll or wait for mail", prompt)
            self.assertNotIn("at the start and end of each turn", prompt)
            self.assertIn("send mail only to the Lead", prompt)
            self.assertIn("factory mail builder lead", prompt)
            self.assertIn("Every turn must end with a handoff", prompt)
            self.assertIn("open cross-repository pull request", prompt)
            self.assertIn("explicit user approval", prompt)

    def test_reviewer_prompt_separates_current_findings_from_follow_up_work(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            config = factory.load_config(root)
            prompt = factory.compose_prompt(root, "reviewer", config["agents"]["reviewer"])
            self.assertIn("Review only the current change", prompt)
            self.assertIn("Do not expand the goal", prompt)
            self.assertIn("Do not use them to block the current change", prompt)
            self.assertIn("FOLLOW-UP OPPORTUNITIES — NOT PART OF THIS CHANGE", prompt)
            self.assertIn("does not change the current verdict", prompt)

    def test_lead_prompt_can_message_workers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            config = factory.load_config(root)
            prompt = factory.compose_prompt(root, "lead", config["agents"]["lead"])
            self.assertIn("send mail to any non-Lead agent", prompt)
            self.assertIn("factory mail lead builder", prompt)
            self.assertIn("factory mail lead reviewer", prompt)
            self.assertIn("--base BASE_SHA --head HEAD_SHA", prompt)
            self.assertIn("Never poll or wait for mail", prompt)
            self.assertNotIn("Every turn must end with a handoff", prompt)
            self.assertIn("open cross-repository pull request", prompt)
            self.assertIn("do not push without explicit approval", prompt)

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

    def test_run_text_reports_command_timeouts(self) -> None:
        with (
            mock.patch.object(
                factory.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired(["tool", "argument"], 2),
            ),
            self.assertRaisesRegex(factory.FactoryError, "timed out after 2 seconds"),
        ):
            factory.run_text(["tool", "argument"], timeout=2)

    def test_update_pulls_installs_and_restarts_with_the_new_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            calls: list[list[str]] = []

            def fake_run(command: list[str], *, check: bool = True):
                calls.append(command)
                return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

            with (
                mock.patch.object(factory, "run_text", side_effect=fake_run),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                code = factory.command_update(
                    argparse.Namespace(
                        project=str(root),
                        no_pull=False,
                        source_only=False,
                        accept_current=[],
                        use_upstream=False,
                        skip_install=False,
                    )
                )

            self.assertEqual(code, 0)
            self.assertEqual(calls[0][-2:], ["pull", "--ff-only"])
            self.assertEqual(calls[1], [str(factory.SOURCE_ROOT / "install")])
            self.assertIn("--no-pull", calls[2])
            self.assertIn("--skip-install", calls[2])
            self.assertEqual(calls[2][-2:], ["--project", str(root)])

    def test_update_records_clean_template_baselines_before_pull(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            state_path = root / ".factory/template-state.json"
            state = json.loads(state_path.read_text())
            state["files"].pop("roles/reviewer.md")
            state_path.write_text(json.dumps(state))

            with (
                mock.patch.object(
                    factory,
                    "run_text",
                    return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                code = factory.command_update(
                    argparse.Namespace(
                        project=str(root),
                        no_pull=False,
                        source_only=False,
                        accept_current=[],
                        use_upstream=False,
                        skip_install=False,
                    )
                )

            recorded = json.loads(state_path.read_text())
            self.assertEqual(code, 0)
            self.assertIn("roles/reviewer.md", recorded["files"])

    def test_update_without_pull_syncs_the_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            sync_result = {
                "updated": ["roles/reviewer.md"],
                "current": [],
                "local": [],
                "review": [],
                "added": [],
            }
            with (
                mock.patch.object(
                    factory,
                    "run_text",
                    return_value=subprocess.CompletedProcess([], 0, stdout="ok\n", stderr=""),
                ),
                mock.patch.object(factory, "sync_project_templates", return_value=sync_result) as sync,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                code = factory.command_update(
                    argparse.Namespace(
                        project=str(root),
                        no_pull=True,
                        source_only=False,
                        accept_current=[],
                        use_upstream=False,
                        skip_install=False,
                    )
                )

            self.assertEqual(code, 0)
            sync.assert_called_once_with(root.resolve(), use_upstream=False)

    def test_update_prints_copyable_review_choices(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            sync_result = {
                "updated": [],
                "current": [],
                "local": [],
                "review": ["roles/reviewer.md"],
                "added": [],
            }
            output = io.StringIO()
            with (
                mock.patch.object(
                    factory,
                    "run_text",
                    return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
                ),
                mock.patch.object(factory, "sync_project_templates", return_value=sync_result),
                contextlib.redirect_stdout(output),
            ):
                code = factory.command_update(
                    argparse.Namespace(
                        project=str(root),
                        no_pull=True,
                        source_only=False,
                        accept_current=[],
                        use_upstream=False,
                        skip_install=False,
                    )
                )

            receipt = output.getvalue()
            self.assertEqual(code, 2)
            self.assertIn("diff -u .factory/roles/reviewer.md", receipt)
            self.assertIn("factory update --no-pull --use-upstream", receipt)
            self.assertIn("--accept-current roles/reviewer.md", receipt)

    def test_start_builds_tabs_and_records_exact_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            head = self.init_git_project(root)
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
            self.assertEqual(registry["agents"]["lead"]["state"], "working")
            self.assertEqual(registry["agents"]["builder"]["surface_id"], "BUILDER-SURFACE")
            self.assertEqual(registry["agents"]["reviewer"]["surface_id"], "REVIEWER-SURFACE")
            self.assertEqual(registry["agents"]["builder"]["worktree_head"], head)
            self.assertEqual(registry["agents"]["reviewer"]["worktree_head"], head)
            self.assertTrue(Path(registry["agents"]["builder"]["worktree"]).is_dir())
            self.assertTrue(Path(registry["agents"]["reviewer"]["worktree"]).is_dir())
            self.assertEqual(registry["watchdog"]["surface_id"], "WATCHDOG-SURFACE")
            self.assertTrue(any(call[0] == "rename-tab" for call in sent))
            self.assertFalse(any("--working-directory" in call for call in sent))
            rename_calls = [call for call in sent if call[0] == "rename-tab"]
            self.assertTrue(all("--title" not in call for call in rename_calls))
            self.assertTrue(
                any(
                    call[0] == "send"
                    and call[-1].startswith("cd -- ")
                    and "run-agent" in call[-1]
                    and ".factory/worktrees/builder" in call[-1]
                    and "FACTORY_PROJECT_ROOT=" in call[-1]
                    and call[-1].startswith(f"cd -- {root.resolve()} && ")
                    and len(call[-1]) < 1000
                    for call in sent
                )
            )

    def test_run_agent_executes_the_provider_without_shell_quoting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            worktree = root / ".factory" / "worktrees" / "builder"
            worktree.mkdir(parents=True)
            with mock.patch.object(factory.os, "execvp") as execute:
                code = factory.command_run_agent(
                    argparse.Namespace(
                        project=str(root),
                        agent="builder",
                        worktree=str(worktree),
                    )
                )

            self.assertEqual(code, 0)
            executable, command = execute.call_args.args
            self.assertEqual(executable, "claude")
            self.assertEqual(command[0], "claude")
            self.assertEqual(len(command), 2)
            self.assertIn(str(worktree), command[1])
            self.assertIn('factory mail builder lead "STATUS AND EVIDENCE"', command[1])

    def test_worktree_reuse_refuses_uncommitted_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_git_project(root)
            config = factory.load_config(root)
            builder = factory.ensure_agent_worktree(root, "builder", config["agents"]["builder"])
            (builder / "unfinished.txt").write_text("not committed\n")

            with self.assertRaisesRegex(factory.FactoryError, "not clean"):
                factory.ensure_agent_worktree(root, "builder", config["agents"]["builder"])

    def test_submodule_manifest_refuses_a_commit_mismatch(self) -> None:
        mismatch = subprocess.CompletedProcess(
            ["git"],
            0,
            stdout="-" + "a" * 40 + " dependency\n",
            stderr="",
        )
        with (
            mock.patch.object(factory, "git_text", return_value=mismatch),
            self.assertRaisesRegex(factory.FactoryError, "not at its recorded commit"),
        ):
            factory.submodule_manifest(Path("/project"))

    def test_review_assignment_checks_out_the_exact_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self.init_git_project(root)
            config = factory.load_config(root)
            builder = factory.ensure_agent_worktree(root, "builder", config["agents"]["builder"])
            reviewer = factory.ensure_agent_worktree(root, "reviewer", config["agents"]["reviewer"])
            (builder / "change.txt").write_text("bounded change\n")
            subprocess.run(["git", "-C", str(builder), "add", "change.txt"], check=True)
            subprocess.run(
                [
                    "git", "-C", str(builder),
                    "-c", "user.name=Factory Test",
                    "-c", "user.email=factory@example.invalid",
                    "commit", "-qm", "Bounded change",
                ],
                check=True,
            )
            head = factory.git_head(builder)
            registry = {
                "active": True,
                "project": str(root),
                "workspace_id": "WORKSPACE",
                "lead": "lead",
                "agents": {
                    "lead": {"surface_id": "LEAD", "state": "ready", "worktree": str(root)},
                    "builder": {"surface_id": "BUILDER", "state": "idle", "worktree": str(builder)},
                    "reviewer": {"surface_id": "REVIEWER", "state": "idle", "worktree": str(reviewer)},
                },
                "watchdog": {"surface_id": "WATCHDOG", "state": "ready"},
            }
            factory.with_registry(root, lambda target: (target.clear(), target.update(registry)))

            with (
                mock.patch.dict(factory.os.environ, {"CMUX_SURFACE_ID": "LEAD"}),
                mock.patch.object(factory, "ping_recipient", return_value="stored"),
            ):
                code = factory.command_mail(
                    argparse.Namespace(
                        project=str(root),
                        sender="lead",
                        recipient="reviewer",
                        message="Review only this bounded change.",
                        kind="assignment",
                        base=base,
                        head=head,
                        urgent=False,
                    )
                )

            self.assertEqual(code, 0)
            self.assertEqual(factory.git_head(reviewer), head)
            self.assertEqual(factory.worktree_changes(reviewer), [])
            message = factory.unread_mail(root, "reviewer")[0].read_text()
            self.assertIn(f'base_sha: "{base}"', message)
            self.assertIn(f'head_sha: "{head}"', message)
            self.assertIn("submodules: []", message)
            updated, _ = factory.with_registry(root)
            self.assertEqual(updated["agents"]["reviewer"]["review_head_sha"], head)

    def test_builder_handoff_must_match_its_clean_committed_head(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = self.init_git_project(root)
            config = factory.load_config(root)
            builder = factory.ensure_agent_worktree(root, "builder", config["agents"]["builder"])
            registry = {
                "active": False,
                "project": str(root),
                "lead": "lead",
                "agents": {
                    "lead": {"state": "ready", "worktree": str(root)},
                    "builder": {
                        "state": "idle",
                        "worktree": str(builder),
                        "task_base_sha": base,
                    },
                },
            }
            factory.with_registry(root, lambda target: (target.clear(), target.update(registry)))
            (builder / "change.txt").write_text("not committed\n")

            with self.assertRaisesRegex(factory.FactoryError, "not clean"):
                factory.command_mail(
                    argparse.Namespace(
                        project=str(root),
                        sender="builder",
                        recipient="lead",
                        message="Ready for review.",
                        kind="handoff",
                        base=base,
                        head=base,
                        urgent=False,
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
            mail = factory.unread_mail(root, "lead")
            self.assertEqual(len(mail), 1)
            self.assertIn("Agent `builder` generation 1 closed", mail[0].read_text())

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

            factory.mark_turn_mail_sent(root, "builder")

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
            journal = (root / ".factory/run/watchdog.jsonl").read_text()
            self.assertIn('"phase": "STOP"', journal)
            self.assertIn("handoff_sent=true", journal)

    def test_stop_without_worker_handoff_sends_one_reminder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            self.register_factory(root)
            factory.begin_agent_turn(root, "builder")
            turns: list[tuple[str, str, str]] = []

            with mock.patch.object(
                factory,
                "send_turn",
                side_effect=lambda workspace, surface, text: turns.append((workspace, surface, text)),
            ):
                factory.handle_agent_stop(root, "builder", "STOP-1", now=100.0)

            self.assertEqual(len(turns), 1)
            self.assertEqual(turns[0][:2], ("WORKSPACE", "BUILDER"))
            self.assertIn("ended without mail to Lead", turns[0][2])
            registry, _ = factory.with_registry(root)
            builder = registry["agents"]["builder"]
            self.assertEqual(builder["state"], "working")
            self.assertEqual(builder["handoff_reminders"], 1)

    def test_duplicate_stop_does_not_send_a_second_handoff_reminder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            self.register_factory(root)
            factory.begin_agent_turn(root, "builder")

            with mock.patch.object(factory, "send_turn") as send_turn:
                factory.handle_agent_stop(root, "builder", "STOP-1", now=100.0)
                factory.handle_agent_stop(root, "builder", "STOP-2", now=100.1)

            self.assertEqual(send_turn.call_count, 1)
            journal = (root / ".factory/run/watchdog.jsonl").read_text()
            self.assertIn("duplicate Stop hook ignored", journal)

    def test_second_turn_without_worker_handoff_alerts_lead(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            self.register_factory(root)
            factory.begin_agent_turn(root, "builder")

            with (
                mock.patch.object(factory, "send_turn"),
                mock.patch.object(factory, "ping_recipient", return_value="stored"),
            ):
                factory.handle_agent_stop(root, "builder", "STOP-1", now=100.0)
                factory.record_prompt_submit(root, "builder")
                factory.handle_agent_stop(root, "builder", "STOP-2", now=102.0)

            registry, _ = factory.with_registry(root)
            self.assertEqual(registry["agents"]["builder"]["state"], "needs-attention")
            mail = factory.unread_mail(root, "lead")
            self.assertEqual(len(mail), 1)
            self.assertIn("ended two turns without the required Lead handoff", mail[0].read_text())

    def test_lead_stop_does_not_require_an_outbound_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            self.register_factory(root)

            with mock.patch.object(factory, "send_turn") as send_turn:
                factory.handle_agent_stop(root, "lead", "STOP-LEAD", now=100.0)

            send_turn.assert_not_called()
            registry, _ = factory.with_registry(root)
            self.assertEqual(registry["agents"]["lead"]["state"], "idle")

    def test_permission_request_writes_lead_mail_and_pings_an_idle_lead(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            self.register_factory(root)
            calls: list[tuple[str, ...]] = []

            event = {
                "type": "event",
                "name": "agent.hook.PermissionRequest",
                "id": "EVENT-2",
                "workspace_id": "WORKSPACE",
                "surface_id": "BUILDER",
                "payload": {"tool_name": "Bash", "command": "git status"},
            }
            with mock.patch.object(factory, "cmux", side_effect=lambda *args: (calls.append(args), {"ok": True})[1]):
                factory.handle_watch_event(root, event)

            registry, _ = factory.with_registry(root)
            self.assertEqual(registry["agents"]["builder"]["state"], "blocked")
            mail = factory.unread_mail(root, "lead")
            self.assertEqual(len(mail), 1)
            self.assertIn("git status", mail[0].read_text())
            self.assertTrue(any(call[0] == "send" and "urgent mail" in call[-1] for call in calls))

    def test_watchdog_wakes_an_idle_agent_with_unread_mail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            self.register_factory(root)
            factory.set_agent_state(root, "builder", "idle", "agent Stop hook")
            factory.write_mail(root, "lead", "builder", "message", "Please run the focused test.")
            turns: list[tuple[str, str, str]] = []

            with mock.patch.object(
                factory,
                "send_turn",
                side_effect=lambda workspace, surface, text: turns.append((workspace, surface, text)),
            ):
                counts = factory.monitor_inboxes(root, {}, {}, now=100.0)

            self.assertEqual(counts["builder"], 1)
            self.assertEqual(len(turns), 1)
            self.assertEqual(turns[0][:2], ("WORKSPACE", "BUILDER"))
            self.assertIn("1 unread message", turns[0][2])
            registry, _ = factory.with_registry(root)
            self.assertEqual(registry["agents"]["builder"]["state"], "working")
            journal = (root / ".factory/run/watchdog.jsonl").read_text()
            self.assertIn('"phase": "OBSERVE"', journal)
            self.assertIn('"phase": "DECIDE"', journal)
            self.assertIn('"phase": "ACT"', journal)
            self.assertIn('"phase": "RESULT"', journal)

    def test_watchdog_does_not_interrupt_a_working_agent_with_unread_mail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            self.register_factory(root)
            factory.set_agent_state(root, "builder", "working", "implementing the task")
            factory.write_mail(root, "lead", "builder", "message", "Use the smaller fixture.")

            with mock.patch.object(factory, "send_turn") as send_turn:
                counts = factory.monitor_inboxes(root, {}, {}, now=100.0)

            self.assertEqual(counts["builder"], 1)
            send_turn.assert_not_called()

    def test_status_includes_each_agent_inbox_volume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            self.register_factory(root)
            factory.write_mail(root, "lead", "builder", "message", "Please review the fixture.")

            with mock.patch.object(factory, "live_surface_ids", return_value={"LEAD", "BUILDER"}):
                data = factory.status_data(root)

            self.assertEqual(data["agents"]["lead"]["inbox_unread"], 0)
            self.assertEqual(data["agents"]["builder"]["inbox_unread"], 1)

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
            self.assertIn("INBOX", text)
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

    def test_mailbox_writes_reads_and_archives_messages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            self.register_factory(root, active=False)

            code = factory.command_mail(
                argparse.Namespace(
                    project=str(root),
                    sender="builder",
                    recipient="lead",
                    message="The parser change is ready for review.",
                    kind="handoff",
                    urgent=False,
                )
            )
            self.assertEqual(code, 0)
            messages = factory.unread_mail(root, "lead")
            self.assertEqual(len(messages), 1)
            self.assertTrue(messages[0].name.endswith(".builder.md"))

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = factory.command_inbox(
                    argparse.Namespace(project=str(root), agent="lead", archive=True)
                )
            self.assertEqual(code, 0)
            self.assertIn("parser change is ready", output.getvalue())
            self.assertEqual(factory.unread_mail(root, "lead"), [])
            archived = list((root / ".factory/inbox/archive/lead").glob("*.builder.md"))
            self.assertEqual(len(archived), 1)

    def test_mailbox_enforces_lead_only_routing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            self.register_factory(root, active=False)

            def send(sender: str, recipient: str) -> int:
                return factory.command_mail(
                    argparse.Namespace(
                        project=str(root),
                        sender=sender,
                        recipient=recipient,
                        message="Test message",
                        kind="message",
                        urgent=False,
                    )
                )

            self.assertEqual(send("lead", "builder"), 0)
            self.assertEqual(send("reviewer", "lead"), 0)
            self.assertEqual(send("watchdog", "lead"), 0)
            with self.assertRaisesRegex(factory.FactoryError, "only to the Lead"):
                send("builder", "reviewer")
            with self.assertRaisesRegex(factory.FactoryError, "only to the Lead"):
                send("reviewer", "builder")
            with self.assertRaisesRegex(factory.FactoryError, "themselves"):
                send("lead", "lead")

    def test_mailbox_rejects_sender_impersonation_in_an_active_factory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            self.register_factory(root)

            def send(sender: str, recipient: str) -> int:
                return factory.command_mail(
                    argparse.Namespace(
                        project=str(root),
                        sender=sender,
                        recipient=recipient,
                        message="Test message",
                        kind="message",
                        urgent=False,
                    )
                )

            with (
                mock.patch.dict(factory.os.environ, {"CMUX_SURFACE_ID": "BUILDER"}),
                mock.patch.object(factory, "ping_recipient", return_value="stored"),
            ):
                self.assertEqual(send("builder", "lead"), 0)
                registry, _ = factory.with_registry(root)
                self.assertTrue(registry["agents"]["builder"]["turn_mail_sent"])
                with self.assertRaisesRegex(factory.FactoryError, "builder, not lead"):
                    send("lead", "reviewer")

    def test_stop_interrupts_workers_and_keeps_the_lead_tab(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            self.register_factory(root)
            calls: list[tuple[str, ...]] = []

            with mock.patch.object(
                factory,
                "cmux",
                side_effect=lambda *args, **_options: calls.append(args),
            ):
                code = factory.command_stop(argparse.Namespace(project=str(root)))

            self.assertEqual(code, 0)
            stopped, _ = factory.with_registry(root)
            self.assertFalse(stopped["active"])
            self.assertEqual(stopped["agents"]["builder"]["state"], "stopped")
            surfaces = {call[4] for call in calls if call[0] == "send-key"}
            self.assertEqual(surfaces, {"BUILDER", "WATCHDOG"})

    def test_stop_bounds_each_cmux_call_and_continues_after_a_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            self.register_factory(root)
            calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

            def fake_cmux(*arguments: str, **options: object):
                calls.append((arguments, options))
                if arguments[4] == "WATCHDOG":
                    raise factory.FactoryError("command timed out after 2 seconds")
                return {"queued": True}

            output = io.StringIO()
            with (
                mock.patch.object(factory, "cmux", side_effect=fake_cmux),
                contextlib.redirect_stdout(output),
            ):
                code = factory.command_stop(argparse.Namespace(project=str(root)))

            self.assertEqual(code, 0)
            stopped, _ = factory.with_registry(root)
            self.assertFalse(stopped["active"])
            self.assertEqual(len(calls), 2)
            self.assertEqual(
                [options.get("timeout") for _, options in calls],
                [factory.STOP_CMUX_TIMEOUT_SECONDS] * 2,
            )
            self.assertIn("WARN  could not stop surface WATCHDOG", output.getvalue())

    def test_doctor_reports_machine_and_project_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.init_project(root)
            output = io.StringIO()

            def fake_run(command: list[str], *, check: bool = True):
                if "rev-parse" in command:
                    return subprocess.CompletedProcess(command, 0, stdout="a" * 40 + "\n", stderr="")
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
