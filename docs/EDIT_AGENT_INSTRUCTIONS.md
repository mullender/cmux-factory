# Edit agent instructions

Agent instructions have two scopes. Project instructions affect one project.
Template instructions become the defaults for projects that you initialize in
the future.

## Edit one project

Run these commands in the project root:

```sh
ls .factory/config .factory/roles .factory/agents
```

Edit the file that owns the rule:

| File | Purpose |
| --- | --- |
| `.factory/config/OPERATING_RULES.md` | Rules shared by all agents |
| `.factory/config/STYLE.md` | Shared writing style |
| `.factory/roles/lead.md` | Lead duties and limits |
| `.factory/roles/builder.md` | Builder duties and limits |
| `.factory/roles/reviewer.md` | Reviewer duties and limits |
| `.factory/agents/<name>/IDENTITY.md` | Durable identity notes for one agent |
| `.factory/factory.toml` | Agent labels, commands, role paths, and policy |

For example, add a project rule to `.factory/config/OPERATING_RULES.md`. Then
review the change:

```sh
git diff -- .factory/config/OPERATING_RULES.md
```

Commit project instructions in the project repository so that every machine
gets the same rules:

```sh
git add .factory/config/OPERATING_RULES.md
git commit -m "docs: update factory operating rules"
git push
```

Start a new factory session after an instruction change. Existing agents keep
the prompt that they received when they started.

## Review a session and improve the instructions

Record short feedback while the factory runs:

```sh
factory note "Keep each assignment small"
factory note "Require evidence before the Lead reports completion"
```

At the end of the session, review the feedback and current lessons:

```sh
tail -n 50 .factory/brain/FEEDBACK.jsonl
$EDITOR .factory/brain/LESSONS.md
```

Move only repeated and useful lessons into the instruction file that owns the
rule. Use `OPERATING_RULES.md` for agent behavior and `STYLE.md` for prose.
Keep one-time project facts in the brain files.

Review and commit the changes:

```sh
git diff -- .factory
git add .factory
git commit -m "docs: apply factory session lessons"
git push
```

This review is manual in the POC. The factory records evidence, but it does not
rewrite its own instructions.

## Change inbox behavior

Shared rules tell agents to check only their own inbox at turn boundaries. The
Watchdog owns terminal monitoring. Keep that boundary when you edit prompts:

```text
Watchdog -> cmux events or targeted screen checks -> recipient inbox
Lead     -> .factory/inbox/lead/ only
```

Inbox files are local runtime data. Git ignores `.factory/inbox/`. Move facts
that must survive the session into `.factory/brain/`.

## Keep Reviewer findings in scope

The Reviewer reports two separate groups:

1. Findings caused or made worse by the current change. These findings can
   block the change.
2. Pre-existing or adjacent issues. These findings go to the Lead for separate
   triage and do not block the change.

For example, a change can improve log display while the Reviewer finds a
pre-existing buffer overflow in the logging system. The Reviewer must report
the overflow as an urgent follow-up. The overflow does not block the display
change unless that change introduces or materially worsens the overflow.

Edit `.factory/roles/reviewer.md` to change this policy. Keep the two report
sections in `.factory/agents/reviewer/HANDOFF.md` so that the Lead can see the
scope boundary.

## Edit the defaults for future projects

Change to the cmux-factory clone:

```sh
cd ~/.local/share/cmux-factory
```

Edit the matching file under `templates/project/.factory/`. For example:

```text
templates/project/.factory/config/OPERATING_RULES.md
templates/project/.factory/config/STYLE.md
templates/project/.factory/roles/lead.md
templates/project/.factory/roles/builder.md
templates/project/.factory/roles/reviewer.md
```

Run the tests before you publish the new defaults:

```sh
python3 -m unittest discover -s tests -v
```

Then review, commit, and push the change:

```sh
git diff
git add templates/project/.factory
git commit -m "docs: update default agent instructions"
git push
```

Other machines can receive the change with the steps in
[Pull factory updates](UPDATING.md).

## Apply a default change to an existing project

`factory init` is idempotent. It does not replace or merge an existing
`.factory` directory. This protects project-specific instructions.

Compare a default file with the project copy:

```sh
diff -u \
  ~/.local/share/cmux-factory/templates/project/.factory/config/STYLE.md \
  .factory/config/STYLE.md
```

Apply the useful parts by hand, review the project diff, and commit it in the
project repository.

## Change an agent provider

Edit `.factory/factory.toml`. Each worker command is a string array and must
contain a separate `{prompt}` argument:

```toml
[agents.builder]
label = "Builder"
command = ["claude", "{prompt}"]
role = ".factory/roles/builder.md"
```

Run this check after the change:

```sh
factory doctor --project
```

The current POC supports command-line agents that accept a prompt argument. It
does not use a provider SDK.

## Related guides

- [Getting started](GETTING_STARTED.md)
- [Pull factory updates](UPDATING.md)
