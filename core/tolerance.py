"""Допуски на диаметр и расчёт волоки под допуск.

ГОСТ 2246-70 (табл. 1, п. 2.2–2.3) — сварочная проволока;
ГОСТ 7417-75 (табл. 1–2, п. 3) — калиброванный круг 3–100 мм, поля h9–h12;
GB/T 14957-1994 (табл. 1, п. 3.1.2–3.1.3) — китайская сварочная проволока 1,6–6,0 мм;
GB/T 905-1994 — китайский холоднотянутый круг 3–80 мм, поля h8–h12;
ГОСТ 8559-75 — калиброванный квадрат, ГОСТ 8560-78 — калиброванный шестигранник: поля h11 и
h12 по ISO 286 от стороны / размера под ключ (3–100 мм; сверить с действующей редакцией).
Числа полей h — по ISO 286 (совпадают с табл. 1 ГОСТ 7417-75: 3,0 мм — −0,025/−0,040/−0,060/−0,100;
3,1 мм — −0,030/−0,048/−0,075/−0,120).

Свои НТД (ТУ, стандарты предприятия, договоры) вводятся вручную в «Волочение → Свои допуски» и
хранятся в dopuski.json рядом с программой: на каждый диаметр — своя строка с верхним и нижним
отклонением и примечанием. Для своих НТД допуск берётся только по точному диаметру."""
import os

from core.paths import app_dir
from core.storage import DamagedFile, load_list, save_list
from core.util import InputError, fmt

# ГОСТ 2246-70, таблица 1: номинал → нижнее отклонение, мм (верхнее — 0)
GOST2246_WELD = {0.3: 0.05, 0.5: 0.06, 0.8: 0.07, 1.0: 0.09, 1.2: 0.09, 1.4: 0.09, 1.5: 0.09,
                 1.6: 0.12, 2.0: 0.12, 2.5: 0.12, 3.0: 0.12, 4.0: 0.16, 5.0: 0.16, 6.0: 0.16,
                 8.0: 0.20, 10.0: 0.24, 12.0: 0.24}
GOST2246_ELECTRODE = {1.6: 0.06, 2.0: 0.06, 2.5: 0.09, 3.0: 0.09, 4.0: 0.12, 5.0: 0.12,
                      6.0: 0.12, 8.0: 0.16}
# GB/T 14957-1994, таблица 1: (обычная точность, повышенная точность)
GBT14957 = {1.6: (0.10, 0.06), 2.0: (0.10, 0.06), 2.5: (0.10, 0.06), 3.0: (0.10, 0.06),
            3.2: (0.12, 0.08), 4.0: (0.12, 0.08), 5.0: (0.12, 0.08), 6.0: (0.12, 0.08)}

# ISO 286-1: допуски IT, мкм, для интервалов «свыше … до … включительно»
IT_TABLE = [(3, {8: 14, 9: 25, 10: 40, 11: 60, 12: 100}),
            (6, {8: 18, 9: 30, 10: 48, 11: 75, 12: 120}),
            (10, {8: 22, 9: 36, 10: 58, 11: 90, 12: 150}),
            (18, {8: 27, 9: 43, 10: 70, 11: 110, 12: 180}),
            (30, {8: 33, 9: 52, 10: 84, 11: 130, 12: 210}),
            (50, {8: 39, 9: 62, 10: 100, 11: 160, 12: 250}),
            (80, {8: 46, 9: 74, 10: 120, 11: 190, 12: 300}),
            (120, {8: 54, 9: 87, 10: 140, 11: 220, 12: 350})]

STANDARDS = [
    "ГОСТ 2246-70, для сварки (наплавки)",
    "ГОСТ 2246-70, для электродов",
    "ГОСТ 2246-70, высоколегированная травленая",
    "ГОСТ 7417-75, h9",
    "ГОСТ 7417-75, h10",
    "ГОСТ 7417-75, h11",
    "ГОСТ 7417-75, h12",
    "GB/T 14957-1994, обычная точность",
    "GB/T 14957-1994, повышенная точность",
    "GB/T 905-1994, h8",
    "GB/T 905-1994, h9",
    "GB/T 905-1994, h10",
    "GB/T 905-1994, h11",
    "GB/T 905-1994, h12",
    "ГОСТ 8559-75 (квадрат), h11",
    "ГОСТ 8559-75 (квадрат), h12",
    "ГОСТ 8560-78 (шестигранник), h11",
    "ГОСТ 8560-78 (шестигранник), h12",
]
PROFILE_STANDARDS = {"ГОСТ 8559-75": "квадрат", "ГОСТ 8560-78": "шестигранник"}
# старые названия (в журнале фильер и настройках) → новые
LEGACY = {f"h{q} (ISO 286), калиброванный круг": f"ГОСТ 7417-75, h{q}" for q in (9, 10, 11, 12)}


def _from_table(table, d, what, next_larger):
    for nom in sorted(table):
        if abs(nom - d) < 1e-6:
            return table[nom]
    if next_larger:
        bigger = [nom for nom in sorted(table) if nom > d]
        if bigger and d > min(table) * 0.5:
            return table[bigger[0]]          # промежуточный размер — по ближайшему большему
    sizes = ", ".join(fmt(x, 1) for x in sorted(table))
    raise InputError(f"Для {what} диаметр {fmt(d, 2)} мм не предусмотрен. Номиналы: {sizes}.")


def _it(q, d, lo, hi, what):
    if not lo <= d <= hi:
        raise InputError(f"{what}: диаметры от {fmt(lo, 0)} до {fmt(hi, 0)} мм.")
    for upto, row in IT_TABLE:
        if d <= upto:
            return row[q] / 1000
    raise InputError(f"{what}: диаметр вне таблицы.")


CUSTOM_FILE = "dopuski.json"
CUSTOM_KEYS = ("ntd", "d", "upper", "lower", "note")
_custom = None          # строки своих НТД; None — ещё не прочитаны


def custom_path():
    return os.path.join(app_dir(), CUSTOM_FILE)


def custom_rows():
    """Свои НТД (читаются один раз; повреждённый файл здесь только пропускается — отложить его
    в резервную копию и сообщить пользователю должен раздел «Свои допуски»)."""
    global _custom
    if _custom is None:
        try:
            _custom = check_custom(load_list(custom_path(), quarantine=False))
        except (DamagedFile, InputError, OSError):
            _custom = []
    return _custom


def set_custom(rows):
    global _custom
    _custom = list(rows)


def check_custom(rows):
    """Проверяет строки своих НТД и возвращает их отсортированными по НТД и диаметру.
    InputError называет номер строки (с 1) и что в ней не так."""
    out, seen = [], set()
    for i, r in enumerate(rows, 1):
        ntd = str(r.get("ntd", "")).strip()
        if not ntd:
            raise InputError(f"Строка {i}: не указано название НТД.")
        try:
            d, up, low = float(r["d"]), float(r["upper"]), float(r["lower"])
        except (KeyError, TypeError, ValueError):
            raise InputError(f"Строка {i} ({ntd}): диаметр и отклонения должны быть числами.")
        if d <= 0:
            raise InputError(f"Строка {i} ({ntd}): диаметр должен быть больше нуля.")
        if up <= low:
            raise InputError(f"Строка {i} ({ntd}, {fmt(d, 2)} мм): верхнее отклонение должно быть "
                             f"больше нижнего (например, 0 и −0,09).")
        if d + low <= 0:
            raise InputError(f"Строка {i} ({ntd}, {fmt(d, 2)} мм): нижнее отклонение больше "
                             f"самого диаметра.")
        key = (ntd.lower(), round(d, 6))
        if key in seen:
            raise InputError(f"Строка {i}: диаметр {fmt(d, 2)} мм для «{ntd}» уже есть.")
        seen.add(key)
        out.append(dict(ntd=ntd, d=d, upper=up, lower=low, note=str(r.get("note", "")).strip()))
    return sorted(out, key=lambda r: (r["ntd"].lower(), r["d"]))


def save_custom(rows, path=None):
    rows = check_custom(rows)
    save_list(rows, path or custom_path())
    set_custom(rows)
    return rows


def custom_names():
    names = []
    for r in custom_rows():
        if r["ntd"] not in names:
            names.append(r["ntd"])
    return names


def all_standards():
    """Встроенные стандарты и свои НТД — для выпадающих списков."""
    return STANDARDS + [n for n in custom_names() if n not in STANDARDS]


def custom_row(standard, d):
    """Строка своего НТД для диаметра d или None, если такого НТД нет.
    InputError — НТД есть, а строки для этого диаметра нет."""
    rows = [r for r in custom_rows() if r["ntd"] == standard]
    if not rows:
        return None
    for r in rows:
        if abs(r["d"] - d) < 1e-6:
            return r
    sizes = ", ".join(fmt(r["d"], 2) for r in rows)
    raise InputError(f"В «{standard}» нет строки для диаметра {fmt(d, 2)} мм. Есть: {sizes}. "
                     f"Добавь её в «Свои допуски».")


def tolerance(standard, d):
    """Возвращает (верхнее, нижнее) отклонение в мм."""
    row = custom_row(standard, d)          # свои НТД — первыми
    if row is not None:
        return row["upper"], row["lower"]
    standard = LEGACY.get(standard, standard)
    if standard.startswith("ГОСТ 2246-70, для сварки"):
        return 0.0, -_from_table(GOST2246_WELD, d, "сварочной проволоки", False)
    if standard.startswith("ГОСТ 2246-70, для электродов"):
        return 0.0, -_from_table(GOST2246_ELECTRODE, d, "проволоки для электродов", False)
    if standard.startswith("ГОСТ 2246-70, высоколег"):
        # п. 2.2: для травленой высоколегированной — на 50 % больше
        return 0.0, -1.5 * _from_table(GOST2246_WELD, d, "сварочной проволоки", False)
    if standard.startswith("ГОСТ 7417-75, h"):
        return 0.0, -_it(int(standard.split("h")[1]), d, 3, 100, "ГОСТ 7417-75")
    if standard.startswith("GB/T 14957"):
        i = 0 if "обычная" in standard else 1
        return 0.0, -_from_table({k: v[i] for k, v in GBT14957.items()}, d,
                                 "проволоки по GB/T 14957", True)
    if standard.startswith("GB/T 905-1994, h"):
        return 0.0, -_it(int(standard.split("h")[1]), d, 3, 80, "GB/T 905-1994")
    for prefix in PROFILE_STANDARDS:
        if standard.startswith(prefix):
            return 0.0, -_it(int(standard.rsplit("h", 1)[1]), d, 3, 100, prefix)
    raise InputError(f"Неизвестный стандарт: {standard}")


def ovality_share(standard):
    """Допустимая овальность в долях поля допуска и пояснение."""
    standard = LEGACY.get(standard, standard)
    if standard.startswith("ГОСТ 7417"):
        return 1.0, "не больше предельного отклонения (по требованию потребителя — половины), п. 3"
    if standard.startswith("GB/T 905"):
        return 0.5, "не больше 50 % допуска"
    if any(standard.startswith(x) for x in PROFILE_STANDARDS):
        return 1.0, ("в пределах поля допуска размера; притупление углов и разность диагоналей — "
                     "по таблицам стандарта")
    return 0.5, "не больше половины допуска"


def curvature(standard, d):
    """Допустимая кривизна прутка, мм на 1 м (ГОСТ 7417-75, табл. 2), или None."""
    standard = LEGACY.get(standard, standard)
    if not standard.startswith("ГОСТ 7417"):
        return None
    q = int(standard.split("h")[1])
    col = 0 if q == 9 else (2 if q == 12 else 1)
    rows = [(25, (1.00, 2.00, 3.00)), (50, (0.75, 1.00, 2.00)), (1e9, (0.50, 1.00, 1.00))]
    for upto, vals in rows:
        if d <= upto:
            return vals[col]


def die_plan(d, upper, lower, reserve_pct=25.0, ovality=0.5):
    """Волока под допуск: новая волока на reserve_pct % поля выше нижней границы,
    остальное поле допуска — запас на износ (волока при износе только растёт)."""
    t = upper - lower
    d_min, d_max = d + lower, d + upper
    die_new = d_min + t * reserve_pct / 100
    return dict(d_min=d_min, d_max=d_max, field=t, ovality=t * ovality, die_new=die_new,
                wear_allow=d_max - die_new)


def check_measure(d, upper, lower, measured):
    """Состояние по замеру: 'ok', 'near' (выбрано 90 % поля и больше), 'out'."""
    d_min, d_max = d + lower, d + upper
    if measured > d_max + 1e-9 or measured < d_min - 1e-9:
        return "out"
    if measured >= d_min + 0.9 * (d_max - d_min):
        return "near"
    return "ok"
