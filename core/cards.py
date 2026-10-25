"""Технологические карты: сохранённые маршруты в файле tekhkarty.json рядом с программой."""
import json
import os
from datetime import datetime

from core.paths import app_dir
from core.util import fmt

CARDS_FILE = "tekhkarty.json"


def cards_path():
    return os.path.join(app_dir(), CARDS_FILE)


def load_cards(path=None):
    path = path or cards_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []


def save_cards(cards, path=None):
    with open(path or cards_path(), "w", encoding="utf-8") as fh:
        json.dump(cards, fh, ensure_ascii=False, indent=2)


def default_name(group, params, mill):
    short = group.split(" (")[0]
    name = f"{short} {fmt(params['d0'], 2)}→{fmt(params['dk'], 2)}"
    return f"{name}, {mill}" if mill else name


def upsert_card(cards, name, mill, group, params, note="", cost=None):
    """Добавляет карту или заменяет карту с тем же названием. Возвращает True, если заменила.
    cost — исходные данные себестоимости (цены и нормы) на момент сохранения."""
    card = dict(name=name, mill=mill, group=group, params=dict(params), note=note,
                cost=dict(cost) if cost else None,
                updated=datetime.now().strftime("%d.%m.%Y %H:%M"))
    for i, c in enumerate(cards):
        if c["name"] == name:
            cards[i] = card
            return True
    cards.append(card)
    return False


# Сравнение вариантов: (название строки, функция значения, формат, что лучше: min / max / None)
COMPARE_METRICS = [
    ("Стан", lambda c, r: c.get("mill") or "—", None, None),
    ("Группа сталей", lambda c, r: c["group"], None, None),
    ("Маршрут, мм", lambda c, r: f"{fmt(c['params']['d0'], 2)} → {fmt(c['params']['dk'], 2)}",
     None, None),
    ("Проходов", lambda c, r: r["n"], 0, "min"),
    ("Отжигов", lambda c, r: r["anneals"], 0, "min"),
    ("Макс. вытяжка за проход", lambda c, r: max(r["lams"]), 3, "min"),
    ("Мин. запас прочности", lambda c, r: r["gamma_min"], 2, "max"),
    ("Мощность на волочение, кВт", lambda c, r: r["power"], 1, "min"),
    ("Скорость стана на финише, м/с", lambda c, r: c["params"]["v"], 1, None),
    ("Производительность, кг/ч", lambda c, r: r["productivity"], 0, "max"),
    ("Макс. температура проволоки, °C", lambda c, r: r.get("t_max"), 0, "min"),
    ("Температура на намотке, °C", lambda c, r: r.get("t_wind"), 0, "min"),
    ("Макс. загрузка привода, %",
     lambda c, r: r["mill"]["max_load"] if r.get("mill") else None, 0, "min"),
    ("Передел, руб/т", lambda c, r: r["cost"]["conversion"] if r.get("cost") else None, 0, "min"),
    ("Электроэнергия, кВт·ч/т", lambda c, r: r["cost"]["kwh_t"] if r.get("cost") else None, 0,
     "min"),
    ("Выпуск, т/мес", lambda c, r: r["cost"]["out_month_t"] if r.get("cost") else None, 0, "max"),
    ("Полная себестоимость, руб/т",
     lambda c, r: r["cost"]["full"] if r.get("cost") and c["cost"].get("full") else None, 0, "min"),
    ("Предупреждений", lambda c, r: len(r["warnings"]), 0, "min"),
]


def compare(cards, results):
    """Таблица сравнения: [(название, [текст по картам], индекс лучшей или None)]."""
    table = []
    for title, get, nd, better in COMPARE_METRICS:
        vals = [get(c, r) for c, r in zip(cards, results)]
        texts = ["—" if v is None else str(v) if nd is None else fmt(v, nd) for v in vals]
        known = [v for v in vals if v is not None]
        best = None
        if better and len(known) >= 2 and len(set(known)) > 1:
            target = min(known) if better == "min" else max(known)
            best = vals.index(target)
        table.append((title, texts, best))
    return table
