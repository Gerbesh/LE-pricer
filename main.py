
import sys, os, logging

MIN_PYTHON = (3, 12)

if sys.version_info < MIN_PYTHON:
    raise RuntimeError("Pricer requires Python 3.12 or newer.")

from PySide6 import QtWidgets, QtCore
from db import PriceDB
from gui import MainWindow
from overlay import PriceOverlay
from worker import OCRWorker
from config import load_config

def main():
    # Configure logging: console + file
    os.makedirs("logs", exist_ok=True)
    log_fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(os.path.join("logs", "app.log"), encoding="utf-8"),
        ],
    )

    app = QtWidgets.QApplication(sys.argv)

    cfg = load_config()
    hotkeys_cfg = cfg.get("hotkeys", {}) if isinstance(cfg, dict) else {}
    item_hotkey = hotkeys_cfg.get("item_capture", "F1")
    inventory_hotkey = hotkeys_cfg.get("inventory_scan", "F2")
    capture_hotkey = hotkeys_cfg.get("template_capture", "F3")
    overlay_cfg = cfg.get("overlay", {}) if isinstance(cfg, dict) else {}
    overlay_duration = max(500, int(overlay_cfg.get("duration_ms", 4000) or 4000))
    inventory_overlay_duration = max(500, int(overlay_cfg.get("inventory_duration_ms", overlay_duration) or overlay_duration))

    db = PriceDB()
    win = MainWindow(db, start_hotkey=item_hotkey, inventory_hotkey=inventory_hotkey, capture_hotkey=capture_hotkey)
    win.show()

    overlay = PriceOverlay(box_duration_ms=overlay_duration, hint_duration_ms=inventory_overlay_duration)
    worker = OCRWorker(
        db,
        hotkey=win.hotkey,
        inventory_hotkey=getattr(win, 'inventoryHotkey', inventory_hotkey),
        capture_hotkey=getattr(win, 'captureHotkey', capture_hotkey),
        template_threshold=float(getattr(win, 'thresholdSpin').value()),
        save_debug_images=bool(getattr(win, 'debugImgCheck').isChecked()),
    )

    # wiring signals
    worker.boxReady.connect(overlay.show_box)
    worker.inventoryReady.connect(overlay.show_inventory_hints)
    worker.status.connect(win.statusMsg)
    win.showBox.connect(overlay.show_box)
    win.attach_worker(worker)
    # auto-refresh known table if worker ever signals updates (reserved)
    def _on_db_changed(kind: str):
        if kind in ("known", "all"):
            win.knownModel.refresh()
    worker.dbChanged.connect(_on_db_changed)

    # react to settings change
    def apply_settings():
        worker.update_settings(
            hotkey=win.hotkeyEdit.text().strip() or "F1",
            inventory_hotkey=getattr(win, "inventoryHotkey", getattr(worker, "inventory_hotkey", "F2")),
            capture_hotkey=getattr(win, "captureHotkey", getattr(worker, "capture_hotkey", "F3")),
            template_threshold=float(win.thresholdSpin.value()),
            save_debug_images=bool(win.debugImgCheck.isChecked()),
        )
        win.inventoryHotkey = getattr(worker, "inventory_hotkey", win.inventoryHotkey)
        win.captureHotkey = getattr(worker, "capture_hotkey", win.captureHotkey)

    win.hotkeyEdit.editingFinished.connect(apply_settings)
    win.thresholdSpin.valueChanged.connect(apply_settings)
    # soft OCR removed

    # start listener
    worker.start()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
