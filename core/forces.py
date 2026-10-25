"""Усилие волочения, запас прочности и мощность по проходам."""
import math

from core.util import area


def route_forces(rows, alpha_deg, mu, sig0, sigf, n_h, ys_ratio=0.85, eps_ref=None):
    """Усилие по формуле Зибеля: σвол = σs·[(1 + μ/α)·ln λ + 2α/3],
    упрочнение σв(ε) = σв0 + K·ε^n, кривая проходит через σв_ref при ε_ref,
    σs — средний предел текучести в проходе (принят 0,85·σв), запас γ = σв после / σвол."""
    a = math.radians(alpha_deg)
    # sigf — прочность при деформации eps_ref; без eps_ref — в конце этого маршрута
    eps_end = eps_ref if eps_ref else rows[-1]["eps"]
    k = (sigf - sig0) / (eps_end ** n_h) if eps_end > 0 else 0.0

    def sig(e):
        return sig0 + k * (max(e, 0.0) ** n_h)

    out, prev = [], 0.0
    for r in rows:
        e_in = 0.0 if r["anneal"] else prev
        s_in, s_out = sig(e_in), sig(r["eps"])
        sigma_s = ys_ratio * (s_in + s_out) / 2
        sd = sigma_s * ((1 + mu / a) * math.log(r["lam"]) + 2 * a / 3)
        force = sd * area(r["d_out"])          # Н
        out.append(dict(sig_out=s_out, sig_d=sd, gamma=s_out / sd, P=force,
                        power=force * r["v"] / 1000))   # кВт
        prev = r["eps"]
    return out


def eps_from_reduction(red_pct):
    """Истинная деформация по обжатию в процентах: ε = −ln(1 − δ)."""
    return -math.log(1 - red_pct / 100)
