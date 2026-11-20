from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from ..widgets import ButtonGrid, ChoiceButton


class PageGroup(QWidget):
    """Several pages under one sidebar entry, switched with buttons along the top.

    It stands in for a Page in MainWindow: activate, deactivate and set_console go to the pages.
    """

    def __init__(self, title, pages):
        """`pages` is [(switch label, page), ...]."""
        super().__init__()
        self.title = title
        self.labels = [label for label, _page in pages]
        self.pages = [page for _label, page in pages]
        self._active = False
        self._settings = QSettings("ps5-hwcon", "ps5-hwcon-gui")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        switch = QWidget()
        switch.setObjectName("pageContent")
        switch_layout = QVBoxLayout(switch)
        switch_layout.setContentsMargins(20, 12, 20, 2)
        self.buttons = []
        for index, label in enumerate(self.labels):
            button = ChoiceButton(label)
            button.clicked.connect(lambda _=False, i=index: self.select(i))
            self.buttons.append(button)
        grid = ButtonGrid(columns=len(pages))
        grid.set_buttons(self.buttons)
        grid.setMaximumWidth(140 * len(pages))
        switch_layout.addWidget(grid)
        layout.addWidget(switch)
        self.stack = QStackedWidget()
        for page in self.pages:
            self.stack.addWidget(page)
        layout.addWidget(self.stack, 1)
        saved = self._settings.value(f"subpage/{title}", "", type=str)
        self.select(self.labels.index(saved) if saved in self.labels else 0)

    def current(self):
        return self.pages[self.stack.currentIndex()]

    def page(self, label):
        """The page under a switch label or page title, for tests and the run driver."""
        for name, page in zip(self.labels, self.pages):
            if label in (name, page.title):
                return page
        return None

    def select(self, index):
        if self._active:
            self.current().deactivate()
        self.stack.setCurrentIndex(index)
        for position, button in enumerate(self.buttons):
            button.set_selected(position == index)
        self._settings.setValue(f"subpage/{self.title}", self.labels[index])
        if self._active:
            self.current().activate()

    def activate(self):
        self._active = True
        self.current().activate()

    def deactivate(self):
        self._active = False
        for page in self.pages:
            page.deactivate()

    def set_console(self, console):
        for page in self.pages:
            page.set_console(console)
