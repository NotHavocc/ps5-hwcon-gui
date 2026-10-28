import copy

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import QSizePolicy, QWidget

from .common import FAN_CURVE_TEMP_MAX, FAN_CURVE_TEMP_MIN, percent_to_pwm, pwm_to_percent
from .widgets import ACCENT

STOP_HANDLE = "stop"
HANDLE_RADIUS = 6
GRAB_RADIUS = 12
MARGIN_LEFT = 42
MARGIN_RIGHT = 14
MARGIN_TOP = 26
MARGIN_BOTTOM = 30


class CurveEditor(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._curve = None
        self._live = (None, None)
        self._hover = None
        self._drag = None
        self.setMouseTracking(True)
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_curve(self, curve):
        self._curve = copy.deepcopy(curve)
        self._drag = None
        self.update()

    def curve(self):
        return copy.deepcopy(self._curve)

    def set_live(self, temp, pwm):
        if self._live != (temp, pwm):
            self._live = (temp, pwm)
            self.update()

    # Geometry

    def _plot(self):
        return QRectF(
            MARGIN_LEFT,
            MARGIN_TOP,
            max(1, self.width() - MARGIN_LEFT - MARGIN_RIGHT),
            max(1, self.height() - MARGIN_TOP - MARGIN_BOTTOM),
        )

    def _to_screen(self, temp, percent):
        plot = self._plot()
        temp = min(FAN_CURVE_TEMP_MAX, max(FAN_CURVE_TEMP_MIN, temp))
        x = plot.left() + (temp - FAN_CURVE_TEMP_MIN) / (FAN_CURVE_TEMP_MAX - FAN_CURVE_TEMP_MIN) * plot.width()
        y = plot.bottom() - percent / 100 * plot.height()
        return QPointF(x, y)

    def _from_screen(self, pos):
        plot = self._plot()
        temp = FAN_CURVE_TEMP_MIN + (pos.x() - plot.left()) / plot.width() * (
            FAN_CURVE_TEMP_MAX - FAN_CURVE_TEMP_MIN
        )
        percent = (plot.bottom() - pos.y()) / plot.height() * 100
        return round(temp), round(min(100, max(0, percent)))

    def _handles(self):
        if self._curve is None:
            return []
        handles = [(STOP_HANDLE, self._to_screen(self._curve["stop"], 0))]
        for index, (temp, pwm) in enumerate(self._curve["points"]):
            handles.append((index, self._to_screen(temp, pwm_to_percent(pwm))))
        return handles

    def _handle_at(self, pos):
        best, best_distance = None, GRAB_RADIUS
        # Points first, so the first point wins over the stop handle when they overlap.
        for handle, point in reversed(self._handles()):
            distance = (point - QPointF(pos)).manhattanLength()
            if distance <= best_distance:
                best, best_distance = handle, distance
        return best

    # Editing

    def _move(self, handle, temp, percent):
        points = self._curve["points"]
        if handle == STOP_HANDLE:
            temp = min(points[0][0] - 1, max(FAN_CURVE_TEMP_MIN, temp))
            if temp == self._curve["stop"]:
                return False
            self._curve["stop"] = temp
            return True

        last = len(points) - 1
        low = points[handle - 1][0] + 1 if handle else self._curve["stop"] + 1
        high = points[handle + 1][0] - 1 if handle < last else FAN_CURVE_TEMP_MAX
        temp = min(high, max(low, temp))
        old_temp, old_pwm = points[handle]
        pwm = old_pwm
        if handle < last:
            pwm_low = points[handle - 1][1] if handle else 0
            pwm_high = points[handle + 1][1]
            if pwm_to_percent(old_pwm) != percent:
                pwm = min(pwm_high, max(pwm_low, percent_to_pwm(percent)))
        if (temp, pwm) == (old_temp, old_pwm):
            return False
        points[handle] = [temp, pwm]
        return True

    def mousePressEvent(self, event):
        if not self.isEnabled() or event.button() != Qt.MouseButton.LeftButton:
            return
        self._drag = self._handle_at(event.position())
        self._hover = self._drag
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._drag is not None:
            if self._move(self._drag, *self._from_screen(pos)):
                self.changed.emit()
            self.update()
            return
        hover = self._handle_at(pos) if self.isEnabled() else None
        if hover != self._hover:
            self._hover = hover
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if hover is not None else Qt.CursorShape.ArrowCursor
            )
            self.update()

    def mouseReleaseEvent(self, _event):
        self._drag = None
        self.update()

    def leaveEvent(self, _event):
        if self._drag is None and self._hover is not None:
            self._hover = None
            self.update()

    def keyPressEvent(self, event):
        handle = self._hover
        if self._curve is None or handle is None or not self.isEnabled():
            return super().keyPressEvent(event)
        if handle == STOP_HANDLE:
            temp, percent = self._curve["stop"], 0
        else:
            temp, pwm = self._curve["points"][handle]
            percent = pwm_to_percent(pwm)
        key = event.key()
        if key == Qt.Key.Key_Left:
            temp -= 1
        elif key == Qt.Key.Key_Right:
            temp += 1
        elif key == Qt.Key.Key_Up:
            percent += 1
        elif key == Qt.Key.Key_Down:
            percent -= 1
        else:
            return super().keyPressEvent(event)
        if self._move(handle, temp, min(100, max(0, percent))):
            self.changed.emit()
        self.update()

    # Painting

    def _describe(self, handle):
        if handle == STOP_HANDLE:
            return f"Fan stops below {self._curve['stop']} °C"
        temp, pwm = self._curve["points"][handle]
        return f"Point {handle + 1}: {temp} °C → {pwm_to_percent(pwm)}%"

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot = self._plot()
        enabled = self.isEnabled()
        accent = QColor(ACCENT if enabled else "#666666")
        text = QColor("#aaaaaa")

        painter.fillRect(plot, QColor("#2b2b2b"))
        grid_pen = QPen(QColor("#444444"), 1)
        painter.setFont(self.font())
        metrics = painter.fontMetrics()
        for temp in range(FAN_CURVE_TEMP_MIN, FAN_CURVE_TEMP_MAX + 1, 10):
            x = self._to_screen(temp, 0).x()
            painter.setPen(grid_pen)
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            painter.setPen(text)
            label = f"{temp}°"
            painter.drawText(
                QPointF(x - metrics.horizontalAdvance(label) / 2, plot.bottom() + metrics.height()),
                label,
            )
        for percent in range(0, 101, 20):
            y = self._to_screen(FAN_CURVE_TEMP_MIN, percent).y()
            painter.setPen(grid_pen)
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(text)
            label = f"{percent}%"
            painter.drawText(
                QPointF(plot.left() - metrics.horizontalAdvance(label) - 6, y + metrics.ascent() / 2 - 1),
                label,
            )
        painter.setPen(QPen(QColor("#555555"), 1))
        painter.drawRect(plot)

        if self._curve is None:
            painter.setPen(text)
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, "Reading fan curve…")
            return

        points = [self._to_screen(t, pwm_to_percent(p)) for t, p in self._curve["points"]]
        stop = self._to_screen(self._curve["stop"], 0)
        first_floor = QPointF(points[0].x(), plot.bottom())

        # Between the stop temperature and point 1 the fan keeps its last state (hysteresis).
        band = QColor(accent)
        band.setAlpha(40)
        painter.fillRect(QRectF(stop.x(), plot.top(), first_floor.x() - stop.x(), plot.height()), band)

        fill = QPainterPath(first_floor)
        for point in points:
            fill.lineTo(point)
        fill.lineTo(QPointF(plot.right(), points[-1].y()))
        fill.lineTo(QPointF(plot.right(), plot.bottom()))
        fill.closeSubpath()
        area = QColor(accent)
        area.setAlpha(50)
        painter.fillPath(fill, area)

        painter.setPen(QPen(accent, 1, Qt.PenStyle.DashLine))
        painter.drawLine(first_floor, points[0])
        painter.setPen(QPen(accent, 2))
        painter.drawPolyline(QPolygonF(points + [QPointF(plot.right(), points[-1].y())]))

        live_temp, live_pwm = self._live
        if live_temp is not None:
            marker = QColor("#f0b44c")
            x = self._to_screen(live_temp, 0).x()
            painter.setPen(QPen(marker, 1, Qt.PenStyle.DotLine))
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            if live_pwm is not None:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(marker)
                painter.drawEllipse(self._to_screen(live_temp, pwm_to_percent(live_pwm)), 4, 4)

        active = self._drag if self._drag is not None else self._hover
        for handle, center in self._handles():
            highlighted = handle == active
            painter.setPen(QPen(QColor("#ffffff") if highlighted else accent, 2))
            painter.setBrush(accent if highlighted else QColor("#333333"))
            radius = HANDLE_RADIUS + (1 if highlighted else 0)
            if handle == STOP_HANDLE:
                painter.drawPolygon(
                    QPolygonF(
                        [
                            center + QPointF(0, -radius),
                            center + QPointF(radius, 0),
                            center + QPointF(0, radius),
                            center + QPointF(-radius, 0),
                        ]
                    )
                )
            else:
                painter.drawEllipse(center, radius, radius)

        painter.setPen(QColor("#ffffff"))
        if active is not None:
            caption = self._describe(active)
        elif live_temp is not None:
            speed = f" · fan {pwm_to_percent(live_pwm)}%" if live_pwm is not None else ""
            caption = f"SoC {round(live_temp)} °C{speed}"
        else:
            caption = ""
        painter.drawText(
            QRectF(plot.left(), 0, plot.width(), MARGIN_TOP - 4),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            caption,
        )
