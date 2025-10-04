
import os
import math
import logging
from PySide6 import QtCore, QtWidgets, QtGui
from ocr import _template_threshold_default
from template_manager import save_samples, save_inventory_sample
from db import PriceDB

class PendingModel(QtCore.QAbstractTableModel):
    headers = ["Название", "Потенциал", "Цена (внести)"]
    def __init__(self, db: PriceDB):
        super().__init__()
        self.db = db
        self.rows = self.db.list_pending()
        self._price_edits: dict[int, str] = {}

    def refresh(self):
        self.beginResetModel()
        self.rows = self.db.list_pending()
        self.endResetModel()

    def rowCount(self, parent=None): return len(self.rows)
    def columnCount(self, parent=None): return 3
    def headerData(self, section, orientation, role):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return self.headers[section]
        return None
    def data(self, index, role):
        if not index.isValid(): return None
        r = self.rows[index.row()]
        c = index.column()
        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            if c == 0: return r.get("name","")
            if c == 1: return r.get("potential", "")
            if c == 2: return self._price_edits.get(index.row(), "")
        return None
    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if not index.isValid() or role != QtCore.Qt.EditRole:
            return False
        if index.column() == 2:
            self._price_edits[index.row()] = str(value)
            self.dataChanged.emit(index, index, [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole])
            return True
        return False
    def flags(self, index):
        if not index.isValid(): return QtCore.Qt.NoItemFlags
        if index.column()==2:
            return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsSelectable
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

class KnownModel(QtCore.QAbstractTableModel):
    lp_slots = list(range(5))
    NAME_COLUMN = 0
    LP_START_COLUMN = 1
    NOTES_COLUMN = LP_START_COLUMN + len(lp_slots)
    UPDATED_COLUMN = NOTES_COLUMN + 1

    headers = ["Название", "LP0", "LP1", "LP2", "LP3", "LP4", "Заметки", "Обновлено"]

    def __init__(self, db: PriceDB):
        super().__init__()
        self.db = db
        self.rows = self.db.list_known()
        self._edits: dict[tuple[int, int], str] = {}

    def refresh(self):
        self.beginResetModel()
        self.rows = self.db.list_known()
        self._edits.clear()
        self.endResetModel()

    def rowCount(self, parent=None):
        return len(self.rows)

    def columnCount(self, parent=None):
        return len(self.headers)

    def headerData(self, section, orientation, role):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return self.headers[section]
        return None

    def _lp_cell_text(self, entry: dict[str, object], pot: int) -> str:
        comment = entry.get(f"comment_lp{pot}")
        if isinstance(comment, str) and comment.strip():
            return comment
        price = entry.get(f"price_lp{pot}")
        if price is None:
            return ""
        if isinstance(price, float) and price.is_integer():
            return str(int(price))
        return str(price)

    def _value_for_cell(self, row: int, column: int) -> str:
        if (row, column) in self._edits:
            return self._edits[(row, column)]
        entry = self.rows[row]
        if column == self.NAME_COLUMN:
            return entry.get("name", "")
        pot = self.column_to_potential(column)
        if pot is not None:
            return self._lp_cell_text(entry, pot)
        if column == self.NOTES_COLUMN:
            return entry.get("notes", "") or ""
        if column == self.UPDATED_COLUMN:
            return entry.get("updated_at", "") or ""
        return ""

    def data(self, index, role):
        if not index.isValid():
            return None
        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            return self._value_for_cell(index.row(), index.column())
        return None

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if not index.isValid() or role != QtCore.Qt.EditRole:
            return False
        if index.column() == self.UPDATED_COLUMN:
            return False
        self._edits[(index.row(), index.column())] = str(value)
        self.dataChanged.emit(index, index, [QtCore.Qt.DisplayRole, QtCore.Qt.EditRole])
        return True

    def flags(self, index):
        if not index.isValid():
            return QtCore.Qt.NoItemFlags
        base = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
        if index.column() == self.UPDATED_COLUMN:
            return base
        return base | QtCore.Qt.ItemIsEditable

    def column_to_potential(self, column: int) -> int | None:
        if self.LP_START_COLUMN <= column < self.LP_START_COLUMN + len(self.lp_slots):
            return self.lp_slots[column - self.LP_START_COLUMN]
        return None

    def iter_lp_columns(self):
        for offset, pot in enumerate(self.lp_slots):
            yield self.LP_START_COLUMN + offset, pot

    def cell_text(self, row: int, column: int) -> str:
        value = self.data(self.index(row, column), role=QtCore.Qt.EditRole)
        return "" if value is None else str(value)


class MainWindow(QtWidgets.QMainWindow):
    # signals from worker
    showBox = QtCore.Signal(str, int, int)
    statusMsg = QtCore.Signal(str)

    def __init__(self, db: PriceDB, start_hotkey: str = "F1", inventory_hotkey: str = "F2", capture_hotkey: str = "F3"):
        super().__init__()
        self.setWindowTitle("LE Item Pricer")
        self.db = db
        self.hotkey = start_hotkey
        self.inventoryHotkey = inventory_hotkey
        self.captureHotkey = capture_hotkey
        self._build_ui()
        self.resize(780, 520)
        # hook placeholder for worker signal later
        self._worker = None

    def _build_ui(self):
        cw = QtWidgets.QWidget()
        self.setCentralWidget(cw)
        v = QtWidgets.QVBoxLayout(cw)

        # Controls
        top = QtWidgets.QHBoxLayout()
        self.hotkeyEdit = QtWidgets.QLineEdit(self.hotkey)
        applyBtn = QtWidgets.QPushButton("Применить")
        self.debugImgCheck = QtWidgets.QCheckBox("Логировать картинки")
        self.debugImgCheck.setChecked(False)
        # Template threshold control
        top.addWidget(QtWidgets.QLabel("Порог рамки:"))
        self.thresholdSpin = QtWidgets.QDoubleSpinBox()
        self.thresholdSpin.setRange(0.30, 0.95)
        self.thresholdSpin.setSingleStep(0.01)
        self.thresholdSpin.setDecimals(2)
        self.thresholdSpin.setValue(_template_threshold_default())
        top.addWidget(QtWidgets.QLabel("Горячая клавиша:"))
        top.addWidget(self.hotkeyEdit, 0)
        top.addWidget(self.thresholdSpin, 0)
        top.addWidget(self.debugImgCheck, 0)
        top.addWidget(applyBtn)
        v.addLayout(top)

        applyBtn.clicked.connect(self._apply_settings)
        # Also apply instantly on value edits
        self.thresholdSpin.valueChanged.connect(self._apply_settings)
        self.debugImgCheck.toggled.connect(self._apply_settings)
        # Soft OCR and config dialog removed

        # Tabs
        tabs = QtWidgets.QTabWidget()
        v.addWidget(tabs, 1)

        # Known tab only (direct editing)

        # Known tab
        self.knownModel = KnownModel(self.db)
        self.knownView = QtWidgets.QTableView()
        self.knownView.setModel(self.knownModel)
        self.knownView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.knownView.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.knownView.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        saveKnownBtn = QtWidgets.QPushButton("Сохранить изменения")
        saveKnownBtn.clicked.connect(self._save_known_changes)
        delKnownBtn = QtWidgets.QPushButton("✖ Удалить выбранные")
        delKnownBtn.setToolTip("Удалить выделенные строки из оцененных")
        delKnownBtn.clicked.connect(self._delete_known_selected)

        ktab = QtWidgets.QWidget()
        kv = QtWidgets.QVBoxLayout(ktab)
        kv.addWidget(self.knownView, 1)
        kh = QtWidgets.QHBoxLayout()
        addRowBtn = QtWidgets.QPushButton("+ Добавить строку")
        addRowBtn.clicked.connect(self._add_known_row)
        kh.addWidget(addRowBtn)
        kh.addStretch(1)
        kh.addWidget(saveKnownBtn)
        kh.addWidget(delKnownBtn)
        kv.addLayout(kh)
        tabs.addTab(ktab, "Цены")

        # Status
        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)
        self.statusMsg.connect(self.status.showMessage)

    def _apply_settings(self):
        self.hotkey = self.hotkeyEdit.text().strip() or self.hotkey
        thr = self.thresholdSpin.value()
        dbg = 'on' if self.debugImgCheck.isChecked() else 'off'
        self.status.showMessage(
            f"Горячие клавиши: предмет {self.hotkey} | инвентарь {self.inventoryHotkey} | шаблон {self.captureHotkey} | Порог рамки: {thr:.2f} | Картинки: {dbg}",
            4000,
        )

    # pending tab removed: direct editing in Known table only

    def _save_known_changes(self):
        errors: list[str] = []
        for r, row in enumerate(self.knownModel.rows):
            key = row.get("key")
            if not key:
                continue
            name = self.knownModel.cell_text(r, self.knownModel.NAME_COLUMN).strip()
            notes = self.knownModel.cell_text(r, self.knownModel.NOTES_COLUMN).strip()
            lp_values: dict[int, str] = {}
            for col, pot in self.knownModel.iter_lp_columns():
                lp_values[pot] = self.knownModel.cell_text(r, col)
            try:
                self.db.edit_known(key, name=name, notes=notes, lp_values=lp_values)
            except ValueError as exc:
                errors.append(str(exc))
            except Exception as exc:
                errors.append(f"{name or key}: {exc}")
        self.knownModel.refresh()
        if errors:
            self.status.showMessage("Ошибки сохранения: " + "; ".join(errors), 6000)
        else:
            self.status.showMessage("Изменения сохранены.", 3000)

    def _delete_known_selected(self):
        sel = self.knownView.selectionModel().selectedRows()
        keys: list[str] = []
        for idx in sel:
            row = idx.row()
            entry = self.knownModel.rows[row]
            key = entry.get("key")
            if key:
                keys.append(key)
        if not keys:
            self.status.showMessage("Нет выбранных строк для удаления.", 2500)
            return
        removed = self.db.delete_known(keys)
        self.knownModel.refresh()
        self.status.showMessage(f"Удалено из оцененных: {removed}.", 3000)

    def _add_known_row(self):
        self.db.add_known()
        self.knownModel.refresh()

    # no _delete_pending_selected in simplified mode

    # Called from main to attach worker for signal handling
    def attach_worker(self, worker):
        self._worker = worker
        self.inventoryHotkey = getattr(worker, "inventory_hotkey", self.inventoryHotkey)
        self.captureHotkey = getattr(worker, "capture_hotkey", self.captureHotkey)
        if hasattr(worker, "requestTemplate"):
            worker.requestTemplate.connect(self._open_template_capture)
        if hasattr(worker, "manualInventoryCapture"):
            worker.manualInventoryCapture.connect(self._open_manual_inventory_dialog)

    def _open_template_capture(self, roi_path: str):
        try:
            dlg = TemplateCaptureDialog(roi_path, self)
            if dlg.exec() == QtWidgets.QDialog.Accepted:
                self.status.showMessage("Образцы сохранены в templates/.", 3000)
        except Exception as e:
            self.status.showMessage(f"Ошибка шаблонов: {e}", 4000)

    def _open_manual_inventory_dialog(self, payload):
        try:
            logging.info("Opening manual inventory dialog")
            data = payload or {}
            path = data.get("path")
            candidates = data.get("items") or []
            logging.info(f"Dialog payload: path={path}, candidates={len(candidates)}")
            if not path or not os.path.exists(path):
                self.status.showMessage("Скриншот для шаблона не найден", 4000)
                return
            dlg = ManualInventoryDialog(path, candidates, self)
            if dlg.exec() == QtWidgets.QDialog.Accepted:
                self.status.showMessage("Шаблон предмета сохранён", 3000)
        except Exception as e:
            self.status.showMessage(f"Ошибка добавления шаблона: {e}", 4000)

    # no LP-only capture in global LP mode


    # no LP-only capture in global LP mode


class ImageSelectWidget(QtWidgets.QLabel):
    rectSelected = QtCore.Signal(QtCore.QRect)

    def __init__(self, pixmap: QtGui.QPixmap):
        super().__init__()
        self.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
        self._orig_pixmap = pixmap
        self._scale = 1.0
        self._selection_rect = QtCore.QRect()
        self._enabled = False
        self._dragging = False
        self._origin: QtCore.QPoint | None = None
        self._scroll_area: QtWidgets.QScrollArea | None = None
        self._pan_active = False
        self._pan_start = QtCore.QPoint()
        self._scroll_start = QtCore.QPoint()
        self._blur_pixmap: QtGui.QPixmap | None = None
        self._apply_scale()
        self._generate_blur_pixmap()

    def _apply_scale(self) -> None:
        if self._orig_pixmap.isNull():
            return
        width = max(1, int(round(self._orig_pixmap.width() * self._scale)))
        height = max(1, int(round(self._orig_pixmap.height() * self._scale)))
        scaled = self._orig_pixmap.scaled(
            width,
            height,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
        super().setPixmap(scaled)
        self.resize(scaled.size())
        self.updateGeometry()

    def _generate_blur_pixmap(self) -> None:
        pix = self.pixmap()
        if pix is None or pix.isNull():
            self._blur_pixmap = None
            return
        scene = QtWidgets.QGraphicsScene()
        item = QtWidgets.QGraphicsPixmapItem(pix)
        blur = QtWidgets.QGraphicsBlurEffect()
        blur.setBlurRadius(12.0)
        item.setGraphicsEffect(blur)
        scene.addItem(item)
        result = QtGui.QPixmap(pix.size())
        result.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(result)
        scene.render(painter, QtCore.QRectF(result.rect()), QtCore.QRectF(pix.rect()))
        painter.end()
        self._blur_pixmap = result

    def set_scroll_area(self, area: QtWidgets.QScrollArea | None) -> None:
        self._scroll_area = area

    def set_scale(self, scale: float) -> None:
        scale = max(0.1, min(3.0, float(scale)))
        if abs(scale - self._scale) < 1e-3:
            return
        self._scale = scale
        self._apply_scale()
        self._generate_blur_pixmap()
        self._selection_rect = QtCore.QRect()
        self.update()

    def current_scale(self) -> float:
        return self._scale

    def start(self):
        self._enabled = True
        self._dragging = False
        self._selection_rect = QtCore.QRect()
        self.update()

    def stop(self):
        self._enabled = False
        self._dragging = False
        self._selection_rect = QtCore.QRect()
        self.update()

    def mousePressEvent(self, e):
        if e.button() == QtCore.Qt.MouseButton.RightButton and self._scroll_area is not None:
            self._pan_active = True
            self._pan_start = e.pos()
            self._scroll_start = QtCore.QPoint(
                self._scroll_area.horizontalScrollBar().value(),
                self._scroll_area.verticalScrollBar().value(),
            )
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            e.accept()
            return
        if not self._enabled or e.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        self._dragging = True
        self._origin = e.pos()
        self._selection_rect = QtCore.QRect(self._origin, QtCore.QSize())
        self.update()

    def mouseMoveEvent(self, e):
        if self._pan_active and self._scroll_area is not None:
            delta = e.pos() - self._pan_start
            self._scroll_area.horizontalScrollBar().setValue(self._scroll_start.x() - delta.x())
            self._scroll_area.verticalScrollBar().setValue(self._scroll_start.y() - delta.y())
            e.accept()
            return
        if not self._enabled or not self._dragging or self._origin is None:
            return
        rect = QtCore.QRect(self._origin, e.pos()).normalized()
        pix = self.pixmap()
        if pix is not None and not pix.isNull():
            rect = rect.intersected(pix.rect())
        self._selection_rect = rect
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == QtCore.Qt.MouseButton.RightButton and self._pan_active:
            self._pan_active = False
            self.unsetCursor()
            e.accept()
            return
        if not self._enabled or e.button() != QtCore.Qt.MouseButton.LeftButton or self._origin is None:
            return
        rect = QtCore.QRect(self._origin, e.pos()).normalized()
        pix = self.pixmap()
        if pix is not None and not pix.isNull():
            rect = rect.intersected(pix.rect())
        self._selection_rect = rect
        self._dragging = False
        self._enabled = False
        self._origin = None
        self.update()
        self._emit_selection()

    def leaveEvent(self, e):
        if self._pan_active:
            self.unsetCursor()
            self._pan_active = False
        super().leaveEvent(e)

    def _emit_selection(self) -> None:
        mapped = self._map_to_original(self._selection_rect)
        if mapped is not None:
            self.rectSelected.emit(mapped)

    def _map_to_original(self, rect: QtCore.QRect) -> QtCore.QRect | None:
        if rect.isNull() or self._orig_pixmap.isNull():
            return None
        rect = rect.normalized()
        scale = self._scale if self._scale else 1.0
        x1 = max(0, int(rect.left() / scale))
        y1 = max(0, int(rect.top() / scale))
        x2 = max(0, int((rect.right() + 1) / scale) - 1)
        y2 = max(0, int((rect.bottom() + 1) / scale) - 1)
        x2 = min(self._orig_pixmap.width() - 1, x2)
        y2 = min(self._orig_pixmap.height() - 1, y2)
        if x2 <= x1:
            x2 = min(self._orig_pixmap.width() - 1, x1 + 1)
        if y2 <= y1:
            y2 = min(self._orig_pixmap.height() - 1, y1 + 1)
        return QtCore.QRect(QtCore.QPoint(x1, y1), QtCore.QPoint(x2, y2))

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._selection_rect.isNull():
            return
        rect = self._selection_rect
        pix = self.pixmap()
        if pix is None or pix.isNull():
            return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        if self._blur_pixmap is not None and not self._blur_pixmap.isNull():
            src = QtCore.QRect(rect.topLeft(), rect.size()).intersected(self._blur_pixmap.rect())
            if not src.isEmpty():
                painter.setOpacity(0.85)
                painter.drawPixmap(rect.topLeft(), self._blur_pixmap, src)
                painter.setOpacity(1.0)
        painter.setBrush(QtGui.QColor(255, 255, 255, 70))
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 220), 2))
        painter.drawRoundedRect(rect, 8, 8)
        painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 60), 1))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)
        painter.end()
class TemplateCaptureDialog(QtWidgets.QDialog):
    def __init__(self, roi_path: str, parent=None, item_name: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Создание шаблонов")
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        self.roi_path = roi_path
        pix = QtGui.QPixmap(self.roi_path)
        self.view = ImageSelectWidget(pix)

        self.stepLbl = QtWidgets.QLabel("Шаг 1: выделите название предмета мышью")
        self.nameRect: QtCore.QRect | None = None

        self.itemEdit = QtWidgets.QLineEdit()
        self.itemEdit.setPlaceholderText("Введите точное название предмета…")
        self.saveBtn = QtWidgets.QPushButton("Сохранить образцы")
        self.saveBtn.setEnabled(False)

        layout = QtWidgets.QVBoxLayout(self)

        self._full_screen_geom: QtCore.QRect | None = None
        screen = None
        parent = self.parent()
        if parent is not None:
            window_handle = getattr(parent, "windowHandle", None)
            if callable(window_handle):
                handle = window_handle()
                if handle is not None:
                    screen = handle.screen()
        if screen is None:
            screen = QtWidgets.QApplication.screenAt(QtGui.QCursor.pos())
        if screen is None:
            screen = QtWidgets.QApplication.primaryScreen()
        if screen is not None:
            self._full_screen_geom = screen.geometry()
            self.setGeometry(self._full_screen_geom)
        layout.addWidget(self.stepLbl)
        layout.addWidget(self.view, 1)

        form = QtWidgets.QFormLayout()
        form.addRow("Название предмета:", self.itemEdit)
        layout.addLayout(form)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(self.saveBtn)
        layout.addLayout(btns)

        # Wire
        self.view.rectSelected.connect(self._on_rect)
        self.saveBtn.clicked.connect(self._save)

        if item_name:
            self.itemEdit.setText(item_name)
        # Start step 1
        self._step = 1
        QtCore.QTimer.singleShot(0, self._apply_fullscreen)
        QtCore.QTimer.singleShot(100, self.view.start)

    def _on_rect(self, rect: QtCore.QRect):
        if self._step == 1:
            self.nameRect = rect
            self._step = 2
            self.stepLbl.setText("Шаг 2: введите название предмета и нажмите 'Сохранить образцы'")
            self.saveBtn.setEnabled(True)

    # no skip LP in global LP mode

    def _save(self):
        name = self.itemEdit.text().strip()
        # Convert Qt rects to (x1,y1,x2,y2)
        def qrect_to_tuple(r: QtCore.QRect):
            # PIL expects (left, top, right, bottom) with right/bottom exclusive
            return (int(r.left()), int(r.top()), int(r.right())+1, int(r.bottom())+1)
        if not name or self.nameRect is None:
            QtWidgets.QMessageBox.warning(self, "Не заполнено", "Укажите название и выделите область названия.")
            return
        name_rect = qrect_to_tuple(self.nameRect)
        try:
            save_samples(self.roi_path, name, name_rect, None, 0)
            # Ensure DB row exists for this name (potential unknown)
            self._ensure_db_entry(name)
            self.accept()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить образцы: {e}")

    def _apply_fullscreen(self) -> None:
        if self._full_screen_geom is not None:
            self.setGeometry(self._full_screen_geom)
        self.showMaximized()

    def _ensure_db_entry(self, name: str):
        par = self.parent()
        db = getattr(par, 'db', None)
        model = getattr(par, 'knownModel', None)
        if db is None:
            return
        target = (name or '').strip().lower()
        rows = db.list_known()
        for rec in rows:
            if (rec.get('name', '') or '').strip().lower() == target:
                return
        db.add_known(name)
        try:
            if model is not None:
                model.refresh()
        except Exception:
            pass


class ManualInventoryDialog(QtWidgets.QDialog):
    def __init__(self, screenshot_path: str, candidates: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Добавить шаблон предмета")
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        self.screenshot_path = screenshot_path
        pix = QtGui.QPixmap(self.screenshot_path)
        self.view = ImageSelectWidget(pix)
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidget(self.view)
        self.scroll.setWidgetResizable(False)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll.setAlignment(QtCore.Qt.AlignCenter)
        self.scroll.setMinimumSize(400, 320)
        self.view.set_scroll_area(self.scroll)

        self.rect: QtCore.QRect | None = None
        self.combo = QtWidgets.QComboBox()
        self.combo.setEditable(False)
        self.combo.addItems(sorted(candidates))
        self.combo.setCurrentIndex(0 if candidates else -1)
        self.hintLbl = QtWidgets.QLabel(
            "Шаг 1: выделите предмет, Шаг 2: выберите название и нажмите 'Сохранить'"
        )
        self.saveBtn = QtWidgets.QPushButton("Сохранить")
        self.saveBtn.setEnabled(bool(candidates))

        self.zoomSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.zoomSlider.setRange(10, 300)
        self.zoomSlider.setSingleStep(5)
        self.zoomValue = QtWidgets.QLabel()

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.hintLbl)
        layout.addWidget(self.scroll, 1)

        zoomLayout = QtWidgets.QHBoxLayout()
        zoomLayout.addWidget(QtWidgets.QLabel("Масштаб:"))
        zoomLayout.addWidget(self.zoomSlider, 1)
        zoomLayout.addWidget(self.zoomValue)
        layout.addLayout(zoomLayout)

        form = QtWidgets.QFormLayout()
        form.addRow("Предмет:", self.combo)
        layout.addLayout(form)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(self.saveBtn)
        layout.addLayout(btns)

        self.view.rectSelected.connect(self._on_rect)
        self.saveBtn.clicked.connect(self._save)
        self.zoomSlider.valueChanged.connect(self._on_zoom_changed)

        base_scale = self._initial_scale_for_pixmap(pix)
        self.zoomSlider.setValue(int(base_scale * 100))
        self.view.set_scale(base_scale)
        self._update_zoom_label(base_scale)

        screen = QtGui.QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else QtCore.QRect(0, 0, 1600, 900)
        max_w = max(640, avail.width() - 120)
        max_h = max(480, avail.height() - 160)
        self.setMaximumSize(max_w, max_h)
        est_w = min(max_w, max(640, int(self.view.width() + 80)))
        est_h = min(max_h, max(480, int(self.view.height() + 200)))
        self.resize(est_w, est_h)
        center_x = avail.center().x() - self.width() // 2
        center_y = avail.center().y() - self.height() // 2
        self.move(max(avail.left(), center_x), max(avail.top(), center_y))

        QtCore.QTimer.singleShot(80, self.view.start)

    def _initial_scale_for_pixmap(self, pix: QtGui.QPixmap) -> float:
        if pix.isNull():
            return 1.0
        screen = QtGui.QGuiApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else QtCore.QRect(0, 0, 1600, 900)
        max_w = max(320, avail.width() - 200)
        max_h = max(240, avail.height() - 240)
        scale_w = max_w / pix.width() if pix.width() else 1.0
        scale_h = max_h / pix.height() if pix.height() else 1.0
        base_scale = min(1.0, scale_w, scale_h)
        return max(0.1, base_scale)

    def _on_zoom_changed(self, value: int):
        scale = max(0.1, value / 100.0)
        self.view.set_scale(scale)
        self._update_zoom_label(scale)
        QtCore.QTimer.singleShot(0, self.view.start)

    def _update_zoom_label(self, scale: float):
        self.zoomValue.setText(f"{int(scale * 100)}%")

    def _on_rect(self, rect: QtCore.QRect):
        self.rect = rect
        if not self.combo.count():
            self.hintLbl.setText("Нет предметов без шаблонов — добавьте новый через другое окно")
            self.saveBtn.setEnabled(False)
        else:
            self.hintLbl.setText("Шаг 2: выберите предмет и нажмите 'Сохранить'")
            self.saveBtn.setEnabled(True)
        QtCore.QTimer.singleShot(80, self.view.start)

    def _save(self):
        if not self.combo.count():
            QtWidgets.QMessageBox.warning(self, "Нет предметов", "Нет предметов для выбора.")
            return
        if self.rect is None or self.rect.width() < 3 or self.rect.height() < 3:
            QtWidgets.QMessageBox.warning(self, "Не выделено", "Выделите область предмета на скриншоте.")
            return
        item_name = self.combo.currentText().strip()
        if not item_name:
            QtWidgets.QMessageBox.warning(self, "Не выбрано", "Выберите название предмета.")
            return
        qrect = self.rect.normalized()
        rect_tuple = (int(qrect.left()), int(qrect.top()), int(qrect.right()) + 1, int(qrect.bottom()) + 1)
        try:
            save_inventory_sample(self.screenshot_path, item_name, rect_tuple)
            QtWidgets.QMessageBox.information(self, "Сохранено", "Шаблон предмета добавлен.")
            self.accept()
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить шаблон: {exc}")

class TemplateCaptureDialog(QtWidgets.QDialog):
    def __init__(self, roi_path: str, parent=None, item_name: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Создание шаблонов")
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        self.roi_path = roi_path
        pix = QtGui.QPixmap(self.roi_path)
        self.view = ImageSelectWidget(pix)

        self.stepLbl = QtWidgets.QLabel("Шаг 1: выделите название предмета мышью")
        self.nameRect: QtCore.QRect | None = None

        self.itemEdit = QtWidgets.QLineEdit()
        self.itemEdit.setPlaceholderText("Введите точное название предмета…")
        self.saveBtn = QtWidgets.QPushButton("Сохранить образцы")
        self.saveBtn.setEnabled(False)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.stepLbl)
        layout.addWidget(self.view, alignment=QtCore.Qt.AlignCenter)

        form = QtWidgets.QFormLayout()
        form.addRow("Название предмета:", self.itemEdit)
        layout.addLayout(form)

        btns = QtWidgets.QHBoxLayout()
        btns.addStretch(1)
        btns.addWidget(self.saveBtn)
        layout.addLayout(btns)

        # Wire
        self.view.rectSelected.connect(self._on_rect)
        self.saveBtn.clicked.connect(self._save)

        if item_name:
            self.itemEdit.setText(item_name)
        # Start step 1
        self._step = 1
        QtCore.QTimer.singleShot(50, self.view.start)

    def _on_rect(self, rect: QtCore.QRect):
        if self._step == 1:
            self.nameRect = rect
            self._step = 2
            self.stepLbl.setText("Шаг 2: введите название предмета и нажмите 'Сохранить образцы'")
            self.saveBtn.setEnabled(True)

    # no skip LP in global LP mode

    def _save(self):
        name = self.itemEdit.text().strip()
        # Convert Qt rects to (x1,y1,x2,y2)
        def qrect_to_tuple(r: QtCore.QRect):
            # PIL expects (left, top, right, bottom) with right/bottom exclusive
            return (int(r.left()), int(r.top()), int(r.right())+1, int(r.bottom())+1)
        if not name or self.nameRect is None:
            QtWidgets.QMessageBox.warning(self, "Не заполнено", "Укажите название и выделите область названия.")
            return
        name_rect = qrect_to_tuple(self.nameRect)
        try:
            save_samples(self.roi_path, name, name_rect, None, 0)
            # Ensure DB row exists for this name (potential unknown)
            self._ensure_db_entry(name)
            self.accept()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить образцы: {e}")

    def _ensure_db_entry(self, name: str):
        par = self.parent()
        db = getattr(par, 'db', None)
        model = getattr(par, 'knownModel', None)
        if db is None:
            return
        target = (name or '').strip().lower()
        rows = db.list_known()
        for rec in rows:
            if (rec.get('name', '') or '').strip().lower() == target:
                return
        db.add_known(name)
        try:
            if model is not None:
                model.refresh()
        except Exception:
            pass




