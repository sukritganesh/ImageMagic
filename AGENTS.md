# Working agreement

Read the README and [contributor guide](CONTRIBUTING.md) before changing the project. Inspect the branch, working tree, and staged diff. Preserve unrelated work.

- Make the smallest change that satisfies the request through the normal user entry point. Reuse existing code where it already expresses the intended behavior.
- Preserve supported inputs, saved data, and existing callers. For persistence changes, check an example created before the change.
- Verify the behavior you changed. Add a regression test when it catches a failure existing checks would miss.
- Keep documentation, commits, and PRs consistent with the contributor guide. Report what you verified and any outstanding limitations.
