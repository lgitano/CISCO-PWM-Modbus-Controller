import sys
from PyQt5.QtWidgets import QPushButton, QStackedWidget, QFrame, QSizePolicy

sys.path.insert(0, "/path/to/folder/containing_pyqt_modbus.py/")
from pyqt_modbus import CiscoQtDragonPanel


class HandlerClass:
    def __init__(self, halcomp, widgets, paths):
        self.hal = halcomp
        self.w = widgets
        self.PATHS = paths

    def initialized__(self):
        if hasattr(self, "psu_panel"):
            return
        self.w.resize(920, 660)
        self.w.btnTabInputs.setChecked(True)
        self.w.systemStack.setCurrentIndex(0)
        self.w.systemStack.setMinimumHeight(385)
        self.w.btnTabInputs.clicked.connect(lambda: self.w.systemStack.setCurrentIndex(0))
        self.w.btnTabOutputs.clicked.connect(lambda: self.w.systemStack.setCurrentIndex(1))

        self.w.ciscoContainer.setMinimumSize(1020, 375)
        self.w.ciscoContainer.setMaximumWidth(16777215)
        self.w.ciscoContainer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        if hasattr(self.w, "inputsLayout") and self.w.inputsLayout.count() > 1:
            item = self.w.inputsLayout.itemAt(1)
            if item and item.spacerItem():
                item.spacerItem().changeSize(0, 0, QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.psu_panel = CiscoQtDragonPanel()
        self.w.ciscoLayout.addWidget(self.psu_panel)
        self.psu_panel.show()

    def closing_cleanup__(self):
        if hasattr(self, "psu_panel"):
            self.psu_panel.timer.stop()


def get_handlers(halcomp, widgets, paths):
    return [HandlerClass(halcomp, widgets, paths)]
