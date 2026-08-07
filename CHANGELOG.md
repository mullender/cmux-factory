# Changelog

This file records user-visible changes to cmux-factory.

## [0.2.0.0] - 2026-08-07

### Added

- Send agent messages through local inbox files without polling another agent's terminal.
- Route permission requests and closed-surface details from the Watchdog to the Lead inbox.
- Ping an idle recipient for urgent mail or notify the user when the recipient is working.
- Read and archive inbox messages with explicit factory commands.

### Changed

- Make the Watchdog responsible for worker monitoring while the Lead checks only its own inbox.

## [0.1.0.0] - 2026-08-07

### Added

- Start a Lead, Builder, Reviewer, and event-based Watchdog in one cmux workspace.
- Keep agent roles, identities, shared rules, session state, and lessons in a readable `.factory` directory.
- Install the command and agent skill from one local clone with idempotent links.
- Inspect agent state and watchdog decisions through human-readable or JSON commands.
- Record session feedback and apply repeated lessons through a manual review.
- Follow task-based setup, operation, instruction, update, and troubleshooting guides on GitHub Pages.
