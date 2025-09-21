
import sys, os, logging

MIN_PYTHON = (3, 12)

if sys.version_info < MIN_PYTHON:
    raise RuntimeError("Pricer requires Python 3.12 or newer.")

from PySide6 import QtWidgets, QtCore
from db import PriceDB
from gui import MainWindow
from overlay import PriceOverlay
from worker import OCRWorker
from ocr import DEFAULT_TESSERACT_EXE

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

    db = PriceDB()
    win = MainWindow(db)
    win.show()

    overlay = PriceOverlay()
    # Defaults: hotkey F1, Tesseract at default Windows path
    worker = OCRWorker(
        db,
        hotkey=(win.hotkeyEdit.text().strip() or "F1"),
        inventory_hotkey=getattr(win, 'inventoryHotkey', "F2"),
        capture_hotkey=getattr(win, 'captureHotkey', "F3"),
        tesseract_path=(win.tessPath.text().strip() or DEFAULT_TESSERACT_EXE),
        template_threshold=float(getattr(win, 'thresholdSpin').value()),
        save_debug_images=bool(getattr(win, 'debugImgCheck').isChecked()),
    )

    # wiring signals
    worker.boxReady.connect(overlay.show_box)
    worker.inventoryReady.connect(overlay.show_inventory_hints)
    worker.status.connect(win.statusMsg)
    worker.requestTemplate.connect(win._open_template_capture)
    worker.manualInventoryCapture.connect(win._open_manual_inventory_dialog)
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
            tesseract_path=win.tessPath.text().strip() or DEFAULT_TESSERACT_EXE,
            template_threshold=float(win.thresholdSpin.value()),
            save_debug_images=bool(win.debugImgCheck.isChecked()),
        )
        win.inventoryHotkey = getattr(worker, "inventory_hotkey", win.inventoryHotkey)
        win.captureHotkey = getattr(worker, "capture_hotkey", win.captureHotkey)

    win.hotkeyEdit.editingFinished.connect(apply_settings)
    win.tessPath.editingFinished.connect(apply_settings)
    win.thresholdSpin.valueChanged.connect(apply_settings)
    # soft OCR removed

    # start listener
    worker.start()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
