"""Общая страница-редактор таблицы своих данных («Свои допуски», «Свои марки»):
правка ячеек, добавление, копирование и удаление строк, примечание к строке, сохранение."""
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QMessageBox, QPlainTextEdit,
                               QTableWidgetItem)

from core.storage import DamagedFile, load_list
from core.util import InputError, fmt, num
from ui.theme import px
from ui.widgets import Page, button, fill_table, label, make_table


class TableEditorPage(Page):
    # (ключ, заголовок, "text" | "num" | "note") — у подкласса
    COLUMNS = []
    COPY_CLEAR = None           # ключ, который очищается при копировании строки
    COPY_TIP = ""
    NOTE_PLACEHOLDER = ""
    FOOTNOTE = ""
    WHAT = ""                   # «допуски», «марки» — для сообщений

    def path(self):
        raise NotImplementedError

    def save_rows(self, rows):
        """Проверяет и сохраняет строки; возвращает сохранённые. InputError — с текстом."""
        raise NotImplementedError

    def saved_text(self, saved):
        return f"Сохранено строк: {len(saved)}."

    def extra_buttons(self):
        return []

    # ---- построение ----
    def build(self):
        self.keys = [k for k, _, _ in self.COLUMNS]
        self.note_col = next(i for i, (_, _, kind) in enumerate(self.COLUMNS) if kind == "note")
        self.table = make_table([h for _, h, _ in self.COLUMNS])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                   | QAbstractItemView.EditTrigger.EditKeyPressed
                                   | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setMinimumHeight(px(280))
        self.body.addWidget(self.table, 1)
        bar = QHBoxLayout()
        b_add = button("Добавить строку")
        b_copy = button("Копировать строку")
        b_copy.setToolTip(self.COPY_TIP)
        b_del = button("Удалить строку")
        b_save = button("Сохранить", primary=True)
        for b in [b_add, b_copy, *self.extra_buttons(), b_del, b_save]:
            bar.addWidget(b)
        bar.addStretch()
        self.body.addLayout(bar)
        self.body.addWidget(label("Примечание к выбранной строке", "section"))
        self.note = QPlainTextEdit()
        self.note.setPlaceholderText(self.NOTE_PLACEHOLDER)
        self.note.setMaximumHeight(px(110))
        self.body.addWidget(self.note)
        if self.FOOTNOTE:
            self.body.addWidget(label(self.FOOTNOTE, "note", True))
        self.body.addWidget(self.status)
        b_add.clicked.connect(lambda: self.add_row())
        b_copy.clicked.connect(self.copy_row)
        b_del.clicked.connect(self.delete_row)
        b_save.clicked.connect(self.save)
        self.table.currentCellChanged.connect(self.show_note)
        self.table.itemChanged.connect(self.on_edit)
        self.note.textChanged.connect(self.note_edited)
        self.dirty = False
        self.reload()

    # ---- данные ----
    def reload(self):
        try:
            rows = load_list(self.path())
        except DamagedFile as e:
            rows = []
            QMessageBox.warning(self, self.title, str(e))
        except OSError as e:
            rows = []
            self.status.setText(f"Не удалось прочитать файл: {e}")
        self.table.blockSignals(True)
        fill_table(self.table, [[_num_text(r.get(k)) if kind == "num" else r.get(k, "")
                                 for k, _, kind in self.COLUMNS] for r in rows])
        self.table.blockSignals(False)
        self.dirty = False
        self.show_note(self.table.currentRow())

    def rows(self):
        """Строки таблицы как словари; числа — с запятой или точкой."""
        out = []
        for r in range(self.table.rowCount()):
            cells = [self._text(r, c) for c in range(len(self.COLUMNS))]
            if not any(cells):
                continue                       # пустую строку просто пропускаем
            row = {}
            for c, (key, head, kind) in enumerate(self.COLUMNS):
                if kind == "num":
                    try:
                        row[key] = num(cells[c])
                    except ValueError:
                        raise InputError(f"Строка {r + 1}: в столбце «{head}» должно быть число.")
                else:
                    row[key] = cells[c]
            out.append(row)
        return out

    def save(self):
        self.status.setText("")
        try:
            saved = self.save_rows(self.rows())
        except InputError as e:
            self.status.setText(str(e))
            return
        except OSError as e:
            QMessageBox.warning(self, self.title, f"Не удалось сохранить:\n{e}")
            return
        self.reload()
        QMessageBox.information(self, self.title, self.saved_text(saved))

    # ---- правка таблицы ----
    def add_row(self, values=None):
        r = self.table.rowCount()
        self.table.blockSignals(True)
        self.table.insertRow(r)
        for c, v in enumerate(values or [""] * len(self.COLUMNS)):
            self.table.setItem(r, c, QTableWidgetItem(v))
        self.table.blockSignals(False)
        focus = self.keys.index(self.COPY_CLEAR) if values and self.COPY_CLEAR else 0
        self.table.setCurrentCell(r, focus)
        self.mark_dirty()

    def copy_row(self):
        r = self.table.currentRow()
        if r < 0:
            self.status.setText("Выбери строку, которую копировать.")
            return
        vals = [self._text(r, c) for c in range(len(self.COLUMNS))]
        if self.COPY_CLEAR:
            vals[self.keys.index(self.COPY_CLEAR)] = ""
        self.add_row(vals)

    def delete_row(self):
        r = self.table.currentRow()
        if r < 0:
            return
        what = " ".join(x for x in (self._text(r, 0), self._text(r, 1)) if x) or "пустую строку"
        if QMessageBox.question(self, "Удалить", f"Удалить строку «{what}»?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.table.removeRow(r)
        self.mark_dirty()

    def on_edit(self, item):
        if item.column() == self.note_col and item.row() == self.table.currentRow():
            self.show_note(item.row())
        self.mark_dirty()

    def show_note(self, row, *args):
        self.note.blockSignals(True)
        self.note.setPlainText(self._text(row, self.note_col) if row >= 0 else "")
        self.note.setEnabled(row >= 0)
        self.note.blockSignals(False)

    def note_edited(self):
        r = self.table.currentRow()
        if r < 0:
            return
        self.table.blockSignals(True)
        self.table.setItem(r, self.note_col, QTableWidgetItem(self.note.toPlainText()))
        self.table.blockSignals(False)
        self.mark_dirty()

    def mark_dirty(self):
        self.dirty = True
        self.status.setText("Есть несохранённые изменения — нажми «Сохранить».")

    def _text(self, r, c):
        it = self.table.item(r, c)
        return it.text().strip() if it else ""

    def on_show(self):
        if not self.dirty:
            self.reload()

    def recalc(self):
        pass


def _num_text(x):
    if x is None or x == "":
        return ""
    try:
        return fmt(float(x), 4).rstrip("0").rstrip(",")
    except (TypeError, ValueError):
        return str(x)
