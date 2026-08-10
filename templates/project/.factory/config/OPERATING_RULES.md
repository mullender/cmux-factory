# Operating rules

- Use the smallest change that meets the done condition.
- Ask before you add a subsystem, dependency, service, or storage layer.
- Separate verified facts from hypotheses.
- Record evidence in the project brain or your agent ledger.
- Send agent-to-agent messages through `.factory/inbox/`.
- Non-Lead agents can send mail only to the Lead. Only the Lead can send mail
  to a non-Lead agent. Agents cannot send mail to themselves.
- Never poll or wait for inbox mail. The Watchdog wakes an agent that has mail.
- When the Watchdog wakes you, read and archive your inbox once.
- Every non-Lead turn must end with `handoff` or `blocked` mail to the Lead.
- Builder and Reviewer use separate Git worktrees under `.factory/worktrees/`.
- Worker processes start in the main project root so they can use shared factory
  state. They must change to their named source worktree before source work.
- A code assignment and its handoff must name the full base and head commits.
- Keep a worker worktree clean before a code handoff. Do not review live files.
- The superproject commit fixes each submodule commit. Keep all submodules clean.
- Before `git push`, check whether the exact remote repository and branch are
  the head of an open cross-repository pull request. If they are, do not push
  unless the user explicitly approves updating that pull request.
- Do not claim completion without validation evidence.
- Only the Builder can change project source in this proof of concept.
- The Reviewer stays independent and read-only.
- Write a handoff before a planned session replacement.
