"""Окно «Экспорт в Excel»: что выгружать — галочками; каждый раздел — отдельный лист книги."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QPushButton, QVBoxLayout)

from ui.theme import px
from ui.widgets import label


class ExportDialog(QDialog):
    """sections — [(ключ, название, пояснение, включён по умолчанию[, доступен])];
    columns — заголовки таблицы проходов (выбор столбцов), columns_key — к какому разделу они."""

    def __init__(self, parent, sections, columns=None, columns_key=None, checked_cols=None):
        super().__init__(parent)
        self.setWindowTitle("Экспорт в Excel")
        self.setMinimumWidth(px(600))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(px(22), px(18), px(22), px(16))
        lay.setSpacing(px(10))
        t = QLabel("Что выгрузить")
        t.setObjectName("pageTitle")
        t.setStyleSheet("font-size: 16pt;")
        lay.addWidget(t)
        lay.addWidget(label("Каждый отмеченный раздел — отдельный лист книги Excel.", "muted", True))
        self.boxes = {}
        for key, title, hint, on, *avail in sections:
            enabled = avail[0] if avail else True
            card = QFrame()
            card.setObjectName("section")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(px(14), px(10), px(14), px(10))
            cl.setSpacing(px(4))
            box = QCheckBox(title)
            box.setChecked(on and enabled)
            box.setEnabled(enabled)
            box.setStyleSheet("font-weight: 600;")
            cl.addWidget(box)
            if hint:
                cl.addWidget(label(hint, "note", True))
            self.boxes[key] = box
            if columns and key == columns_key:
                cl.addLayout(self._columns(columns, checked_cols, box))
            lay.addWidget(card)
        bb = QDialogButtonBox()
        self.ok = bb.addButton("Сохранить…", QDialogButtonBox.ButtonRole.AcceptRole)
        self.ok.setProperty("primary", "true")
        bb.addButton("Отмена", QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        for box in self.boxes.values():
            box.toggled.connect(self._update_ok)
        self._update_ok()

    def _columns(self, columns, checked, parent_box):
        wrap = QVBoxLayout()
        wrap.setContentsMargins(px(26), px(4), 0, 0)
        bar = QHBoxLayout()
        bar.addWidget(label("Столбцы:", "note"))
        for text, state in (("все", True), ("ничего", False)):
            b = QPushButton(text)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("padding: 2px 10px;")
            b.clicked.connect(lambda _=False, s=state: [c.setChecked(s) for c in self.cols])
            bar.addWidget(b)
        bar.addStretch()
        wrap.addLayout(bar)
        grid = QGridLayout()
        grid.setHorizontalSpacing(px(14))
        grid.setVerticalSpacing(px(2))
        self.cols = []
        for i, h in enumerate(columns):
            c = QCheckBox(h)
            c.setChecked(checked is None or h in checked)
            grid.addWidget(c, i // 2, i % 2)
            self.cols.append(c)
            c.setEnabled(parent_box.isChecked())
        parent_box.toggled.connect(lambda on: [c.setEnabled(on) for c in self.cols])
        wrap.addLayout(grid)
        return wrap

    def _update_ok(self, *args):
        self.ok.setEnabled(any(b.isChecked() for b in self.boxes.values()))

    def chosen(self):
        return {k for k, b in self.boxes.items() if b.isChecked()}

    def chosen_columns(self):
        return [c.text() for c in getattr(self, "cols", []) if c.isChecked()]
