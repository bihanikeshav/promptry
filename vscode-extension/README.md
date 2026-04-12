# promptry VS Code Extension

Regression testing for LLM prompts -- run evals, view results, and detect drift, all from VS Code.

## Features

- **Run Eval Suite** -- pick a suite from a quick-pick list and run it in an integrated terminal.
- **Doctor** -- run `promptry doctor` to check your environment.
- **Open Dashboard** -- launch the promptry web dashboard.

## Prerequisites

Install promptry in your Python environment:

```bash
pip install promptry
```

Make sure `promptry` is available on your PATH, or set `promptry.pythonPath` in VS Code settings to point to the correct Python executable.

## Extension Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `promptry.pythonPath` | `python` | Path to the Python executable with promptry installed |

## Usage

1. Open a workspace that contains a `promptry.toml` file.
2. Open the Command Palette (`Ctrl+Shift+P`) and search for `promptry`.
3. Pick a command: **Run Eval Suite**, **Doctor**, or **Open Dashboard**.
