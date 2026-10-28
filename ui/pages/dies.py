"""Раздел «Журнал фильер»: наработка и износ, хранение в filery.json."""
import os
from datetime import date

from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QInputDialog,
                               QLabel, QLineEdit, QMessageBox)

from core.data import DIE_TYPES
from core.dies import actual_life
from core.paths import app_dir
from core.storage import DamagedFile, load_list, save_list
from core.tolerance import all_standards, check_measure, tolerance
from core.util import InputError, fmt
from ui.theme import T
from ui.widgets import (FieldError, NumField, Page, button, fill_table, label, make_table, panel,
                        tab_box)
from ui.anim import AnimatedTabWidget
from ui.pages.tolerance import refill
from ui.popup import notify


class DiesPage(Page):
    title = "Журнал фильер"
    hint = "Наработка, замеры и износ волок. Данные — в файле filery.json рядом с программой."

    def build(self):
        self.path = os.path.join(app_dir(), "filery.json")
        self.dies = self.load()
        self.tabs = AnimatedTabWidget()
        self.body.addWidget(self.tabs, 1)
        lst = tab_box(self.tabs, "Фильеры")
        add_tab = tab_box(self.tabs, "Добавить фильеру")
        p = panel()
        g = QGridLayout(p)
        g.setContentsMargins(18, 16, 18, 16)
        g.setHorizontalSpacing(14)
        self.f_id = QLineEdit()
        self.f_type = QComboBox()
        self.f_type.addItems(DIE_TYPES)
        self.f_d = NumField("Номинал d")
        self.f_place = QLineEdit()
        self.f_limit = NumField("Ресурс")
        g.addWidget(QLabel("Номер"), 0, 0)
        g.addWidget(self.f_id, 0, 1)
        g.addWidget(QLabel("Тип"), 0, 2)
        g.addWidget(self.f_type, 0, 3)
        g.addWidget(QLabel("Номинал d, мм"), 1, 0)
        g.addWidget(self.f_d, 1, 1)
        g.addWidget(QLabel("Стан / позиция"), 1, 2)
        g.addWidget(self.f_place, 1, 3)
        g.addWidget(QLabel("Ресурс, т"), 2, 0)
        g.addWidget(self.f_limit, 2, 1)
        self.f_tol = QComboBox()
        self.f_tol.addItems(["без допуска"] + all_standards())
        g.addWidget(QLabel("Допуск на проволоку"), 2, 2)
        g.addWidget(self.f_tol, 2, 3)
        add = button("Добавить фильеру", primary=True)
        g.addWidget(add, 3, 3)
        add_tab.addWidget(p)
        add_tab.addStretch()
        self.table = make_table(["Номер", "Тип", "d, мм", "Стан / позиция", "Установлена",
                                 "Наработка, т", "Ресурс, т", "Износ, %", "Замер, мм",
                                 "До верхней границы, мкм", "Статус"])
        lst.addWidget(self.table, 1)
        bar = QHBoxLayout()
        b_use = button("Добавить наработку…")
        b_meas = button("Записать замер…")
        b_off = button("Снять с работы")
        b_del = button("Удалить")
        self.show_off = QCheckBox("Показывать снятые")
        for w in (b_use, b_meas, b_off, b_del, self.show_off):
            bar.addWidget(w)
        bar.addWidget(label("  Оранжевым — износ от 90 % или замер у верхней границы допуска; "
                            "красным — ресурс исчерпан или замер вне допуска.", "note", True), 1)
        lst.addLayout(bar)
        self.life = label("", "muted", True)
        lst.addWidget(self.life)
        lst.addWidget(self.status)
        add.clicked.connect(self.add_die)
        b_use.clicked.connect(self.add_usage)
        b_meas.clicked.connect(self.add_measure)
        b_off.clicked.connect(self.retire)
        b_del.clicked.connect(self.delete)
        self.show_off.toggled.connect(self.refresh)
        self.refresh()

    def recalc(self):
        self.refresh()

    def on_show(self):
        # журнал мог измениться в «Маршруте» (запись партии) — читаем заново, чтобы не затереть
        self.dies = self.load()
        refill(self.f_tol, all_standards(), first=["без допуска"])
        self.refresh()

    def load(self):
        self.readonly = False
        try:
            return load_list(self.path)
        except DamagedFile as e:
            QMessageBox.warning(self, "Журнал фильер", str(e))
            return []
        except OSError as e:
            # файл не открылся (занят, нет прав) — работаем без него, но поверх не пишем
            self.readonly = True
            QMessageBox.warning(self, "Журнал фильер",
                                f"Не удалось открыть журнал, изменения не будут сохранены:\n{e}")
            return []

    def save(self):
        if getattr(self, "readonly", False):
            QMessageBox.warning(self, "Журнал фильер", "Журнал не был прочитан при запуске — "
                                "сохранение отключено, чтобы не затереть файл. Перезапусти программу.")
            return
        try:
            save_list(self.dies, self.path)
        except OSError as e:
            QMessageBox.warning(self, "Журнал фильер", f"Не удалось сохранить файл:\n{e}")

    def refresh(self, *args):
        self.shown = [d for d in self.dies
                      if d["status"] == "в работе" or self.show_off.isChecked()]
        rows, colors = [], []
        for d in self.shown:
            wear = d["used"] / d["limit"] * 100
            state, left = self.tol_state(d)
            meas = d.get("measured")
            rows.append((d["id"], d["type"], fmt(d["d"], 3), d["place"], d["installed"],
                         fmt(d["used"], 2), fmt(d["limit"], 1), fmt(wear, 0),
                         fmt(meas, 3) if meas else "—",
                         fmt(left, 0) if left is not None else "—", d["status"]))
            if d["status"] != "в работе":
                colors.append((None, T["muted"]))
            elif wear >= 100 or state == "out":
                colors.append((T["warn_soft"], T["warn"]))
            elif wear >= 90 or state == "near":
                colors.append((T["anneal"], None))
            else:
                colors.append(None)
        fill_table(self.table, rows, colors)
        life = actual_life(self.dies)
        if life:
            by_type = [(t, actual_life(self.dies, t)) for t in DIE_TYPES]
            parts = [f"{t} — {fmt(x[0], 1)} т ({x[1]} шт.)" for t, x in by_type if x]
            self.life.setText(f"Фактическая стойкость по снятым фильерам: {fmt(life[0], 1)} т в "
                              f"среднем ({life[1]} шт.); " + "; ".join(parts) + ". Её можно взять "
                              "в себестоимость: «Маршрут» → «Экономика».")
        else:
            self.life.setText("Фактическая стойкость появится, когда будут сняты с работы "
                              "фильеры с записанной наработкой.")

    @staticmethod
    def tol_state(d):
        """Состояние по допуску и остаток до верхней границы, мкм (или None, если нет данных)."""
        std, meas = d.get("tol"), d.get("measured")
        if not std or std == "без допуска" or not meas:
            return None, None
        try:
            up, low = tolerance(std, d["d"])
        except InputError:
            return None, None
        return check_measure(d["d"], up, low, meas), (d["d"] + up - meas) * 1000

    def add_measure(self):
        d = self.selected()
        if not d:
            return
        val, ok = QInputDialog.getDouble(self, "Замер",
                                         f"Диаметр проволоки после фильеры {d['id']}, мм:",
                                         d.get("measured") or d["d"], 0.01, 200.0, 3)
        if ok:
            d["measured"] = val
            d["measured_on"] = date.today().strftime("%d.%m.%Y")
            self.save()
            self.refresh()

    def selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            notify(self, "Сначала выбери фильеру в таблице", "info")
            return None
        return self.shown[rows[0].row()]

    def add_die(self):
        for f in (self.f_d, self.f_limit):
            f.set_error(False)
        try:
            die_id = self.f_id.text().strip()
            if not die_id:
                raise InputError("Укажи номер фильеры.")
            if any(d["id"] == die_id for d in self.dies):
                raise InputError(f"Фильера с номером {die_id} уже есть в журнале.")
            d = self.f_d.value()
            limit = self.f_limit.value()
            if self.f_tol.currentText() != "без допуска":
                try:
                    tolerance(self.f_tol.currentText(), d)
                except InputError as e:
                    raise FieldError(self.f_d, str(e))
        except FieldError as e:
            e.field.set_error(True, str(e))
            QMessageBox.warning(self, "Проверь данные", str(e))
            return
        except InputError as e:
            QMessageBox.warning(self, "Проверь данные", str(e))
            return
        self.status.setText("")
        self.dies.append(dict(id=die_id, type=self.f_type.currentText(), d=d,
                              place=self.f_place.text().strip() or "—",
                              installed=date.today().strftime("%d.%m.%Y"),
                              used=0.0, limit=limit, status="в работе",
                              tol=self.f_tol.currentText(), measured=None))
        self.save()
        self.refresh()
        for w in (self.f_id, self.f_d, self.f_place):
            w.clear()
        self.tabs.setCurrentIndex(0)

    def add_usage(self):
        d = self.selected()
        if not d:
            return
        t, ok = QInputDialog.getDouble(self, "Наработка",
                                       f"Сколько тонн протянуто через фильеру {d['id']}?",
                                       0.0, 0.0, 100000.0, 3)
        if ok and t > 0:
            d["used"] += t
            self.save()
            self.refresh()

    def retire(self):
        d = self.selected()
        if d and QMessageBox.question(self, "Снять с работы", f"Снять фильеру {d['id']} с работы?") \
                == QMessageBox.StandardButton.Yes:
            d["status"] = "снята"
            self.save()
            self.refresh()

    def delete(self):
        d = self.selected()
        if d and QMessageBox.question(self, "Удалить",
                                      f"Удалить фильеру {d['id']} из журнала навсегда?") \
                == QMessageBox.StandardButton.Yes:
            self.dies.remove(d)
            self.save()
            self.refresh()
