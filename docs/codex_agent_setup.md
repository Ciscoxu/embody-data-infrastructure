# Codex Agent Setup

This repository uses Codex Agent conventions:

- `AGENTS.md` contains durable repository instructions. A more deeply nested
  `AGENTS.md` may refine instructions for its subtree when needed.
- `.agents/skills/<skill-name>/SKILL.md` contains repository-scoped reusable
  workflows that Codex can discover.
- `EXECUTION_PLAN.md` is project design input. Its human-wearable/teleoperation
  scope, semantic boundaries, and phase boundaries are summarized as actionable
  instructions in `AGENTS.md`.
- The repository skill requires Codex to classify the collection mode and each
  action-like signal before implementing processing logic.
- `pyproject.toml` remains the source of truth for build, CLI, test, lint, and
  type-check commands.

No Cursor `.cursor/rules` or `.cursor/skills` configuration is used.
