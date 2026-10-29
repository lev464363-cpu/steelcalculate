"""Модель очага деформации при волочении через коническую волоку (верхняя оценка Avitzur).

Течение в очаге — радиальное к вершине конуса (сферическое поле скоростей): металл входит в
очаг через сферическую поверхность радиуса ρ₀ = R₀ / sin α и выходит через ρf = Rf / sin α.
Линия тока, лежащая под углом θ к оси (0 ≤ θ ≤ α), остаётся на относительном радиусе
ξ = r / R = sin θ / sin α — до и после волоки одним и тем же (постоянство объёма).

Деформация на линии тока за проход:
    ε(ξ) = 2·ln(R₀/Rf)·√(1 − 11/12·sin²θ)  +  (2/√3)·tg θ,
первое слагаемое — течение внутри очага, второе — сдвиг на входной и выходной поверхностях
(по (1/√3)·tg θ на каждой). В оси (ξ = 0) — однородная деформация 2·ln(R₀/Rf), у поверхности —
больше. Коэффициент неравномерности φ = ε̄ / εоднор, ε̄ — среднее по площади сечения.

Напряжение волочения (Avitzur):
    σвол/σs = 2·f(α)·ln(R₀/Rf) + (2/√3)·(α/sin²α − ctg α)
              + (2/√3)·m·(ctg α·ln(R₀/Rf) + Lп/Rf) + σq/σs,
f(α) — множитель течения в очаге (→ 1 при малых α), m — фактор трения; по закону Кулона при
давлении на волоку ≈ σs: m ≈ √3·μ. Lп — длина калибрующего пояска.

Параметр очага Δ (Wright) и риск разрыва сердцевины: Δ > 3 — растяжение в оси, Δ > 4 — явный
риск; порог можно уточнить по расчётам в DEFORM (core.deform_link)."""
import math

from core.dies import DELTA_MAX, DELTA_RISK, delta

N_RINGS = 21                 # точек по радиусу: ξ = 0; 0,05; … 1


def f_alpha(a):
    """Множитель течения в очаге f(α) по Avitzur."""
    if a < 1e-6:
        return 1.0
    s2 = math.sin(a) ** 2
    k = math.sqrt(11 / 12)
    root = math.sqrt(1 - 11 / 12 * s2)
    return (1 - math.cos(a) * root
            + 1 / math.sqrt(11 * 12) * math.log((1 + k) / (k * math.cos(a) + root))) / s2


def strain_at(xi, lam, a):
    """Деформация за проход на относительном радиусе ξ (0 — ось, 1 — поверхность)."""
    th = math.asin(min(max(xi, 0.0), 1.0) * math.sin(a))
    return (math.log(lam) * math.sqrt(1 - 11 / 12 * math.sin(th) ** 2)
            + 2 / math.sqrt(3) * math.tan(th))


def rings(n=N_RINGS):
    return [i / (n - 1) for i in range(n)]


def area_mean(values, xs):
    """Среднее по площади круга: ∫ v·2ξ dξ (трапеции)."""
    tot = 0.0
    for i in range(len(xs) - 1):
        tot += (values[i] * xs[i] + values[i + 1] * xs[i + 1]) * (xs[i + 1] - xs[i])
    return tot


def avitzur_stress(lam, a, m, bearing_rel=0.0, back_rel=0.0):
    """σвол/σs по Avitzur; bearing_rel = Lп/Rf, back_rel = σq/σs."""
    ln = 0.5 * math.log(lam)                      # ln(R₀/Rf)
    redundant = 2 / math.sqrt(3) * (a / math.sin(a) ** 2 - 1 / math.tan(a))
    friction = 2 / math.sqrt(3) * m * (ln / math.tan(a) + bearing_rel)
    return 2 * f_alpha(a) * ln + redundant + friction + back_rel


def pass_profile(lam, alpha_deg, xs=None):
    """Профиль деформации за проход: значения по ξ, среднее, φ, поверхность и ось."""
    a = math.radians(alpha_deg)
    xs = xs or rings()
    eps = [strain_at(x, lam, a) for x in xs]
    homog = math.log(lam)
    mean = area_mean(eps, xs)
    return dict(xs=xs, eps=eps, mean=mean, homog=homog, phi=mean / homog if homog else 1.0,
                surface=eps[-1], center=eps[0])


def route_deformation(rows, forces, p, bearing_share=0.35, calib=None):
    """Модель по всему маршруту. rows/forces — из plan_route, p — параметры маршрута.
    calib — поправки DEFORM (core.deform_link.Calibration): множитель сдвиговой деформации,
    множитель усилия, порог Δ. Возвращает по проходу профиль, накопленные деформации и
    прочность по сечению, напряжение Avitzur, Δ и оценку риска."""
    a = math.radians(p["alpha"])
    m = math.sqrt(3) * p["mu"]
    k_shear = calib.k_shear if calib else 1.0
    d_limit = calib.delta_limit if calib and calib.delta_limit else DELTA_RISK
    xs = rings()
    # кривая упрочнения та же, что в расчёте усилий (core.forces): σв = σ_base + K·εⁿ
    from core.forces import eps_from_reduction
    eps_ref = eps_from_reduction(p["redref"])
    k = (p["sigf"] - p["sig0"]) / eps_ref ** p["nh"] if eps_ref > 0 else 0.0
    base, cum, out = p["sig0"], [0.0] * len(xs), []
    sig_in = base                                  # средняя прочность на входе в проход
    for r, f in zip(rows, forces):
        if r["anneal"]:
            base, cum = p.get("sig_ann") or p["sig0"], [0.0] * len(xs)
            sig_in = base
        prof = pass_profile(r["lam"], p["alpha"], xs)
        homog = prof["homog"]
        # поправка DEFORM — к сдвиговой (неоднородной) части
        eps = [homog + (e - homog) * k_shear for e in prof["eps"]] if k_shear != 1.0 \
            else prof["eps"]
        cum = [c + e for c, e in zip(cum, eps)]
        sig = [base + k * c ** p["nh"] for c in cum]
        # средний предел текучести в проходе — как в формуле Зибеля (core.forces)
        sig_s = p.get("ys", 0.85) * (sig_in + f["sig_out"]) / 2
        sig_in = f["sig_out"]
        rel = avitzur_stress(r["lam"], a, m, bearing_share * 2,
                             f.get("sig_q", 0.0) / sig_s if sig_s else 0.0)
        dlt = delta(a, r["lam"])
        risk = "риск" if dlt > d_limit else ("внимание" if dlt > DELTA_MAX else "норма")
        mean = area_mean(eps, xs)
        out.append(dict(i=r["i"], lam=r["lam"], eps=eps, mean=mean, phi=mean / homog,
                        surface=eps[-1], center=eps[0], cum=cum, cum_surface=cum[-1],
                        cum_center=cum[0], sig=sig, sig_mean=area_mean(sig, xs),
                        sig_d_avitzur=rel * sig_s * (calib.k_force if calib else 1.0),
                        sig_d_siebel=f["sig_d"], delta=dlt, risk=risk, anneal=r["anneal"]))
    return dict(xs=xs, passes=out, delta_limit=d_limit,
                worst=max(out, key=lambda x: x["delta"]) if out else None)
