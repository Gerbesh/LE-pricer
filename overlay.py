from PySide6 import QtCore, QtGui, QtWidgets


class HintWindow(QtWidgets.QWidget):
    def __init__(self, rect: tuple[int, int, int, int], lines: list[str], duration_ms: int = 3500):
        super().__init__()
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.Tool
            | QtCore.Qt.WindowStaysOnTopHint
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        self._lines = [str(line) for line in (lines or [])]
        self._font = QtGui.QFont("Segoe UI", 9)
        self._padding = 6
        self._text_margin = 8
        self._configure_geometry(rect)
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.close)
        self._timer.start(max(500, duration_ms))
        self.show()
        self.raise_()

    def _configure_geometry(self, rect: tuple[int, int, int, int]):
        left, top, right, bottom = [int(v) for v in rect]
        width = max(12, right - left)
        height = max(12, bottom - top)
        metrics = QtGui.QFontMetrics(self._font)
        text_width = max((metrics.horizontalAdvance(line) for line in self._lines), default=0)
        text_height = metrics.lineSpacing() * max(1, len(self._lines))
        highlight_w = max(width, text_width + self._text_margin * 2)
        highlight_h = max(height, text_height + self._text_margin * 2)
        self._highlight_rect = QtCore.QRect(self._padding, self._padding, highlight_w, highlight_h)
        geom = QtCore.QRect(
            left - self._padding,
            top - self._padding,
            self._highlight_rect.width() + self._padding * 2,
            self._highlight_rect.height() + self._padding * 2,
        )
        self.setGeometry(geom)
        self._text_origin = QtCore.QPoint(
            self._highlight_rect.left() + self._text_margin,
            self._highlight_rect.top() + self._text_margin,
        )

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setPen(QtGui.QPen(QtGui.QColor(48, 182, 240, 240), 2))
        painter.setBrush(QtGui.QColor(48, 182, 240, 60))
        painter.drawRoundedRect(self._highlight_rect, 8, 8)
        painter.setFont(self._font)
        painter.setPen(QtGui.QColor(5, 5, 5))
        metrics = QtGui.QFontMetrics(self._font)
        y = self._text_origin.y() + metrics.ascent()
        x = self._text_origin.x()
        for line in self._lines:
            painter.drawText(x, y, line)
            y += metrics.lineSpacing()


class PriceOverlay(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        # Configure window flags after construction (PySide6 doesn't accept 'flags' kwarg)
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.Tool
            | QtCore.Qt.WindowStaysOnTopHint
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        self._text = ""
        self._rect = QtCore.QRect(0, 0, 220, 56)
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self._hint_windows: list[HintWindow] = []

    def show_box(self, text: str, x: int, y: int, duration_ms: int = 2200):
        self._text = text
        # Multi-line sizing support
        lines = (text or "").splitlines() or [""]
        max_len = max((len(s) for s in lines), default=0)
        line_h = 22
        pad_h = 14
        h = max(44, line_h * len(lines) + pad_h)
        # place a bit above y (which is top of item name)
        w = max(240, 10 * max_len + 40)
        self._rect = QtCore.QRect(x, max(5, y - h - 8), w, h)
        self.setGeometry(self._rect.adjusted(-8, -8, 8, 8))
        self.show()
        self.raise_()
        self._timer.start(duration_ms)

    def show_inventory_hints(self, hints: list[dict], duration_ms: int = 3500):
        for window in self._hint_windows:
            try:
                window.close()
                window.deleteLater()
            except Exception:
                pass
        self._hint_windows = []
        if not hints:
            return
        for hint in hints:
            rect = hint.get('rect')
            lines = hint.get('lines', [])
            if not rect or len(rect) != 4:
                continue
            window = HintWindow(tuple(int(v) for v in rect), list(lines), duration_ms)
            self._hint_windows.append(window)
        QtCore.QTimer.singleShot(duration_ms + 300, self._cleanup_hints)

    def _cleanup_hints(self):
        alive: list[HintWindow] = []
        for window in self._hint_windows:
            if window.isVisible():
                alive.append(window)
            else:
                window.deleteLater()
        self._hint_windows = alive

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        r = self.rect().adjusted(4, 4, -4, -4)
        # white box with subtle shadow
        shadow = QtGui.QColor(0, 0, 0, 70)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(shadow)
        p.drawRoundedRect(r.adjusted(2, 2, 2, 2), 10, 10)

        p.setBrush(QtGui.QColor("white"))
        p.drawRoundedRect(r, 10, 10)

        # text
        p.setPen(QtGui.QColor("black"))
        font = QtGui.QFont("Segoe UI", 12, QtGui.QFont.DemiBold)
        p.setFont(font)
        # Support multi-line text
        p.drawText(r, QtCore.Qt.AlignCenter, self._text)

