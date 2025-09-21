# Repository Guidelines

## Project Structure & Modules
- Root-level Python app. Key files: `main.py` (entry), `gui.py` (UI), `worker.py` (background tasks), `ocr.py` (recognition), `overlay.py` (display), `db.py` (data access), `prices.json` (sample data), `requirements.txt` (deps).
- Tests folder not present; place new tests under `tests/` mirroring module names (e.g., `tests/test_db.py`).

## Build, Run, and Dev
- Install deps: `py -3.12 -m venv .venv && .venv\Scripts\python -m pip install -r requirements.txt` (Windows 10/11) or `python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` (Unix).
- Run app: `python main.py`.
- Lint (if installed): `ruff .` and `flake8 .`.
- Format (if installed): `ruff format .` or `black .`.

## Coding Style & Naming
- Python 3.12+. Use 4-space indentation, type hints for public functions, and f-strings for formatting.
- Modules: snake_case filenames (`ocr.py`, `worker.py`).
- Functions/variables: snake_case. Classes: PascalCase. Constants: UPPER_SNAKE.
- Keep functions focused; prefer pure helpers in modules like `db.py` and UI code in `gui.py`.

## Testing Guidelines
- Framework: `pytest`. Add `pytest` to `requirements.txt` when introducing tests.
- Naming: files `tests/test_*.py`; tests use Arrange–Act–Assert pattern.
- Run tests: `pytest -q` (optionally `-k name` to filter). Aim for coverage of critical paths (DB I/O, OCR parsing, worker flows).

## Commit & PR Guidelines
- Commits: present-tense, scoped messages (e.g., "Add OCR parsing for totals"). Group related changes; keep diffs focused.
- PRs: include purpose, summary of changes, screenshots of UI changes (`gui.py`/`overlay.py`), and linked issues. Note manual test steps.

## Security & Config Tips
- Do not commit secrets or personal data. Use environment variables for API keys.
- Validate external inputs (OCR results, file paths). Handle errors with clear messages; avoid crashing the GUI thread.

## Architecture Notes
- `main.py` wires modules together. Long-running or blocking work lives in `worker.py`. UI in `gui.py` and `overlay.py`. Data access in `db.py`. Keep boundaries clean and modules import-light.
