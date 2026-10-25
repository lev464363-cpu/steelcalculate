"""Себестоимость передела волочения, руб/т годной продукции.

Обозначения: Qт — теоретическая производительность стана, кг/ч (при непрерывной работе);
Kи — коэффициент использования стана (доля календарного времени смены, когда стан тянет);
Qф = Qт·Kи — фактическая производительность за час работы смены.

Каждая статья считается как «затраты за час смены / кг за час смены», а в конце всё делится
на выход годного: затраты на переработанную тонну ложатся на годную продукцию.
"""
from core.coating import copper_share
from core.drawing import split_stages
from core.util import InputError, g_per_m

ENERGY_BY_PASSPORT = "по паспорту стана и коэффициенту загрузки"
ENERGY_BY_ROUTE = "по расчёту маршрута (мощность на волочение / КПД + холостой ход)"
ENERGY_METHODS = [ENERGY_BY_PASSPORT, ENERGY_BY_ROUTE]


def productivity(rho, d, v):
    """Теоретическая производительность, кг/ч: масса 1 м (г) × скорость (м/с) × 3,6."""
    return g_per_m(rho, d) * v * 3.6


def work_power(c):
    """Мощность, потребляемая станом во время волочения, кВт."""
    p_idle = c["p_inst"] * c["idle_pct"] / 100
    if c["energy_method"] == ENERGY_BY_ROUTE:
        return c["p_draw"] / (c["eta_pct"] / 100) + p_idle, p_idle
    return c["p_inst"] * c["load_pct"] / 100, p_idle


def cost_breakdown(c):
    """c — словарь входных данных (см. тесты и раздел «Себестоимость передела»).
    Возвращает статьи (название, руб/т годной), итоги и производственные показатели."""
    ku = c["ku_pct"] / 100
    yield_ = c["yield_pct"] / 100
    if not 0 < ku <= 1:
        raise InputError("Коэффициент использования стана — от 1 до 100 %.")
    if not 0 < yield_ <= 1:
        raise InputError("Выход годного — от 1 до 100 %.")
    q_t = productivity(c["rho"], c["d"], c["v"])
    q_f = q_t * ku                          # кг за календарный час смены
    hours_year = c["shifts"] * c["shift_h"] * c["days"]
    out_year_t = q_f * hours_year / 1000    # переработано, т/год

    # Энергия: во время работы — рабочая мощность, во время простоев — холостой ход
    p_work, p_idle = work_power(c)
    kwh_per_hour = p_work * ku + p_idle * (1 - ku)
    kwh_t = kwh_per_hour / q_f * 1000

    labor_per_hour = c["workers"] * c["rate"] * (1 + c["tax_pct"] / 100)
    labor_t = labor_per_hour / q_f * 1000

    items = [
        ("Электроэнергия", kwh_t * c["tariff"]),
        ("Оплата труда со страховыми взносами", labor_t),
        ("Цеховые накладные", labor_t * c["overhead_pct"] / 100),
        ("Фильеры", c["n_passes"] * c["die_price"] / c["die_life_t"]),
        ("Смазка", c["lube_kg_t"] * c["lube_price"]),
        ("Отжиги", c["anneals"] * c["anneal_cost_t"]),
        ("Прочие материалы", c["other_t"]),
        ("Амортизация стана", c["mill_price"] / c["mill_years"] / out_year_t),
        ("Ремонт и обслуживание стана", c["mill_price"] * c["repair_pct"] / 100 / out_year_t),
    ]
    cu_kg_t = 0.0
    if c.get("copper"):
        loss = c["cu_loss_pct"] / 100
        if loss >= 1:
            raise InputError("Потери меди должны быть меньше 100 %.")
        share = copper_share(c["d"], c["cu_um"] / 1000, c["rho"])[2]
        cu_kg_t = share * 1000 / (1 - loss)
        items.append(("Медь на омеднение", cu_kg_t * c["cu_price"]))

    # пересчёт на тонну годной
    items = [(name, val / yield_) for name, val in items]
    conversion = sum(v for _, v in items)

    full_items = []
    if c.get("full"):
        consumption = 1 / yield_                       # т катанки на т годной
        full_items = [
            ("Катанка (заготовка)", c["rod_price"] * consumption),
            ("Возврат отходов", -c["scrap_price"] * (consumption - 1)),
            ("Упаковка", c["pack_price"] / c["pack_kg"] * 1000),
        ]
    full = conversion + sum(v for _, v in full_items)

    warnings = []
    if p_work > c["p_inst"] * 1.0001:
        warnings.append("Рабочая мощность получилась больше паспортной: проверь КПД, холостой "
                        "ход или скорость волочения.")
    return dict(items=items, conversion=conversion, full_items=full_items, full=full,
                q_t=q_t, q_f=q_f, out_year_t=out_year_t, out_month_t=out_year_t / 12,
                kwh_t=kwh_t, p_work=p_work, p_idle=p_idle, cu_kg_t=cu_kg_t, warnings=warnings)


# Входные данные себестоимости, которые хранятся в техкарте (остальное берётся из маршрута)
COST_NUM_KEYS = ("shifts", "shift_h", "days", "ku_pct", "yield_pct", "p_inst", "load_pct",
                 "eta_pct", "idle_pct", "tariff", "workers", "rate", "tax_pct", "overhead_pct",
                 "die_price", "die_life_t", "lube_kg_t", "lube_price", "anneal_cost_t", "other_t",
                 "mill_price", "mill_years", "repair_pct")
COPPER_KEYS = ("cu_um", "cu_loss_pct", "cu_price")
FULL_KEYS = ("rod_price", "scrap_price", "pack_price", "pack_kg")


def cost_for_route(cost, p, res):
    """Себестоимость рассчитанного маршрута. Продукт, проходы, отжиги и мощность — из маршрута.
    Если в маршруте есть отжиги, каждый этап между ними — отдельный прогон через стан: затраты,
    зависящие от времени работы стана, считаются по этапам и складываются."""
    rows, forces = res["rows"], res["forces"]
    stages, k = [], 0
    for st in split_stages(rows):
        stages.append((st, forces[k:k + len(st)]))
        k += len(st)
    if len(stages) <= 1:
        c = dict(cost, d=p["dk"], v=p["v"], rho=p["rho"], n_passes=res["n"],
                 anneals=res["anneals"], p_draw=res["power"])
        return dict(cost_breakdown(c), stages=1)

    yield_ = cost["yield_pct"] / 100
    order, agg, kwh, inv_q, warnings, p_work, p_idle = [], {}, 0.0, 0.0, [], 0.0, 0.0
    for st_rows, st_forces in stages:
        c = dict(cost, d=st_rows[-1]["d_out"], v=st_rows[-1]["v"], rho=p["rho"],
                 n_passes=len(st_rows), anneals=0, p_draw=sum(f["power"] for f in st_forces),
                 yield_pct=100, copper=False, full=False)
        r = cost_breakdown(c)
        # Под вопросом: статьи на тонну («Смазка», «Прочие материалы») складываются по этапам,
        # т. е. при одном отжиге (2 этапа) учитываются дважды. Верно, если норма задана на тонну
        # за один прогон через стан; если на тонну готовой проволоки — завышено в число этапов.
        # Оставлено до решения технолога; фильеры и время стана по этапам складываются корректно.
        for name, val in r["items"]:
            if name not in agg:
                order.append(name)
                agg[name] = 0.0
            agg[name] += val
        kwh += r["kwh_t"]
        inv_q += 1 / r["q_f"]
        p_work, p_idle = max(p_work, r["p_work"]), r["p_idle"]
        warnings += [w for w in r["warnings"] if w not in warnings]
    agg["Отжиги"] = res["anneals"] * cost["anneal_cost_t"]
    cu_kg_t = 0.0
    if cost.get("copper"):
        loss = cost["cu_loss_pct"] / 100
        if loss >= 1:
            raise InputError("Потери меди должны быть меньше 100 %.")
        share = copper_share(p["dk"], cost["cu_um"] / 1000, p["rho"])[2]
        cu_kg_t = share * 1000 / (1 - loss)
        order.append("Медь на омеднение")
        agg["Медь на омеднение"] = cu_kg_t * cost["cu_price"]
    items = [(name, agg[name] / yield_) for name in order]
    conversion = sum(v for _, v in items)
    full_items = []
    if cost.get("full"):
        consumption = 1 / yield_
        full_items = [("Катанка (заготовка)", cost["rod_price"] * consumption),
                      ("Возврат отходов", -cost["scrap_price"] * (consumption - 1)),
                      ("Упаковка", cost["pack_price"] / cost["pack_kg"] * 1000)]
    q_f = 1 / inv_q                                   # тонна проходит все этапы по очереди
    hours_year = cost["shifts"] * cost["shift_h"] * cost["days"]
    out_year = q_f * hours_year / 1000
    return dict(items=items, conversion=conversion, full_items=full_items,
                full=conversion + sum(v for _, v in full_items),
                q_t=q_f / (cost["ku_pct"] / 100), q_f=q_f, out_year_t=out_year,
                out_month_t=out_year / 12, kwh_t=kwh / yield_, p_work=p_work, p_idle=p_idle,
                cu_kg_t=cu_kg_t, warnings=warnings, stages=len(stages))


FORMULAS = [
    "Производительность. Теоретическая Qт = масса 1 м (г) × скорость (м/с) × 3,6, кг/ч. "
    "Фактическая Qф = Qт × Kи, где Kи — коэффициент использования стана.",
    "Принцип. Каждая статья — затраты за час смены, делённые на Qф. В конце все статьи делятся "
    "на выход годного.",
    "Электроэнергия, кВт·ч/т = (Pраб × Kи + Pхх × (1 − Kи)) / Qф × 1000. Рабочая мощность по "
    "паспорту = Pуст × Kзагр, по маршруту = Pволоч / КПД + Pхх.",
    "Оплата труда = рабочих × ставка × (1 + взносы) / Qф. Накладные — % от зарплаты.",
    "Фильеры = число проходов × цена / стойкость. Смазка = расход × цена. Отжиги = число "
    "отжигов × стоимость отжига на тонну.",
    "Маршрут с отжигами: смазка и прочие материалы считаются на каждый этап между отжигами и "
    "складываются (норма понимается как расход на тонну за один прогон через стан). Если норма "
    "задана на тонну готовой проволоки, эти статьи завышены в число этапов — под вопросом.",
    "Медь = доля меди в проволоке / (1 − потери) × цена.",
    "Амортизация = стоимость стана / срок / годовой выпуск. Ремонт = стоимость × % / годовой "
    "выпуск. Годовой выпуск = Qф × смены × часы × дни.",
    "Полная себестоимость = передел + катанка / выход − отходы × (1 / выход − 1) + упаковка "
    "(цена / масса нетто).",
]
