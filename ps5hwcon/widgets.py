from PyQt6.QtCore import QPropertyAnimation, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

ACCENT = "#1a9fff"


def restyle(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def muted_label(text="", word_wrap=True):
    label = QLabel(text)
    label.setObjectName("muted")
    label.setWordWrap(word_wrap)
    return label


class Card(QGroupBox):
    def __init__(self, title="", parent=None):
        super().__init__(title, parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 8, 12, 12)
        self._layout.setSpacing(10)

    def set_title(self, title):
        self.setTitle(title)

    def add(self, widget):
        self._layout.addWidget(widget)
        return widget

    def add_layout(self, layout):
        self._layout.addLayout(layout)
        return layout


class InfoRow(QWidget):
    def __init__(self, label, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        top = QHBoxLayout()
        top.setSpacing(12)
        self.label = QLabel(label)
        self.value = QLabel("…")
        self.value.setObjectName("value")
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        top.addWidget(self.label)
        top.addStretch(1)
        top.addWidget(self.value)
        layout.addLayout(top)
        self.description = muted_label()
        self.description.hide()
        layout.addWidget(self.description)

    def set(self, value, description=None, error=False):
        self.value.setText(value)
        self.description.setText(description or "")
        self.description.setVisible(bool(description))
        self.description.setObjectName("error" if error else "muted")
        restyle(self.description)


class ToggleRow(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, label, description="", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.checkbox = QCheckBox(label)
        self.checkbox.clicked.connect(self.toggled.emit)
        layout.addWidget(self.checkbox)
        self.description = muted_label(description)
        self.description.setContentsMargins(22, 0, 0, 0)
        layout.addWidget(self.description)

    def set_checked(self, checked):
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(checked)
        self.checkbox.blockSignals(False)

    def is_checked(self):
        return self.checkbox.isChecked()

    def set_description(self, text):
        self.description.setText(text)

    def setEnabled(self, enabled):
        self.checkbox.setEnabled(enabled)


class SliderRow(QWidget):
    changed = pyqtSignal(int)

    def __init__(self, label, description="", suffix="", format_value=None, parent=None):
        super().__init__(parent)
        self._values = [0]
        self._suffix = suffix
        self._format = format_value or (lambda v: f"{v}{suffix}")
        self._reset_value = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.label = QLabel(f"{label}:")
        self.label.setMinimumWidth(130)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.valueChanged.connect(self._on_slider)
        self.value_label = QLabel()
        self.value_label.setObjectName("value")
        self.value_label.setMinimumWidth(70)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.reset_button = QToolButton()
        self.reset_button.setText("↺")
        self.reset_button.setToolTip("Reset")
        self.reset_button.setObjectName("reset")
        self.reset_button.clicked.connect(self._reset)
        self.reset_button.hide()
        row.addWidget(self.label)
        row.addWidget(self.slider, 1)
        row.addWidget(self.value_label)
        row.addWidget(self.reset_button)
        layout.addLayout(row)

        self.description = muted_label(description)
        self.description.setVisible(bool(description))
        layout.addWidget(self.description)

    def set_values(self, values, value=None, end_labels=None, reset_value=None):
        self._values = list(values) or [0]
        self._reset_value = reset_value
        self.reset_button.setVisible(reset_value is not None)
        low, high = end_labels or (self._format(self._values[0]), self._format(self._values[-1]))
        self.slider.setToolTip(f"{low} – {high}")
        self.slider.blockSignals(True)
        self.slider.setRange(0, len(self._values) - 1)
        self.slider.setPageStep(max(1, len(self._values) // 10))
        self.slider.blockSignals(False)
        self.set_value(self._values[0] if value is None else value)

    def set_range(self, low, high, step=1, value=None, **kwargs):
        values = list(range(low, high + 1, step))
        if values[-1] != high:
            values.append(high)
        self.set_values(values, value, **kwargs)

    def _index_of(self, value):
        return min(range(len(self._values)), key=lambda i: (abs(self._values[i] - value), i))

    def set_value(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(self._index_of(value))
        self.slider.blockSignals(False)
        self.value_label.setText(self._format(self.value()))

    def value(self):
        return self._values[self.slider.value()]

    def _on_slider(self, _index):
        self.value_label.setText(self._format(self.value()))
        self.changed.emit(self.value())

    def _reset(self):
        if self._reset_value is None or not self.slider.isEnabled():
            return
        self.slider.setValue(self._index_of(self._reset_value))

    def setEnabled(self, enabled):
        self.slider.setEnabled(enabled)
        self.reset_button.setEnabled(enabled)
        self.value_label.setEnabled(enabled)


class ChoiceButton(QPushButton):
    """A button with a title, an optional subtitle and an accent bar when selected."""

    def __init__(self, title, subtitle="", parent=None):
        super().__init__(parent)
        self.setObjectName("choice")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(46 if subtitle else 34)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(0)
        self._title = QLabel(title)
        self._title.setObjectName("choiceTitle")
        self._subtitle = QLabel(subtitle)
        self._subtitle.setObjectName("choiceSub")
        for label in (self._title, self._subtitle):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout.addWidget(label)
        self._subtitle.setVisible(bool(subtitle))
        self._title_text = title
        self.setProperty("selected", False)

    def sizeHint(self):
        return self.layout().sizeHint()

    def set_selected(self, selected):
        if self.property("selected") != selected:
            self.setProperty("selected", selected)
            restyle(self)

    def set_busy(self, busy):
        self._title.setText("Applying…" if busy else self._title_text)


class ButtonGrid(QWidget):
    """Lays buttons out in columns; a lone last button spans the row."""

    def __init__(self, columns=2, parent=None):
        super().__init__(parent)
        self.columns = columns
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(8)
        self.buttons = []

    def set_buttons(self, buttons):
        for button in self.buttons:
            self.grid.removeWidget(button)
            button.deleteLater()
        self.buttons = list(buttons)
        count = len(self.buttons)
        for index, button in enumerate(self.buttons):
            row, column = divmod(index, self.columns)
            span = self.columns - column if index == count - 1 else 1
            self.grid.addWidget(button, row, column, 1, span)
        for column in range(self.columns):
            self.grid.setColumnStretch(column, 1)


class Toast(QFrame):
    """A transient message pinned to the bottom of its parent window."""

    DURATION_MS = 3500

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        self.label = QLabel()
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(250)
        self._fade.finished.connect(self._fade_done)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self.hide()

    def show_message(self, text, critical=False):
        self.setProperty("critical", critical)
        restyle(self)
        self.label.setText(("⚠  " if critical else "") + text)
        self.reposition()
        self._fade.stop()
        self._effect.setOpacity(1.0)
        self.show()
        self.raise_()
        self._timer.start(self.DURATION_MS * (2 if critical else 1))

    def reposition(self):
        parent = self.parentWidget()
        width = min(520, parent.width() - 40)
        self.setFixedWidth(width)
        self.adjustSize()
        self.move((parent.width() - width) // 2, parent.height() - self.height() - 64)

    def _fade_out(self):
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _fade_done(self):
        if self._effect.opacity() == 0.0:
            self.hide()

    def mousePressEvent(self, _event):
        self._timer.stop()
        self.hide()
