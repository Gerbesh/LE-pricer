
import threading, time, traceback, logging, os
from datetime import datetime
from PySide6 import QtCore
from db import PriceDB
from ocr import (
    detect_roi,
    set_debug_image_saving,
    set_tesseract_path,
    ocr_full,
    parse_item,
    get_last_detection_stats,
    _screen_geom,
    _grab_bbox,
)
import keyboard
from template_manager import (
    match_item_by_templates,
    detect_potential_global,
    match_inventory_regions,
    list_items_missing_inventory,
    list_all_items,
)


def _format_price(value) -> str:
    try:
        n = float(value)
    except Exception:
        return str(value)
    neg = n < 0
    n = abs(n)
    s = f"{n:.2f}"
    ip, fp = s.split('.')
    # trim trailing zeros in fractional part
    fp = fp.rstrip('0')
    def group3(t: str) -> str:
        rev = t[::-1]
        parts = [rev[i:i+3] for i in range(0, len(rev), 3)]
        return '.'.join(parts)[::-1]
    ip_g = group3(ip)
    out = ip_g if not fp else f"{ip_g},{fp}"
    return f"-{out}" if neg else out

class OCRWorker(QtCore.QObject):
    boxReady = QtCore.Signal(str, int, int)  # text, x, y
    status = QtCore.Signal(str)
    dbChanged = QtCore.Signal(str)  # kind: 'pending' | 'known' | 'all'
    requestTemplate = QtCore.Signal(str)  # path to ROI image for interactive labeling
    inventoryReady = QtCore.Signal(list)  # list of hint payloads
    manualInventoryCapture = QtCore.Signal(object)  # payload for manual template capture

    def __init__(self, db: PriceDB, hotkey: str = "F1", inventory_hotkey: str = "F2", capture_hotkey: str | None = "F3", tesseract_path: str | None = None, template_threshold: float | None = None, save_debug_images: bool = False):
        super().__init__()
        self.db = db
        self.hotkey = hotkey
        self.inventory_hotkey = inventory_hotkey
        self.capture_hotkey = capture_hotkey
        self.tesseract_path = tesseract_path
        self.template_threshold = template_threshold
        self.save_debug_images = bool(save_debug_images)
        self._running = False
        self._thread = None
        self._hotkey_handles: list[int] = []
        self._log = logging.getLogger(__name__)

    def _hotkey_loop(self):
        inventory_label = self.inventory_hotkey or "—"
        capture_label = self.capture_hotkey or "—"
        info_msg = f"Слушаю хоткеи {self.hotkey} / {inventory_label} / {capture_label} (м.б. требуются права админа)."
        self.status.emit(info_msg)
        handles: list[int] = []
        try:
            self._log.info("Registering hotkey '%s' for price check", self.hotkey)
            handles.append(keyboard.add_hotkey(self.hotkey, self._on_trigger, suppress=True))
            self._log.info("Hotkey listener started on '%s'", self.hotkey)
            
            if self.inventory_hotkey:
                try:
                    self._log.info("Registering inventory hotkey '%s'", self.inventory_hotkey)
                    handles.append(keyboard.add_hotkey(self.inventory_hotkey, self._on_inventory_scan, suppress=True))
                    self._log.info("Inventory hotkey started on '%s'", self.inventory_hotkey)
                except Exception as exc:
                    self._log.exception("Failed to register inventory hotkey '%s': %s", self.inventory_hotkey, exc)
            
            if self.capture_hotkey:
                try:
                    self._log.info("Registering capture hotkey '%s'", self.capture_hotkey)
                    handles.append(keyboard.add_hotkey(self.capture_hotkey, self._on_manual_capture, suppress=True))
                    self._log.info("Capture hotkey started on '%s'", self.capture_hotkey)
                except Exception as exc:
                    self._log.exception("Failed to register capture hotkey '%s': %s", self.capture_hotkey, exc)
            self._hotkey_handles = handles
            while self._running:
                time.sleep(0.1)
        finally:
            for handle in handles:
                try:
                    keyboard.remove_hotkey(handle)
                except Exception:
                    pass
            self._hotkey_handles = []
            self.status.emit("Слушатель остановлен.")
            self._log.info("Hotkey listener stopped")


    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._hotkey_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _ocr_roi(self, roi_img, roi_offset: tuple[int, int]):
        """Run OCR on a pre-captured ROI without re-grabbing the screen."""
        set_tesseract_path(self.tesseract_path)
        debug_token = os.path.join("logs", f"roiocr_{int(time.time()*1000)}")
        data = ocr_full(roi_img, debug_save=debug_token)
        parsed = parse_item(data)
        parsed["image_size"] = getattr(roi_img, "size", (0, 0))
        nbx, nby = parsed.get("name_bbox", (0, 0))
        parsed["name_bbox"] = (roi_offset[0] + int(nbx), roi_offset[1] + int(nby))
        parsed["roi"] = {"left": roi_offset[0], "top": roi_offset[1], "size": getattr(roi_img, "size", (0, 0))}
        parsed["detection"] = get_last_detection_stats()
        return parsed

    def _format_price_value(self, value) -> str:
        if value is None:
            return "—"
        if isinstance(value, (int, float)):
            return _format_price(value)
        try:
            numeric = float(str(value).replace(',', '.'))
            return _format_price(numeric)
        except Exception:
            return str(value)

    def _inventory_lines_for_item(self, item_name: str) -> list[str]:
        prices = self.db.get_prices_by_potential(item_name, threshold=70)
        title = item_name.strip() or "Неизвестный предмет"
        lines: list[str] = [title]
        for pot in range(5):
            price_value = prices.get(pot)
            value_txt = self._format_price_value(price_value)
            lines.append(f"{pot} ЛП: {value_txt}")
        return lines

    def update_settings(self, hotkey: str | None = None, inventory_hotkey: str | None = None, capture_hotkey: str | None = None, tesseract_path: str | None = None, template_threshold: float | None = None, save_debug_images: bool | None = None):
        if hotkey:
            self.hotkey = hotkey
        if inventory_hotkey:
            self.inventory_hotkey = inventory_hotkey
        if capture_hotkey:
            self.capture_hotkey = capture_hotkey
        if tesseract_path is not None:
            self.tesseract_path = tesseract_path
        if template_threshold is not None:
            try:
                self.template_threshold = float(template_threshold)
            except Exception:
                pass
        if save_debug_images is not None:
            self.save_debug_images = bool(save_debug_images)
        # apply image debug setting immediately
        try:
            set_debug_image_saving(self.save_debug_images)
        except Exception:
            pass
        # restart to apply hotkey
        self.stop()
        time.sleep(0.15)
        self.start()

    def _on_manual_capture(self):
        try:
            self._log.info("Manual inventory capture triggered")
            self.status.emit("Готовлю скриншот для шаблона...")
            screen_left, screen_top, screen_w, screen_h = _screen_geom()
            snapshot = _grab_bbox(screen_left, screen_top, screen_w, screen_h)
            os.makedirs("logs", exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            snap_path = os.path.join("logs", f"manual_capture_{ts}.png")
            snapshot.save(snap_path)
            try:
                from log_utils import enforce_logs_quota
                enforce_logs_quota(300.0, logs_dir="logs")
            except Exception:
                pass
            candidates = list_items_missing_inventory()
            if not candidates:
                candidates = list_all_items()
            payload = {"path": snap_path, "items": candidates}
            self._log.info(f"Emitting manualInventoryCapture with screenshot at {snap_path} and {len(candidates)} items")
            self.manualInventoryCapture.emit(payload)
            self.status.emit("Открываю окно выбора предмета...")
            if candidates:
                self.status.emit("Выберите область на скриншоте и предмет для шаблона")
            else:
                self.status.emit("Нет шаблонов для обновления")
        except Exception as e:
            traceback.print_exc()
            self._log.exception("Manual inventory capture failed: %s", e)
            self.status.emit("Ошибка подготовки скриншота для шаблона")

    def _on_inventory_scan(self):
        try:
            self._log.debug("Inventory scan triggered. Detecting item templates...")
            self.status.emit("Сканирую инвентарь...")
            screen_left, screen_top, screen_w, screen_h = _screen_geom()
            inv_left = screen_left + screen_w // 2
            inv_top = screen_top + screen_h // 2
            inv_w = max(1, screen_w - (inv_left - screen_left))
            inv_h = max(1, screen_h - (inv_top - screen_top))
            roi_img = _grab_bbox(inv_left, inv_top, inv_w, inv_h)
            matches = match_inventory_regions(roi_img, threshold=0.80)
            hints: list[dict[str, object]] = []
            for match in matches:
                rect = match.get("rect")
                if not rect or len(rect) != 4:
                    continue
                global_rect = (
                    inv_left + int(rect[0]),
                    inv_top + int(rect[1]),
                    inv_left + int(rect[2]),
                    inv_top + int(rect[3]),
                )
                item_name = str(match.get("item") or "")
                lines = self._inventory_lines_for_item(item_name)
                hints.append({
                    "item": item_name,
                    "score": match.get("score"),
                    "rect": global_rect,
                    "lines": lines,
                })
                self._log.debug(
                    "Inventory match '%s' score=%.3f rect=%s",
                    match.get("item"),
                    match.get("score", 0.0),
                    global_rect,
                )
            if hints:
                self.inventoryReady.emit(hints)
                self.status.emit(f"Найдено {len(hints)} предмет(ов) в инвентаре")
                self._log.info("Inventory scan matched %d item(s)", len(hints))
            else:
                self.inventoryReady.emit([])
                self.status.emit("Совпадений в инвентаре не найдено")
        except Exception as e:
            traceback.print_exc()
            self._log.exception("Inventory scan failed: %s", e)
            self.inventoryReady.emit([])
            self.status.emit("Ошибка сканирования инвентаря")

    def _on_trigger(self):
        try:
            self._log.info("Price check hotkey triggered")
            self.status.emit("Определяю область предмета...")
            self._log.debug("Hotkey triggered. Detecting ROI and matching templates...")
            t0 = time.perf_counter()
            # 1) Detect ROI
            roi_img, roi_offset = detect_roi(self.template_threshold)
            detect_stats = get_last_detection_stats()
            if detect_stats:
                self._log.debug("Corner detection stats: %s", detect_stats)
            # 2) Try template-based match first
            match = match_item_by_templates(roi_img)
            if match:
                item_name, score = match
                # Detect potential globally via 1lp..4lp templates
                potential, pot_score = detect_potential_global(roi_img)
                # Lookup price/comment in DB by name (and potential when set)
                price_txt = None
                rec, sc = (None, 0)
                if potential is not None and int(potential or 0) > 0:
                    rec, sc = self.db.find_best([item_name], threshold=80, potential=int(potential), strict_potential=True)
                if not rec:
                    rec, sc = self.db.find_best([item_name], threshold=80)
                if rec is not None:
                    price_txt = rec.get("price")
                # Compose overlay text: name(+LP) on first line, price/comment on second
                if price_txt is None or str(price_txt).strip() == "":
                    second = "нет в таблице"
                else:
                    if isinstance(price_txt, (int, float)):
                        second = _format_price(price_txt)
                    else:
                        # try numeric conversion
                        try:
                            second = _format_price(float(str(price_txt).replace(",",".")))
                        except Exception:
                            second = str(price_txt)
                lp_suffix = f" (ЛП {int(potential)})" if potential is not None else ""
                txt = f"{item_name}{lp_suffix}\n{second}"
                self.boxReady.emit(txt, roi_offset[0] + 40, roi_offset[1] + 60)
                dt = (time.perf_counter() - t0) * 1000
                self._log.info("Template match %.0f ms: '%s' (score=%.2f, pot=%s)", dt, item_name, score, potential)
                return

            # 3) No templates — open capture dialog
            self.status.emit("Шаблон не найден — откроется окно создания шаблонов")
            try:
                os.makedirs("logs", exist_ok=True)
                roi_path = os.path.join("logs", f"roi_{int(time.time()*1000)}.png")
                roi_img.save(roi_path)
                from log_utils import enforce_logs_quota
                enforce_logs_quota(300.0, logs_dir="logs")
            except Exception:
                roi_path = ""
            self.requestTemplate.emit(roi_path)

            parsed = self._ocr_roi(roi_img, roi_offset)
            detection = parsed.get("detection")
            if detection:
                self._log.debug("OCR fallback detection: %s", detection)
            left, top = parsed.get("name_bbox", (roi_offset[0] + 40, roi_offset[1] + 60))
            nm = (parsed.get("name", "") or "").strip()
            lines = parsed.get("lines", [])
            if nm:
                lines = [nm] + list(lines)
            bigrams = []
            L = min(6, len(lines))
            for i in range(L - 1):
                a = lines[i].strip(); b = lines[i + 1].strip()
                if a and b:
                    bigrams.append(f"{a} {b}")
            if bigrams:
                lines = list(lines) + bigrams

            potential, pot_score = detect_potential_global(roi_img)
            if pot_score:
                self._log.debug("LP detection score: %.3f for potential %s", pot_score, potential)

            rec, score = (None, 0)
            if potential is not None and int(potential or 0) > 0:
                rec, score = self.db.find_best(lines, threshold=80, potential=int(potential), strict_potential=True)
            if not rec:
                rec, score = self.db.find_best(lines, threshold=80, potential=potential)
            if rec and rec.get("price") is not None:
                price = rec.get("price")
                if isinstance(price, (int, float)):
                    show_txt = f"Цена: {_format_price(price)}"
                else:
                    try:
                        _ = float(str(price).replace(",", "."))
                        show_txt = f"Цена: {_format_price(price)}"
                    except Exception:
                        show_txt = str(price)
                lp_suffix = f" (ЛП {int(potential)})" if potential is not None else ""
                msg = f"{nm or '—'}{lp_suffix}"
                if show_txt:
                    msg = f"{msg}\n{show_txt}"
                self.boxReady.emit(msg, left, top)
                dt = (time.perf_counter() - t0) * 1000
                self._log.info(
                    "Fallback OCR %.0f ms; fuzzy=%s%% for '%s' (pot=%s score=%.2f)",
                    dt,
                    score,
                    rec.get('name'),
                    rec.get('potential'),
                    pot_score,
                )
                return
            elif rec:
                lp_suffix = f" (ЛП {int(potential)})" if potential is not None else ""
                msg = f"{nm or '—'}{lp_suffix}"
                msg = f"{msg}\nСовпадение без цены"
                self.boxReady.emit(msg, left, top)
                self._log.info("Match %s%% for '%s' (pot=%s) but price=None", score, rec.get('name'), rec.get('potential'))
                return

            lp_suffix = f" (ЛП {int(potential)})" if potential is not None else ""
            msg = f"{nm or '—'}{lp_suffix}"
            msg = f"{msg}\nСовпадений не найдено"
            self.boxReady.emit(msg, left, top)
            self._log.info("No match >=80%%. Potential=%s. Lines sample=%s", potential, lines[:3])

        except Exception as e:
            traceback.print_exc()
            self._log.exception("Error during OCR/lookup: %s", e)
            self.boxReady.emit("OCR ошибка", 40, 40)
