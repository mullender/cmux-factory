# Changelog

This file records user-visible changes to cmux-factory.

## [0.3.2.0] - 2026-08-09

### Added

- Count unread mail for every agent in the Watchdog.
- Wake an idle agent when its inbox is not empty.
- Show each agent's unread count in `factory status`.
- Record inbox count changes and periodic summaries in the Watchdog journal.

## [0.3.1.0] - 2026-08-08

### Added

- Use all reviewed upstream rules with `factory update --no-pull --use-upstream`.
- Print copyable diff, upstream, and keep-current commands when review is required.

### Changed

- Record clean managed-file baselines before pulling new central templates.

## [0.3.0.1] - 2026-08-08

### Fixed

- Stop the factory even when a cmux terminal-control request does not return.

## [0.3.0.0] - 2026-08-07

### Added

- Update the factory source, command links, skill links, and managed project rules with `factory update`.
- Keep a template baseline so updates can preserve local project rules and identify conflicts.
- Review conflicting central rules under `.factory/update/` before you accept or merge them.

### Changed

- Let `factory init` add safe update metadata without replacing existing project rules.

## [0.2.1.0] - 2026-08-07

### Changed

- Limit Reviewer blocking findings to defects caused or materially worsened by the current change.
- Report pre-existing and adjacent issues as separate follow-up opportunities for Lead triage.
- Give Reviewer handoffs separate sections for the current verdict and later work.
- Route all agent mail through the Lead and verify the sender against its registered cmux surface.
- Stop Lead and Builder pushes that would update an open cross-repository pull request without explicit approval.

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
