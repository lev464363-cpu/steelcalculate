"""Подвкладка «Свои допуски»: ручной ввод НТД — на каждый диаметр своя строка."""
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QMessageBox, QPlainTextEdit,
                               QTableWidgetItem)

from core.storage import DamagedFile, load_list
from core.tolerance import custom_path, save_custom
from core.util import InputError, fmt, num
from ui.theme import px
from ui.widgets import Page, button, fill_table, label, make_table

HEAD = ["НТД (название)", "Диаметр, мм", "Верхнее отклонение, мм", "Нижнее отклонение, мм",
        "Примечание"]
NOTE_COL = 4


class CustomTolPage(Page):
    title = "Свои допуски"
    hint = ("Допуски по своим НТД: ТУ, стандартам предприятия, договорам. Каждая строка — один "
            "диаметр. Сохранённые НТД появляются в списках «Допуски и волоки» и «Журнал фильер». "
            "Данные — в файле dopuski.json рядом с программой.")

    def build(self):
        self.table = make_table(HEAD)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                   | QAbstractItemView.EditTrigger.EditKeyPressed
                                   | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setMinimumHeight(px(280))
        self.body.addWidget(self.table, 1)
        bar = QHBoxLayout()
        b_add = button("Добавить строку")
        b_copy = button("Копировать строку")
        b_copy.setToolTip("Та же НТД и отклонения — останется поменять диаметр.")
        b_del = button("Удалить строку")
        b_save = button("Сохранить", primary=True)
        for b in (b_add, b_copy, b_del, b_save):
            bar.addWidget(b)
        bar.addStretch()
        self.body.addLayout(bar)
        self.body.addWidget(label("Примечание к выбранной строке", "section"))
        self.note = QPlainTextEdit()
        self.note.setPlaceholderText("Например: пункт ТУ, условия поставки, овальность, "
                                     "согласование с потребителем…")
        self.note.setMaximumHeight(px(110))
        self.body.addWidget(self.note)
        self.body.addWidget(label(
            "Отклонения — в миллиметрах со знаком: для проволоки «в минус» верхнее 0, нижнее "
            "−0,09. Можно писать через запятую. Двойной щелчок по ячейке — правка. Допуск "
            "берётся только для диаметра, который есть в таблице.", "note", True))
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
            rows = load_list(custom_path())
        except DamagedFile as e:
            rows = []
            QMessageBox.warning(self, "Свои допуски", str(e))
        except OSError as e:
            rows = []
            self.status.setText(f"Не удалось прочитать файл допусков: {e}")
        self.table.blockSignals(True)
        fill_table(self.table, [(r.get("ntd", ""), _num_text(r.get("d")), _num_text(r.get("upper")),
                                 _num_text(r.get("lower")), r.get("note", "")) for r in rows])
        self.table.blockSignals(False)
        self.dirty = False
        self.show_note(self.table.currentRow())

    def rows(self):
        """Строки таблицы как словари; числа — с запятой или точкой."""
        out = []
        for r in range(self.table.rowCount()):
            cells = [self._text(r, c) for c in range(len(HEAD))]
            if not any(cells):
                continue                       # пустую строку просто пропускаем
            vals = {}
            for key, c in (("d", 1), ("upper", 2), ("lower", 3)):
                try:
                    vals[key] = num(cells[c])
                except ValueError:
                    raise InputError(f"Строка {r + 1}: в столбце «{HEAD[c]}» должно быть число.")
            out.append(dict(ntd=cells[0], note=cells[NOTE_COL], **vals))
        return out

    def save(self):
        self.status.setText("")
        try:
            saved = save_custom(self.rows())
        except InputError as e:
            self.status.setText(str(e))
            return
        except OSError as e:
            QMessageBox.warning(self, "Свои допуски", f"Не удалось сохранить:\n{e}")
            return
        self.reload()
        n = len({r["ntd"] for r in saved})
        self.status.setText("")
        QMessageBox.information(self, "Свои допуски", f"Сохранено строк: {len(saved)}, НТД: {n}. "
                                                      f"Они уже есть в списках допусков.")

    # ---- правка таблицы ----
    def add_row(self, values=None):
        r = self.table.rowCount()
        self.table.blockSignals(True)
        self.table.insertRow(r)
        for c, v in enumerate(values or [""] * len(HEAD)):
            self.table.setItem(r, c, QTableWidgetItem(v))
        self.table.blockSignals(False)
        self.table.setCurrentCell(r, 1 if values else 0)
        self.mark_dirty()

    def copy_row(self):
        r = self.table.currentRow()
        if r < 0:
            self.status.setText("Выбери строку, которую копировать.")
            return
        vals = [self._text(r, c) for c in range(len(HEAD))]
        vals[1] = ""                            # диаметр — новый
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
        if item.column() == NOTE_COL and item.row() == self.table.currentRow():
            self.show_note(item.row())
        self.mark_dirty()

    def show_note(self, row, *args):
        self.note.blockSignals(True)
        self.note.setPlainText(self._text(row, NOTE_COL) if row >= 0 else "")
        self.note.setEnabled(row >= 0)
        self.note.blockSignals(False)

    def note_edited(self):
        r = self.table.currentRow()
        if r < 0:
            return
        self.table.blockSignals(True)
        self.table.setItem(r, NOTE_COL, QTableWidgetItem(self.note.toPlainText()))
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
