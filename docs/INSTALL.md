# Install on a fresh machine

This guide installs cmux-factory and verifies that it can reach cmux and your
agent commands.

## Prerequisites

Install these tools first:

- cmux, with the `cmux` command available
- Git
- Python 3.11 or later
- Codex, Claude, or both

Sign in to each agent command that you plan to use.

## Install cmux-factory

1. Clone the repository:

   ```sh
   git clone https://github.com/mullender/cmux-factory.git \
     ~/.local/share/cmux-factory
   cd ~/.local/share/cmux-factory
   ```

2. Install the command and agent skill:

   ```sh
   ./install
   ```

   The installer creates these symbolic links:

   ```text
   ~/.local/bin/factory
   ~/.codex/skills/start-factory
   ~/.claude/skills/start-factory
   ```

   Each link points into the cloned repository. The installer does not copy
   the files.

3. Add the command directory to `PATH` if needed:

   ```sh
   grep -qxF 'export PATH="$HOME/.local/bin:$PATH"' ~/.zshrc || \
     printf '%s\n' 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
   source ~/.zshrc
   ```

4. Install the cmux agent hooks:

   ```sh
   cmux hooks setup
   ```

5. Verify the installation:

   ```sh
   factory version
   factory doctor
   ```

   `factory doctor` must report `PASS` for the cmux binary and socket. It skips
   the project check when you run it outside a factory project.

## Initialize the first project

Change to any directory inside a Git project and run:

```sh
factory init
```

The command finds the Git root, creates `.factory`, and prints the exact cmux
commands for that project. See [Getting started](GETTING_STARTED.md) for the
launch flow.

## Troubleshooting

### `factory: command not found`

Confirm that the link exists and that the command directory is on `PATH`:

```sh
ls -l ~/.local/bin/factory
printf '%s\n' "$PATH"
```

### The installer reports that a target exists

The installer does not replace a file or a link that points somewhere else.
Inspect the reported target. Remove or move it only if you know that it is an
old installation.

### An agent check fails

Open `.factory/factory.toml` in the project. Each non-Lead agent command must
exist on `PATH`. You can replace `claude` or `codex` with another command that
accepts the generated prompt as an argument.

## Related guides

- [Edit agent instructions](EDIT_AGENT_INSTRUCTIONS.md)
- [Pull factory updates](UPDATING.md)
