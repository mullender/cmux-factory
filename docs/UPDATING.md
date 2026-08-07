# Pull factory updates

The installation uses symbolic links into the cloned repository. A fast-forward
Git pull updates the `factory` command and `/start-factory` skill in place.

## Check for local changes

Change to the installed clone and inspect it:

```sh
cd ~/.local/share/cmux-factory
git status --short
```

If the command prints local changes, commit them or move them before you pull.
Do not discard changes that you do not understand.

## Pull the update

Run:

```sh
git pull --ff-only
./install
cmux hooks setup
```

`--ff-only` stops if the local and remote histories have diverged. It does not
create an unexpected merge commit. Running `./install` again verifies the
links and adds any link that a later release needs.

## Verify the update

Run:

```sh
factory version
factory doctor
```

Start a new Codex or Claude session before you use an updated skill. A running
agent can keep the skill text that it loaded when it started.

## Understand what updates automatically

The pull updates these installed components because they are symbolic links:

- The `factory` command
- The `/start-factory` skill for Codex
- The `/start-factory` skill for Claude
- The templates used by later `factory init` commands

The pull does not change `.factory` directories in existing projects. Each
project owns those files. Apply a template change by following
[Edit agent instructions](EDIT_AGENT_INSTRUCTIONS.md#apply-a-default-change-to-an-existing-project).

## Pull changes to a project brain

If project instructions changed in the project repository, update that project
separately:

```sh
cd /path/to/project
git status --short
git pull --ff-only
```

Review changes under `.factory/` before you start the next factory session.

## Troubleshooting

### Git reports that a fast-forward is not possible

The installed clone has local commits that are not on the remote branch. Run:

```sh
git status
git log --oneline --decorate --graph --all -20
```

Review the histories before you merge, rebase, or push. Do not force-push the
shared branch.

### The command changed but an agent uses old instructions

Stop the old factory session and start a new Lead. New agents receive fresh
prompts when `factory start` launches them.

## Related guides

- [Install on a fresh machine](INSTALL.md)
- [Edit agent instructions](EDIT_AGENT_INSTRUCTIONS.md)
