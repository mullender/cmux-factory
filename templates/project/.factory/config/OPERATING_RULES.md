# Operating rules

- Use the smallest change that meets the done condition.
- Ask before you add a subsystem, dependency, service, or storage layer.
- Separate verified facts from hypotheses.
- Record evidence in the project brain or your agent ledger.
- Send agent-to-agent messages through `.factory/inbox/`.
- Non-Lead agents can send mail only to the Lead. Only the Lead can send mail
  to a non-Lead agent. Agents cannot send mail to themselves.
- Check your inbox at turn boundaries. Do not poll another agent's terminal.
- Do not claim completion without validation evidence.
- Only the Builder can change project source in this proof of concept.
- The Reviewer stays independent and read-only.
- Write a handoff before a planned session replacement.
