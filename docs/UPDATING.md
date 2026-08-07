# Update cmux-factory

The update command refreshes the factory source, installed links, and managed
project rules. Run it from a project directory:

```sh
factory update
```

The command performs these steps:

1. Run `git pull --ff-only` in the cmux-factory clone.
2. Run the installer again to verify command and skill links.
3. Add required runtime ignore entries.
4. Update managed project rules that the project did not change.
5. Keep project-specific rules and report files that need review.

Start a new Lead after an update. Running agents keep the prompt that they
received when they started.

## Understand managed files

The factory manages these template files:

```text
.factory/config/*.md
.factory/roles/*.md
.factory/agents/*/IDENTITY.md
```

It does not update project state, handoffs, brain files, or `factory.toml`.
It does not remove an old managed file when the central template removes it.
Review and remove obsolete files by hand.
Project-specific provider commands and agent names stay unchanged.

The factory records template hashes in `.factory/template-state.json`. Commit
this file with the project brain so that another machine can make the same safe
update decision.

## Understand update decisions

For each managed file, the command prints one status:

- `CURRENT`: the project already has the latest template.
- `UPDATED`: only the central template changed, so the project file changed.
- `LOCAL`: only the project changed, so the project file stayed unchanged.
- `ADDED`: the central template added a managed file.
- `REVIEW`: both sides changed, or an old project has no safe baseline.

When the command prints `REVIEW`, it leaves the project file unchanged and
writes the new template under `.factory/update/`:

```text
REVIEW  .factory/roles/reviewer.md
        new template: .factory/update/roles/reviewer.md.new
```

The command exits with status 2 when review is required.

## Resolve a rule conflict

Compare the project rule with the new template:

```sh
diff -u \
  .factory/roles/reviewer.md \
  .factory/update/roles/reviewer.md.new
```

Choose one resolution.

To use the central template, copy it over the project file and run the update
again without pulling:

```sh
cp .factory/update/roles/reviewer.md.new \
  .factory/roles/reviewer.md
factory update --no-pull
```

To keep or merge the project rule, edit it and mark the latest template as
reviewed:

```sh
$EDITOR .factory/roles/reviewer.md
factory update --no-pull \
  --accept-current roles/reviewer.md
```

Review and commit the project changes:

```sh
git diff -- .factory
git add .factory
git commit -m "chore: update factory rules"
git push
```

## Test local template edits

Use the current clone without a Git pull:

```sh
cd /path/to/project
factory update --no-pull
```

This is useful while you edit files under
`templates/project/.factory/` in the factory clone.

## Update only commands and skills

Run:

```sh
factory update --source-only
```

This updates the source and installer links but does not change a project.

## Update an explicit project

Run:

```sh
factory update --project /path/to/project
```

## Troubleshooting

### Git cannot fast-forward

The factory clone has local commits or a different history. Inspect it before
you merge or rebase:

```sh
cd ~/.local/share/cmux-factory
git status
git log --oneline --decorate --graph --all -20
```

The update command does not force-push, reset, or discard local changes.

### An old project has no template state

The command adopts files that exactly match the latest template. It marks
different files as `REVIEW` because it cannot know whether they are old or
project-specific. Resolve each reported file once. Later updates can then make
safe decisions from the recorded baseline.

## Related guides

- [Install on a fresh machine](INSTALL.md)
- [Edit agent instructions](EDIT_AGENT_INSTRUCTIONS.md)
