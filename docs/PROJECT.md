# Project Documentation

## System Overview
LE Pricer is a desktop helper for Last Epoch players. It listens for configurable hotkeys, captures the game window, extracts text through OCR, and overlays pricing tips pulled from a local JSON database. The app is split across three cooperating components:

1. **GUI (`gui.MainWindow`)** – Presents configuration, price tables, and template management. Emits signals for worker actions and reflects worker status updates.
2. **Worker (`worker.OCRWorker`)** – Runs in the background thread, subscribes to global hotkeys, performs screenshot capture, runs OCR via `ocr.py`, and pushes results back to the GUI.
3. **Overlay (`overlay.PriceOverlay`)** – A frameless, always-on-top window bound to the worker for lightweight in-game hints.

## Key Workflows
### Hotkey Capture
1. The user presses the main capture hotkey (default `F1`).
2. `OCRWorker` captures the target region using template metadata from `template_manager.py`.
3. `ocr.parse_item` (see `ocr.py`) preprocesses and feeds the image to Tesseract.
4. Parsed item data is sent to `db.PriceDB.lookup_price` to resolve known values.
5. The worker emits `boxReady` with overlay payload and `status` messages for the GUI.

### Template Calibration
- Initiated via GUI actions (`MainWindow._open_template_capture`).
- Delegates to `template_manager.py` routines for storing raw template captures and serialization.
- Updated templates are written under `templates/` (ignored in Git) so local customizations stay outside version control.

### Data Management
- `PriceDB` uses `prices.json` as the primary store and persists user edits to disk.
- The module exposes high-level helpers (`add_price`, `update_item`, `list_known`) to keep GUI logic lean.

## Configuration & Persistence
- Runtime settings (hotkeys, threshold, debug flags) are owned by the GUI and relayed to the worker via `OCRWorker.update_settings`.
- Logs are written to `logs/app.log` with rotation handled externally (delete folder to reset).
- Templates and debug captures live in `templates/` and `logs/debug/` respectively; both are ignored by Git to avoid leaking personal captures.

## Error Handling Strategy
- User-facing messages go through `MainWindow.statusMsg` so the GUI remains responsive.
- Exceptions in the worker trigger `status` updates and are also logged for diagnostics.
- OCR failures fall back to informative overlay messages rather than raising.

## Development Notes
- The app targets Python 3.12; enforce it via `main.MIN_PYTHON`.
- Prefer type hints on public functions (`db.py`, `worker.py`) so static analysis is easier.
- Keep modules import-light to avoid circular dependencies: GUI ↔ worker by signals, worker ↔ overlay only through Qt signals.
- Tests belong in `tests/` and should mirror module names (`tests/test_db.py`, etc.). Add `pytest` to dependencies when introducing automated checks.

## Release Checklist
- Regenerate templates on the target machine and verify OCR against representative items.
- Clear `logs/` and `templates/` before packaging a build.
- Bump version metadata inside `config.py` or dedicated release notes if present.
- Capture fresh screenshots for documentation (see `docs/` or README gallery section if added).

## License
Distributed under MIT unless overridden for a specific release. Ensure no proprietary fonts, captures, or account data leave the local machine.
