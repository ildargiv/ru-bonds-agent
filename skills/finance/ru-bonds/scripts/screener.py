"""Скринер облигаций MOEX: выгружает все бумаги с режимов торгов, доходности/дюрации/спреды,
фильтрует и сортирует.

  python screener.py --boards TQCB TQIR --min-yield 20 --max-dur-days 730 --min-volume 1000000
  python screener.py --boards TQOB --sort duration          # кривая ОФЗ
  python screener.py --type fixed --listlevel 1 2 --csv out.csv
  python screener.py --name "Сегежа"                        # все выпуски эмитента

Типы (--type): fixed | floater (КС/RUONIA) | linker (ИПЦ) | fix_unk (купон известен до оферты) |
amort (амортизируемые) | struct (структурные — обычно исключать!) | fx (валютные) | any.
Колонка "Тип" + subtype ("До оферты (put)", "Бессрочные") — обязательно смотрите при отборе.
"""
import argparse
import csv
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _iss import get, table, num, BOARDS  # noqa: E402


def load_board(board):
    d = get(f"/engines/stock/markets/bonds/boards/{board}/securities.json",
            **{"iss.only": "securities,marketdata,marketdata_yields"})
    secs = {s["SECID"]: s for s in table(d.get("securities"))}
    mkt = {m["SECID"]: m for m in table(d.get("marketdata"))}
    ylds = {y["SECID"]: y for y in table(d.get("marketdata_yields"))}
    rows = []
    for sid, s in secs.items():
        m, y = mkt.get(sid, {}), ylds.get(sid, {})
        btype = (s.get("BONDTYPE") or "").lower()
        details = (s.get("COUPON_DETAILS") or "").lower()
        if "линкер" in btype or "ипц" in details or "ОФЗ-ИН" in (s.get("SECNAME") or ""):
            ctype = "linker"
        elif "плава" in btype or "ключев" in details or "ruonia" in details:
            ctype = "floater"
        elif "неизвестн" in details:
            ctype = "fix_unk"   # фикс до оферты, дальше купон определит эмитент
        elif "структур" in btype:
            ctype = "struct"
        elif "аморт" in btype:
            ctype = "amort"
        elif "валют" in btype:
            ctype = "fx"
        else:
            ctype = "fixed"
        rows.append({
            "secid": sid, "isin": s.get("ISIN"), "name": s.get("SHORTNAME"), "board": board,
            "price": num(m.get("LAST")) or num(s.get("PREVWAPRICE")) or num(s.get("PREVPRICE")),
            "ytm": num(y.get("EFFECTIVEYIELD")) or num(s.get("YIELDATPREVWAPRICE")),
            "yield_to": y.get("YIELDDATE"), "to_type": y.get("YIELDDATETYPE"),
            "dur_days": num(y.get("DURATION")),
            "g_spread": num(y.get("GSPREADBP")), "z_spread": num(y.get("ZSPREADBP")),
            "coupon_pct": num(s.get("COUPONPERCENT")), "coupon_period": s.get("COUPONPERIOD"),
            "matdate": s.get("MATDATE"), "offerdate": s.get("OFFERDATE"),
            "listlevel": s.get("LISTLEVEL"), "currency": s.get("FACEUNIT"),
            "volume": num(m.get("VALTODAY"), 0) or 0, "trades": m.get("NUMTRADES"),
            "ctype": ctype, "subtype": s.get("BONDSUBTYPE"), "coupon_base": s.get("COUPON_DETAILS"), "status": s.get("STATUS"),
        })
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--boards", nargs="+", default=["TQCB", "TQOB", "TQIR"], help=", ".join(f"{k}={v}" for k, v in BOARDS.items()))
    ap.add_argument("--min-yield", type=float)
    ap.add_argument("--max-yield", type=float, default=60, help="Отсечь мусор/предефолтные (по умолчанию 60%%)")
    ap.add_argument("--min-dur-days", type=float)
    ap.add_argument("--max-dur-days", type=float)
    ap.add_argument("--min-volume", type=float, default=0, help="Оборот за день, ₽")
    ap.add_argument("--listlevel", nargs="+", type=int)
    ap.add_argument("--type", choices=["fixed", "floater", "linker", "fix_unk", "amort", "struct", "fx", "any"], default="any")
    ap.add_argument("--currency", help="SUR/RUB, USD, CNY, EUR")
    ap.add_argument("--name", help="Подстрока в названии")
    ap.add_argument("--sort", choices=["ytm", "duration", "g_spread", "volume"], default="ytm")
    ap.add_argument("--top", type=int, default=50)
    ap.add_argument("--csv")
    a = ap.parse_args()

    rows = []
    for b in a.boards:
        try:
            rows += load_board(b)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] {b}: {e}", file=sys.stderr)
    today = dt.date.today().isoformat()
    f = []
    for r in rows:
        if r["status"] not in (None, "A"):
            continue
        if r["matdate"] and r["matdate"] != "0000-00-00" and r["matdate"] <= today:
            continue
        if a.min_yield is not None and (r["ytm"] is None or r["ytm"] < a.min_yield):
            continue
        if r["ytm"] is not None and r["ytm"] > a.max_yield:
            continue
        if a.min_dur_days is not None and (r["dur_days"] is None or r["dur_days"] < a.min_dur_days):
            continue
        if a.max_dur_days is not None and (r["dur_days"] is None or r["dur_days"] > a.max_dur_days):
            continue
        if r["volume"] < a.min_volume:
            continue
        if a.listlevel and r["listlevel"] not in a.listlevel:
            continue
        if a.type != "any" and r["ctype"] != a.type:
            continue
        if a.currency and (r["currency"] or "").upper() != a.currency.upper():
            continue
        if a.name and a.name.lower() not in (r["name"] or "").lower():
            continue
        f.append(r)
    key = {"ytm": lambda r: -(r["ytm"] or 0), "duration": lambda r: r["dur_days"] or 1e9,
           "g_spread": lambda r: -(r["g_spread"] or -1e9), "volume": lambda r: -r["volume"]}[a.sort]
    f.sort(key=key)

    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(f[0].keys()) if f else ["secid"], delimiter=";")
            w.writeheader()
            w.writerows(f)
        print(f"Сохранено {len(f)} строк в {a.csv}")
    print(f"Найдено {len(f)} из {len(rows)}. Топ {min(a.top, len(f))}:")
    print(f"{'SECID':<14}{'Название':<24}{'Цена':>8}{'YTM%':>7}{'Дюр,д':>7}{'G,бп':>6}{'Куп%':>7} {'Погаш.':<11}{'Оферта':<11}{'Лист':>4}{'Тип':>8}{'Оборот,млн':>11}")
    for r in f[: a.top]:
        print(f"{r['secid']:<14}{(r['name'] or '')[:23]:<24}{(r['price'] or 0):>8.2f}{(r['ytm'] or 0):>7.2f}"
              f"{(r['dur_days'] or 0):>7.0f}{(r['g_spread'] or 0):>6.0f}{(r['coupon_pct'] or 0):>7.2f} "
              f"{(r['matdate'] or '')[:10]:<11}{(r['offerdate'] or '-')[:10]:<11}{r['listlevel'] or '':>4}"
              f"{r['ctype']:>8}{r['volume']/1e6:>11.1f}")


if __name__ == "__main__":
    main()
