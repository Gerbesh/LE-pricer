# LE Pricer

Desktop companion app that reads Last Epoch loot tooltips via OCR, looks up prices, and overlays quick hints in-game.

## Highlights
- OCR pipeline powered by Tesseract to extract item names and affix tiers from screenshots.
- PySide6 desktop UI for managing price data, capture hotkeys, and template calibration.
- Lightweight overlay panel that mirrors price lookup results without blocking the game.
- Background worker that listens for global hotkeys so OCR runs outside the GUI thread.

## Getting Started
### Prerequisites
- Python 3.12 or newer (`python --version`).
- Tesseract OCR installed with English and Russian language packs. On Windows, prefer the UB Mannheim build and add `tesseract.exe` to `%PATH%`.

### Installation
```powershell
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
```
On macOS/Linux replace the second line with `source .venv/bin/activate`.

### First Run
```powershell
python main.py
```
When the UI opens, point Tesseract to the installed binary if auto-detection fails, then calibrate capture templates.

## Default Hotkeys
- `F1` - capture the hovered item and show the overlay.
- `F2` - capture the inventory grid for stash association (if enabled).
- `F3` - open the template capture dialog for recalibration.
Hotkeys are configurable inside the main window and updates apply instantly.

## Project Layout
- `main.py` - application entry point, wires UI, worker, overlay, and database together.
- `gui.py` - PySide6 main window, settings widgets, and data models.
- `worker.py` - background `OCRWorker` thread that listens for hotkeys and dispatches OCR work.
- `ocr.py` - screen capture helpers, preprocessing utilities, and Tesseract integration.
- `overlay.py` - always-on-top widget that shows pricing results in-game.
- `db.py` - local JSON-backed price store with helper queries and persistence routines.
- `template_manager.py` - utilities for maintaining capture templates.
- `prices.json` - sample data bundle used for local testing.
- `tests/` - pytest-based regression tests (add new ones here).

## Development
- Lint: `ruff .` or `flake8 .` (optional but recommended).
- Format: `ruff format .` or `black .`.
- Tests: `pytest -q` (add `pytest` to `requirements.txt` if needed).
- Logs are written to `logs/app.log`; delete the folder to reset between runs.

## Troubleshooting
- **Hotkeys ignored:** ensure the app runs with sufficient privileges (try "Run as administrator" on Windows) and no other tool grabs the same hotkeys.
- **OCR misses characters:** verify the correct language packs are installed and re-run template calibration with a crisp tooltip screenshot.
- **Overlay not visible:** confirm Last Epoch uses windowed or borderless mode so the overlay can be drawn on top.

## FAQ

### English
**How do I change the capture hotkeys?** Use the main window inputs under the Hotkeys section; edits apply immediately to the background worker.
**Where do I point the app to Tesseract?** Set the executable path in the Tesseract field on the main screen; leave blank for the default installer path.
**How do I recalibrate templates?** Press F3 or use the template capture button; select the item name box and save the sample.

### Р§Р°СЃС‚Рѕ Р·Р°РґР°РІР°РµРјС‹Рµ РІРѕРїСЂРѕСЃС‹ (RU)
**РљР°Рє РёР·РјРµРЅРёС‚СЊ РіРѕСЂСЏС‡РёРµ РєР»Р°РІРёС€Рё?** РћС‚РєСЂРѕР№С‚Рµ РіР»Р°РІРЅРѕРµ РѕРєРЅРѕ Рё РѕР±РЅРѕРІРёС‚Рµ РїРѕР»СЏ РіРѕСЂСЏС‡РёС… РєР»Р°РІРёС€; РёР·РјРµРЅРµРЅРёСЏ СЃСЂР°Р·Сѓ РїСЂРёРјРµРЅСЏСЋС‚СЃСЏ Рє С„РѕРЅРѕРІРѕРјСѓ СЃРµСЂРІРёСЃСѓ.
**Р“РґРµ СѓРєР°Р·Р°С‚СЊ РїСѓС‚СЊ Рє Tesseract?** Р’РІРµРґРёС‚Рµ РїСѓС‚СЊ Рє tesseract.exe РІ РїРѕР»Рµ "Tesseract" РЅР° РіР»Р°РІРЅРѕРј СЌРєСЂР°РЅРµ РёР»Рё РѕСЃС‚Р°РІСЊС‚Рµ РµРіРѕ РїСѓСЃС‚С‹Рј РґР»СЏ Р·РЅР°С‡РµРЅРёСЏ РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ.
**РљР°Рє РїРµСЂРµСЃРЅСЏС‚СЊ С€Р°Р±Р»РѕРЅС‹ РїСЂРµРґРјРµС‚РѕРІ?** РќР°Р¶РјРёС‚Рµ F3 РёР»Рё РєРЅРѕРїРєСѓ Р·Р°С…РІР°С‚Р° С€Р°Р±Р»РѕРЅРѕРІ, РІС‹РґРµР»РёС‚Рµ СЂР°РјРєРѕР№ РЅР°Р·РІР°РЅРёРµ РїСЂРµРґРјРµС‚Р° Рё СЃРѕС…СЂР°РЅРёС‚Рµ РѕР±СЂР°Р·РµС†.

## License
The project is distributed under the MIT License. See `LICENSE` if supplied with the release.

