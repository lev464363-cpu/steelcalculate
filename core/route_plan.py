"""Полный расчёт маршрута по набору параметров.
Общий для страницы маршрута, техкарт, сравнения вариантов и печати."""
import math

from core.dies import DELTA_RISK, delta
from core.drawing import build_route
from core.forces import eps_from_reduction, route_forces
from core.mills import check_mill
from core.thermal import T_AGING, T_WINDING, wire_temperatures
from core.util import fmt, g_per_m

# Параметры маршрута: всё, что нужно для расчёта и сохраняется в техкарте
PARAM_KEYS = ("d0", "dk", "n", "ratio", "lmax", "v", "drum", "limit", "alpha", "mu", "gmin",
              "sig0", "sigf", "nh", "rho", "redref", "t0", "tw", "cool", "cp", "vcool",
              "dcool", "lams", "ys", "sq", "sig_ann", "sig_min", "sig_max", "kF", "dlim")
# могут быть пустыми; dlim — предел Δ по DEFORM (пусто — ориентир Wright)
OPTIONAL_KEYS = ("drum", "lams", "sig_ann", "sig_min", "sig_max", "dlim")
# значения для техкарт, сохранённых до появления расчёта нагрева, σт/σв и противонатяжения
THERMAL_DEFAULTS = dict(t0=20.0, tw=25.0, cool=50.0, cp=470.0, ys=0.85, sq=0.0, sig_ann=None,
                        sig_min=None, sig_max=None, kF=1.0, dlim=None)


def plan_route(p, group="", mill=None):
    """mill — профиль стана (словарь) или None: тогда проверка на стане не выполняется."""
    p = dict(THERMAL_DEFAULTS, **{k: v for k, v in p.items()
                                  if v is not None or k in OPTIONAL_KEYS})
    n = int(p["n"])

    def compute(force=None):
        total, lams, rows, anneals = build_route(p["d0"], p["dk"], n, p["ratio"], p["limit"],
                                                 p["lmax"], p["v"], p["drum"], p.get("v_stages"),
                                                 p.get("lams"), force)
        forces = route_forces(rows, p["alpha"], p["mu"], p["sig0"], p["sigf"], p["nh"],
                              ys_ratio=p["ys"], eps_ref=eps_from_reduction(p["redref"]),
                              back=p["sq"], sig_ann=p["sig_ann"], k_force=p["kF"])
        return total, lams, rows, anneals, forces

    total, lams, rows, anneals, forces = compute()
    if p["sig_max"] is not None and forces[-1]["sig_out"] > p["sig_max"] + 1e-9:
        # Готовая проволока прочнее требования: отжиг по прочности. Перебираем место отжига
        # с конца маршрута и берём то, где прочность наибольшая, но не выше верхней границы
        # (и, если задана, не ниже нижней).
        best = None
        for j in range(n, 1, -1):
            cand = compute(j)
            s = cand[4][-1]["sig_out"]
            if s > p["sig_max"] + 1e-9:
                continue
            in_range = p["sig_min"] is None or s >= p["sig_min"] - 1e-9
            key = (in_range, s)
            if best is None or key > best[0]:
                best = (key, cand)
        if best is not None:
            total, lams, rows, anneals, forces = best[1]
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
    sig_end = forces[-1]["sig_out"]
    lo_ok = p["sig_min"] is None or sig_end >= p["sig_min"] - 1e-9
    hi_ok = p["sig_max"] is None or sig_end <= p["sig_max"] + 1e-9
    if not (lo_ok and hi_ok):
        if p["sig_max"] is None:
            need = f"не ниже {fmt(p['sig_min'], 0)}"
        elif p["sig_min"] is None:
            need = f"не выше {fmt(p['sig_max'], 0)}"
        else:
            need = f"{fmt(p['sig_min'], 0)}–{fmt(p['sig_max'], 0)}"
        warnings.append(f"Прочность готовой проволоки по расчёту {fmt(sig_end, 0)} МПа, а по "
                        f"требованию {need} МПа. "
                        + ("Нужно больше обжатие после последнего отжига или более прочная "
                           "заготовка." if not lo_ok else
                           "Нужен отжиг ближе к финишу или меньшее суммарное обжатие."))
    # риск разрыва сердцевины («ёлочка»): параметр очага Δ выше предела
    d_lim = p["dlim"] or DELTA_RISK
    burst = [r["i"] for r in rows if delta(math.radians(p["alpha"]), r["lam"]) > d_lim + 1e-9]
    if burst:
        warnings.append(f"Параметр очага деформации Δ выше {fmt(d_lim, 1)} на проходах "
                        f"{', '.join(map(str, burst))}: риск разрыва сердцевины. Уменьши угол "
                        f"волоки или увеличь обжатие на этих проходах (вкладка «Деформация»).")
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
                sig_end=sig_end, strength_ok=lo_ok and hi_ok,
                power=sum(f["power"] for f in forces), productivity=gpm * p["v"] * 3.6,
                eps=math.log(total), weak=weak, over=over, warnings=warnings)


def suggest_n_full(p, group="", mill=None):
    """Минимальное число проходов, при котором вытяжка, запас прочности и (если задано)
    требование к прочности готовой проволоки в норме. Если требование по прочности не
    выполнимо ни при каком числе проходов — минимальное по вытяжке и запасу прочности."""
    from core.drawing import distribute
    from core.util import InputError
    fallback = None
    for n in range(1, 61):
        lams = distribute((p["d0"] / p["dk"]) ** 2, n, p["ratio"])
        if max(lams) > p["lmax"] or min(lams) <= 1:
            continue
        try:
            res = plan_route(dict(p, n=n), group, mill)
        except InputError:
            continue
        if res["gamma_min"] >= p["gmin"]:
            if res["strength_ok"]:
                return n
            fallback = fallback or n
    return fallback
