# cmux-factory

`cmux-factory` is a small cmux harness for named coding agents and a shared
project brain.

The user talks to one lead agent. The lead assigns work to agents in other tabs.
All agents read and write plain files under `.factory/`.

## Proof-of-concept scope

The proof of concept does nine things:

1. It uses the current cmux tab as the Lead.
2. It creates Builder, Reviewer, and Watchdog tabs in the same pane.
3. It launches each configured agent with its role prompt.
4. It records exact cmux workspace, pane, and surface IDs.
5. It shows a readable watchdog journal and status report.
6. It sends agent messages through local inbox files.
7. It wakes an idle agent when that agent has unread mail.
8. It requires each non-Lead turn to end with mail to the Lead.
9. It gives Builder and Reviewer separate Git worktrees.

The watchdog reports a closed agent surface and tells the Lead. It does not
restart the agent in this version. Recovery comes after the launch and
observation loop works in real use.

## Monitoring and mail

The Watchdog monitors agents. It uses the structured `cmux events` stream first
and can use a targeted `read-screen` when an event lacks enough detail. The
Lead does not poll worker terminals.

Agents exchange files under `.factory/inbox/<recipient>/`. Agents do not poll or
wait for mail. The Watchdog counts unread mail every two seconds. If an agent is
idle and its inbox is not empty, the Watchdog sends one short wake-up turn. It
does not interrupt a working agent. It retries after 30 seconds if the agent
becomes idle without clearing the inbox.

Every non-Lead turn must send mail to the Lead before cmux emits its Stop hook.
The Watchdog logs each Stop event and whether that turn sent a handoff. If it did
not, the Watchdog sends one reminder turn. If that turn also ends without mail,
the Watchdog marks the agent as needing attention and alerts the Lead.

```text
STOP    builder    hook received event=... state=working handoff_sent=false reminders=0
DECIDE  builder    wake worker because Stop had no Lead handoff
```

`factory status` shows the current unread count for each agent. The Watchdog
journal records count changes, each wake-up decision, each action, and its
result. It also records an inbox count summary every 60 seconds.

Urgent mail still has a direct path. It pings an idle recipient at once. If the
recipient is working, cmux shows a notification and does not type into the
active prompt.

Mail uses a Lead-centered topology. Builder, Reviewer, and Watchdog can send
mail only to the Lead. Only the Lead can send mail to a non-Lead agent. The
`factory mail` command enforces this rule.

Git ignores the inbox because a permission event can contain command text.
Durable facts and lessons stay under `.factory/brain/`.

```sh
factory status
factory mail lead builder "Please add the focused test" \
  --kind assignment --base BASE_SHA
factory mail builder lead "The change is ready for review" \
  --kind handoff --base BASE_SHA --head HEAD_SHA
factory inbox lead --archive
```

## Commit-based review

Builder works on the persistent `factory/builder` branch in
`.factory/worktrees/builder/`. Reviewer uses a detached worktree in
`.factory/worktrees/reviewer/`. A review assignment checks out the exact head
commit and its recorded submodule commits before it sends mail to Reviewer.
Worker processes start in the main project root so they can use shared factory
state. Their prompts require source and Git work in the named worktree.

Only Lead can push code. Builder and Reviewer hand off commits and never push.
Lead asks for permission before each push that updates an open pull request in
a public repository.

```sh
factory mail lead reviewer "Review this parser change only" \
  --kind assignment --base BASE_SHA --head HEAD_SHA
```

The factory refuses to move or reuse a dirty worker worktree. It does not reset,
merge, rebase, cherry-pick, or remove worktrees. `factory status` shows each
worktree path, commit, and clean state.

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

The installer creates symlinks. Update the source, links, and the nearest
project rules with:

```sh
factory update
```

The command uses `git pull --ff-only`. It keeps project-specific rule changes
and writes a `.new` file when both the project and central template changed.

## Documentation

- [Task-based tutorial site](https://mullender.github.io/cmux-factory/)
- [Install on a fresh machine](docs/INSTALL.md)
- [Getting started](docs/GETTING_STARTED.md)
- [Edit agent instructions](docs/EDIT_AGENT_INSTRUCTIONS.md)
- [Update cmux-factory](docs/UPDATING.md)

## Start a project

Run `factory init` from any directory inside a Git project. It finds the Git
root. If the factory already exists and has a valid configuration, it preserves
project rules, refreshes safe metadata, and prints `READY`.

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
factory update
factory update --no-pull --use-upstream  # accept all reviewed upstream rules
factory events --follow
factory check-in builder working "Investigating the parser"
factory mail builder lead "The parser is ready" \
  --kind handoff --base BASE_SHA --head HEAD_SHA
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
- No automatic merge, rebase, reset, or worktree cleanup
- No message queue
- No GitHub watcher
- No database
- No background updater

These limits are deliberate. Add a mechanism only after an observed failure
shows that it is needed.
