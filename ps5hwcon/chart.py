import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

SERIES_COLORS = ("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181")
SURFACE = QColor("#333333")
GRID = QColor("#454545")
AXIS_TEXT = QColor("#aaaaaa")
TEXT = QColor("#ffffff")
CROSSHAIR = QColor("#888888")
TOOLTIP_BG = QColor("#2b2b2b")
TOOLTIP_BORDER = QColor("#555555")
GRID_LINES = 4
LEGEND_HEIGHT = 20
AXIS_WIDTH = 64


def _nice_step(span):
    raw = span / GRID_LINES
    magnitude = 10 ** math.floor(math.log10(raw))
    return next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)


def _ago(seconds):
    seconds = round(seconds)
    if seconds < 60:
        return f"{seconds} s ago" if seconds else "now"
    return f"{seconds // 60} min {seconds % 60:02d} s ago"


class LineChart(QWidget):
    """Time-series lines on one shared axis, with a legend and a hover crosshair."""

    def __init__(self, format_value, y_range=None, parent=None):
        super().__init__(parent)
        self.format_value = format_value
        self.y_range = y_range
        self.series = []
        self.now = 0.0
        self.span = 300
        self.hover_x = None
        self.setMinimumHeight(170)
        self.setMouseTracking(True)

    def set_data(self, series, now, span):
        """`series` is [(name, color, [(time, value or None), ...]), ...]."""
        self.series = series
        self.now = now
        self.span = span
        self.update()

    def _legend_height(self):
        return LEGEND_HEIGHT if len(self.series) > 1 else 0

    def _plot_rect(self):
        top = 8 + self._legend_height()
        return QRectF(AXIS_WIDTH, top, self.width() - AXIS_WIDTH - 10, self.height() - top - 24)

    def _bounds(self):
        """(low, high, step): the axis range, rounded out to whole gridline steps."""
        if self.y_range is not None:
            low, high = self.y_range
            return low, high, (high - low) / GRID_LINES
        values = [v for _, _, points in self.series for t, v in points if v is not None]
        if not values:
            return 0, GRID_LINES, 1
        low, high = min(values), max(values)
        if high - low < 1:
            low, high = low - 1, high + 1
        step = _nice_step(high - low)
        return math.floor(low / step) * step, math.ceil(high / step) * step, step

    def _to_point(self, rect, low, high, t, value):
        x = rect.right() - (self.now - t) / self.span * rect.width()
        y = rect.bottom() - (value - low) / (high - low) * rect.height()
        return QPointF(x, y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        metrics = QFontMetrics(painter.font())
        rect = self._plot_rect()
        low, high, step = self._bounds()
        self._paint_legend(painter, metrics)
        self._paint_axes(painter, rect, low, high, step)
        painter.save()
        painter.setClipRect(rect.adjusted(-2, -2, 2, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for name, color, points in self.series:
            path = QPainterPath()
            drawing = False
            for t, value in points:
                if value is None or t < self.now - self.span - 5:
                    drawing = False
                    continue
                point = self._to_point(rect, low, high, t, value)
                if drawing:
                    path.lineTo(point)
                else:
                    path.moveTo(point)
                    drawing = True
            pen = QPen(QColor(color), 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(path)
        painter.restore()
        if self.hover_x is not None:
            self._paint_hover(painter, metrics, rect, low, high)

    def _paint_legend(self, painter, metrics):
        if len(self.series) < 2:
            return
        x = AXIS_WIDTH
        for name, color, points in self.series:
            latest = next((v for _, v in reversed(points) if v is not None), None)
            label = f"{name}  {self.format_value(latest) if latest is not None else '–'}"
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(QRectF(x, 8 + 4, 12, 4), 2, 2)
            painter.setPen(TEXT)
            painter.drawText(QPointF(x + 18, 8 + metrics.ascent() - 1), label)
            x += 18 + metrics.horizontalAdvance(label) + 18

    def _paint_axes(self, painter, rect, low, high, step):
        lines = round((high - low) / step)
        for index in range(lines + 1):
            value = low + step * index
            y = rect.bottom() - rect.height() * index / lines
            painter.setPen(QPen(GRID, 1))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            painter.setPen(AXIS_TEXT)
            text = self.format_value(value)
            painter.drawText(
                QRectF(0, y - 8, AXIS_WIDTH - 8, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                text,
            )
        minutes = self.span / 60
        for fraction, text in ((0, f"-{minutes:g} min"), (0.5, f"-{minutes / 2:g} min"), (1, "now")):
            x = rect.left() + rect.width() * fraction
            align = (Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignHCenter, Qt.AlignmentFlag.AlignRight)
            box = QRectF(x - 50 * (fraction * 2), rect.bottom() + 6, 100, 16)
            painter.drawText(box, align[int(fraction * 2)] | Qt.AlignmentFlag.AlignTop, text)

    def _paint_hover(self, painter, metrics, rect, low, high):
        t = self.now - (rect.right() - self.hover_x) / rect.width() * self.span
        rows = []
        snapped = None
        for name, color, points in self.series:
            near = [(abs(pt - t), pt, v) for pt, v in points if v is not None]
            if not near:
                continue
            _, pt, value = min(near)
            snapped = pt if snapped is None else snapped
            rows.append((name, color, value, self._to_point(rect, low, high, pt, value)))
        if not rows:
            return
        x = self._to_point(rect, low, high, snapped, low).x()
        painter.setPen(QPen(CROSSHAIR, 1))
        painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        for _, color, _, point in rows:
            painter.setPen(QPen(SURFACE, 2))
            painter.setBrush(QColor(color))
            painter.drawEllipse(point, 4.5, 4.5)

        lines = [_ago(self.now - snapped)] + [
            f"{name}  {self.format_value(value)}" if len(self.series) > 1 else self.format_value(value)
            for name, _, value, _ in rows
        ]
        width = max(metrics.horizontalAdvance(line) for line in lines) + 34
        height = metrics.height() * len(lines) + 12
        left = x + 12 if x + 12 + width < rect.right() else x - 12 - width
        box = QRectF(left, rect.top() + 4, width, height)
        painter.setPen(QPen(TOOLTIP_BORDER, 1))
        painter.setBrush(TOOLTIP_BG)
        painter.drawRoundedRect(box, 4, 4)
        y = box.top() + 6 + metrics.ascent()
        painter.setPen(AXIS_TEXT)
        painter.drawText(QPointF(box.left() + 10, y), lines[0])
        for (name, color, _, _), line in zip(rows, lines[1:]):
            y += metrics.height()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(QRectF(box.left() + 10, y - metrics.ascent() / 2 - 1, 10, 4), 2, 2)
            painter.setPen(TEXT)
            painter.drawText(QPointF(box.left() + 26, y), line)

    def mouseMoveEvent(self, event):
        rect = self._plot_rect()
        x = event.position().x()
        self.hover_x = x if rect.left() <= x <= rect.right() and self.series else None
        self.update()

    def leaveEvent(self, event):
        self.hover_x = None
        self.update()
