# cmux-factory repository contract

Keep this project small and easy to inspect.

- cmux provides tabs, terminal control, events, notifications, and session
  lifecycle.
- Python provides deterministic identity, launch, status, and journal logic.
- Markdown skills and role files provide judgment.
- Plain project files provide durable state.
- The user talks to one Lead. Other agents report through shared files.
- Use exact cmux IDs. Names are only display labels.
- Every watchdog action must state the observation, decision, action, and
  result.
- Do not scrape terminal history for lifecycle state.
- Do not add a database, service framework, message broker, workflow language,
  or provider SDK without an observed need.
- Do not add automatic recovery until the observed launch and status loop is
  reliable.
- Do not hide Git operations in an updater. Use plain Git commands.
- Write new prose in Simplified Technical English.
- Run `python3 -m unittest discover -s tests -v` after code changes.
