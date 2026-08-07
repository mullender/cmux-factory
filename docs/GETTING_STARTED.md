# Getting started

Install cmux-factory first. See [Install on a fresh machine](INSTALL.md).

## Initialize a project

Run this command from any directory inside a Git project:

```sh
factory init
```

The command finds the Git root and creates `.factory` there. If a valid factory
already exists, the command prints `READY` and changes nothing. This makes the
command safe to run again.

Outside a Git project, the command uses the current directory. You can also
give it a directory:

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
cmux workspace.

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

## Next steps

- [Edit agent instructions](EDIT_AGENT_INSTRUCTIONS.md)
- [Pull factory updates](UPDATING.md)
