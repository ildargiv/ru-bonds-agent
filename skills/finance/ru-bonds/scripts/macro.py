"""Рыночный фон для облигаций: кривая КБД (ОФЗ, MOEX/ЦБ), ключевые индексы облигаций.
Ключевую ставку, RUONIA и инфляцию агент берёт с cbr.ru (см. references/data-sources.md).

  python macro.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _iss import get, table  # noqa: E402

INDICES = ["RGBITR", "RGBI", "RUCBTRNS", "RUCBCPNS", "RUCBTR3B3YNS", "RUGBITR1Y", "RUGBITR10Y"]


def main():
    zc = table(get("/engines/stock/zcyc.json", **{"iss.only": "yearyields"}).get("yearyields"))
    if zc:
        print(f"КБД (G-curve) на {zc[0]['tradedate']} {zc[0]['tradetime']}:")
        print("  " + " | ".join(f"{r['period']:g}г: {r['value']:.2f}%" for r in zc))
        short, long_ = zc[0]["value"], zc[-1]["value"]
        shape = "инвертирована" if short > long_ + 0.25 else ("плоская" if abs(short - long_) <= 0.25 else "нормальная (растущая)")
        print(f"  Форма кривой: {shape} (короткий конец {short:.2f}% vs длинный {long_:.2f}%)")
    print("\nИндексы облигаций MOEX:")
    for idx in INDICES:
        try:
            d = get(f"/engines/stock/markets/index/securities/{idx}.json", **{"iss.only": "marketdata,securities"})
            md = table(d.get("marketdata"))
            sc = table(d.get("securities"))
            if md:
                m = md[0]
                nm = sc[0].get("NAME") or sc[0].get("SHORTNAME") if sc else idx
                print(f"  {idx:<14} {m.get('CURRENTVALUE') or m.get('LASTVALUE')}  "
                      f"изм.день {m.get('LASTCHANGEPRC')}%  к открытию {m.get('LASTCHANGETOOPENPRC') or ''}%  | {nm}")
        except Exception as e:  # noqa: BLE001
            print(f"  {idx}: недоступно ({e})")


if __name__ == "__main__":
    main()
