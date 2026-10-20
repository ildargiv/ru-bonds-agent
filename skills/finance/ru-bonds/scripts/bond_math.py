"""Облигационная математика: YTM, дюрация Маколея/модифицированная, выпуклость, PV01,
сценарный анализ цены и total return. Можно импортировать или вызывать из CLI.

CLI пример (поток платежей вручную):
  python bond_math.py --price 98.5 --nkd 12.3 --face 1000 \
      --flows 2026-12-01:40.5 2027-06-01:40.5 2027-12-01:1040.5
"""
import argparse
import datetime as dt
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _t(d0, d1):
    return (d1 - d0).days / 365.0


def pv(flows, y, d0):
    """flows: [(date, amount)], y — эффективная годовая доходность (доля). Конвенция MOEX: (1+y)^t."""
    return sum(a / (1 + y) ** _t(d0, d) for d, a in flows if d > d0)


def ytm(dirty, flows, d0, lo=-0.5, hi=3.0):
    """Эффективная доходность к погашению/оферте по грязной цене (в деньгах)."""
    for _ in range(200):
        mid = (lo + hi) / 2
        if pv(flows, mid, d0) > dirty:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def duration(flows, y, d0):
    p = pv(flows, y, d0)
    mac = sum(_t(d0, d) * a / (1 + y) ** _t(d0, d) for d, a in flows if d > d0) / p
    mod = mac / (1 + y)
    conv = sum(_t(d0, d) * (_t(d0, d) + 1) * a / (1 + y) ** (_t(d0, d) + 2)
               for d, a in flows if d > d0) / p
    return {"macaulay_years": mac, "modified": mod, "convexity": conv,
            "pv01_per_1000": p * mod * 0.0001}


def price_change(mod, conv, dy):
    """Относительное изменение цены при сдвиге доходности dy (доля, напр. 0.01 = +100 б.п.)."""
    return -mod * dy + 0.5 * conv * dy ** 2


def scenarios(dirty, flows, d0, y0, shifts_bp=(-300, -200, -100, 0, 100, 200, 300), horizon_days=365,
              reinvest=None):
    """Total return за горизонт при параллельном сдвиге доходности.
    reinvest — ставка реинвестирования купонов (доля), по умолчанию = y0."""
    reinvest = y0 if reinvest is None else reinvest
    h = d0 + dt.timedelta(days=horizon_days)
    res = []
    for bp in shifts_bp:
        y = y0 + bp / 10000
        received = sum(a * (1 + reinvest) ** _t(d, h) for d, a in flows if d0 < d <= h)
        remaining = [(d, a) for d, a in flows if d > h]
        end_val = pv(remaining, y, h) if remaining else 0.0
        tr = (received + end_val) / dirty - 1
        res.append({"shift_bp": bp, "total_return_%": round(tr * 100, 2),
                    "annualized_%": round(((1 + tr) ** (365 / horizon_days) - 1) * 100, 2)})
    return res


def after_tax_yield(dirty, flows, d0, buy_clean_price, face, tax=0.13):
    """Грубая оценка доходности после НДФЛ: налог с купонов и с положительной разницы
    (номинал - цена покупки) при погашении. Ставка НДФЛ: 13% / 15% (свыше 2.4 млн ₽) и выше
    по прогрессивной шкале — уточняйте актуальные ставки и льготы (ИИС, ЛДВ не применяется к купонам)."""
    net = []
    last = max(d for d, _ in flows)
    for d, a in flows:
        if d <= d0:
            continue
        if d == last:
            coupon_part = a - face
            gain = max(face - buy_clean_price, 0)
            net.append((d, a - tax * coupon_part - tax * gain))
        else:
            net.append((d, a * (1 - tax)))
    return ytm(dirty, net, d0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--price", type=float, required=True, help="Чистая цена, %% от номинала")
    ap.add_argument("--nkd", type=float, default=0.0, help="НКД в рублях на 1 бумагу")
    ap.add_argument("--face", type=float, default=1000.0)
    ap.add_argument("--flows", nargs="+", required=True, help="YYYY-MM-DD:сумма (купон+амортизация/погашение)")
    ap.add_argument("--date", default=None, help="Дата расчёта (по умолчанию сегодня)")
    a = ap.parse_args()
    d0 = dt.date.fromisoformat(a.date) if a.date else dt.date.today()
    flows = []
    for f in a.flows:
        d, v = f.split(":")
        flows.append((dt.date.fromisoformat(d), float(v)))
    dirty = a.price / 100 * a.face + a.nkd
    y = ytm(dirty, flows, d0)
    dur = duration(flows, y, d0)
    print(f"Грязная цена: {dirty:.2f}")
    print(f"YTM (эфф.): {y*100:.2f}%")
    print(f"Дюрация Маколея: {dur['macaulay_years']:.2f} лет; модиф.: {dur['modified']:.2f}; "
          f"выпуклость: {dur['convexity']:.2f}; PV01: {dur['pv01_per_1000']:.3f} ₽")
    print(f"Доходность после НДФЛ 13% (оценка): "
          f"{after_tax_yield(dirty, flows, d0, a.price / 100 * a.face, a.face)*100:.2f}%")
    print("Сценарии на 1 год (параллельный сдвиг):")
    for s in scenarios(dirty, flows, d0, y):
        print(f"  {s['shift_bp']:+5d} б.п. -> TR {s['total_return_%']:+.2f}%")


if __name__ == "__main__":
    main()
