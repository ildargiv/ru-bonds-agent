"""Полная карточка облигации с MOEX ISS: параметры выпуска, котировки, доходность/дюрация/спреды
от биржи, график купонов, амортизаций и оферт, сравнение с КБД, собственный пересчёт метрик.

  python moex_bond.py RU000A10XXXX            # по ISIN
  python moex_bond.py SU26238RMFS4            # по SECID
  python moex_bond.py SU26238RMFS4 --json     # машиночитаемый вывод
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _iss import get, get_paged, table, resolve, num, date  # noqa: E402
import bond_math as bm  # noqa: E402

DESC_KEYS = ["SECID", "NAME", "ISIN", "REGNUMBER", "ISSUEDATE", "MATDATE", "BUYBACKDATE", "FACEVALUE",
             "INITIALFACEVALUE", "FACEUNIT", "ISSUESIZE", "COUPONFREQUENCY", "COUPONPERCENT", "COUPONVALUE",
             "DAYSTOREDEMPTION", "LISTLEVEL", "ISQUALIFIEDINVESTORS", "MORNINGSESSION", "EVENINGSESSION",
             "COUPON_BENCHMARK", "COUPON_BENCHMARK_SPREAD", "PROGRAMREGISTRYNUMBER", "TYPENAME", "BOND_TYPE", "BOND_SUBTYPE", "EMITTER_ID", "EMITTER", "INN", "EARLYREPAYMENT", "HASDEFAULT",
             "HASTECHNICALDEFAULT", "ISSUBORDINATED", "ISGUARANTEED"]


def zcyc_yield(years):
    """Доходность КБД (G-curve) ЦБ/MOEX на заданный срок, линейная интерполяция."""
    try:
        rows = table(get("/engines/stock/zcyc.json", **{"iss.only": "yearyields"}).get("yearyields"))
    except Exception:
        return None
    pts = sorted((r["period"], r["value"]) for r in rows)
    if not pts:
        return None
    if years <= pts[0][0]:
        return pts[0][1]
    for (t1, y1), (t2, y2) in zip(pts, pts[1:]):
        if t1 <= years <= t2:
            return y1 + (y2 - y1) * (years - t1) / (t2 - t1)
    return pts[-1][1]


def collect(query):
    secid, board, emitter = resolve(query)
    desc = {r["name"]: r["value"] for r in table(
        get(f"/securities/{secid}.json", **{"iss.only": "description"}).get("description"))}
    md = get(f"/engines/stock/markets/bonds/securities/{secid}.json",
             **{"iss.only": "securities,marketdata,marketdata_yields"})
    secs = table(md.get("securities"))
    sec = next((s for s in secs if s["BOARDID"] == board), secs[0] if secs else {})
    mkt = next((m for m in table(md.get("marketdata")) if m["BOARDID"] == sec.get("BOARDID")), {})
    yld = next((m for m in table(md.get("marketdata_yields")) if m["BOARDID"] == sec.get("BOARDID")), {})
    path = f"/statistics/engines/stock/markets/bonds/bondization/{secid}.json"
    coupons = get_paged(path, "coupons", **{"iss.only": "coupons,coupons.cursor"})
    amorts = get_paged(path, "amortizations", **{"iss.only": "amortizations,amortizations.cursor"})
    offers = get_paged(path, "offers", **{"iss.only": "offers,offers.cursor"})
    desc["EMITTER"], desc["INN"] = emitter.get("title"), emitter.get("inn")
    return secid, desc, sec, mkt, yld, coupons, amorts, offers


def build_flows(coupons, amorts, today, until=None):
    flows = {}
    for c in coupons:
        d = date(c["coupondate"])
        if d and d > today and (until is None or d <= until) and c.get("value") is not None:
            flows[d] = flows.get(d, 0) + float(c["value"])
    for a in amorts:
        d = date(a["amortdate"])
        if d and d > today and (until is None or d <= until) and a.get("value") is not None:
            flows[d] = flows.get(d, 0) + float(a["value"])
    return sorted(flows.items())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", help="ISIN, SECID или часть названия")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    secid, desc, sec, mkt, yld, coupons, amorts, offers = collect(a.query)
    today = dt.date.today()

    price = num(mkt.get("LAST")) or num(mkt.get("WAPRICE")) or num(sec.get("PREVWAPRICE")) or num(sec.get("PREVPRICE"))
    face = num(sec.get("FACEVALUE"), 1000.0)
    nkd = num(sec.get("ACCRUEDINT"), 0.0)
    future_coupons = [c for c in coupons if (date(c["coupondate"]) or today) > today]
    unknown = [c for c in future_coupons if c.get("value") is None]
    future_offers = [o for o in offers if (date(o.get("offerdate")) or today) > today]
    put_date = date(future_offers[0]["offerdate"]) if future_offers else None
    if not put_date and date(sec.get("OFFERDATE")) and date(sec.get("OFFERDATE")) > today:
        put_date = date(sec.get("OFFERDATE"))

    own = {}
    if price and not unknown:
        flows = build_flows(coupons, amorts, today)
        if flows:
            dirty = price / 100 * face + nkd
            y = bm.ytm(dirty, flows, today)
            own = {"ytm_%": round(y * 100, 2), **{k: round(v, 3) for k, v in bm.duration(flows, y, today).items()}}
            own["scenarios_1y"] = bm.scenarios(dirty, flows, today, y)
    if price and put_date:
        # к оферте: номинал гасится по цене оферты (обычно 100%)
        flows = build_flows(coupons, amorts, today, until=put_date)
        if not any(c.get("value") is None for c in future_coupons
                   if date(c["coupondate"]) <= put_date):
            # остаток номинала на дату оферты = текущий номинал минус амортизации до оферты
            amort_before = sum(float(x["value"] or 0) for x in amorts
                               if (date(x["amortdate"]) or today) > today and date(x["amortdate"]) <= put_date)
            outstanding = face - amort_before
            offer_price = num(future_offers[0].get("price"), 100) if future_offers else 100
            flows.append((put_date, outstanding * offer_price / 100))
            y = bm.ytm(price / 100 * face + nkd, flows, today)
            own["ytm_to_put_%"] = round(y * 100, 2)

    dur_years = (num(yld.get("DURATION"), 0) or 0) / 365
    g = zcyc_yield(dur_years) if dur_years else None

    out = {
        "secid": secid,
        "description": {k: desc.get(k) for k in DESC_KEYS if desc.get(k) is not None},
        "board": sec.get("BOARDID"), "board_name": sec.get("BOARDNAME"),
        "bond_type": sec.get("BONDTYPE"), "bond_subtype": sec.get("BONDSUBTYPE"),
        "coupon_details": sec.get("COUPON_DETAILS"),
        "market": {"price_%": price, "bid": mkt.get("BID"), "offer": mkt.get("OFFER"),
                   "spread_bidask_%": (round(num(mkt["OFFER"]) - num(mkt["BID"]), 3)
                                       if num(mkt.get("BID")) and num(mkt.get("OFFER")) else None),
                   "volume_today_rub": mkt.get("VALTODAY"), "num_trades": mkt.get("NUMTRADES"),
                   "nkd": nkd, "face": face, "face_unit": sec.get("FACEUNIT"),
                   "next_coupon": sec.get("NEXTCOUPON"), "coupon_value": sec.get("COUPONVALUE"),
                   "coupon_%": sec.get("COUPONPERCENT"), "coupon_period_days": sec.get("COUPONPERIOD"),
                   "offer_date": sec.get("OFFERDATE"), "call_date": sec.get("CALLOPTIONDATE"),
                   "put_date": sec.get("PUTOPTIONDATE"), "buyback_date": sec.get("BUYBACKDATE"),
                   "buyback_price": sec.get("BUYBACKPRICE")},
        "moex_yields": {"effective_yield_%": yld.get("EFFECTIVEYIELD"), "yield_date": yld.get("YIELDDATE"),
                        "yield_date_type": yld.get("YIELDDATETYPE"), "duration_days": yld.get("DURATION"),
                        "g_spread_bp": yld.get("GSPREADBP"), "z_spread_bp": yld.get("ZSPREADBP"),
                        "yield_to_offer_%": yld.get("YIELDTOOFFER"), "yield_last_coupon_%": yld.get("YIELDLASTCOUPON")},
        "kbd_yield_at_duration_%": round(g, 2) if g else None,
        "own_calc": own,
        "future_coupons": [{"date": c["coupondate"], "value": c["value"], "%": c["valueprc"]} for c in future_coupons],
        "unknown_coupons": len(unknown),
        "amortizations": [{"date": x["amortdate"], "value": x["value"], "%": x["valueprc"], "src": x["data_source"]}
                          for x in amorts if (date(x["amortdate"]) or today) > today],
        "offers": [{"date": o["offerdate"], "type": o.get("offertype"), "price": o.get("price"),
                    "window": f"{o.get('offerdatestart')}..{o.get('offerdateend')}"} for o in offers],
        "links": {
            "moex": f"https://www.moex.com/ru/issue.aspx?code={secid}",
            "smartlab": f"https://smart-lab.ru/q/bonds/{secid}/",
            "dohod": f"https://www.dohod.ru/ik/analytics/bonds/{desc.get('ISIN', secid)}",
            "rusbonds_search": f"https://rusbonds.ru/bonds?search={desc.get('ISIN', secid)}",
            "gir_bo": f"https://bo.nalog.gov.ru/search?query={desc.get('INN') or ''}",
            "e_disclosure_search": "https://www.e-disclosure.ru/poisk-po-kompaniyam",
        },
    }
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
        return

    d = out["description"]
    print(f"=== {d.get('NAME')} | {secid} | ISIN {d.get('ISIN')} ===")
    print(f"Режим: {out['board']} ({out['board_name']}); тип: {out['bond_type']} / {out['bond_subtype']}; "
          f"купон: {out['coupon_details']}")
    print(f"Листинг: {d.get('LISTLEVEL')}; только для квалов: {d.get('ISQUALIFIEDINVESTORS')}; "
          f"субординир.: {d.get('ISSUBORDINATED')}; дефолт/тех.дефолт: {d.get('HASDEFAULT')}/{d.get('HASTECHNICALDEFAULT')}")
    print(f"Эмитент: {d.get('EMITTER')} | ИНН {d.get('INN')}")
    if d.get("COUPON_BENCHMARK"):
        print(f"Флоатер: база {d.get('COUPON_BENCHMARK')} + спред {d.get('COUPON_BENCHMARK_SPREAD')} п.п.")
    print(f"Размещение {d.get('ISSUEDATE')} -> погашение {d.get('MATDATE')}; объём {d.get('ISSUESIZE')} шт.;")
    m = out["market"]
    print(f"Цена {m['price_%']}% | bid/ask {m['bid']}/{m['offer']} (спред {m['spread_bidask_%']}) | "
          f"оборот сегодня {m['volume_today_rub']} ₽, сделок {m['num_trades']}")
    print(f"Номинал {m['face']} {m['face_unit']} | НКД {m['nkd']} | купон {m['coupon_%']}% = {m['coupon_value']} "
          f"каждые {m['coupon_period_days']} дн., след. {m['next_coupon']}")
    print(f"Оферта {m['offer_date']} | call {m['call_date']} | put {m['put_date']} | buyback {m['buyback_date']} @ {m['buyback_price']}")
    y = out["moex_yields"]
    print(f"MOEX: YTM {y['effective_yield_%']}% к {y['yield_date']} ({y['yield_date_type']}), дюрация {y['duration_days']} дн., "
          f"G-спред {y['g_spread_bp']} б.п., Z-спред {y['z_spread_bp']} б.п., к оферте {y['yield_to_offer_%']}")
    print(f"КБД на сроке дюрации: {out['kbd_yield_at_duration_%']}%")
    if own:
        print(f"Собственный расчёт: {json.dumps({k: v for k, v in own.items() if k != 'scenarios_1y'}, ensure_ascii=False)}")
        if "scenarios_1y" in own:
            print("  TR за 1 год при сдвиге ставок: " +
                  ", ".join(f"{s['shift_bp']:+d}бп→{s['total_return_%']:+.1f}%" for s in own["scenarios_1y"]))
    elif out["unknown_coupons"]:
        print(f"Купоны неизвестны: {out['unknown_coupons']} шт. (флоатер/переменный купон/до оферты) — "
              "YTM считается к оферте или через прогноз базовой ставки")
    print(f"Будущих купонов: {len(out['future_coupons'])}; ближайшие: "
          + "; ".join(f"{c['date']} {c['value']}" for c in out["future_coupons"][:4]))
    if out["amortizations"]:
        print("Амортизация/погашение: " + "; ".join(f"{x['date']} {x['value']} ({x['%']}%)" for x in out["amortizations"]))
    if out["offers"]:
        print("Оферты: " + "; ".join(f"{o['date']} {o['type']} @ {o['price']}" for o in out["offers"]))
    print("Ссылки: " + " | ".join(out["links"].values()))


if __name__ == "__main__":
    main()
