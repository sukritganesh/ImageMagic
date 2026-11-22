# Contributing

## Code and documentation

Use a focused branch from current `main`. Keep changes readable and scoped to the problem. Update the README when setup, commands, or user-visible behavior changes. Put implementation rationale next to the code that needs it.

## Validation

After setup, run the tests from the repository root in PowerShell.

```powershell
.\ComfyUI_windows_portable\python_embeded\python.exe -m unittest discover -s tests
```

Exercise the affected path before submitting. For a UI change, check the interaction in the browser, including keyboard navigation where relevant. For an installer change, check first-time setup and rerunning it. For documentation, verify commands and relative links. Run `git diff --check` and review the staged patch.

## Commits and pull requests

Stage only the files for the change. Use short, focused commit subjects with prefixes such as `feat:`, `fix:`, `docs:`, or `test:`. Keep credentials, local data, logs, and downloaded dependencies out of commits.

Open a PR against `main`. Describe what changed, why, and how you tested it. Include a screenshot for a visual change when it helps review. Address actionable feedback and check the final revision before merging. Respect branch protections and merge only when authorized.

## Build a Windows release

On Windows, install [Inno Setup](https://jrsoftware.org/inno-setup/downloads) (v1.0.0 was built with 7.1.1 x64). From the repository root run `ISCC.exe installer\ImageMagic.iss`, using the compiler's full path if needed. The installer is written to `dist\`. Build from the release commit, test that executable in a separate install folder, and attach it, its SHA-256 checksum, and [WINDOWS-SETUP.md](docs/WINDOWS-SETUP.md) to a draft release targeting the same commit.
