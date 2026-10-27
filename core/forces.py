"""Усилие волочения, запас прочности и мощность по проходам."""
import math

from core.util import area


def route_forces(rows, alpha_deg, mu, sig0, sigf, n_h, ys_ratio=0.85, eps_ref=None, back=0.0,
                 sig_ann=None):
    """Усилие по формуле Зибеля: σвол = σs·[(1 + μ/α)·ln λ + 2α/3] + σq·λ^(−μ/α),
    упрочнение σв(ε) = σв0 + K·ε^n, кривая проходит через σв_ref при ε_ref,
    σs — средний предел текучести в проходе (ys_ratio·σв, по умолчанию 0,85), запас γ = σв после / σвол.
    back — противонатяжение σq, МПа: на всех проходах, кроме первого прохода каждого этапа
    (проволока идёт с размотчика). Слагаемое σq·λ^(−μ/α) — по Заксу. Противонатяжение
    держит предыдущий барабан, поэтому его мощность меньше на σq·S·v; в нагрев волоки идёт
    только работа деформации и трения σвол − σq.
    sig_ann — прочность после отжига, МПа: с неё начинается кривая упрочнения этапов после
    отжига (прирост K·εⁿ тот же); без неё — прочность заготовки σв0."""
    a = math.radians(alpha_deg)
    # sigf — прочность при деформации eps_ref; без eps_ref — в конце этого маршрута
    eps_end = eps_ref if eps_ref else rows[-1]["eps"]
    k = (sigf - sig0) / (eps_end ** n_h) if eps_end > 0 else 0.0

    def sig(e, base):
        return base + k * (max(e, 0.0) ** n_h)

    def tension(j):
        """Противонатяжение на проходе j: нет на первом проходе этапа."""
        return back if 0 < j < len(rows) and not rows[j]["anneal"] else 0.0

    out, prev, base = [], 0.0, sig0
    for j, r in enumerate(rows):
        if r["anneal"]:
            base = sig_ann or sig0
        e_in = 0.0 if r["anneal"] else prev
        s_in, s_out = sig(e_in, base), sig(r["eps"], base)
        sigma_s = ys_ratio * (s_in + s_out) / 2
        sq = tension(j)
        sd = (sigma_s * ((1 + mu / a) * math.log(r["lam"]) + 2 * a / 3)
              + sq * r["lam"] ** (-mu / a))
        s = area(r["d_out"])
        force = sd * s                         # Н
        # барабан тянет из волоки с усилием P, а противонатяжение следующего прохода ему помогает
        drum_force = force - tension(j + 1) * s
        out.append(dict(sig_out=s_out, sig_d=sd, sig_q=sq, sig_heat=sd - sq, gamma=s_out / sd,
                        P=force, power=drum_force * r["v"] / 1000))   # кВт
        prev = r["eps"]
    return out


def eps_from_reduction(red_pct):
    """Истинная деформация по обжатию в процентах: ε = −ln(1 − δ)."""
    return -math.log(1 - red_pct / 100)


def fit_n(sig0, sigf, red_ref, red_meas, sig_meas):
    """Показатель упрочнения n по одному замеру: прочность sig_meas после суммарного обжатия
    red_meas, %. Кривая σв = σв0 + (σв,ref − σв0)·(ε/ε_ref)ⁿ проходит через обе точки:
        n = ln((σзам − σв0) / (σв,ref − σв0)) / ln(εзам / ε_ref)."""
    from core.util import InputError
    if not 0 < red_meas < 100:
        raise InputError("Обжатие замера — от 0 до 100 %.")
    if abs(red_meas - red_ref) < 0.5:
        raise InputError("Замер должен быть при другом обжатии, чем опорная точка "
                         f"({red_ref:g} %): нужна вторая точка кривой.")
    if sig_meas <= sig0:
        raise InputError("Прочность по замеру должна быть выше прочности заготовки.")
    e_m, e_r = eps_from_reduction(red_meas), eps_from_reduction(red_ref)
    n = math.log((sig_meas - sig0) / (sigf - sig0)) / math.log(e_m / e_r)
    if not 0.05 <= n <= 1.5:
        raise InputError(f"По замеру выходит n = {n:.2f} — вне разумного диапазона 0,05–1,5. "
                         "Проверь замер и прочность заготовки и опорную точку.")
    return n
