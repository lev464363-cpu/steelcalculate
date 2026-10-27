"""Маршрут волочения: распределение вытяжки по проходам, отжиги, скорости."""
import math

from core.util import InputError, fmt


def distribute(total, n, ratio):
    """Вытяжки по проходам: линейно убывают от ratio·λпосл до λпосл,
    произведение равно общей вытяжке."""
    if n == 1:
        return [total]

    def lams(last):
        return [last * (ratio - (ratio - 1) * i / (n - 1)) for i in range(n)]

    def prod(last):
        p = 1.0
        for x in lams(last):
            p *= x
        return p

    lo, hi = 1e-9, total
    for _ in range(200):
        mid = (lo + hi) / 2
        if prod(mid) < total:
            lo = mid
        else:
            hi = mid
    return lams((lo + hi) / 2)


def build_route(d0, dk, n, ratio, limit_pct, lam_max, v_fin, drum_mm, v_stages=None,
                lams_manual=None, force_anneal=None):
    """v_stages — скорости на финише каждого этапа между отжигами (иначе у всех v_fin);
    lams_manual — ручная раскладка вытяжек (из редактора обжатий), иначе — автоматическая;
    force_anneal — номер прохода, перед которым отжиг нужен по прочности готовой проволоки."""
    total = (d0 / dk) ** 2
    lams = manual_fits(lams_manual, total, n) or distribute(total, n, ratio)
    if min(lams) <= 1.0:
        raise InputError("При таком перевесе обжатия последние проходы выходят без обжатия.\n"
                         "Уменьши перевес обжатия в начале маршрута или число проходов.")
    rows, anneals = [], 0
    d_in = base = d0  # base — диаметр после катанки или последнего отжига
    for i, lam in enumerate(lams, 1):
        d_out = dk if i == n else d_in / math.sqrt(lam)
        notes = []
        red_cum = (1 - (d_out / base) ** 2) * 100
        anneal = False
        by_strength = i == force_anneal and d_in < base
        if (red_cum > limit_pct or by_strength) and d_in < base:
            anneal, anneals, base = True, anneals + 1, d_in
            red_cum = (1 - (d_out / base) ** 2) * 100
            notes.append("ОТЖИГ перед проходом" + (" (по прочности готовой)"
                                                    if by_strength and red_cum <= limit_pct else ""))
        over = lam > lam_max + 1e-9
        if over:
            notes.append(f"вытяжка выше {fmt(lam_max, 2)}")
        if red_cum > limit_pct:
            notes.append("обжатие за проход выше предела")
        v = v_fin * (dk / d_out) ** 2
        rpm = v * 60 / (math.pi * drum_mm / 1000) if drum_mm else None
        rows.append(dict(i=i, d_in=d_in, d_out=d_out, lam=lam,
                         red=(1 - 1 / lam) * 100, red_cum=red_cum,
                         eps=2 * math.log(base / d_out), v=v, rpm=rpm,
                         anneal=anneal, over=over, notes="; ".join(notes)))
        d_in = d_out
    # Отжиг делит маршрут на отдельные прогоны через стан: каждый этап идёт на заданной
    # скорости на своём последнем проходе, внутри этапа скорости — по постоянству объёма.
    for s, stage in enumerate(split_stages(rows)):
        d_end = stage[-1]["d_out"]
        v_end = v_stages[s] if v_stages and s < len(v_stages) else v_fin
        for r in stage:
            r["v"] = v_end * (d_end / r["d_out"]) ** 2
            r["rpm"] = r["v"] * 60 / (math.pi * drum_mm / 1000) if drum_mm else None
    return total, lams, rows, anneals


def split_stages(rows):
    """Делит проходы на этапы: новый этап начинается с прохода, перед которым стоит отжиг."""
    stages = []
    for r in rows:
        if not stages or r.get("anneal"):
            stages.append([])
        stages[-1].append(r)
    return stages


def suggest_n(d0, dk, ratio, lam_max):
    total = (d0 / dk) ** 2
    for n in range(1, 100):
        lams = distribute(total, n, ratio)
        if max(lams) <= lam_max and min(lams) > 1:
            return n
    return None


def heading_reduction(d):
    """Оптимальное обжатие калиброванного прутка под холодную высадку, % — по а.с. СССР 1752466:
    (0,0036…0,0038)·d·100 %, для прутков 6,5–34 мм. Возвращает (мин, макс) или None вне диапазона."""
    if not 6.5 <= d <= 34:
        return None
    return 0.36 * d, 0.38 * d


LAM_FLOOR = 1.01        # меньше — проход практически без обжатия
LAM_CEIL = 1.80         # больше — за пределами любой практики (обжатие 44 %)


def manual_fits(lams, total, n):
    """Ручная раскладка годится, если в ней n проходов и она даёт ту же общую вытяжку."""
    if not lams or len(lams) != n:
        return None
    prod = math.prod(lams)
    return list(lams) if abs(prod / total - 1) < 1e-6 else None


def redistribute(lams, i, new_lam, pinned, total):
    """Проход i получает вытяжку new_lam и закрепляется; незакреплённые проходы пропорционально
    (в логарифмах) перераспределяют остаток так, чтобы общая вытяжка не изменилась.
    Возвращает (вытяжки, закреплённые) или None, если двигать нечего."""
    n = len(lams)
    pinned = set(pinned) | {i}
    free = [j for j in range(n) if j not in pinned]
    if not free:
        return None
    ln_total = math.log(total)
    ln_pinned_other = sum(math.log(lams[j]) for j in pinned if j != i)
    # пределы для прохода i: свободным должно остаться не меньше LAM_FLOOR каждому
    hi = ln_total - ln_pinned_other - len(free) * math.log(LAM_FLOOR)
    lo = math.log(LAM_FLOOR)
    ln_new = min(max(math.log(new_lam), lo), min(hi, math.log(LAM_CEIL)))
    target = ln_total - ln_pinned_other - ln_new
    cur = sum(math.log(lams[j]) for j in free)
    out = list(lams)
    out[i] = math.exp(ln_new)
    if cur <= 0 or target <= 0:
        return None
    k = target / cur
    for j in free:
        out[j] = math.exp(k * math.log(lams[j]))
    return out, pinned
