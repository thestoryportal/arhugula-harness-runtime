@AGENTS.md

The instructions for operating this deployment are in `AGENTS.md`, imported above, so that Claude Code and every other agent CLI read one text. Only what is specific to Claude Code follows.

- In the init ask-protocol, ask the operator with the ask-question tool, one init question per tool question. When an init question has more options than the tool accepts, or wants free text such as a path, ask it in plain chat instead; do not drop options to make it fit.
- The Bash tool is not a terminal the operator can type into. For the commands `AGENTS.md` lists as needing the operator at a terminal, give them the command to run in their own terminal.
