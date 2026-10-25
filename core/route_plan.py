"""Полный расчёт маршрута по набору параметров.
Общий для страницы маршрута, техкарт, сравнения вариантов и печати."""
import math

from core.drawing import build_route
from core.forces import eps_from_reduction, route_forces
from core.mills import check_mill
from core.thermal import T_AGING, T_WINDING, wire_temperatures
from core.util import fmt, g_per_m

# Параметры маршрута: всё, что нужно для расчёта и сохраняется в техкарте
PARAM_KEYS = ("d0", "dk", "n", "ratio", "lmax", "v", "drum", "limit", "alpha", "mu", "gmin",
              "sig0", "sigf", "nh", "rho", "redref", "t0", "tw", "cool", "cp", "vcool",
              "dcool", "lams")
# значения для техкарт, сохранённых до появления расчёта нагрева
THERMAL_DEFAULTS = dict(t0=20.0, tw=25.0, cool=50.0, cp=470.0)


def plan_route(p, group="", mill=None):
    """mill — профиль стана (словарь) или None: тогда проверка на стане не выполняется."""
    p = dict(THERMAL_DEFAULTS, **{k: v for k, v in p.items()
                                  if v is not None or k in ("drum", "lams")})
    n = int(p["n"])
    total, lams, rows, anneals = build_route(p["d0"], p["dk"], n, p["ratio"], p["limit"],
                                             p["lmax"], p["v"], p["drum"], p.get("v_stages"),
                                             p.get("lams"))
    forces = route_forces(rows, p["alpha"], p["mu"], p["sig0"], p["sigf"], p["nh"],
                          eps_ref=eps_from_reduction(p["redref"]))
    gpm = g_per_m(p["rho"], p["dk"])
    weak = [r["i"] for r, f in zip(rows, forces) if f["gamma"] < p["gmin"]]
    over = [r["i"] for r in rows if r["over"]]
    warnings = []
    if weak:
        warnings.append(f"Запас прочности ниже {fmt(p['gmin'], 2)} на проходах "
                        f"{', '.join(map(str, weak))}: возможны обрывы. Уменьши вытяжку на этих "
                        f"проходах, добавь проход или улучши смазку.")
    if over:
        warnings.append("Есть проходы с вытяжкой выше допустимой: увеличь число проходов "
                        "или нажми «Подобрать число проходов».")
    if anneals and "углеродистой ленты" in group:
        warnings.append("Порошковую проволоку с углеродистой оболочкой обычно тянут без отжига: "
                        "лучше пересмотреть маршрут или диаметр трубки.")
    # опорная скорость охлаждения: если не задана — охлаждение задано при текущей скорости
    v_ref = p.get("vcool") or p["v"]
    thermal = wire_temperatures(rows, forces, p["rho"], p["cp"], p["t0"], p["tw"], p["cool"],
                                v_ref=v_ref, d_ref=p.get("dcool") or p["dk"])
    hot = [r["i"] for r, t in zip(rows, thermal) if t["t_out"] > T_AGING]
    if hot:
        warnings.append(f"Температура проволоки после волоки выше {fmt(T_AGING, 0)} °C на проходах "
                        f"{', '.join(map(str, hot))}: условия для статического деформационного "
                        f"старения. Усиль охлаждение, снизь скорость или трение.")
    if thermal[-1]["t_drum"] > T_WINDING:
        warnings.append(f"Проволока уходит на намотку при {fmt(thermal[-1]['t_drum'], 0)} °C: "
                        f"тёплая намотка (100–140 °C) ведёт к старению на катушке.")
    mill_res = check_mill(mill, rows, forces, p["v"]) if mill else None
    if mill_res:
        warnings += mill_res["warnings"]
    return dict(total=total, lams=lams, rows=rows, forces=forces, anneals=anneals, n=n,
                thermal=thermal, t_max=max(t["t_out"] for t in thermal),
                t_wind=thermal[-1]["t_drum"], mill=mill_res,
                gpm=gpm, gamma_min=min(f["gamma"] for f in forces),
                power=sum(f["power"] for f in forces), productivity=gpm * p["v"] * 3.6,
                eps=math.log(total), weak=weak, over=over, warnings=warnings)


def suggest_n_full(p, group="", mill=None):
    """Минимальное число проходов, при котором и вытяжка, и запас прочности в норме."""
    from core.drawing import distribute
    from core.util import InputError
    for n in range(1, 61):
        lams = distribute((p["d0"] / p["dk"]) ** 2, n, p["ratio"])
        if max(lams) > p["lmax"] or min(lams) <= 1:
            continue
        try:
            res = plan_route(dict(p, n=n), group, mill)
        except InputError:
            continue
        if res["gamma_min"] >= p["gmin"]:
            return n
    return None
