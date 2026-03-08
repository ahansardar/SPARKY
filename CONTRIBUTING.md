# Contributing to SPARKY

Thanks for contributing to SPARKY.

This project is a Windows-focused desktop AI assistant built mainly in Python. The most useful contributions are bug fixes, stability improvements, documentation updates, and carefully scoped features that fit the current local-first design.

## Before You Start

- Read [README.md](README.md) for setup, requirements, and feature context.
- Check existing issues and pull requests before starting work.
- Prefer small, focused pull requests over large mixed changes.
- If your change affects voice, automation, updater, or system control behavior, include clear testing notes.

## Development Environment

Recommended environment:

- Windows 10 or Windows 11
- Python 3.11+
- Ollama installed and available on `PATH`
- Microphone and speakers for voice-related changes

Setup:

```powershell
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
playwright install
```

If your work touches model-backed features, pull the required models:

```powershell
ollama pull llama3:8b
ollama pull llava:7b
```

Run the app locally:

```powershell
python src/ai_agent.py
```

## Project Areas

High-level layout:

- `src/`: main runtime, app entrypoint, voice I/O, updater, LLM integration
- `actions/`: executable actions such as browser control, media, reminders, and file/system tasks
- `agent/`: planning, execution, task queue, and error handling
- `memory/`: memory storage and management
- `assets/`: UI icons, sounds, and images
- `ui.py`: desktop UI
- `system_stats.py`: system monitoring support

## Contribution Guidelines

### Scope

- Keep changes tightly scoped to one problem.
- Avoid unrelated refactors in the same pull request.
- Preserve current behavior unless the change explicitly intends to modify it.
- Be careful with code paths that control apps, files, browser automation, audio devices, or system settings.

### Code Style

- Follow the existing style in the touched file.
- Prefer clear names and straightforward control flow.
- Add comments only where the logic is non-obvious.
- Do not introduce new dependencies unless they are necessary and justified in the pull request.

### Documentation

Update documentation when you change:

- setup steps
- commands or user-facing behavior
- environment variables
- packaged assets or required models
- installer or updater behavior

## Testing Expectations

There is no formal automated test suite in the repo yet, so every pull request should include manual verification notes.

Before opening a PR, run at least:

```powershell
python -m compileall src actions agent memory ui.py system_stats.py
```

Then validate the relevant flow locally. Examples:

- UI changes: launch the app and verify the affected screen or interaction.
- Voice changes: test microphone input, wake word, and TTS if applicable.
- Action changes: verify the target action with safe, reproducible inputs.
- Browser automation changes: confirm the Playwright-backed flow after `playwright install`.
- Installer/build changes: run the affected script in `installer/` if your change touches packaging.

If you cannot test a path locally, state that clearly in the pull request.

## Pull Request Process

1. Fork the repository and create a branch from `main`.
2. Name the branch clearly, for example `fix/wake-word-restart` or `docs/contributing-guide`.
3. Make the smallest change that fully solves the problem.
4. Run the relevant checks and manual validation.
5. Open a pull request with enough context for review.

Include in the PR description:

- what changed
- why it changed
- how you tested it
- screenshots or recordings for UI changes, if relevant
- any known limitations or follow-up work

## Commit Guidance

Use clear commit messages that describe the actual change.

Good examples:

- `fix: restart wake listener after audio device failure`
- `docs: add contributor setup and PR guidelines`
- `ui: improve status indicator during processing`

## Security and Safety

SPARKY can trigger local automation, open applications, manipulate files, and interact with system settings. Keep that in mind when contributing.

- Do not add hidden or unexpected side effects.
- Prefer explicit user-triggered behavior.
- Call out any risky behavior changes in the pull request.
- Avoid committing secrets, local paths, tokens, or personal data.

## Large Changes

For major features, architecture changes, or dependency additions, open an issue first or describe the proposal clearly before investing in a large implementation. That reduces review churn and helps keep the project direction coherent.
