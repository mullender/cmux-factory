# cmux-factory

`cmux-factory` is a small cmux harness for named coding agents and a shared
project brain.

The user talks to one lead agent. The lead assigns work to agents in other tabs.
All agents read and write plain files under `.factory/`.

## Proof-of-concept scope

The proof of concept does six things:

1. It uses the current cmux tab as the Lead.
2. It creates Builder, Reviewer, and Watchdog tabs in the same pane.
3. It launches each configured agent with its role prompt.
4. It records exact cmux workspace, pane, and surface IDs.
5. It shows a readable watchdog journal and status report.
6. It sends agent messages through local inbox files.

The watchdog reports a closed agent surface and tells the Lead. It does not
restart the agent in this version. Recovery comes after the launch and
observation loop works in real use.

## Monitoring and mail

The Watchdog monitors agents. It uses the structured `cmux events` stream first
and can use a targeted `read-screen` when an event lacks enough detail. The
Lead does not poll worker terminals.

Agents exchange files under `.factory/inbox/<recipient>/`. The Lead checks only
`.factory/inbox/lead/` at turn boundaries. An urgent Watchdog message can send
one short ping to an idle Lead. If the Lead is working, cmux shows a
notification and does not type into the active prompt.

Git ignores the inbox because a permission event can contain command text.
Durable facts and lessons stay under `.factory/brain/`.

```sh
factory mail builder lead "The change is ready for review" --kind handoff
factory inbox lead
factory inbox lead --archive
```

## Install

For a new machine, follow [Install on a fresh machine](docs/INSTALL.md).

```sh
git clone https://github.com/mullender/cmux-factory.git \
  ~/.local/share/cmux-factory
cd ~/.local/share/cmux-factory
./install
cmux hooks setup
factory doctor
```

The installer creates symlinks. A later `git pull --ff-only` updates the
installed command and skills in place.

## Documentation

- [Task-based tutorial site](https://mullender.github.io/cmux-factory/)
- [Install on a fresh machine](docs/INSTALL.md)
- [Getting started](docs/GETTING_STARTED.md)
- [Edit agent instructions](docs/EDIT_AGENT_INSTRUCTIONS.md)
- [Pull factory updates](docs/UPDATING.md)

## Start a project

Run `factory init` from any directory inside a Git project. It finds the Git
root. If the factory already exists and has a valid configuration, it changes
nothing and prints `READY`.

```sh
factory init
```

The command prints the next steps. You can open the project from a normal
terminal:

```sh
cmux /path/to/project
```

Then start a Lead in the new cmux terminal:

```sh
codex /start-factory
# Or:
claude /start-factory
```

From an existing cmux terminal, one command can create the workspace and start
the Lead:

```sh
cmux new-workspace --name project --cwd /path/to/project \
  --command 'codex /start-factory' --focus true
```

See [Getting started](docs/GETTING_STARTED.md) for the full workflow and the
Claude equivalent. See [Edit agent instructions](docs/EDIT_AGENT_INSTRUCTIONS.md)
to change shared rules, writing style, roles, identities, or provider commands.

Useful commands:

```sh
factory status
factory events --follow
factory check-in builder working "Investigating the parser"
factory mail builder lead "The parser is ready" --kind handoff
factory inbox lead --archive
factory note "Builder proposed a service when one function was enough"
factory stop
```

## Development

The program uses the Python standard library. Run the tests with:

```sh
python3 -m unittest discover -s tests -v
```

The tutorial site is plain HTML, CSS, and JavaScript under `docs/`. Preview it
locally with:

```sh
python3 -m http.server 8000 --directory docs
```

GitHub Pages must use the `main` branch and `/docs` directory.

## Current limits

- No automatic restart
- No worktree management
- No message queue
- No GitHub watcher
- No database
- No background updater

These limits are deliberate. Add a mechanism only after an observed failure
shows that it is needed.
