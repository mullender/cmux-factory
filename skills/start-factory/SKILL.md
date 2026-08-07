---
name: start-factory
description: Start the project cmux factory from the current agent session. Use when the user asks to start, launch, or resume the factory or its named agents.
---

# Start factory

The current agent becomes the Lead. Keep the user in this session.

1. Find the project root that contains `.factory/factory.toml`.
2. Read `.factory/config/OPERATING_RULES.md`, `.factory/config/STYLE.md`,
   `.factory/roles/lead.md`, and `.factory/brain/NOW.md`.
3. Run `factory doctor --project`.
4. Stop if the doctor reports a failure. Explain the exact failed check.
5. Run `factory start`.
6. Read the launch receipt. Report the named tabs and their surface IDs.
7. Act as the Lead. Assign bounded work and require file-backed evidence.
8. Check `factory inbox lead` at the start and end of each turn. Do not poll
   worker terminals.
9. Send worker instructions with `factory mail lead RECIPIENT "MESSAGE"`.
   Workers and the Watchdog can send mail only to the Lead.

The proof of concept does not restart agents. If the watchdog reports a closed
surface, tell the user and preserve the last handoff.
