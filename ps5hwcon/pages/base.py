from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from ..common import STATUS_POLL_MS


class Page(QScrollArea):
    title = ""
    poll_method = None

    def __init__(self, bridge, notify, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.notify = notify
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("pageContent")
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(20, 10, 20, 10)
        self.body.setSpacing(8)
        self.setWidget(content)

        self._active = False
        self._polling = False
        self._timer = QTimer(self)
        self._timer.setInterval(STATUS_POLL_MS)
        self._timer.timeout.connect(self.refresh_status)

    def finish_layout(self):
        self.body.addStretch(1)

    def add(self, widget):
        self.body.addWidget(widget)
        return widget

    def call(self, method, *args, callback):
        def deliver(result):
            if self._active:
                callback(result)

        self.bridge.call(method, *args, callback=deliver)

    def activate(self):
        self._active = True
        self._polling = False
        self.on_activate()
        if self.poll_method:
            self._timer.start()

    def deactivate(self):
        self._active = False
        self._timer.stop()

    def refresh_status(self, callback=None):
        if self.poll_method is None or self._polling:
            return
        self._polling = True

        def done(result):
            self._polling = False
            self.on_status(result)
            if callback:
                callback(result)

        def deliver(result):
            if self._active:
                done(result)
            else:
                self._polling = False

        self.bridge.call(self.poll_method, callback=deliver)

    def on_activate(self):
        pass

    def on_status(self, result):
        pass
