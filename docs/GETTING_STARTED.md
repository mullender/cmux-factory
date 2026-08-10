# Getting started

Install cmux-factory first. See [Install on a fresh machine](INSTALL.md).

## Initialize a project

Run this command from any directory inside a Git project:

```sh
factory init
```

The command finds the Git root and creates `.factory` there. If a valid factory
already exists, the command preserves project rules, refreshes safe metadata,
and prints `READY`. This makes the command safe to run again.

Outside a Git project, the command uses the current directory. You can inspect
the created files, but `factory start` needs a Git repository with at least one
commit. You can also give `factory init` a directory:

```sh
factory init /path/to/project
```

The directory must already exist. If `.factory` exists but is not a valid
factory, the command stops. It does not replace unknown files.

## Start from a normal terminal

Open the project in cmux:

```sh
cmux /path/to/project
```

In the terminal that cmux opens, start one Lead agent:

```sh
codex /start-factory
```

You can use Claude instead:

```sh
claude /start-factory
```

The Lead checks the project and starts the other agents in tabs in the same
cmux workspace. Builder starts in `.factory/worktrees/builder/`. Reviewer starts
with `.factory/worktrees/reviewer/` as its source worktree. Worker processes use
the main project root for shared factory state, then change to their named
worktree for source and Git work. The worktrees remain after `factory stop`.

## Start from an existing cmux terminal

This command creates a workspace and starts Codex as the Lead:

```sh
cmux new-workspace --name project --cwd /path/to/project \
  --command 'codex /start-factory' --focus true
```

For Claude, run:

```sh
cmux new-workspace --name project --cwd /path/to/project \
  --command 'claude /start-factory' --focus true
```

Replace `project` and `/path/to/project` with the project name and absolute
path. `factory init` prints commands with the correct values.

## Fallback prompt

If `/start-factory` is not available, start Codex or Claude and give it this
prompt:

```text
Run factory doctor --project, then run factory start. You are the Lead.
```

`factory start` must run inside cmux. The current agent tab becomes the Lead.

## Use the inbox

The Watchdog monitors agents and counts each inbox every two seconds. If an
agent is idle and has unread mail, the Watchdog wakes it. The Lead does not poll
worker terminals. Agents do not poll or wait for mail. When the Watchdog wakes
an agent, that agent reads and archives its inbox once:

```sh
factory inbox lead --archive
```

Agents can send messages without writing into another active prompt:

```sh
factory mail builder lead "I need a decision" --kind blocked --urgent
```

Builder, Reviewer, and Watchdog can send mail only to the Lead. Only the Lead
can send mail to a non-Lead agent. Workers cannot message each other. The
command rejects mail that breaks this rule.

Normal mail wakes an idle recipient through the Watchdog. It does not interrupt
a working agent. Urgent mail pings an idle recipient at once. If the recipient
is working, cmux shows a notification instead. The Watchdog writes permission
requests and closed-tab details to the Lead inbox.

Every Builder and Reviewer turn must end with a mail handoff to the Lead. The
Watchdog logs each cmux Stop hook. If a worker stops without a handoff, it sends
one reminder. If the reminder also fails, it alerts the Lead.

Use `factory status` to see each inbox count. Use `factory events --follow` to
see the Watchdog observation, decision, action, and result.

Each Stop record includes the cmux event ID, agent state, handoff state, and
reminder count. This evidence will show whether the cmux Stop hook is reliable
enough for the handoff rule.

## Assign and review a committed change

Get the Builder base from `factory status`, or use the current Builder commit.
Then send one bounded task:

```sh
factory mail lead builder "Add the focused parser test" \
  --kind assignment --base BASE_SHA
```

Builder commits the result and sends the exact range:

```sh
factory mail builder lead "Ready. Focused tests pass." \
  --kind handoff --base BASE_SHA --head HEAD_SHA
```

Send that same range to Reviewer:

```sh
factory mail lead reviewer "Review the parser test change only" \
  --kind assignment --base BASE_SHA --head HEAD_SHA
```

The assignment moves only the clean, idle Reviewer worktree. It checks out
`HEAD_SHA` in detached mode, updates submodules to the commits recorded by the
superproject, and records the commit data in the mail file. Reviewer reports on
`BASE_SHA..HEAD_SHA` and returns the same values in its handoff.

If a worker worktree has uncommitted files, the factory stops and explains the
files. It never resets them. Inspect the state with:

```sh
factory status
git -C .factory/worktrees/builder status
git -C .factory/worktrees/reviewer status
```

## Next steps

- [Edit agent instructions](EDIT_AGENT_INSTRUCTIONS.md)
- [Update cmux-factory](UPDATING.md)
