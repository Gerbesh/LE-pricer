from PySide6 import QtCore, QtGui, QtWidgets
import re

VALUE_RE = re.compile(r"-?\d[\d\s]*")
PRICE_THRESHOLD = 100000


def _extract_value(line: str) -> int | None:
    if not line:
        return None
    cleaned = str(line).replace(' ', ' ')
    match = VALUE_RE.search(cleaned)
    if not match:
        return None
    fragment = match.group()
    negative = fragment.strip().startswith('-')
    digits = ''.join(ch for ch in fragment if ch.isdigit())
    if not digits:
        return None
    try:
        value = int(digits)
    except Exception:
        return None
    return -value if negative else value


def _line_color(value: int | None, threshold: int, original: str | None = None) -> QtGui.QColor:
    if value is None:
        if original:
            lowered = original.lower()
            if 'нет' in lowered or 'unknown' in lowered or 'нет ' in lowered or ' no ' in lowered:
                return QtGui.QColor(210, 82, 82, 185)
        return QtGui.QColor(90, 100, 120, 150)
    if value >= threshold:
        return QtGui.QColor(68, 170, 108, 185)
    return QtGui.QColor(210, 82, 82, 185)


class HintWindow(QtWidgets.QWidget):
    def __init__(
        self,
        rect: tuple[int, int, int, int],
        lines: list[str],
        duration_ms: int = 4000,
        threshold: int = PRICE_THRESHOLD,
    ):
        super().__init__()
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.Tool
            | QtCore.Qt.WindowStaysOnTopHint
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        self._lines = [str(line) for line in (lines or [])]
        self._font = QtGui.QFont("Segoe UI", 10)
        self._padding = 10
        self._text_margin = 12
        self._threshold = threshold
        self._line_layout: list[dict[str, object]] = []
        self._configure_geometry(rect)
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.close)
        self._timer.start(max(500, duration_ms))
        self.show()
        self.raise_()

    def _configure_geometry(self, rect: tuple[int, int, int, int]):
        left, top, right, bottom = [int(v) for v in rect]
        width = max(16, right - left)
        height = max(16, bottom - top)
        metrics = QtGui.QFontMetrics(self._font)
        text_width = max((metrics.horizontalAdvance(line) for line in self._lines), default=0)
        line_spacing = metrics.lineSpacing()
        content_width = max(width, text_width + self._text_margin * 2)
        content_height = max(height, line_spacing * max(1, len(self._lines)) + self._text_margin * 2)
        self._highlight_rect = QtCore.QRect(self._padding, self._padding, content_width, content_height)
        geom = QtCore.QRect(
            left - self._padding,
            top - self._padding,
            self._highlight_rect.width() + self._padding * 2,
            self._highlight_rect.height() + self._padding * 2,
        )
        self.setGeometry(geom)
        self._build_line_layout(metrics)

    def _build_line_layout(self, metrics: QtGui.QFontMetrics) -> None:
        line_spacing = metrics.lineSpacing()
        inner_left = self._highlight_rect.left() + self._text_margin
        inner_width = max(40, self._highlight_rect.width() - self._text_margin * 2)
        y = self._highlight_rect.top() + self._text_margin
        layout: list[dict[str, object]] = []
        for line in self._lines:
            rect = QtCore.QRect(inner_left, y - metrics.ascent() - 6, inner_width, line_spacing + 12)
            baseline = y + metrics.ascent()
            value = _extract_value(line)
            layout.append({
                "text": line,
                "rect": rect,
                "baseline": baseline,
                "color": _line_color(value, self._threshold, line),
            })
            y += line_spacing
        self._line_layout = layout

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        shadow_rect = self._highlight_rect.adjusted(-4, -4, 4, 4)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(0, 0, 0, 90))
        painter.drawRoundedRect(shadow_rect, 14, 14)
        painter.setBrush(QtGui.QColor(24, 28, 38, 225))
        painter.setPen(QtGui.QPen(QtGui.QColor(120, 180, 255, 170), 1.4))
        painter.drawRoundedRect(self._highlight_rect, 12, 12)
        for entry in self._line_layout:
            rect = entry["rect"]
            color = entry["color"]
            painter.setBrush(color)
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(rect, 8, 8)
        painter.setFont(self._font)
        painter.setPen(QtGui.QColor(255, 255, 255))
        for entry in self._line_layout:
            rect = entry["rect"]
            baseline = entry["baseline"]
            painter.drawText(rect.left() + 8, int(baseline), entry["text"])  # type: ignore[arg-type]


class PriceOverlay(QtWidgets.QWidget):
    def __init__(self, box_duration_ms: int = 4000, hint_duration_ms: int = 4000, price_threshold: int = PRICE_THRESHOLD):
        super().__init__()
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.Tool
            | QtCore.Qt.WindowStaysOnTopHint
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        self._font = QtGui.QFont("Segoe UI", 12, QtGui.QFont.DemiBold)
        self._padding = 12
        self._text_margin = 14
        self._lines: list[str] = []
        self._highlight_rect = QtCore.QRect(self._padding, self._padding, 220, 56)
        self._line_layout: list[tuple[str, QtCore.QRect, int, QtGui.QColor]] = []
        self._layout_dirty = False
        self._box_duration_ms = max(500, int(box_duration_ms))
        self._hint_duration_ms = max(500, int(hint_duration_ms))
        self._price_threshold = price_threshold
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self._hint_windows: list[HintWindow] = []

    def show_box(self, text: str, x: int, y: int, duration_ms: int | None = None):
        self._lines = (text or "").splitlines() or [""]
        metrics = QtGui.QFontMetrics(self._font)
        text_width = max((metrics.horizontalAdvance(line) for line in self._lines), default=0)
        line_spacing = metrics.lineSpacing()
        highlight_w = max(240, text_width + self._text_margin * 2)
        highlight_h = max(line_spacing + self._text_margin * 2, line_spacing * len(self._lines) + self._text_margin * 2)
        widget_w = highlight_w + self._padding * 2
        widget_h = highlight_h + self._padding * 2
        top = max(5, y - highlight_h - self._padding)
        geom = QtCore.QRect(x - self._padding, top - self._padding, widget_w, widget_h)
        self.setGeometry(geom)
        self._highlight_rect = QtCore.QRect(self._padding, self._padding, highlight_w, highlight_h)
        self._layout_dirty = True
        self.show()
        self.raise_()
        duration = duration_ms if duration_ms is not None else self._box_duration_ms
        self._timer.start(max(500, duration))

    def show_inventory_hints(self, hints: list[dict], duration_ms: int | None = None):
        for window in self._hint_windows:
            try:
                window.close()
                window.deleteLater()
            except Exception:
                pass
        self._hint_windows = []
        if not hints:
            return
        lifetime = duration_ms if duration_ms is not None else self._hint_duration_ms
        lifetime = max(500, int(lifetime))
        for hint in hints:
            rect = hint.get('rect')
            lines = hint.get('lines', [])
            if not rect or len(rect) != 4:
                continue
            window = HintWindow(tuple(int(v) for v in rect), list(lines), duration_ms=lifetime, threshold=self._price_threshold)
            self._hint_windows.append(window)
        QtCore.QTimer.singleShot(lifetime + 300, self._cleanup_hints)

    def _cleanup_hints(self):
        alive: list[HintWindow] = []
        for window in self._hint_windows:
            if window.isVisible():
                alive.append(window)
            else:
                window.deleteLater()
        self._hint_windows = alive

    def _ensure_line_layout(self) -> None:
        if not self._layout_dirty:
            return
        metrics = QtGui.QFontMetrics(self._font)
        line_spacing = metrics.lineSpacing()
        inner_left = self._highlight_rect.left() + self._text_margin
        inner_width = max(40, self._highlight_rect.width() - self._text_margin * 2)
        y = self._highlight_rect.top() + self._text_margin
        layout: list[tuple[str, QtCore.QRect, int, QtGui.QColor]] = []
        for line in self._lines:
            rect = QtCore.QRect(inner_left, y - metrics.ascent() - 6, inner_width, line_spacing + 12)
            baseline = y + metrics.ascent()
            color = _line_color(_extract_value(line), self._price_threshold, line)
            layout.append((line, rect, int(baseline), color))
            y += line_spacing
        self._line_layout = layout
        self._layout_dirty = False

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        self._ensure_line_layout()
        shadow_rect = self._highlight_rect.adjusted(-4, -4, 4, 4)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(0, 0, 0, 90))
        painter.drawRoundedRect(shadow_rect, 16, 16)
        painter.setBrush(QtGui.QColor(20, 24, 34, 225))
        painter.setPen(QtGui.QPen(QtGui.QColor(120, 180, 255, 170), 1.6))
        painter.drawRoundedRect(self._highlight_rect, 14, 14)
        for line, rect, baseline, color in self._line_layout:
            painter.setBrush(color)
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(rect, 8, 8)
        painter.setFont(self._font)
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255)))
        for line, rect, baseline, color in self._line_layout:
            painter.drawText(rect.left() + 10, baseline, line)
