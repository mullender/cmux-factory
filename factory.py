#!/usr/bin/env python3
"""Small cmux agent factory proof of concept."""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from typing import Any, Callable


SOURCE_ROOT = Path(__file__).resolve().parent
TEMPLATE_ROOT = SOURCE_ROOT / "templates" / "project" / ".factory"
VERSION = "0.3.0.1"
TEMPLATE_STATE_FORMAT = 1
MANAGED_TEMPLATE_PATTERNS = (
    "config/*.md",
    "roles/*.md",
    "agents/*/IDENTITY.md",
)
RUNTIME_IGNORE_ENTRIES = ("run/", "inbox/", "update/", "agents/*/STATUS.json")
STOP_CMUX_TIMEOUT_SECONDS = 2.0


class FactoryError(RuntimeError):
    """A clear operator error."""


def current_source_version() -> str:
    path = SOURCE_ROOT / "VERSION"
    try:
        value = path.read_text().strip()
    except OSError:
        return VERSION
    return value or VERSION


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def find_project_root(start: Path) -> Path:
    current = start.expanduser().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".factory" / "factory.toml").is_file():
            return candidate
    raise FactoryError("no .factory/factory.toml found; run factory init in the project root")


def project_root(value: str | None) -> Path:
    return find_project_root(Path(value) if value else Path.cwd())


def initialization_root(value: str) -> Path:
    requested = Path(value).expanduser().resolve()
    if not requested.is_dir():
        raise FactoryError(f"project directory does not exist: {requested}")

    git = shutil.which("git")
    if git:
        result = run_text([git, "-C", str(requested), "rev-parse", "--show-toplevel"], check=False)
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip()).resolve()
    return requested


def print_next_steps(root: Path) -> None:
    open_project = shlex.join(["cmux", str(root)])
    codex_lead = shlex.join(["codex", "/start-factory"])
    claude_lead = shlex.join(["claude", "/start-factory"])
    codex_workspace = shlex.join(
        [
            "cmux",
            "new-workspace",
            "--name",
            root.name,
            "--cwd",
            str(root),
            "--command",
            codex_lead,
            "--focus",
            "true",
        ]
    )
    claude_workspace = shlex.join(
        [
            "cmux",
            "new-workspace",
            "--name",
            root.name,
            "--cwd",
            str(root),
            "--command",
            claude_lead,
            "--focus",
            "true",
        ]
    )

    print("NEXT  choose one path")
    print("FROM A NORMAL TERMINAL")
    print(f"  {open_project}")
    print("  Then run one command in the new cmux terminal:")
    print(f"  {codex_lead}")
    print(f"  {claude_lead}")
    print("FROM AN EXISTING CMUX TERMINAL")
    print(f"  {codex_workspace}")
    print(f"  {claude_workspace}")
    print("FALLBACK PROMPT")
    print("  Run factory doctor --project, then run factory start. You are the Lead.")


def load_config(root: Path) -> dict[str, Any]:
    path = root / ".factory" / "factory.toml"
    try:
        with path.open("rb") as stream:
            config = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise FactoryError(f"cannot read {path}: {exc}") from exc

    if config.get("version") != 1:
        raise FactoryError("factory.toml must have version = 1")
    required_files = [
        ".factory/config/OPERATING_RULES.md",
        ".factory/config/STYLE.md",
        ".factory/brain/NOW.md",
    ]
    for relative in required_files:
        if not (root / relative).is_file():
            raise FactoryError(f"factory project file is missing: {relative}")
    agents = config.get("agents")
    if not isinstance(agents, dict) or not agents:
        raise FactoryError("factory.toml must define at least one agent")
    for name in agents:
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
            raise FactoryError(f"invalid agent name: {name!r}")
    current = [name for name, data in agents.items() if isinstance(data, dict) and data.get("current") is True]
    if len(current) != 1:
        raise FactoryError("factory.toml must define exactly one current agent")
    for name, data in agents.items():
        if not isinstance(data, dict):
            raise FactoryError(f"agents.{name} must be a table")
        identity = root / ".factory" / "agents" / name / "IDENTITY.md"
        if not identity.is_file():
            raise FactoryError(f"agent identity file is missing: {identity.relative_to(root)}")
        role = data.get("role")
        if not isinstance(role, str) or not (root / role).is_file():
            raise FactoryError(f"agents.{name}.role must name an existing file")
        if not data.get("current"):
            command = data.get("command")
            if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
                raise FactoryError(f"agents.{name}.command must be a non-empty string array")
            if "{prompt}" not in command:
                raise FactoryError(f"agents.{name}.command must contain a {{prompt}} argument")
    return config


def cmux_bin() -> str:
    value = shutil.which("cmux")
    if value:
        return value
    bundled = Path("/Applications/cmux.app/Contents/Resources/bin/cmux")
    if bundled.is_file():
        return str(bundled)
    raise FactoryError("cmux is not installed or is not on PATH")


def run_text(
    command: list[str],
    *,
    check: bool = True,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise FactoryError(
            f"command timed out after {timeout:g} seconds: {shlex.join(command)}"
        ) from exc
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise FactoryError(f"command failed: {shlex.join(command)}: {detail}")
    return result


def cmux(*arguments: str, timeout: float | None = None) -> Any:
    command = [cmux_bin(), "--json", "--id-format", "uuids", *arguments]
    result = run_text(command, timeout=timeout)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FactoryError(f"cmux returned invalid JSON for {arguments[0]}") from exc


def find_value(value: Any, names: set[str]) -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in names and isinstance(item, str):
                return item
        for item in value.values():
            found = find_value(item, names)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_value(item, names)
            if found:
                return found
    return None


def runtime_dir(root: Path) -> Path:
    return root / ".factory" / "run"


def registry_path(root: Path) -> Path:
    return runtime_dir(root) / "registry.json"


def with_registry(root: Path, update: Callable[[dict[str, Any]], Any] | None = None) -> tuple[dict[str, Any], Any]:
    directory = runtime_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / "registry.lock"
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = registry_path(root)
        if path.is_file():
            try:
                data = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise FactoryError(f"cannot read {path}: {exc}") from exc
        else:
            data = {}
        result = update(data) if update else None
        if update:
            atomic_json(path, data)
        return data, result


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def atomic_text(path: Path, value: str, *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode is None and path.is_file():
        mode = path.stat().st_mode & 0o777
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def managed_template_files(template_root: Path | None = None) -> dict[str, Path]:
    source = template_root or TEMPLATE_ROOT
    files: dict[str, Path] = {}
    for pattern in MANAGED_TEMPLATE_PATTERNS:
        for path in source.glob(pattern):
            if path.is_file():
                files[path.relative_to(source).as_posix()] = path
    return dict(sorted(files.items()))


def ensure_runtime_ignore(root: Path) -> list[str]:
    path = root / ".factory" / ".gitignore"
    try:
        lines = path.read_text().splitlines() if path.is_file() else []
    except OSError as exc:
        raise FactoryError(f"cannot read {path}: {exc}") from exc
    missing = [entry for entry in RUNTIME_IGNORE_ENTRIES if entry not in lines]
    if missing:
        updated = lines + missing
        mode = None if path.is_file() else 0o644
        atomic_text(path, "\n".join(updated) + "\n", mode=mode)
    return missing


def template_state_path(root: Path) -> Path:
    return root / ".factory" / "template-state.json"


def remove_generated_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def load_template_state(root: Path) -> dict[str, Any]:
    path = template_state_path(root)
    if not path.is_file():
        return {
            "format": TEMPLATE_STATE_FORMAT,
            "factory_version": current_source_version(),
            "files": {},
        }
    try:
        state = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise FactoryError(f"cannot read {path}: {exc}") from exc
    if state.get("format") != TEMPLATE_STATE_FORMAT or not isinstance(state.get("files"), dict):
        raise FactoryError(f"unsupported template state: {path}")
    return state


def adopt_matching_template_files(root: Path, template_root: Path | None = None) -> int:
    state = load_template_state(root)
    tracked = state["files"]
    adopted = 0
    for relative, source in managed_template_files(template_root).items():
        if relative in tracked:
            continue
        project_file = root / ".factory" / relative
        source_hash = file_sha256(source)
        if source_hash is not None and file_sha256(project_file) == source_hash:
            tracked[relative] = source_hash
            adopted += 1
    state["factory_version"] = current_source_version()
    atomic_json(template_state_path(root), state)
    return adopted


def sync_project_templates(
    root: Path,
    template_root: Path | None = None,
    *,
    use_upstream: bool = False,
) -> dict[str, list[str]]:
    state = load_template_state(root)
    tracked = state["files"]
    result: dict[str, list[str]] = {
        "updated": [],
        "current": [],
        "local": [],
        "review": [],
        "added": [],
    }
    review_root = root / ".factory" / "update"

    for relative, source in managed_template_files(template_root).items():
        project_file = root / ".factory" / relative
        review_file = review_root / f"{relative}.new"
        source_hash = file_sha256(source)
        project_hash = file_sha256(project_file)
        baseline_hash = tracked.get(relative)
        if source_hash is None:
            continue

        if project_hash == source_hash:
            remove_generated_file(review_file)
            tracked[relative] = source_hash
            result["current"].append(relative)
            continue
        if project_hash is None and baseline_hash is None:
            remove_generated_file(review_file)
            atomic_text(project_file, source.read_text(), mode=source.stat().st_mode & 0o777)
            tracked[relative] = source_hash
            result["added"].append(relative)
            continue
        if baseline_hash is not None and project_hash == baseline_hash:
            remove_generated_file(review_file)
            atomic_text(project_file, source.read_text(), mode=source.stat().st_mode & 0o777)
            tracked[relative] = source_hash
            result["updated"].append(relative)
            continue
        if baseline_hash is not None and source_hash == baseline_hash:
            remove_generated_file(review_file)
            result["local"].append(relative)
            continue
        if use_upstream:
            remove_generated_file(review_file)
            atomic_text(project_file, source.read_text(), mode=source.stat().st_mode & 0o777)
            tracked[relative] = source_hash
            result["updated"].append(relative)
            continue

        atomic_text(review_file, source.read_text())
        result["review"].append(relative)

    state["factory_version"] = current_source_version()
    atomic_json(template_state_path(root), state)
    return result


def accept_current_templates(
    root: Path,
    relatives: list[str],
    template_root: Path | None = None,
) -> list[str]:
    sources = managed_template_files(template_root)
    state = load_template_state(root)
    accepted: list[str] = []
    for value in relatives:
        relative = value.removeprefix(".factory/")
        source = sources.get(relative)
        if source is None:
            raise FactoryError(f"not a managed template file: {value}")
        project_file = root / ".factory" / relative
        if not project_file.is_file():
            raise FactoryError(f"project file is missing: .factory/{relative}")
        source_hash = file_sha256(source)
        if source_hash is None:
            raise FactoryError(f"template file is missing: {source}")
        state["files"][relative] = source_hash
        remove_generated_file(root / ".factory" / "update" / f"{relative}.new")
        accepted.append(relative)
    state["factory_version"] = current_source_version()
    atomic_json(template_state_path(root), state)
    return accepted


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.write(json.dumps(value, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def read_file(root: Path, relative: str) -> str:
    path = root / relative
    try:
        return path.read_text().strip()
    except OSError as exc:
        raise FactoryError(f"cannot read {path}: {exc}") from exc


def compose_prompt(root: Path, name: str, agent: dict[str, Any]) -> str:
    config = load_config(root)
    lead_name = next(agent_name for agent_name, data in config["agents"].items() if data.get("current"))
    label = str(agent.get("label") or name.title())
    rules = read_file(root, ".factory/config/OPERATING_RULES.md")
    style = read_file(root, ".factory/config/STYLE.md")
    identity = read_file(root, f".factory/agents/{name}/IDENTITY.md")
    role = read_file(root, str(agent["role"]))
    now = read_file(root, ".factory/brain/NOW.md")
    if name == lead_name:
        mail_rule = (
            f"You can send mail to any non-Lead agent with `factory mail {name} RECIPIENT \"MESSAGE\"`. "
            "Non-Lead agents can send mail only to you."
        )
    else:
        mail_rule = (
            f"You can send mail only to the Lead with `factory mail {name} {lead_name} \"MESSAGE\"`. "
            "Do not message another non-Lead agent."
        )
    return "\n\n".join(
        [
            f"# Factory identity\n\nYou are {label}, agent `{name}`, in project `{root.name}`.",
            rules,
            style,
            identity,
            role,
            now,
            (
                "# Check-in\n\n"
                f"Run `factory check-in {name} working \"SHORT SUMMARY\"` when work starts. "
                f"Run `factory check-in {name} idle \"SHORT SUMMARY\"` when a turn ends. "
                f"Keep durable notes under `.factory/agents/{name}/`."
            ),
            (
                "# Inbox\n\n"
                f"Run `factory inbox {name}` at the start and end of each turn. "
                f"After you process all shown messages, run `factory inbox {name} --archive`. "
                f"Do not poll another agent's terminal. {mail_rule}"
            ),
        ]
    )


def wait_for_surface_text(workspace_id: str, surface_id: str, text: str, timeout: float = 3.0) -> None:
    needle = text[-80:]
    deadline = time.monotonic() + timeout
    while True:
        screen = cmux(
            "read-screen",
            "--workspace", workspace_id,
            "--surface", surface_id,
            "--lines", "20",
        )
        screen_text = find_value(screen, {"text"}) or ""
        if needle in screen_text or time.monotonic() >= deadline:
            return
        time.sleep(0.1)


def send_turn(workspace_id: str, surface_id: str, text: str) -> None:
    receipt = cmux("send", "--workspace", workspace_id, "--surface", surface_id, text)
    if isinstance(receipt, dict) and receipt.get("queued") is True:
        wait_for_surface_text(workspace_id, surface_id, text)
    cmux("send-key", "--workspace", workspace_id, "--surface", surface_id, "Enter")


def rename_tab(workspace_id: str, surface_id: str, title: str) -> None:
    cmux("rename-tab", "--workspace", workspace_id, "--surface", surface_id, title)


def new_surface(workspace_id: str, pane_id: str) -> str:
    receipt = cmux(
        "new-surface",
        "--type", "terminal",
        "--pane", pane_id,
        "--workspace", workspace_id,
        "--focus", "false",
    )
    surface_id = None
    if isinstance(receipt, dict) and isinstance(receipt.get("surface_id"), str):
        surface_id = receipt["surface_id"]
    if not surface_id:
        surface_id = find_value(receipt, {"surface_id"}) or find_value(receipt, {"id"})
    if not surface_id:
        raise FactoryError("cmux did not return the new surface ID")
    return surface_id


def set_agent_state(root: Path, name: str, state: str, reason: str) -> None:
    def update(registry: dict[str, Any]) -> None:
        agent = registry.get("agents", {}).get(name)
        if isinstance(agent, dict):
            agent["state"] = state
            agent["reason"] = reason
            agent["updated_at"] = utc_now()

    with_registry(root, update)


def command_init(args: argparse.Namespace) -> int:
    root = initialization_root(args.directory)
    target = root / ".factory"
    if target.exists():
        load_config(root)
        ensure_runtime_ignore(root)
        adopt_matching_template_files(root)
        print(f"READY {target}")
        print_next_steps(root)
        return 0
    shutil.copytree(TEMPLATE_ROOT, target)
    config = target / "factory.toml"
    config.write_text(config.read_text().replace('name = "project-name"', f'name = {json.dumps(root.name)}'))
    ensure_runtime_ignore(root)
    adopt_matching_template_files(root)
    print(f"INIT  {target}")
    print_next_steps(root)
    return 0


def command_version(_: argparse.Namespace) -> int:
    commit = run_text(["git", "-C", str(SOURCE_ROOT), "rev-parse", "--short", "HEAD"], check=False)
    dirty = run_text(["git", "-C", str(SOURCE_ROOT), "status", "--porcelain"], check=False)
    commit_text = commit.stdout.strip() if commit.returncode == 0 else "unknown"
    suffix = " dirty" if dirty.stdout.strip() else ""
    print(f"cmux-factory {VERSION}")
    print(f"source {SOURCE_ROOT}")
    print(f"git {commit_text}{suffix}")
    return 0


def print_process_output(result: subprocess.CompletedProcess[str]) -> None:
    for value in (result.stdout.strip(), result.stderr.strip()):
        if value:
            print(value)


def print_review_instructions(root: Path, relatives: list[str]) -> None:
    print("REVIEW NEXT STEPS")
    print(f"  {shlex.join(['cd', '--', str(root)])}")
    print("  Inspect each change:")
    for relative in relatives:
        print(
            "    "
            + shlex.join(
                [
                    "diff",
                    "-u",
                    f".factory/{relative}",
                    f".factory/update/{relative}.new",
                ]
            )
        )
    print("  Use every upstream rule:")
    print("    factory update --no-pull --use-upstream")
    print("  Keep or merge the current rules, then record that choice:")
    command = ["factory", "update", "--no-pull"]
    for relative in relatives:
        command.extend(["--accept-current", relative])
    print(f"    {shlex.join(command)}")


def command_update(args: argparse.Namespace) -> int:
    if args.source_only and (args.accept_current or args.use_upstream):
        raise FactoryError("--source-only cannot select a project rule resolution")
    if args.accept_current and args.use_upstream:
        raise FactoryError("--accept-current cannot be combined with --use-upstream")

    if not args.no_pull and not args.source_only:
        try:
            root = project_root(args.project)
        except FactoryError:
            if args.project is not None or args.accept_current or args.use_upstream:
                raise
        else:
            ensure_runtime_ignore(root)
            adopted = adopt_matching_template_files(root)
            if adopted:
                print(f"BASELINE recorded {adopted} clean managed file(s) before pull")

    if args.no_pull:
        print(f"SOURCE keep local files at {SOURCE_ROOT}")
    else:
        pull = run_text(["git", "-C", str(SOURCE_ROOT), "pull", "--ff-only"])
        print_process_output(pull)
        print(f"SOURCE updated {SOURCE_ROOT}")

    if not args.skip_install:
        installer = SOURCE_ROOT / "install"
        if not installer.is_file():
            raise FactoryError(f"installer is missing: {installer}")
        installed = run_text([str(installer)])
        print_process_output(installed)

    if args.source_only:
        print(f"UPDATE source-only version={current_source_version()}")
        return 0

    if not args.no_pull:
        refreshed_command = [
            sys.executable,
            str(SOURCE_ROOT / "factory.py"),
            "update",
            "--no-pull",
            "--skip-install",
        ]
        if args.project is not None:
            refreshed_command.extend(["--project", args.project])
        for relative in args.accept_current:
            refreshed_command.extend(["--accept-current", relative])
        if args.use_upstream:
            refreshed_command.append("--use-upstream")
        refreshed = run_text(refreshed_command, check=False)
        print_process_output(refreshed)
        return refreshed.returncode

    try:
        root = project_root(args.project)
    except FactoryError:
        if args.project is not None or args.accept_current or args.use_upstream:
            raise
        print("PROJECT skip; no .factory directory in the current path")
        print(f"UPDATE source version={current_source_version()}")
        return 0

    ignore_entries = ensure_runtime_ignore(root)
    if ignore_entries:
        print(f"UPDATED .factory/.gitignore: added {', '.join(ignore_entries)}")
    accepted = accept_current_templates(root, args.accept_current)
    for relative in accepted:
        print(f"ACCEPT  .factory/{relative}")
    result = sync_project_templates(root, use_upstream=args.use_upstream)
    for status in ("added", "updated", "current", "local"):
        for relative in result[status]:
            print(f"{status.upper():<7} .factory/{relative}")
    for relative in result["review"]:
        print(f"REVIEW  .factory/{relative}")
        print(f"        new template: .factory/update/{relative}.new")
    if result["review"]:
        print_review_instructions(root, result["review"])
    print(
        f"UPDATE project={root} version={current_source_version()} "
        f"updated={len(result['updated']) + len(result['added'])} "
        f"review={len(result['review'])}"
    )
    return 2 if result["review"] else 0


def doctor_check(label: str, action: Callable[[], str]) -> tuple[bool, str]:
    try:
        detail = action()
        print(f"PASS  {label}: {detail}")
        return True, detail
    except (FactoryError, OSError, ValueError) as exc:
        print(f"FAIL  {label}: {exc}")
        return False, str(exc)


def command_doctor(args: argparse.Namespace) -> int:
    results: list[bool] = []

    ok, _ = doctor_check("cmux binary", lambda: cmux_bin())
    results.append(ok)

    def ping() -> str:
        result = run_text([cmux_bin(), "ping"])
        if result.stdout.strip() != "PONG":
            raise FactoryError(f"expected PONG, got {result.stdout.strip()!r}")
        return "PONG"

    ok, _ = doctor_check("cmux socket", ping)
    results.append(ok)

    try:
        root = project_root(args.project)
    except FactoryError as exc:
        if args.project is not None:
            print(f"FAIL  project: {exc}")
            results.append(False)
        else:
            print("SKIP  project: no .factory directory in the current path")
        return 0 if all(results) else 1

    ok, _ = doctor_check("project config", lambda: f"{load_config(root)['name']} (version 1)")
    results.append(ok)
    if ok:
        config = load_config(root)
        for name, agent in config["agents"].items():
            if agent.get("current"):
                continue
            command = agent["command"][0]

            def locate(command: str = command) -> str:
                found = shutil.which(command)
                if not found:
                    raise FactoryError(f"{command} is not on PATH")
                return found

            check_ok, _ = doctor_check(f"agent {name}", locate)
            results.append(check_ok)

    ignore = root / ".factory" / ".gitignore"

    def check_ignore() -> str:
        text = ignore.read_text()
        required = set(RUNTIME_IGNORE_ENTRIES)
        missing = sorted(item for item in required if item not in text.splitlines())
        if missing:
            raise FactoryError(f"missing entries: {', '.join(missing)}")
        return str(ignore)

    ok, _ = doctor_check("runtime ignore", check_ignore)
    results.append(ok)
    return 0 if all(results) else 1


def command_start(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    config = load_config(root)
    identity = cmux("identify")
    caller = identity.get("caller") if isinstance(identity, dict) else None
    if not isinstance(caller, dict):
        raise FactoryError("cmux identify did not return caller identity")
    workspace_id = caller.get("workspace_id")
    pane_id = caller.get("pane_id")
    lead_surface_id = caller.get("surface_id")
    window_id = caller.get("window_id")
    if not all(isinstance(item, str) and item for item in (workspace_id, pane_id, lead_surface_id, window_id)):
        raise FactoryError("factory start must run from a terminal inside cmux")

    existing, _ = with_registry(root)
    if existing.get("active"):
        if existing.get("workspace_id") == workspace_id:
            print("READY factory is already active in this workspace")
            return command_status(argparse.Namespace(project=str(root), json=False))
        raise FactoryError("factory is active in another workspace; run factory stop first")

    agents: dict[str, Any] = {}
    current_name = next(name for name, data in config["agents"].items() if data.get("current"))
    current_agent = config["agents"][current_name]
    current_label = str(current_agent.get("label") or current_name.title())
    rename_tab(workspace_id, lead_surface_id, f"{current_label} · {root.name}")
    agents[current_name] = {
        "generation": 1,
        "label": current_label,
        "surface_id": lead_surface_id,
        "state": "working",
        "reason": "current session registered as Lead",
        "current": True,
        "updated_at": utc_now(),
    }

    for name, agent in config["agents"].items():
        if agent.get("current"):
            continue
        label = str(agent.get("label") or name.title())
        surface_id = new_surface(workspace_id, pane_id)
        rename_tab(workspace_id, surface_id, f"{label} · {root.name}")
        agents[name] = {
            "generation": 1,
            "label": label,
            "surface_id": surface_id,
            "state": "starting",
            "reason": "surface created",
            "current": False,
            "updated_at": utc_now(),
        }

    watchdog_surface_id = new_surface(workspace_id, pane_id)
    rename_tab(workspace_id, watchdog_surface_id, f"Watchdog · {root.name}")
    registry = {
        "format": 1,
        "active": True,
        "project": str(root),
        "workspace_id": workspace_id,
        "window_id": window_id,
        "pane_id": pane_id,
        "lead": current_name,
        "agents": agents,
        "watchdog": {"surface_id": watchdog_surface_id, "state": "starting"},
        "started_at": utc_now(),
    }
    with_registry(root, lambda target: (target.clear(), target.update(registry)))

    for name, agent in config["agents"].items():
        if agent.get("current"):
            continue
        prompt = compose_prompt(root, name, agent)
        command = [prompt if item == "{prompt}" else item for item in agent["command"]]
        launch = f"cd -- {shlex.quote(str(root))} && {shlex.join(command)}"
        send_turn(workspace_id, agents[name]["surface_id"], launch)
        set_agent_state(root, name, "launched", f"launched {command[0]}")

    watch_command = shlex.join(
        [sys.executable, str(SOURCE_ROOT / "factory.py"), "watch", "--project", str(root)]
    )
    watchdog_launch = f"cd -- {shlex.quote(str(root))} && {watch_command}"
    send_turn(workspace_id, watchdog_surface_id, watchdog_launch)

    def watchdog_ready(data: dict[str, Any]) -> None:
        data["watchdog"]["state"] = "launched"
        data["watchdog"]["updated_at"] = utc_now()

    with_registry(root, watchdog_ready)
    print(f"START workspace={workspace_id} pane={pane_id}")
    for name, data in agents.items():
        print(f"AGENT {name:<10} g{data['generation']} surface={data['surface_id']}")
    print(f"WATCH surface={watchdog_surface_id}")
    print("LIMIT watchdog reports failures but does not restart agents")
    return 0


def live_surface_ids(workspace_id: str) -> set[str]:
    health = cmux("surface-health", "--workspace", workspace_id)
    surfaces = health.get("surfaces") if isinstance(health, dict) else None
    if not isinstance(surfaces, list):
        raise FactoryError("cmux surface-health returned malformed data")
    return {item["id"] for item in surfaces if isinstance(item, dict) and isinstance(item.get("id"), str)}


def last_journal_record(root: Path) -> dict[str, Any] | None:
    path = runtime_dir(root) / "watchdog.jsonl"
    if not path.is_file():
        return None
    lines = [line for line in path.read_text().splitlines() if line.strip()]
    if not lines:
        return None
    try:
        value = json.loads(lines[-1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def status_data(root: Path) -> dict[str, Any]:
    registry, _ = with_registry(root)
    if not registry:
        return {"active": False, "project": str(root), "agents": {}}
    live: set[str] = set()
    health_error = None
    if registry.get("active") and isinstance(registry.get("workspace_id"), str):
        try:
            live = live_surface_ids(registry["workspace_id"])
        except FactoryError as exc:
            health_error = str(exc)
    result = dict(registry)
    result["health_error"] = health_error
    result["last_watchdog_record"] = last_journal_record(root)
    result_agents: dict[str, Any] = {}
    for name, agent in registry.get("agents", {}).items():
        if not isinstance(agent, dict):
            continue
        item = dict(agent)
        item["surface_live"] = item.get("surface_id") in live
        result_agents[name] = item
    result["agents"] = result_agents
    return result


def command_status(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    data = status_data(root)
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0
    print(f"FACTORY {Path(data['project']).name} active={str(data.get('active', False)).lower()}")
    if data.get("workspace_id"):
        print(f"WORKSPACE {data['workspace_id']}")
    print("AGENT       GEN  STATE            LIVE  REASON")
    for name, agent in data.get("agents", {}).items():
        print(
            f"{name:<11} {agent.get('generation', '-'):>3}  "
            f"{str(agent.get('state', 'unknown')):<16} "
            f"{str(agent.get('surface_live', False)).lower():<5} "
            f"{agent.get('reason', '')}"
        )
    record = data.get("last_watchdog_record")
    if isinstance(record, dict):
        print(
            f"WATCHDOG {record.get('at', '?')} {record.get('phase', '?')} "
            f"{record.get('agent', '-')} {record.get('message', '')}"
        )
    elif data.get("active"):
        print("WATCHDOG no journal record yet")
    if data.get("health_error"):
        print(f"HEALTH ERROR {data['health_error']}")
    return 0


def journal(root: Path, phase: str, message: str, *, agent: str | None = None, **extra: Any) -> None:
    record = {"at": utc_now(), "phase": phase, "message": message}
    if agent:
        record["agent"] = agent
    record.update(extra)
    append_jsonl(runtime_dir(root) / "watchdog.jsonl", record)
    name = agent or "-"
    print(f"{record['at']} {phase:<7} {name:<10} {message}", flush=True)


def agent_for_surface(registry: dict[str, Any], surface_id: str | None) -> str | None:
    if not surface_id:
        return None
    for name, agent in registry.get("agents", {}).items():
        if isinstance(agent, dict) and agent.get("surface_id") == surface_id:
            return name
    return None


def inbox_dir(root: Path, recipient: str) -> Path:
    return root / ".factory" / "inbox" / recipient


def unread_mail(root: Path, recipient: str) -> list[Path]:
    directory = inbox_dir(root, recipient)
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob("*.md") if path.is_file())


def write_mail(root: Path, sender: str, recipient: str, kind: str, message: str) -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = inbox_dir(root, recipient) / f"{stamp}.{sender}.md"
    content = (
        f"---\nfrom: {sender}\nto: {recipient}\nat: {utc_now()}\nkind: {kind}\n---\n\n"
        f"{message.strip()}\n"
    )
    atomic_text(path, content)
    return path


def ping_recipient(root: Path, recipient: str, *, urgent: bool) -> str:
    registry, _ = with_registry(root)
    if not registry.get("active"):
        return "stored"
    agent = registry.get("agents", {}).get(recipient)
    workspace_id = registry.get("workspace_id")
    if not isinstance(agent, dict) or not isinstance(workspace_id, str):
        return "stored"
    surface_id = agent.get("surface_id")
    if not isinstance(surface_id, str):
        return "stored"

    if urgent and agent.get("state") in {"ready", "idle"}:
        send_turn(
            workspace_id,
            surface_id,
            f"Factory inbox: urgent mail for {recipient}. Run `factory inbox {recipient} --archive`.",
        )
        return "agent pinged"

    if urgent:
        cmux(
            "notify",
            "--title", f"cmux-factory mail for {recipient}",
            "--body", f"Urgent factory mail is waiting in .factory/inbox/{recipient}/",
            "--workspace", workspace_id,
            "--surface", surface_id,
        )
        return "user notified"
    return "stored"


def handle_watch_event(root: Path, event: dict[str, Any]) -> None:
    registry, _ = with_registry(root)
    if event.get("workspace_id") != registry.get("workspace_id"):
        return
    name = agent_for_surface(registry, event.get("surface_id"))
    if not name:
        return
    event_name = str(event.get("name") or "unknown")
    journal(root, "OBSERVE", event_name, agent=name, event_id=event.get("id"))
    if event_name == "surface.closed":
        reason = "registered agent surface closed"
        set_agent_state(root, name, "needs-attention", reason)
        journal(root, "DECIDE", "mark needs-attention; automatic restart is disabled", agent=name)
        lead_name = registry.get("lead")
        if isinstance(lead_name, str):
            generation = registry.get("agents", {}).get(name, {}).get("generation", "?")
            message = (
                f"Agent `{name}` generation {generation} closed. Automatic restart is disabled in "
                "the proof of concept. Preserve its handoff and tell the user."
            )
            mail = write_mail(root, "watchdog", lead_name, "surface-closed", message)
            action = ping_recipient(root, lead_name, urgent=True)
            journal(root, "ACT", f"wrote {mail.relative_to(root)}; {action}", agent=name)
        journal(root, "RESULT", "Lead inbox contains the failure details", agent=name)
    elif event_name.startswith("agent.hook."):
        hook = event_name.removeprefix("agent.hook.")
        if hook == "PermissionRequest":
            set_agent_state(root, name, "blocked", "agent permission request")
            lead_name = registry.get("lead")
            if isinstance(lead_name, str):
                payload = json.dumps(event.get("payload", {}), indent=2, sort_keys=True)
                message = (
                    f"Agent `{name}` is waiting for permission on surface `{event.get('surface_id', '?')}`.\n\n"
                    f"Event `{event.get('id', '?')}` details:\n\n```json\n{payload}\n```"
                )
                mail = write_mail(root, "watchdog", lead_name, "permission", message)
                action = ping_recipient(root, lead_name, urgent=True)
                journal(root, "ACT", f"wrote {mail.relative_to(root)}; {action}", agent=name)
            journal(root, "RESULT", "Lead inbox contains the permission request", agent=name)
        elif hook == "Stop":
            set_agent_state(root, name, "idle", "agent Stop hook")
        elif hook in {"UserPromptSubmit", "PreToolUse"}:
            set_agent_state(root, name, "working", f"agent {hook} hook")


def command_watch(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    registry, _ = with_registry(root)
    if not registry.get("active"):
        raise FactoryError("factory is not active")
    cursor = runtime_dir(root) / "events.cursor"
    journal(root, "START", "watchdog event stream started")
    command = [
        cmux_bin(), "events",
        "--category", "agent",
        "--category", "surface",
        "--cursor-file", str(cursor),
        "--reconnect",
        "--no-ack",
        "--no-heartbeat",
    ]
    process = subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert process.stdout is not None
    try:
        for line in process.stdout:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                journal(root, "ERROR", f"invalid event line: {line.strip()[:120]}")
                continue
            if isinstance(event, dict) and event.get("type") == "event":
                handle_watch_event(root, event)
    except KeyboardInterrupt:
        journal(root, "STOP", "watchdog interrupted")
    finally:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
    return 0


def command_events(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    path = runtime_dir(root) / "watchdog.jsonl"
    position = 0
    while True:
        if path.is_file():
            with path.open() as stream:
                stream.seek(position)
                while True:
                    line = stream.readline()
                    if not line:
                        break
                    position = stream.tell()
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        print(line.rstrip())
                        continue
                    print(
                        f"{record.get('at', '?')} {record.get('phase', '?'):<7} "
                        f"{record.get('agent', '-'):<10} {record.get('message', '')}",
                        flush=True,
                    )
        if not args.follow:
            return 0
        time.sleep(0.25)


def command_check_in(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    registry, _ = with_registry(root)
    if args.agent not in registry.get("agents", {}):
        raise FactoryError(f"unknown registered agent: {args.agent}")
    status = {
        "agent": args.agent,
        "state": args.state,
        "summary": args.summary,
        "updated_at": utc_now(),
    }
    atomic_json(root / ".factory" / "agents" / args.agent / "STATUS.json", status)
    set_agent_state(root, args.agent, args.state, args.summary)
    print(f"CHECK-IN {args.agent} {args.state}: {args.summary}")
    return 0


def command_note(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    record = {"at": utc_now(), "note": args.text}
    append_jsonl(root / ".factory" / "brain" / "FEEDBACK.jsonl", record)
    print(f"NOTE  {record['at']} {args.text}")
    return 0


def command_mail(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    agents = load_config(root)["agents"]
    lead_name = next(name for name, data in agents.items() if data.get("current"))
    if args.sender not in agents and args.sender != "watchdog":
        raise FactoryError(f"unknown mail sender: {args.sender}")
    if args.recipient not in agents:
        raise FactoryError(f"unknown mail recipient: {args.recipient}")
    registry, _ = with_registry(root)
    if registry.get("active"):
        surface_id = os.environ.get("CMUX_SURFACE_ID")
        actual_sender = agent_for_surface(registry, surface_id)
        watchdog = registry.get("watchdog")
        if (
            actual_sender is None
            and isinstance(watchdog, dict)
            and watchdog.get("surface_id") == surface_id
        ):
            actual_sender = "watchdog"
        if actual_sender is None:
            raise FactoryError("cannot verify the mail sender from this cmux surface")
        if actual_sender != args.sender:
            raise FactoryError(f"mail sender is {actual_sender}, not {args.sender}")
    if args.sender == args.recipient:
        raise FactoryError("agents cannot send mail to themselves")
    if args.sender != lead_name and args.recipient != lead_name:
        raise FactoryError(f"{args.sender} can send mail only to the Lead ({lead_name})")
    path = write_mail(root, args.sender, args.recipient, args.kind, args.message)
    action = ping_recipient(root, args.recipient, urgent=args.urgent)
    print(f"MAIL  {path.relative_to(root)}; {action}")
    return 0


def command_inbox(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    agents = load_config(root)["agents"]
    if args.agent not in agents:
        raise FactoryError(f"unknown inbox agent: {args.agent}")
    messages = unread_mail(root, args.agent)
    print(f"INBOX {args.agent} unread={len(messages)}")
    if not messages:
        return 0

    archive = root / ".factory" / "inbox" / "archive" / args.agent
    if args.archive:
        archive.mkdir(parents=True, exist_ok=True)
    for path in messages:
        print(f"--- {path.name} ---")
        print(path.read_text().rstrip())
        if args.archive:
            path.replace(archive / path.name)
    if args.archive:
        print(f"ARCHIVE {len(messages)} message(s) -> {archive.relative_to(root)}")
    return 0


def command_stop(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    registry, _ = with_registry(root)
    if not registry.get("active"):
        print("STOP  factory is not active")
        return 0
    workspace_id = registry.get("workspace_id")
    surfaces: list[str] = []
    watchdog = registry.get("watchdog")
    if isinstance(watchdog, dict) and isinstance(watchdog.get("surface_id"), str):
        surfaces.append(watchdog["surface_id"])
    for agent in registry.get("agents", {}).values():
        if isinstance(agent, dict) and not agent.get("current") and isinstance(agent.get("surface_id"), str):
            surfaces.append(agent["surface_id"])
    for surface_id in surfaces:
        try:
            cmux(
                "send-key",
                "--workspace",
                workspace_id,
                "--surface",
                surface_id,
                "ctrl+c",
                timeout=STOP_CMUX_TIMEOUT_SECONDS,
            )
        except FactoryError as exc:
            print(f"WARN  could not stop surface {surface_id}: {exc}")

    def stop(data: dict[str, Any]) -> None:
        data["active"] = False
        data["stopped_at"] = utc_now()
        for agent in data.get("agents", {}).values():
            if isinstance(agent, dict) and not agent.get("current"):
                agent["state"] = "stopped"
                agent["reason"] = "factory stop requested"

    with_registry(root, stop)
    print("STOP  watchdog and worker processes interrupted; tabs remain open")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="factory")
    subparsers = result.add_subparsers(dest="command", required=True)

    def add_project_option(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument(
            "--project",
            nargs="?",
            const=".",
            help="require a project at this path; defaults to the nearest .factory directory",
        )

    init = subparsers.add_parser("init", help="create .factory in a project")
    init.add_argument("directory", nargs="?", default=".")
    init.set_defaults(handler=command_init)

    version = subparsers.add_parser("version", help="show source and version")
    version.set_defaults(handler=command_version)

    update = subparsers.add_parser("update", help="update the factory source, links, and project rules")
    add_project_option(update)
    update.add_argument("--no-pull", action="store_true", help="use the current local factory source")
    update.add_argument("--source-only", action="store_true", help="do not update a project .factory directory")
    update.add_argument(
        "--accept-current",
        action="append",
        default=[],
        metavar="FILE",
        help="keep a reviewed project file and mark the latest template as handled",
    )
    update.add_argument(
        "--use-upstream",
        action="store_true",
        help="replace every rule that requires review with its upstream template",
    )
    update.add_argument("--skip-install", action="store_true", help=argparse.SUPPRESS)
    update.set_defaults(handler=command_update)

    doctor = subparsers.add_parser("doctor", help="check machine and project setup")
    add_project_option(doctor)
    doctor.set_defaults(handler=command_doctor)

    start = subparsers.add_parser("start", help="start agents in the current cmux pane")
    add_project_option(start)
    start.set_defaults(handler=command_start)

    status = subparsers.add_parser("status", help="show agent and watchdog state")
    add_project_option(status)
    status.add_argument("--json", action="store_true")
    status.set_defaults(handler=command_status)

    watch = subparsers.add_parser("watch", help="run the watchdog event loop")
    add_project_option(watch)
    watch.set_defaults(handler=command_watch)

    events = subparsers.add_parser("events", help="read the watchdog journal")
    add_project_option(events)
    events.add_argument("--follow", action="store_true")
    events.set_defaults(handler=command_events)

    check_in = subparsers.add_parser("check-in", help="record agent progress")
    add_project_option(check_in)
    check_in.add_argument("agent")
    check_in.add_argument("state", choices=["starting", "working", "blocked", "idle", "done"])
    check_in.add_argument("summary")
    check_in.set_defaults(handler=command_check_in)

    note = subparsers.add_parser("note", help="record process feedback")
    add_project_option(note)
    note.add_argument("text")
    note.set_defaults(handler=command_note)

    mail = subparsers.add_parser("mail", help="write a message to an agent inbox")
    add_project_option(mail)
    mail.add_argument("sender")
    mail.add_argument("recipient")
    mail.add_argument("message")
    mail.add_argument("--kind", choices=["message", "blocked", "permission", "handoff"], default="message")
    mail.add_argument("--urgent", action="store_true", help="ping an idle recipient or notify the user")
    mail.set_defaults(handler=command_mail)

    inbox = subparsers.add_parser("inbox", help="read one agent inbox")
    add_project_option(inbox)
    inbox.add_argument("agent")
    inbox.add_argument("--archive", action="store_true", help="archive all messages after printing them")
    inbox.set_defaults(handler=command_inbox)

    stop = subparsers.add_parser("stop", help="interrupt workers and watchdog")
    add_project_option(stop)
    stop.set_defaults(handler=command_stop)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except FactoryError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
