"""Геометрия и материал волоки по проходам.

Оптимальный полуугол (минимум напряжения волочения в формуле Зибеля, dσ/dα = 0):
    α* = √(1,5 · μ · ln λ)
Параметр формы очага деформации (Wright, Wire Technology):
    Δ = (α / r) · (1 + √(1 − r))²,  r = 1 − 1/λ
Минимум усилия обычно при Δ ≈ 2–3; снижение Δ к 1–1,5 даёт более равномерную деформацию и
стойкость волоки; при больших Δ растёт растягивающее напряжение в оси проволоки — риск разрыва
сердцевины («ёлочки»). Рекомендуемый угол: не больше оптимального и не больше угла, при котором Δ = 3.
"""
import math

DELTA_MAX = 3.0          # ориентир теории (Wright)
DELTA_RISK = 4.0         # выше — явный риск разрыва сердцевины
STD_ANGLES = (8, 10, 12, 14, 16, 18, 20, 22, 24)   # рабочий угол 2α, градусы


def angle_range(group, d_out, final):
    """Практический диапазон рабочего угла 2α, градусы (TKT Group; US 4404827: 8–16°):
    низкоуглеродистая сталь 12–14°, высокоуглеродистая 10–12°, тонкая проволока ~10°,
    чистовой проход 10–12°; цветные (мягкие) — до 18° (Esteves)."""
    fam = family_of(group)
    if fam == "nonferrous":
        return (14, 18) if not final else (12, 16)
    if d_out < 1.0:
        return 10, 10
    if fam == "hard" or final:
        return 10, 12
    return 12, 14


def alpha_opt(mu, lam):
    """Оптимальный полуугол, рад."""
    return math.sqrt(1.5 * mu * math.log(lam))


def delta(alpha, lam):
    r = 1 - 1 / lam
    return alpha / r * (1 + math.sqrt(1 - r)) ** 2


def alpha_for_delta(d, lam):
    r = 1 - 1 / lam
    return d * r / (1 + math.sqrt(1 - r)) ** 2


def family_of(group):
    g = group.lower()
    if "нержав" in g:
        return "stainless"
    if "пружин" in g or "шх15" in g or "подшипник" in g:
        return "hard"
    if any(x in g for x in ("медь", "латунь", "бронз", "алюмин", "цинк", "никель", "титан")):
        return "nonferrous"
    return "steel"


def material(group, d, wet, final):
    """Материал волоки по группе, диаметру и условиям (по источникам раздела «Аналитика»)."""
    fam = family_of(group)
    if fam == "nonferrous":
        if d < 0.05:
            return "природный алмаз"
        return "ПКА (поликристаллический алмаз)" if d <= 2.5 else "твёрдый сплав ВК6"
    if final and wet and d <= 2.0:
        return "ПКА — чистовая волока; твёрдый сплав ВК3 — запасной вариант"
    if wet or d < 1.5:
        return "твёрдый сплав ВК3 / ВК4 (3–4 % Co)"
    if fam == "stainless":
        return "твёрдый сплав ВК4 / ВК6 мелкозернистый"
    if d > 6:
        return "твёрдый сплав ВК8"
    return "твёрдый сплав ВК6 / ВК6М"


def bearing_share(group, wet):
    """Длина калибрующего пояска в долях выходного диаметра (ориентир по источникам)."""
    fam = family_of(group)
    if wet:
        return 0.30
    return {"hard": 0.50, "stainless": 0.45, "nonferrous": 0.30}.get(fam, 0.40)


def recommend_pass(group, d_out, lam, mu, wet, final):
    a_opt = alpha_opt(mu, lam)
    a_rec = min(a_opt, alpha_for_delta(DELTA_MAX, lam))
    two = math.degrees(2 * a_rec)
    # ближайший стандартный 2α в практическом диапазоне; если он нарушает Δ — меньший,
    # но не ниже нижней границы практики
    lo, hi = angle_range(group, d_out, final)
    std = min(STD_ANGLES, key=lambda s: abs(s - two))
    std = max(lo, min(hi, std))
    while delta(math.radians(std / 2), lam) > DELTA_MAX and std > lo:
        std = max(s for s in STD_ANGLES if s < std)
    std = max(lo, std)
    a_std = math.radians(std / 2)
    share = bearing_share(group, wet)
    return dict(two_opt=math.degrees(2 * a_opt), two_rec=two, two_std=std, range=(lo, hi),
                delta=delta(a_std, lam), bearing=share * d_out, share=share,
                material=material(group, d_out, wet, final))


def plan_dies(rows, group, mu, wet_from=1.6, journal=None, match_pct=1.0):
    """Рекомендации по каждому проходу и подбор из журнала фильер (номинал ± match_pct %)."""
    free = [d for d in (journal or []) if d.get("status") == "в работе"
            and d.get("used", 0) < d.get("limit", 1)]
    used_ids, out = set(), []
    for i, r in enumerate(rows):
        wet = r["d_out"] <= wet_from
        rec = recommend_pass(group, r["d_out"], r["lam"], mu, wet, i == len(rows) - 1)
        tol = r["d_out"] * match_pct / 100
        cand = sorted((d for d in free if d["id"] not in used_ids
                       and abs(d["d"] - r["d_out"]) <= tol),
                      key=lambda d: abs(d["d"] - r["d_out"]))
        match = cand[0] if cand else None
        if match:
            used_ids.add(match["id"])
        notes = []
        if rec["delta"] > DELTA_RISK:
            notes.append("параметр очага деформации > 4: риск разрыва сердцевины — нужен меньший угол "
                         "или больше обжатие")
        elif rec["delta"] > DELTA_MAX:
            notes.append("параметр очага деформации > 3: повышенное растяжение в оси; для лёгкого "
                         "чистового прохода обычно допустимо — следить за сердцевиной")
        lo, hi = rec["range"]
        if not lo <= round(rec["two_rec"]) <= hi:
            notes.append(f"угол приведён к практике {lo}–{hi}°" if lo != hi else
                         f"угол приведён к практике {lo}°")
        out.append(dict(rec, i=r["i"], d_out=r["d_out"], lam=r["lam"], wet=wet,
                        stock=match["id"] if match else None, notes="; ".join(notes)))
    return out


def load_journal():
    """Журнал фильер (filery.json рядом с программой); при ошибке — пустой список."""
    import os
    from core.paths import app_dir
    from core.storage import load_list
    try:
        # только чтение: повреждённый файл откладывает и показывает раздел «Журнал фильер»
        return load_list(os.path.join(app_dir(), "filery.json"), quarantine=False)
    except (OSError, ValueError):
        return []


def book_batch(journal, ids, tons, note=""):
    """Добавляет партию (т) к наработке фильер с номерами ids и пишет её в историю фильеры.
    Возвращает номера, которых нет среди фильер «в работе»."""
    from datetime import date
    by_id = {d["id"]: d for d in journal if d.get("status") == "в работе"}
    missing = []
    for die_id in ids:
        d = by_id.get(die_id)
        if d is None:
            missing.append(die_id)
            continue
        d["used"] = d.get("used", 0) + tons
        d.setdefault("log", []).append(dict(date=date.today().strftime("%d.%m.%Y"), t=tons,
                                            note=note))
    return missing


def actual_life(journal, die_type=None):
    """Фактическая стойкость: средняя наработка снятых фильер, т. (среднее, число) или None."""
    used = [d.get("used", 0) for d in journal if d.get("status") == "снята"
            and d.get("used", 0) > 0 and (die_type is None or d.get("type") == die_type)]
    return (sum(used) / len(used), len(used)) if used else None
