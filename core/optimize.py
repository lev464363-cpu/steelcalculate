"""Поиск самого дешёвого допустимого маршрута волочения.

Перебираются число проходов n и перевес обжатия k; для каждой пары находится наибольшая скорость
на финише, при которой выполнены все ограничения (скорость и мощность стана, нагрев проволоки и
температура намотки). Себестоимость передела падает с ростом скорости, поэтому для пары (n, k)
берётся наибольшая допустимая скорость, а из всех пар — самая дешёвая."""
import math

from core.cost import ENERGY_BY_ROUTE, cost_for_route
from core.data import GROUPS
from core.drawing import distribute, split_stages
from core.route_plan import plan_route
from core.util import InputError

# Исходные данные себестоимости по умолчанию (как в «Экономике» маршрута), энергия — по маршруту
DEFAULT_COST = dict(shifts=2, shift_h=12, days=250, ku_pct=75, yield_pct=97, p_inst=632,
                    load_pct=60, eta_pct=85, idle_pct=10, tariff=8, workers=2, rate=450,
                    tax_pct=30.2, overhead_pct=100, die_price=7000, die_life_t=35, lube_kg_t=1.5,
                    lube_price=250, anneal_cost_t=3000, other_t=300, mill_price=45e6,
                    mill_years=10, repair_pct=4, energy_method=ENERGY_BY_ROUTE, copper=False,
                    full=False)
DEFAULT_LIMITS = dict(gmin=1.4, t_max=180.0, t_wind=100.0, v_max=30.0, n_max=24, lam_min=1.10,
                      lam_min_last=1.05,
                      ratios=(1.0, 1.05, 1.1, 1.15, 1.2, 1.25, 1.3))
# Точка калибровки охлаждения: 50 % перегрева снимается при 15 м/с на проволоке 1,2 мм (условно)
DEFAULT_THERMAL = dict(t0=20.0, tw=25.0, cool=50.0, vcool=15.0, dcool=1.2)


def _stage_ok(p, group, s, last, limits):
    """Нагрев этапа s в норме (этапы независимы: отжиг остужает проволоку)."""
    r = plan_route(p, group)
    k0 = 0
    for idx, st in enumerate(split_stages(r["rows"])):
        if idx == s:
            th = r["thermal"][k0:k0 + len(st)]
            ok = max(t["t_out"] for t in th) <= limits["t_max"]
            if last:
                ok = ok and th[-1]["t_drum"] <= limits["t_wind"]
            return ok
        k0 += len(st)
    return False


def optimize(group, rho, dk, d0=5.5, cost=None, thermal=None, limits=None, alpha=6.0, mu=0.05,
             overrides=None):
    """Возвращает лучший маршрут (словарь) или None, если допустимого нет.
    overrides — замена параметров группы и металла (limit, lmax, sig0, sigf, nh, redref, cp)."""
    cost = dict(DEFAULT_COST, **(cost or {}))
    thermal = dict(DEFAULT_THERMAL, **(thermal or {}))
    lim = dict(DEFAULT_LIMITS, **(limits or {}))
    g = GROUPS[group]
    h = g["hardening"]
    base = dict(d0=d0, dk=dk, lmax=g["lam_max"], limit=g["limit"], alpha=alpha, mu=mu,
                gmin=lim["gmin"], sig0=h["sig0"], sigf=h["sigf"], nh=h["n"], redref=h["red_ref"],
                rho=rho, cp=g.get("cp", 470), drum=None, **thermal)
    base.update(overrides or {})
    # мощность, доступная на волочение: (Pуст − Pхх) · КПД
    p_avail = (cost["p_inst"] * (1 - cost["idle_pct"] / 100)) * cost["eta_pct"] / 100
    total = (d0 / dk) ** 2
    best = None
    for n in range(1, lim["n_max"] + 1):
        for k in lim["ratios"]:
            lams = distribute(total, n, k)
            # вытяжка убывает к финишу: все проходы, кроме чистового, — не меньше lam_min,
            # чистовой (калибрующий) — не меньше lam_min_last
            if max(lams) > base["lmax"] or lams[-1] < lim["lam_min_last"] - 1e-9 or (
                    n > 1 and lams[-2] < lim["lam_min"] - 1e-9):
                continue
            p = dict(base, n=n, ratio=k, v=1.0)
            try:
                r1 = plan_route(p, group)
            except InputError:
                continue
            if r1["gamma_min"] < lim["gmin"]:
                continue
            # Каждый этап между отжигами — отдельный прогон со своей скоростью: для каждого
            # находим наибольшую скорость по стану, мощности и нагреву (у последнего — и намотке).
            stages_rows, powers, k0 = split_stages(r1["rows"]), [], 0
            for st in stages_rows:
                powers.append(sum(f["power"] for f in r1["forces"][k0:k0 + len(st)]))
                k0 += len(st)
            m = len(stages_rows)
            speeds, limits_by, feasible = [lim["v_max"]] * m, [], True
            for s_i in range(m):
                v_pow = p_avail / powers[s_i] if powers[s_i] > 0 else lim["v_max"]
                hi = min(lim["v_max"], v_pow)
                why = "скорость стана" if lim["v_max"] <= v_pow else "мощность стана"
                last = s_i == m - 1

                def ok(v):
                    vs = list(speeds)
                    vs[s_i] = v
                    return _stage_ok(dict(p, v=vs[-1], v_stages=vs), group, s_i, last, lim)
                if not ok(hi):
                    lo = 0.2
                    if not ok(lo):
                        feasible = False
                        break
                    for _ in range(22):
                        mid = (lo + hi) / 2
                        if ok(mid):
                            lo = mid
                        else:
                            hi = mid
                    hi = lo
                    why = "нагрев проволоки"
                speeds[s_i] = math.floor(hi * 100) / 100      # вниз: ограничение строго

                limits_by.append(why)
            if not feasible:
                continue
            limit_by = limits_by[-1]
            pv = dict(p, v=speeds[-1], v_stages=speeds if m > 1 else None)
            r = plan_route(pv, group)
            c = cost_for_route(cost, pv, r)
            cand = dict(n=n, ratio=k, v=pv["v"], lam1=r["lams"][0], lamn=r["lams"][-1],
                        anneals=r["anneals"], gamma_min=r["gamma_min"], t_max=r["t_max"],
                        t_wind=r["t_wind"], q_t=c["q_t"], q_f=c["q_f"], kwh_t=c["kwh_t"],
                        conversion=c["conversion"], limit_by=limit_by, params=pv,
                        stages=c.get("stages", 1), v_stages=speeds)
            if best is None or cand["conversion"] < best["conversion"] - 1e-6:
                best = cand
    return best
