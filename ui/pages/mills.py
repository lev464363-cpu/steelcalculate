"""Подвкладка «Станы»: профили станов (барабаны, привод, мощность, кинематика)."""
from PySide6.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QMessageBox, QVBoxLayout)

from core.mills import DRIVE_COMMON, DRIVES, load_mills, save_mills
from core.util import InputError, fmt, num
from ui.theme import sized
from ui.widgets import FieldError, NumField, Page, button, label, panel


class MillsPage(Page):
    title = "Станы"
    hint = "Профили станов из паспорта. Название профиля выбирается в маршруте на вкладке «Стан»."

    def build(self):
        self.mills = []
        row = QHBoxLayout()
        row.setSpacing(16)
        left = QVBoxLayout()
        self.list = QListWidget()
        sized(self.list, "fixed", 240)
        left.addWidget(self.list, 1)
        b_new = button("Новый стан", primary=True)
        b_del = button("Удалить")
        left.addWidget(b_new)
        left.addWidget(b_del)
        row.addLayout(left)

        p = panel()
        g = QGridLayout(p)
        g.setContentsMargins(18, 16, 18, 16)
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(8)
        self.f_name = QLineEdit()
        self.f_name.setPlaceholderText("например, 1К89М №2")
        self.f_drive = QComboBox()
        self.f_drive.addItems(DRIVES)
        self.f_drums = NumField("Число барабанов")
        self.f_d = NumField("Диаметр барабана")
        self.f_vmax = NumField("Макс. скорость")
        self.f_power = NumField("Мощность двигателя барабана")
        self.f_eta = NumField("КПД привода")
        self.f_eta.setText("85")
        self.f_kin = QLineEdit()
        self.f_kin.setPlaceholderText("через точку с запятой: 1,26; 1,26; 1,24 …")
        rows = [("Название", self.f_name), ("Привод", self.f_drive),
                ("Число барабанов (блоков)", self.f_drums), ("Диаметр барабана, мм", self.f_d),
                ("Макс. скорость на чистовом барабане, м/с", self.f_vmax),
                ("Мощность двигателя одного барабана, кВт", self.f_power),
                ("КПД привода, %", self.f_eta),
                ("Кинематические вытяжки между барабанами", self.f_kin)]
        for i, (text, w) in enumerate(rows):
            lab = QLabel(text)
            lab.setWordWrap(True)
            g.addWidget(lab, i, 0)
            g.addWidget(w, i, 1)
        g.addWidget(label("Кинематические вытяжки нужны только для общего привода: их на одну "
                          "меньше, чем барабанов, от первого барабана к чистовому (отношение окружных "
                          "скоростей соседних барабанов). Мощность двигателя можно оставить пустой — "
                          "тогда загрузка привода не проверяется.", "note", True), len(rows), 0, 1, 2)
        save = button("Сохранить профиль", primary=True)
        g.addWidget(save, len(rows) + 1, 1)
        g.addWidget(self.status, len(rows) + 2, 0, 1, 2)
        g.setRowStretch(len(rows) + 3, 1)
        row.addWidget(p, 1)
        self.body.addLayout(row, 1)

        self.list.currentRowChanged.connect(self.show_mill)
        b_new.clicked.connect(self.new_mill)
        b_del.clicked.connect(self.delete_mill)
        save.clicked.connect(self.save_mill)
        self.f_drive.currentIndexChanged.connect(self._enable)
        self.refresh()
        self._enable()

    def _enable(self, *args):
        self.f_kin.setEnabled(self.f_drive.currentText() == DRIVE_COMMON)

    def refresh(self, select=None):
        try:
            self.mills = load_mills()
        except (OSError, ValueError) as e:
            self.mills = []
            self.status.setText(f"Не удалось прочитать файл станов: {e}")
        self.list.blockSignals(True)
        self.list.clear()
        self.list.addItems([m["name"] for m in self.mills])
        self.list.blockSignals(False)
        if select is not None and 0 <= select < len(self.mills):
            self.list.setCurrentRow(select)
        elif not self.mills:
            self.status.setText("Профилей пока нет. Нажми «Новый стан» и внеси данные из паспорта.")

    def show_mill(self, idx):
        if not 0 <= idx < len(self.mills):
            return
        m = self.mills[idx]
        self.f_name.setText(m["name"])
        self.f_drive.setCurrentText(m.get("drive", DRIVES[0]))
        self.f_drums.setText(str(m["drums"]))
        self.f_d.setText(fmt(m["drum_d"], 0))
        self.f_vmax.setText(fmt(m["v_max"], 1))
        self.f_power.setText(fmt(m["p_motor"], 1) if m.get("p_motor") else "")
        self.f_eta.setText(fmt(m.get("eta", 85), 0))
        self.f_kin.setText("; ".join(fmt(k, 3) for k in m.get("kin") or []))
        self.status.setText("")

    def new_mill(self):
        self.list.clearSelection()
        self.list.setCurrentRow(-1)
        for w in (self.f_name, self.f_drums, self.f_d, self.f_vmax, self.f_power, self.f_kin):
            w.clear()
        self.f_eta.setText("85")
        self.f_name.setFocus()
        self.status.setText("Заполни данные и нажми «Сохранить профиль».")

    def _read(self):
        for f in (self.f_drums, self.f_d, self.f_vmax, self.f_power, self.f_eta):
            f.set_error(False)
        name = self.f_name.text().strip()
        if not name:
            raise InputError("Укажи название стана.")
        drums = self.f_drums.value()
        if drums != int(drums) or drums < 1:
            raise FieldError(self.f_drums, "Число барабанов — целое число от 1.")
        eta = self.f_eta.value()
        if eta > 100:
            raise FieldError(self.f_eta, "КПД — не больше 100 %.")
        m = dict(name=name, drive=self.f_drive.currentText(), drums=int(drums),
                 drum_d=self.f_d.value(), v_max=self.f_vmax.value(),
                 p_motor=self.f_power.value(optional=True), eta=eta, kin=None)
        if m["drive"] == DRIVE_COMMON:
            parts = [x for x in self.f_kin.text().replace(" ", "").split(";") if x]
            try:
                kin = [num(x) for x in parts]
            except ValueError:
                raise InputError("Кинематические вытяжки — числа через точку с запятой.")
            if len(kin) != m["drums"] - 1 or any(k <= 1 for k in kin):
                raise InputError(f"Нужно {m['drums'] - 1} кинематических вытяжек больше 1 "
                                 f"(на одну меньше, чем барабанов).")
            m["kin"] = kin
        return m

    def save_mill(self):
        try:
            m = self._read()
        except FieldError as e:
            e.field.set_error(True, str(e))
            self.status.setText(str(e))
            return
        except InputError as e:
            self.status.setText(str(e))
            return
        idx = next((i for i, x in enumerate(self.mills) if x["name"] == m["name"]), None)
        cur = self.list.currentRow()
        if idx is None and 0 <= cur < len(self.mills):
            idx = cur                     # переименование выбранного профиля
        if idx is None:
            self.mills.append(m)
            idx = len(self.mills) - 1
        else:
            self.mills[idx] = m
        try:
            save_mills(self.mills)
        except OSError as e:
            self.status.setText(f"Не удалось сохранить: {e}")
            return
        self.refresh(select=idx)
        self.status.setText(f"Профиль «{m['name']}» сохранён.")

    def delete_mill(self):
        idx = self.list.currentRow()
        if not 0 <= idx < len(self.mills):
            return
        name = self.mills[idx]["name"]
        if QMessageBox.question(self, "Удалить", f"Удалить профиль стана «{name}»?") \
                != QMessageBox.StandardButton.Yes:
            return
        del self.mills[idx]
        try:
            save_mills(self.mills)
        except OSError as e:
            self.status.setText(f"Не удалось сохранить: {e}")
            return
        self.new_mill()
        self.refresh()
