# Contributing

## Code and documentation

Use a focused branch from current `main`. Keep changes readable and scoped to the problem. Update the README when setup, commands, or user-visible behavior changes. Put implementation rationale next to the code that needs it.

## Validation

Exercise the affected path before submitting. For a UI change, check the interaction in the browser, including keyboard navigation where relevant. For an installer change, check first-time setup and rerunning it. For documentation, verify commands and relative links. Run `git diff --check` and review the staged patch.

## Commits and pull requests

Stage only the files for the change. Use short, focused commit subjects with prefixes such as `feat:`, `fix:`, `docs:`, or `test:`. Keep credentials, local data, logs, and downloaded dependencies out of commits.

Open a PR against `main`. Describe what changed, why, and how you tested it. Include a screenshot for a visual change when it helps review. Address actionable feedback and check the final revision before merging. Respect branch protections and merge only when authorized.
