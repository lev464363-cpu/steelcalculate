"""Проверка расчётов на известных примерах.
Запуск: открыть этот файл в IDLE и нажать F5 (или python -m unittest из папки программы)."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.util import num, fmt, area, g_per_m, InputError          # noqa: E402
from core.drawing import distribute, build_route, suggest_n, heading_reduction  # noqa: E402
from core.forces import route_forces, eps_from_reduction           # noqa: E402
from core.coating import copper_share, thickness_from_share        # noqa: E402
from core.data import GROUPS, REFERENCE, DENSITY_MAP, PACKAGES     # noqa: E402
from core.route_plan import plan_route, suggest_n_full, PARAM_KEYS  # noqa: E402
from core.cards import upsert_card, compare, default_name, save_cards, load_cards  # noqa: E402
from core.tolerance import tolerance, die_plan, check_measure, STANDARDS  # noqa: E402
from core.cost import (cost_breakdown, cost_for_route, ENERGY_BY_PASSPORT,  # noqa: E402
                       ENERGY_BY_ROUTE, COST_NUM_KEYS)


class TestUtil(unittest.TestCase):
    def test_num_accepts_comma(self):
        self.assertEqual(num("1,25"), 1.25)
        self.assertEqual(num(" 3.5 "), 3.5)
        with self.assertRaises(ValueError):
            num("")

    def test_fmt_uses_comma(self):
        self.assertEqual(fmt(1.23456, 2), "1,23")

    def test_mass_of_wire(self):
        # 1 м проволоки 1,2 мм из стали 7,85 г/см³ весит около 8,88 г
        self.assertAlmostEqual(g_per_m(7.85, 1.2), 8.878, places=3)
        self.assertAlmostEqual(area(2.0), math.pi, places=9)


class TestRoute(unittest.TestCase):
    def test_uniform_distribution(self):
        lams = distribute(21.0, 14, 1.0)
        self.assertTrue(all(abs(x - 21 ** (1 / 14)) < 1e-9 for x in lams))

    def test_product_and_ratio(self):
        total = (5.5 / 1.2) ** 2
        lams = distribute(total, 14, 1.15)
        self.assertAlmostEqual(math.prod(lams), total, places=6)
        self.assertAlmostEqual(lams[0] / lams[-1], 1.15, places=6)
        self.assertAlmostEqual(lams[0], 1.331, places=3)   # значение из пояснения пользователю

    def test_route_reaches_final_diameter(self):
        total, lams, rows, anneals = build_route(5.5, 1.2, 14, 1.15, 96, 1.35, 15, None)
        self.assertAlmostEqual(rows[-1]["d_out"], 1.2, places=9)
        self.assertEqual(anneals, 0)                        # 95,2 % < 96 %
        self.assertAlmostEqual(rows[-1]["v"], 15.0, places=9)

    def test_anneal_inserted_when_limit_exceeded(self):
        total, lams, rows, anneals = build_route(5.5, 1.2, 14, 1.15, 80, 1.35, 15, None)
        self.assertGreaterEqual(anneals, 1)
        for r in rows:
            self.assertLessEqual(r["red_cum"], 80 + 1e-6)

    def test_speeds_follow_volume_constancy(self):
        _, _, rows, _ = build_route(5.5, 1.2, 10, 1.1, 99, 1.6, 20, 500)
        for r in rows:
            self.assertAlmostEqual(r["v"] * area(r["d_out"]), 20 * area(1.2), places=6)
            self.assertAlmostEqual(r["rpm"], r["v"] * 60 / (math.pi * 0.5), places=6)

    def test_too_much_ratio_rejected(self):
        with self.assertRaises(InputError):
            build_route(1.3, 1.2, 10, 3.0, 99, 2.0, 10, None)

    def test_suggest_n(self):
        n = suggest_n(5.5, 1.2, 1.15, 1.35)
        self.assertLessEqual(max(distribute((5.5 / 1.2) ** 2, n, 1.15)), 1.35)
        self.assertGreater(max(distribute((5.5 / 1.2) ** 2, n - 1, 1.15)), 1.35)


class TestStages(unittest.TestCase):
    def test_each_stage_runs_at_finish_speed(self):
        from core.drawing import split_stages
        _, _, rows, anneals = build_route(5.5, 1.2, 14, 1.15, 80, 1.35, 15, None)
        stages = split_stages(rows)
        self.assertEqual(len(stages), anneals + 1)
        for st in stages:
            self.assertAlmostEqual(st[-1]["v"], 15, places=9)
            for r in st:
                self.assertAlmostEqual(r["v"] * area(r["d_out"]), 15 * area(st[-1]["d_out"]),
                                       places=6)

    def test_anneal_costs_more_than_single_chain(self):
        from core.cost import cost_breakdown
        p = dict(BASE, limit=80)
        res = plan_route(p)
        self.assertGreaterEqual(res["anneals"], 1)
        cost = {k: v for k, v in COST.items() if k in COST_NUM_KEYS}
        cost.update(energy_method=ENERGY_BY_PASSPORT, copper=False, full=False)
        staged = cost_for_route(cost, p, res)
        single = cost_breakdown(dict(cost, d=p["dk"], v=p["v"], rho=p["rho"], n_passes=res["n"],
                                     anneals=res["anneals"], p_draw=res["power"]))
        self.assertEqual(staged["stages"], res["anneals"] + 1)
        self.assertGreater(staged["conversion"], single["conversion"])

    def test_mill_checks_each_stage(self):
        from core.mills import check_mill, DRIVE_INDIVIDUAL
        p = dict(BASE, limit=80)
        res = plan_route(p)
        mill = dict(name="M", drive=DRIVE_INDIVIDUAL, drums=10, drum_d=600, v_max=20,
                    p_motor=0, eta=85)
        chk = check_mill(mill, res["rows"], res["forces"], p["v"])
        self.assertTrue(chk["fits"])                     # 14 проходов, но этапы короче 10
        self.assertTrue(all(x["drum"] <= 10 for x in chk["per"]))


class TestHeading(unittest.TestCase):
    def test_patent_values(self):
        # а.с. 1752466: от 2,4 % для 6,5 мм до 12,6 % для 34 мм
        lo, hi = heading_reduction(6.5)
        self.assertTrue(lo <= 2.4 <= hi)
        lo, hi = heading_reduction(34)
        self.assertTrue(lo <= 12.6 <= hi)
        self.assertIsNone(heading_reduction(5.0))


class TestForces(unittest.TestCase):
    def test_siebel_by_hand(self):
        # один проход λ = 1,3, α = 6°, μ = 0,05, σв 600 → 800 МПа
        row = dict(lam=1.3, eps=math.log(1.3), anneal=False, d_out=2.0, v=10.0)
        f = route_forces([row], 6, 0.05, 600, 800, 0.5)[0]
        a = math.radians(6)
        sigma_s = 0.85 * (600 + 800) / 2
        expected = sigma_s * ((1 + 0.05 / a) * math.log(1.3) + 2 * a / 3)
        self.assertAlmostEqual(f["sig_d"], expected, places=6)
        self.assertAlmostEqual(f["gamma"], 800 / expected, places=6)
        self.assertAlmostEqual(f["P"], expected * math.pi, places=6)   # площадь 2 мм = π мм²

    def test_final_strength_matches_input(self):
        _, _, rows, _ = build_route(5.5, 1.2, 14, 1.15, 96, 1.35, 15, None)
        forces = route_forces(rows, 6, 0.05, 560, 1050, 0.5)
        self.assertAlmostEqual(forces[-1]["sig_out"], 1050, places=6)
        self.assertTrue(all(2.0 < f["gamma"] < 4.5 for f in forces))   # как в версии 3.1

    def test_reference_point_independent_of_route(self):
        # кривая привязана к обжатию 60 %: один проход 17 % даёт прочность ниже опорной
        _, _, rows, _ = build_route(22, 20, 1, 1.0, 60, 1.25, 0.5, None)
        f = route_forces(rows, 6, 0.05, 600, 880, 0.5, eps_ref=eps_from_reduction(60))[0]
        self.assertTrue(600 < f["sig_out"] < 880)
        # а маршрут ровно до 60 % выходит на опорную прочность
        d1 = 22 * math.sqrt(0.4)
        _, _, rows, _ = build_route(22, d1, 4, 1.0, 99, 1.4, 0.5, None)
        f = route_forces(rows, 6, 0.05, 600, 880, 0.5, eps_ref=eps_from_reduction(60))
        self.assertAlmostEqual(f[-1]["sig_out"], 880, places=6)

    def test_more_friction_less_safety(self):
        _, _, rows, _ = build_route(5.5, 1.2, 14, 1.15, 96, 1.35, 15, None)
        g1 = min(f["gamma"] for f in route_forces(rows, 6, 0.05, 560, 1050, 0.5))
        g2 = min(f["gamma"] for f in route_forces(rows, 6, 0.10, 560, 1050, 0.5))
        self.assertLess(g2, g1)

    def test_back_tension(self):
        _, _, rows, _ = build_route(5.5, 1.2, 14, 1.15, 96, 1.35, 15, None)
        f0 = route_forces(rows, 6, 0.05, 560, 1050, 0.5)
        f1 = route_forces(rows, 6, 0.05, 560, 1050, 0.5, back=100)
        b = 0.05 / math.radians(6)
        self.assertAlmostEqual(f1[0]["sig_d"], f0[0]["sig_d"], places=9)   # с размотчика
        for r, a, c in zip(rows[1:], f0[1:], f1[1:]):
            self.assertAlmostEqual(c["sig_d"], a["sig_d"] + 100 * r["lam"] ** -b, places=9)
            self.assertLess(c["gamma"], a["gamma"])
            self.assertAlmostEqual(c["sig_heat"], c["sig_d"] - 100, places=9)
        # предыдущий барабан разгружен, суммарная мощность чуть меньше
        self.assertLess(f1[0]["power"], f0[0]["power"])
        self.assertAlmostEqual(f1[-1]["power"], f1[-1]["P"] * rows[-1]["v"] / 1000, places=9)
        self.assertLess(sum(f["power"] for f in f1), sum(f["power"] for f in f0))
        # после отжига — новый прогон с размотчика, противонатяжения нет
        _, _, rows, anneals = build_route(5.5, 1.2, 14, 1.15, 70, 1.35, 15, None)
        self.assertGreater(anneals, 0)
        f2 = route_forces(rows, 6, 0.05, 560, 1050, 0.5, back=100)
        self.assertTrue(all(f["sig_q"] == 0 for r, f in zip(rows, f2) if r["anneal"]))
        # нулевое противонатяжение и σт/σв по умолчанию — прежний расчёт
        res = plan_route(BASE)
        same = plan_route(dict(BASE, sq=0.0, ys=0.85))
        self.assertEqual(res["gamma_min"], same["gamma_min"])
        self.assertLess(plan_route(dict(BASE, sq=80))["t_max"], res["t_max"] + 1e-9)

    def test_strength_after_anneal(self):
        _, _, rows, anneals = build_route(5.5, 1.2, 14, 1.15, 70, 1.35, 15, None)
        self.assertGreater(anneals, 0)
        f0 = route_forces(rows, 6, 0.05, 560, 1050, 0.5)
        f1 = route_forces(rows, 6, 0.05, 560, 1050, 0.5, sig_ann=480)
        first = next(i for i, r in enumerate(rows) if r["anneal"])
        for i in range(first):                         # до отжига ничего не меняется
            self.assertAlmostEqual(f1[i]["sig_out"], f0[i]["sig_out"], places=9)
        for i in range(first, len(rows)):              # после — кривая ниже на 80 МПа
            self.assertAlmostEqual(f0[i]["sig_out"] - f1[i]["sig_out"], 80, places=9)

    def test_strength_requirement(self):
        res = plan_route(BASE)
        s = res["sig_end"]
        self.assertTrue(plan_route(dict(BASE, sig_min=s - 10, sig_max=s + 10))["strength_ok"])
        low = plan_route(dict(BASE, sig_min=s + 10))
        self.assertFalse(low["strength_ok"])
        self.assertTrue(any("не ниже" in w for w in low["warnings"]))
        # прочнее требования — программа сама ставит отжиг по прочности
        cut = plan_route(dict(BASE, sig_max=s - 10))
        self.assertTrue(cut["strength_ok"])
        self.assertGreater(cut["anneals"], res["anneals"])
        self.assertLessEqual(cut["sig_end"], s - 10 + 1e-9)
        self.assertTrue(any("по прочности" in r["notes"] for r in cut["rows"]))

    def test_strength_anneal_example(self):
        # 5,5 → 3,0 мм, требование 550–850 МПа: без отжига прочность намного выше
        p = dict(BASE, dk=3.0, n=6, limit=96, sig0=550, sigf=1050)
        free = plan_route(p)
        self.assertGreater(free["sig_end"], 850)
        r = plan_route(dict(p, sig_min=550, sig_max=850))
        self.assertTrue(r["strength_ok"])
        self.assertTrue(550 <= r["sig_end"] <= 850)
        self.assertEqual(r["anneals"], free["anneals"] + 1)
        # подбор числа проходов учитывает требование по прочности
        n = suggest_n_full(dict(p, sig_min=550, sig_max=850))
        self.assertTrue(plan_route(dict(p, n=n, sig_min=550, sig_max=850))["strength_ok"])

    def test_fit_n(self):
        from core.forces import fit_n
        # кривая с n = 0,4 через 95 %: точка при 60 % даёт обратно n = 0,4
        e60, e95 = eps_from_reduction(60), eps_from_reduction(95)
        s60 = 560 + (1050 - 560) * (e60 / e95) ** 0.4
        self.assertAlmostEqual(fit_n(560, 1050, 95, 60, s60), 0.4, places=9)
        for bad in ((560, 1050, 95, 95, 900), (560, 1050, 95, 60, 500)):
            with self.assertRaises(InputError):
                fit_n(*bad)


class TestCoating(unittest.TestCase):
    def test_copper_share(self):
        cu, st, share = copper_share(1.2, 0.0005, 7.85)
        self.assertAlmostEqual(share * 100, 0.1898, places=3)

    def test_reverse_is_inverse(self):
        t = thickness_from_share(1.2, 0.002, 7.85)
        self.assertAlmostEqual(copper_share(1.2, t, 7.85)[2], 0.002, places=9)


BASE = dict(d0=5.5, dk=1.2, n=14, ratio=1.15, lmax=1.35, v=15, drum=None, limit=96, alpha=6,
            mu=0.05, gmin=1.4, sig0=560, sigf=1050, nh=0.5, rho=7.85, redref=95)


class TestPlanAndCards(unittest.TestCase):
    def test_plan_matches_parts(self):
        res = plan_route(BASE, "Кремнемарганцовистая")
        self.assertEqual(res["n"], 14)
        self.assertEqual(len(res["rows"]), 14)
        self.assertAlmostEqual(res["productivity"], g_per_m(7.85, 1.2) * 15 * 3.6, places=6)
        self.assertEqual(res["warnings"], [])
        self.assertEqual(set(PARAM_KEYS), set(BASE) | {"t0", "tw", "cool", "cp", "vcool", "dcool", "lams", "ys", "sq",
                                                     "sig_ann", "sig_min", "sig_max"})

    def test_suggest_full_respects_gamma(self):
        p = dict(BASE, gmin=3.0)
        n = suggest_n_full(p)
        self.assertIsNotNone(n)
        self.assertGreaterEqual(plan_route(dict(p, n=n))["gamma_min"], 3.0)
        self.assertLess(plan_route(dict(p, n=n - 1))["gamma_min"], 3.0)

    def test_cards_roundtrip_and_replace(self):
        import tempfile
        cards = []
        self.assertFalse(upsert_card(cards, "A", "1К89М", "g", BASE))
        self.assertTrue(upsert_card(cards, "A", "1К89М", "g", dict(BASE, n=16)))
        self.assertEqual(len(cards), 1)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t.json")
            save_cards(cards, path)
            self.assertEqual(load_cards(path)[0]["params"]["n"], 16)
            self.assertEqual(load_cards(os.path.join(tmp, "none.json")), [])
        self.assertIn("1К89М", default_name("Группа (x)", BASE, "1К89М"))

    def test_damaged_user_file_is_kept(self):
        """Повреждённый файл не теряется: уходит в резервную копию, запись — атомарная."""
        import tempfile
        from core.storage import DamagedFile, load_list, save_list
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "stany.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('[{"name": "1К89М"} {"name": "без запятой"}]')
            with self.assertRaises(DamagedFile):
                load_list(path, quarantine=False)
            self.assertTrue(os.path.exists(path))          # только чтение — файл на месте
            with self.assertRaises(DamagedFile):
                load_list(path)
            self.assertFalse(os.path.exists(path))
            backups = [f for f in os.listdir(tmp) if "повреждён" in f]
            self.assertEqual(len(backups), 1)
            with open(os.path.join(tmp, backups[0]), encoding="utf-8") as fh:
                self.assertIn("без запятой", fh.read())
            self.assertEqual(load_list(path), [])
            save_list([{"name": "новый"}], path)
            self.assertEqual(load_list(path), [{"name": "новый"}])
            self.assertEqual(sorted(os.listdir(tmp)), sorted([backups[0], "stany.json"]))
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"name": "не список"}')
            with self.assertRaises(DamagedFile):
                load_list(path)

    def test_compare_marks_best(self):
        c1 = dict(name="14", mill="1К89М", group="g", params=BASE)
        c2 = dict(name="18", mill="1К89М", group="g", params=dict(BASE, n=18))
        r1, r2 = plan_route(c1["params"]), plan_route(c2["params"])
        table = {t: (texts, best) for t, texts, best in compare([c1, c2], [r1, r2])}
        self.assertEqual(table["Проходов"][1], 0)
        self.assertEqual(table["Мин. запас прочности"][1], 1)   # больше проходов — больше запас
        self.assertIsNone(table["Стан"][1])


class TestTolerance(unittest.TestCase):
    def test_custom_ntd(self):
        import tempfile
        from core import tolerance as tl
        rows = [dict(ntd="ТУ 1211-001", d=1.2, upper=0, lower=-0.05,
                     note="п. 3.2"),
                dict(ntd="ТУ 1211-001", d=1.0, upper=0.02, lower=-0.04, note="")]
        old = tl._custom
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "dopuski.json")
                saved = tl.save_custom(rows, path)
                self.assertEqual([r["d"] for r in saved], [1.0, 1.2])       # по диаметру
                with open(path, encoding="utf-8") as fh:
                    self.assertIn("п. 3.2", fh.read())
            self.assertIn("ТУ 1211-001", tl.all_standards())
            self.assertEqual(tl.tolerance("ТУ 1211-001", 1.2), (0.0, -0.05))
            self.assertEqual(tl.tolerance("ТУ 1211-001", 1.0), (0.02, -0.04))
            self.assertEqual(tl.custom_row("ТУ 1211-001", 1.2)["note"], "п. 3.2")
            with self.assertRaises(InputError):                          # только точный диаметр
                tl.tolerance("ТУ 1211-001", 1.1)
            self.assertEqual(tl.tolerance(STANDARDS[0], 1.2), (0.0, -0.09))  # встроенные — как были
            for bad in (dict(ntd="", d=1, upper=0, lower=-0.1),
                        dict(ntd="X", d=1, upper=-0.1, lower=0),
                        dict(ntd="X", d=0.05, upper=0, lower=-0.1)):
                with self.assertRaises(InputError):
                    tl.check_custom([bad])
            with self.assertRaises(InputError):                          # повтор диаметра
                tl.check_custom([rows[1], dict(rows[1], note="другая")])
        finally:
            tl._custom = old

    def test_gost2246(self):
        self.assertEqual(tolerance(STANDARDS[0], 1.2), (0.0, -0.09))
        self.assertEqual(tolerance(STANDARDS[0], 1.6), (0.0, -0.12))
        self.assertEqual(tolerance(STANDARDS[1], 4.0), (0.0, -0.12))
        self.assertAlmostEqual(tolerance(STANDARDS[2], 1.2)[1], -0.135)
        with self.assertRaises(InputError):
            tolerance(STANDARDS[0], 1.3)

    def test_iso286(self):
        self.assertAlmostEqual(tolerance("h11 (ISO 286), калиброванный круг", 20)[1], -0.130)
        self.assertAlmostEqual(tolerance("h9 (ISO 286), калиброванный круг", 3)[1], -0.025)
        self.assertAlmostEqual(tolerance("h9 (ISO 286), калиброванный круг", 3.01)[1], -0.030)

    def test_die_plan_and_measure(self):
        plan = die_plan(1.2, 0.0, -0.09, 25)
        self.assertAlmostEqual(plan["die_new"], 1.1325)
        self.assertAlmostEqual(plan["wear_allow"], 0.0675)
        self.assertAlmostEqual(plan["ovality"], 0.045)
        self.assertEqual(check_measure(1.2, 0, -0.09, 1.15), "ok")
        self.assertEqual(check_measure(1.2, 0, -0.09, 1.195), "near")
        self.assertEqual(check_measure(1.2, 0, -0.09, 1.205), "out")


# Ручной пример: Qт = 1000 кг/ч задаётся подбором скорости, Kи = 80 %, выход 100 %
D, RHO = 2.0, 7.85
V_1000 = 1000 / (g_per_m(RHO, D) * 3.6)
COST = dict(d=D, v=V_1000, rho=RHO, n_passes=10, anneals=1, p_draw=300,
            shifts=2, shift_h=12, days=250, ku_pct=80, yield_pct=100,
            energy_method=ENERGY_BY_PASSPORT, p_inst=632, load_pct=50, eta_pct=85, idle_pct=10,
            tariff=10, workers=2, rate=500, tax_pct=30, overhead_pct=100,
            die_price=8000, die_life_t=40, lube_kg_t=2, lube_price=200, other_t=300,
            anneal_cost_t=2500, mill_price=48_000_000, mill_years=10, repair_pct=5,
            copper=False, full=False)


class TestCost(unittest.TestCase):
    def test_hand_example(self):
        r = cost_breakdown(COST)
        items = dict(r["items"])
        self.assertAlmostEqual(r["q_t"], 1000, places=6)
        self.assertAlmostEqual(r["q_f"], 800, places=6)
        # энергия: (632·0,5·0,8 + 63,2·0,2) / 800 кг · 1000 = 331,8 кВт·ч/т
        self.assertAlmostEqual(r["kwh_t"], (316 * 0.8 + 63.2 * 0.2) / 800 * 1000, places=6)
        self.assertAlmostEqual(items["Электроэнергия"], r["kwh_t"] * 10, places=6)
        # труд: 2·500·1,3 = 1300 руб/ч / 0,8 т/ч = 1625 руб/т
        self.assertAlmostEqual(items["Оплата труда со страховыми взносами"], 1625, places=6)
        self.assertAlmostEqual(items["Цеховые накладные"], 1625, places=6)
        self.assertAlmostEqual(items["Фильеры"], 10 * 8000 / 40, places=6)
        self.assertAlmostEqual(items["Смазка"], 400, places=6)
        self.assertAlmostEqual(items["Отжиги"], 2500, places=6)
        # выпуск: 800 кг/ч · 6000 ч = 4800 т/год; амортизация 4,8 млн / 4800 т = 1000 руб/т
        self.assertAlmostEqual(r["out_year_t"], 4800, places=6)
        self.assertAlmostEqual(items["Амортизация стана"], 1000, places=6)
        self.assertAlmostEqual(items["Ремонт и обслуживание стана"], 500, places=6)
        self.assertAlmostEqual(r["conversion"], sum(items.values()), places=6)

    def test_yield_spreads_costs(self):
        a = cost_breakdown(COST)["conversion"]
        b = cost_breakdown(dict(COST, yield_pct=95))["conversion"]
        self.assertAlmostEqual(b, a / 0.95, places=6)

    def test_downtime_raises_cost(self):
        a = cost_breakdown(COST)["conversion"]
        b = cost_breakdown(dict(COST, ku_pct=60))["conversion"]
        self.assertGreater(b, a)

    def test_energy_by_route(self):
        r = cost_breakdown(dict(COST, energy_method=ENERGY_BY_ROUTE))
        self.assertAlmostEqual(r["p_work"], 300 / 0.85 + 63.2, places=6)
        self.assertEqual(r["warnings"], [])
        r = cost_breakdown(dict(COST, energy_method=ENERGY_BY_ROUTE, p_draw=600))
        self.assertTrue(r["warnings"])

    def test_copper_and_full(self):
        r = cost_breakdown(dict(COST, copper=True, cu_um=0.5, cu_loss_pct=10, cu_price=1000,
                                full=True, rod_price=80000, scrap_price=20000, pack_price=150,
                                pack_kg=15, yield_pct=98))
        share = copper_share(2.0, 0.0005, 7.85)[2]
        self.assertAlmostEqual(r["cu_kg_t"], share * 1000 / 0.9, places=6)
        full = dict(r["full_items"])
        self.assertAlmostEqual(full["Катанка (заготовка)"], 80000 / 0.98, places=6)
        self.assertAlmostEqual(full["Возврат отходов"], -20000 * (1 / 0.98 - 1), places=6)
        self.assertAlmostEqual(full["Упаковка"], 10000, places=6)
        self.assertAlmostEqual(r["full"], r["conversion"] + sum(full.values()), places=6)

    def test_vat_on_rod(self):
        base = dict(COST, full=True, rod_price=80000, scrap_price=20000, pack_price=150,
                    pack_kg=80, yield_pct=98)
        r = cost_breakdown(dict(base, rod_vat_pct=22))
        full = dict(r["full_items"])
        self.assertAlmostEqual(full["Катанка (заготовка), с НДС 22 %"], 80000 * 1.22 / 0.98,
                               places=6)
        self.assertAlmostEqual(full["Упаковка"], 150 / 80 * 1000, places=6)   # моток 80 кг
        old = dict(cost_breakdown(base)["full_items"])                       # старые техкарты
        self.assertAlmostEqual(old["Катанка (заготовка)"], 80000 / 0.98, places=6)
        self.assertIn(("Моток", 80.0), PACKAGES)


class TestGrades(unittest.TestCase):
    ROW = dict(name="Св-08Г2С-О, свой", rho=7.85, limit=90, lam_max=1.3, sig0=580, sigf=1100,
               red_ref=95, n=0.45, cp=470, note="по сертификату")

    def test_grade_becomes_group(self):
        import tempfile
        from core import grades
        try:
            with tempfile.TemporaryDirectory() as tmp:
                saved = grades.save_grades([self.ROW], os.path.join(tmp, "marki.json"))
                self.assertEqual(saved[0]["sig0"], 580)
                g = GROUPS[self.ROW["name"]]
                self.assertEqual(g["family"], grades.FAMILY)
                self.assertEqual(g["hardening"]["n"], 0.45)
                self.assertEqual(DENSITY_MAP[self.ROW["name"]], 7.85)
                self.assertEqual(list(GROUPS)[-1], self.ROW["name"])        # в конце списка
                p = dict(BASE, sig0=580, sigf=1100, nh=0.45, redref=95)
                self.assertEqual(plan_route(p, self.ROW["name"])["n"], 14)
                # пересохранение без марки — группа пропадает, встроенные целы
                n_before = len(GROUPS)
                grades.save_grades([], os.path.join(tmp, "marki.json"))
                self.assertNotIn(self.ROW["name"], GROUPS)
                self.assertEqual(len(GROUPS), n_before - 1)
        finally:
            grades.apply_grades([])

    def test_bad_grades(self):
        from core.grades import check_grades
        builtin = next(iter(GROUPS))
        for bad in (dict(self.ROW, name=""), dict(self.ROW, name=builtin),
                    dict(self.ROW, sigf=500), dict(self.ROW, limit=150),
                    dict(self.ROW, rho="x")):
            with self.assertRaises(InputError):
                check_grades([bad])
        with self.assertRaises(InputError):                      # повтор названия
            check_grades([self.ROW, dict(self.ROW, name=self.ROW["name"].upper())])


class TestCostInCards(unittest.TestCase):
    COST = {k: v for k, v in COST.items() if k in COST_NUM_KEYS}

    def setUp(self):
        self.cost = dict(self.COST, energy_method=ENERGY_BY_PASSPORT, copper=False, full=False)

    def test_cost_for_route_uses_route(self):
        res = plan_route(BASE)
        r = cost_for_route(self.cost, BASE, res)
        direct = cost_breakdown(dict(self.cost, d=1.2, v=15, rho=7.85, n_passes=14,
                                     anneals=res["anneals"], p_draw=res["power"]))
        self.assertAlmostEqual(r["conversion"], direct["conversion"], places=6)

    def test_card_keeps_cost_and_compare(self):
        cards = []
        upsert_card(cards, "A", "1К89М", "g", BASE, cost=self.cost)
        upsert_card(cards, "B", "1К89М", "g", dict(BASE, v=20), cost=self.cost)
        upsert_card(cards, "C", "1К89М", "g", BASE)          # без себестоимости
        self.assertIsNone(cards[2]["cost"])
        res = []
        for c in cards:
            r = plan_route(c["params"])
            r["cost"] = cost_for_route(c["cost"], c["params"], r) if c["cost"] else None
            res.append(r)
        table = {t: (texts, best) for t, texts, best in compare(cards, res)}
        texts, best = table["Передел, руб/т"]
        self.assertEqual(texts[2], "—")
        self.assertEqual(best, 1)          # быстрее стан — дешевле передел
        self.assertEqual(table["Полная себестоимость, руб/т"][0], ["—", "—", "—"])


class TestThermalAndMill(unittest.TestCase):
    def test_heating_formula(self):
        from core.thermal import wire_temperatures
        rows = [dict(i=1, anneal=False), dict(i=2, anneal=True)]
        forces = [dict(sig_d=400.0), dict(sig_d=400.0)]
        t = wire_temperatures(rows, forces, 7.85, 470, 20, 25, 50)
        dt = 0.9 * 400e6 / (470 * 7850)            # ≈ 97,6 °C
        self.assertAlmostEqual(t[0]["dT"], dt, places=6)
        self.assertAlmostEqual(t[0]["t_drum"], 25 + (20 + dt - 25) * 0.5, places=6)
        self.assertAlmostEqual(t[1]["t_in"], 20, places=6)   # после отжига — холодная

    def test_calibration_is_inverse(self):
        from core.thermal import wire_temperatures, calibrate_cooling
        res = plan_route(BASE)
        t = wire_temperatures(res["rows"], res["forces"], 7.85, 470, 20, 25, 42.0)
        cool = calibrate_cooling(res["rows"], res["forces"], 7.85, 470, 20, 25, 10,
                                 t[9]["t_drum"])
        self.assertAlmostEqual(cool, 42.0, places=4)
        self.assertIsNone(calibrate_cooling(res["rows"], res["forces"], 7.85, 470, 20, 25,
                                            10, 5000))

    def test_speed_and_diameter_cooling(self):
        from core.thermal import remaining_share
        self.assertAlmostEqual(remaining_share(50, None, 10, 1, 2), 0.5)      # без опорной скорости
        self.assertAlmostEqual(remaining_share(50, 15, 15, 1.2, 1.2), 0.5)    # в опорной точке
        self.assertAlmostEqual(remaining_share(50, 15, 7.5, 1.2, 1.2), 0.25)  # вдвое медленнее
        self.assertGreater(remaining_share(50, 15, 15, 1.2, 2.4), 0.5)        # толще — остывает хуже
        slow = plan_route(dict(BASE, v=8, vcool=15))["t_max"]
        fast = plan_route(dict(BASE, v=25, vcool=15))["t_max"]
        self.assertLess(slow, fast)

    def test_more_cooling_colder(self):
        hot = plan_route(dict(BASE, cool=30))["t_max"]
        cold = plan_route(dict(BASE, cool=70))["t_max"]
        self.assertLess(cold, hot)

    def test_old_cards_get_defaults(self):
        self.assertIn("t_max", plan_route(BASE))       # без тепловых ключей тоже считается

    def test_mill_individual_and_too_short(self):
        from core.mills import check_mill, DRIVE_INDIVIDUAL
        res = plan_route(BASE)
        mill = dict(name="M", drive=DRIVE_INDIVIDUAL, drums=16, drum_d=600, v_max=20,
                    p_motor=10, eta=85)
        chk = check_mill(mill, res["rows"], res["forces"], 15)
        self.assertEqual(chk["per"][-1]["drum"], 16)       # последний проход — чистовой барабан
        self.assertEqual(chk["per"][0]["drum"], 3)
        f0 = res["forces"][0]
        self.assertAlmostEqual(chk["per"][0]["load"], f0["power"] / 0.85 / 10 * 100, places=6)
        short = check_mill(dict(mill, drums=10), res["rows"], res["forces"], 15)
        self.assertFalse(short["fits"])

    def test_mill_common_drive_slip(self):
        from core.mills import check_mill, DRIVE_COMMON
        p = dict(BASE, n=4, d0=2.0, dk=1.2, ratio=1.0, lmax=1.5)
        res = plan_route(p)
        lam = res["lams"][0]
        # кинематическая вытяжка чуть меньше вытяжки в волоке — барабан быстрее проволоки
        mill = dict(name="C", drive=DRIVE_COMMON, drums=4, drum_d=500, v_max=20, p_motor=0,
                    eta=85, kin=[lam * 0.97] * 3)
        chk = check_mill(mill, res["rows"], res["forces"], p["v"])
        self.assertAlmostEqual(chk["per"][-1]["slip"], 0.0, places=6)
        self.assertGreater(chk["per"][0]["slip"], 0)
        # кинематическая больше вытяжки в волоке — проволока обгоняет барабан
        bad = check_mill(dict(mill, kin=[lam * 1.03] * 3), res["rows"], res["forces"], p["v"])
        self.assertTrue(any("обгоняет" in w for w in bad["warnings"]))


class TestAnalytics(unittest.TestCase):
    def test_price_structure(self):
        from core.analytics import price_structure
        r = price_structure(155, 53300, 20000, 12, 97, 22)
        parts = {n: v for n, v, _ in r["parts"]}
        self.assertAlmostEqual(r["wire"], 155 / 1.22, places=6)
        self.assertAlmostEqual(parts["Катанка"], 53300 / 1.22 / 1000 / 0.97, places=6)
        self.assertAlmostEqual(sum(s for _, _, s in r["parts"]), 100, places=6)

    def test_articles_well_formed(self):
        from core.data import ANALYTICS, ANALYTICS_SIGN
        self.assertEqual(ANALYTICS_SIGN, "Так думает Claude")
        self.assertGreaterEqual(len(ANALYTICS), 5)
        for a in ANALYTICS:
            self.assertTrue(a["conclusion"], a["title"])
            for s in a["sections"]:
                self.assertTrue((s.get("points") or s.get("table")) and s.get("sources"),
                                s["head"])

    def test_claims_match_program(self):
        # «0,8 мм в 2,25 раза меньше кг/ч, чем 1,2 мм при той же скорости»
        self.assertAlmostEqual(g_per_m(7.85, 1.2) / g_per_m(7.85, 0.8), 2.25, places=6)


class TestOptimizer(unittest.TestCase):
    G = "Кремнемарганцовистая (Св-08ГС, Св-08Г2С)"

    def test_best_route_respects_limits(self):
        from core.optimize import optimize, DEFAULT_LIMITS as L
        b = optimize(self.G, 7.85, 1.2)
        self.assertIsNotNone(b)
        self.assertGreaterEqual(b["gamma_min"], L["gmin"])
        self.assertLessEqual(b["t_max"], L["t_max"] + 1e-6)
        self.assertLessEqual(b["t_wind"], L["t_wind"] + 1e-6)
        self.assertLessEqual(b["v"], L["v_max"] + 1e-9)
        self.assertTrue(all(L["v_min"] - 1e-9 <= v <= L["v_max"] + 1e-9 for v in b["v_stages"]))
        self.assertGreaterEqual(b["lamn"], L["lam_min_last"] - 1e-9)   # чистовой — от 1,05

    def test_mill_limits_route(self):
        from core.optimize import optimize
        from core.mills import DRIVE_INDIVIDUAL
        mill = dict(name="M", drive=DRIVE_INDIVIDUAL, drums=10, drum_d=560, v_max=20,
                    p_motor=52, eta=85, kin=None)
        b = optimize(self.G, 7.85, 1.2, mill=mill)
        self.assertIsNotNone(b)
        r = plan_route(b["params"], self.G, mill)
        self.assertTrue(r["mill"]["fits"])
        self.assertLessEqual(r["mill"]["max_load"], 100 + 1e-6)        # ни один барабан не перегружен
        free = optimize(self.G, 7.85, 1.2)
        self.assertGreaterEqual(b["conversion"], free["conversion"] - 1e-6)
        # на стане из 4 барабанов этапы короче — нужны отжиги или маршрута нет
        short = optimize(self.G, 7.85, 1.2, mill=dict(mill, drums=4, p_motor=None))
        if short is not None:
            r = plan_route(short["params"], self.G, dict(mill, drums=4, p_motor=None))
            self.assertTrue(r["mill"]["fits"])

    def test_book_batch_and_actual_life(self):
        from core.dies import actual_life, book_batch
        j = [dict(id="1", type="ВК6", used=10.0, status="в работе"),
             dict(id="2", type="ВК6", used=30.0, status="снята"),
             dict(id="3", type="ПКА", used=50.0, status="снята")]
        self.assertEqual(book_batch(j, ["1", "2", "9"], 2.5, "партия 7"), ["2", "9"])
        self.assertAlmostEqual(j[0]["used"], 12.5)
        self.assertEqual(j[0]["log"][0]["t"], 2.5)
        self.assertEqual(j[1]["used"], 30.0)                          # снятая не меняется
        self.assertEqual(actual_life(j), (40.0, 2))
        self.assertEqual(actual_life(j, "ВК6"), (30.0, 1))
        self.assertIsNone(actual_life(j[:1]))

    def test_too_slow_is_infeasible(self):
        from core.optimize import optimize
        # на стане без запаса мощности этап не тянется даже на 5 м/с — маршрута нет
        self.assertIsNone(optimize(self.G, 7.85, 1.2, cost=dict(p_inst=5)))
        self.assertIsNotNone(optimize(self.G, 7.85, 1.2, cost=dict(p_inst=5),
                                      limits=dict(v_min=0.2)))

    def test_better_cooling_is_cheaper(self):
        from core.optimize import optimize
        base = optimize(self.G, 7.85, 1.2)
        cold = optimize(self.G, 7.85, 1.2, thermal=dict(cool=70))
        self.assertLess(cold["conversion"], base["conversion"])

    def test_no_anneal_is_cheaper(self):
        from core.optimize import optimize
        a = optimize(self.G, 7.85, 1.0)
        b = optimize(self.G, 7.85, 1.0, overrides=dict(limit=98))
        self.assertGreater(a["anneals"], b["anneals"])
        self.assertLess(b["conversion"], a["conversion"])


class TestDies(unittest.TestCase):
    def test_delta_matches_source(self):
        from core.dies import delta
        lam = 1 / (1 - 0.19)                         # пример Wright: r = 0,19, полуугол 6°
        self.assertAlmostEqual(delta(math.radians(6), lam), 2.0, delta=0.02)

    def test_alpha_opt_is_minimum_of_siebel(self):
        from core.dies import alpha_opt
        a = alpha_opt(0.05, 1.25)
        row = dict(lam=1.25, eps=math.log(1.25), anneal=False, d_out=1.0, v=1.0)

        def sd(deg):
            return route_forces([row], deg, 0.05, 500, 700, 0.5)[0]["sig_d"]
        deg = math.degrees(a)
        self.assertLess(sd(deg), sd(deg - 1))
        self.assertLess(sd(deg), sd(deg + 1))

    def test_recommended_follows_practice(self):
        from core.dies import recommend_pass, plan_dies, angle_range
        G = "Кремнемарганцовистая"
        # основные проходы 12–14°, чистовой и высокоуглеродистая 10–12°, тонкая ~10°
        self.assertEqual(angle_range(G, 2.0, False), (12, 14))
        self.assertEqual(angle_range(G, 1.2, True), (10, 12))
        self.assertEqual(angle_range("Высокоуглеродистая пружинная", 2.0, False), (10, 12))
        self.assertEqual(angle_range(G, 0.8, True), (10, 10))
        for lam, final in ((1.10, True), (1.2, False), (1.3, False)):
            r = recommend_pass(G, 1.2, lam, 0.05, False, final)
            lo, hi = r["range"]
            self.assertTrue(lo <= r["two_std"] <= hi)
        # лёгкий чистовой проход: Δ от 3 до 4 — мягкое предупреждение, выше 4 — риск
        plan = plan_dies([dict(i=1, d_out=1.2, lam=1.10)], G, 0.05)
        self.assertIn("параметр очага деформации > 3", plan[0]["notes"])
        plan = plan_dies([dict(i=1, d_out=1.2, lam=1.06)], G, 0.05)
        self.assertIn("риск", plan[0]["notes"])

    def test_materials_and_journal(self):
        from core.dies import material, plan_dies
        G = "Кремнемарганцовистая (Св-08ГС, Св-08Г2С)"
        self.assertIn("ПКА", material(G, 1.2, True, True))
        self.assertIn("ВК6", material(G, 4.0, False, False))
        self.assertIn("ВК8", material(G, 8.0, False, False))
        self.assertIn("ПКА", material("Медь М1", 1.0, True, False))
        res = plan_route(BASE)
        journal = [dict(id="A", d=1.205, status="в работе", used=1, limit=50),
                   dict(id="B", d=1.2, status="снята", used=1, limit=50)]
        plan = plan_dies(res["rows"], G, 0.05, 1.6, journal, 1.0)
        self.assertEqual(plan[-1]["stock"], "A")          # снятая фильера не подбирается
        self.assertEqual(sum(1 for x in plan if x["stock"]), 1)


class TestAuditFixes(unittest.TestCase):
    """Правки по итогам аудита (решения технолога)."""

    def test_limits(self):
        self.assertEqual(GROUPS["Низкоуглеродистая (Св-08А, Св-08АА, Св-08ГА, Св-10ГА)"]["limit"], 92)
        self.assertEqual(GROUPS["Кремнемарганцовистая (Св-08ГС, Св-08Г2С)"]["limit"], 92)
        st = GROUPS["Нержавеющая аустенитная (Св-04Х19Н9, Св-04Х19Н11М3 и др.)"]
        self.assertEqual(st["limit"], 75)
        self.assertEqual((st["hardening"]["sigf"], st["hardening"]["red_ref"]), (1550, 77))
        for name, g in GROUPS.items():
            if name.startswith("Порошковая"):
                self.assertLessEqual(g["limit"], 75)

    def test_copper_rules(self):
        from core.coating import copper_note
        self.assertEqual(copper_note(0.2), "")
        self.assertIn("ТУ", copper_note(0.35))
        self.assertIn("AWS", copper_note(0.6))

    def test_tolerance_tables(self):
        from core.tolerance import tolerance, curvature, ovality_share
        self.assertEqual(tolerance("ГОСТ 7417-75, h9", 3.0), (0.0, -0.025))       # табл. 1
        self.assertEqual(tolerance("ГОСТ 7417-75, h12", 3.1), (0.0, -0.12))
        self.assertEqual(tolerance("GB/T 14957-1994, обычная точность", 2.0), (0.0, -0.10))
        self.assertEqual(tolerance("GB/T 14957-1994, повышенная точность", 3.5), (0.0, -0.08))
        self.assertAlmostEqual(tolerance("GB/T 905-1994, h8", 20)[1], -0.033)
        self.assertEqual(tolerance("h11 (ISO 286), калиброванный круг", 20), (0.0, -0.13))
        self.assertEqual(curvature("ГОСТ 7417-75, h10", 20), 2.0)
        self.assertEqual(ovality_share("ГОСТ 7417-75, h11")[0], 1.0)
        with self.assertRaises(InputError):
            tolerance("ГОСТ 7417-75, h9", 120)


class TestDraftEditor(unittest.TestCase):
    """Ручная раскладка обжатий: перетаскивание прохода не меняет готовый диаметр."""

    def test_redistribute_keeps_total(self):
        from core.drawing import redistribute
        total = (5.5 / 1.2) ** 2
        lams = distribute(total, 14, 1.15)
        new, pinned = redistribute(lams, 3, 1.33, set(), total)
        self.assertAlmostEqual(math.prod(new), total, places=9)
        self.assertAlmostEqual(new[3], 1.33, places=9)
        self.assertEqual(pinned, {3})
        # второй проход: первый закреплён и не меняется
        new2, pinned2 = redistribute(new, 7, 1.15, pinned, total)
        self.assertAlmostEqual(new2[3], 1.33, places=9)
        self.assertAlmostEqual(math.prod(new2), total, places=9)
        self.assertEqual(pinned2, {3, 7})

    def test_redistribute_limits(self):
        from core.drawing import redistribute, LAM_FLOOR, LAM_CEIL
        total = (2.0 / 1.6) ** 2
        lams = distribute(total, 3, 1.0)
        new, _ = redistribute(lams, 0, 5.0, set(), total)        # тянем слишком сильно
        self.assertLessEqual(new[0], LAM_CEIL + 1e-9)
        self.assertTrue(all(x >= LAM_FLOOR - 1e-9 for x in new))
        self.assertAlmostEqual(math.prod(new), total, places=9)
        self.assertIsNone(redistribute(lams, 0, 1.2, {1, 2}, total))   # двигать нечего

    def test_manual_route(self):
        from core.drawing import redistribute
        total = (5.5 / 1.2) ** 2
        auto = plan_route(BASE)
        new, _ = redistribute(auto["lams"], 0, 1.30, set(), total)
        res = plan_route(dict(BASE, lams=new))
        self.assertAlmostEqual(res["lams"][0], 1.30, places=9)
        self.assertAlmostEqual(res["rows"][-1]["d_out"], 1.2, places=9)
        # чужая раскладка (другое число проходов) игнорируется — берётся автоматическая
        res2 = plan_route(dict(BASE, n=15, lams=new))
        self.assertEqual(len(res2["rows"]), 15)


class TestFormulas(unittest.TestCase):
    def test_all_sections_present(self):
        from core.formulas import SECTIONS
        titles = [t for t, _ in SECTIONS]
        for must in ("Маршрут волочения", "Усилие волочения и запас прочности", "Омеднение",
                     "Допуски и волоки", "Себестоимость передела (руб/т годной)"):
            self.assertIn(must, titles)
        for _, items in SECTIONS:
            self.assertTrue(items)
            for name, formula, note in items:
                self.assertTrue(name and (formula or note))

    def test_documented_constants_match_code(self):
        # константы, упомянутые в формулах, совпадают с расчётом
        from core.coating import RHO_CU
        self.assertEqual(RHO_CU, 8.94)
        lo, hi = heading_reduction(10)
        self.assertAlmostEqual(lo, 3.6)
        self.assertAlmostEqual(hi, 3.8)
        row = dict(lam=1.2, eps=math.log(1.2), anneal=False, d_out=1.0, v=1.0)
        f = route_forces([row], 6, 0.0, 500, 600, 0.5)[0]
        a = math.radians(6)
        self.assertAlmostEqual(f["sig_d"], 0.85 * 550 * (math.log(1.2) + 2 * a / 3), places=6)


class TestStandards(unittest.TestCase):
    def test_blocks_well_formed(self):
        from core.data import STANDARDS
        self.assertGreaterEqual(len(STANDARDS), 4)
        for b in STANDARDS:
            for key in ("title", "ru", "cn", "rows", "conclusion", "sources"):
                self.assertIn(key, b, b.get("title"))
            for row in b["rows"]:
                self.assertEqual(len(row), 3, row)
            for g in b.get("grades", []):
                self.assertEqual(len(g), 4, g)

    def test_consistent_with_program_data(self):
        # допуск ГОСТ 2246 в сравнении совпадает с тем, что считает раздел «Допуски»
        from core.data import STANDARDS
        self.assertEqual(tolerance("ГОСТ 2246-70, для сварки (наплавки)", 1.2), (0.0, -0.09))
        text = " ".join(" ".join(r) for r in STANDARDS[0]["rows"])
        self.assertIn("−0,09", text)
        self.assertIn("−0,12", text)
        # h11 для 20 мм = 0,130 — та же таблица ISO 286, что и в GB/T 905
        self.assertAlmostEqual(tolerance("h11 (ISO 286), калиброванный круг", 20)[1], -0.130)


class TestData(unittest.TestCase):
    def test_groups_complete(self):
        self.assertGreaterEqual(len(GROUPS), 6)
        for name, g in GROUPS.items():
            for key in ("limit", "lam_max", "rho", "src", "hardening"):
                self.assertIn(key, g, name)
            h = g["hardening"]
            self.assertLess(h["sig0"], h["sigf"], name)
            self.assertTrue(0 < g["limit"] < 100, name)
            self.assertGreater(g["lam_max"], 1, name)

    def test_materials_unique_and_sane(self):
        names = [it["name"] for items in REFERENCE.values() for it in items]
        self.assertEqual(len(names), len(set(names)), "повторяющиеся марки")
        for items in REFERENCE.values():
            for it in items:
                for key in ("name", "analog", "rho", "comp", "use", "std"):
                    self.assertIn(key, it, it.get("name"))
                self.assertTrue(1.5 < it["rho"] < 22, it["name"])
        self.assertEqual(DENSITY_MAP["БрБ2"], 8.25)

    def test_structural_groups(self):
        fams = {g["family"] for g in GROUPS.values()}
        self.assertEqual(len(fams), 3)
        self.assertIn("Медь М1", GROUPS)
        self.assertIn("Среднеуглеродистая (35, 45)", GROUPS)
        for g in GROUPS.values():
            self.assertIn("prep", g)
        # каждую группу можно рассчитать: маршрут 10 → 8 мм за 2 прохода
        for name, g in GROUPS.items():
            h = g["hardening"]
            _, _, rows, _ = build_route(10, 8, 2, 1.05, g["limit"], g["lam_max"], 1, None)
            forces = route_forces(rows, 6, 0.05, h["sig0"], h["sigf"], h["n"],
                                  eps_ref=eps_from_reduction(h["red_ref"]))
            self.assertTrue(all(f["gamma"] > 1 for f in forces), name)
            self.assertTrue(0 < h["red_ref"] < 100, name)

    def test_packages(self):
        self.assertTrue(all(kg > 0 for _, kg in PACKAGES))


if __name__ == "__main__":
    unittest.main(verbosity=2)
