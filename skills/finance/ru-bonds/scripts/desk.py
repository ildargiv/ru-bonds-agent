"""Список наблюдения и папки выпусков облигаций («рабочий стол» и база знаний Obsidian).

  python desk.py add RU000A10XXXX [--note "зачем следим"]   # папка + карточка + кредитный тезис + запись в список
  python desk.py list                                       # что под наблюдением
  python desk.py status [SECID ...]                         # что изменилось с последнего разбора: цена, YTM, спред, оферты
  python desk.py show SECID                                 # содержимое папки и последние записи хронологии
  python desk.py analysed SECID --verdict "Держать" --score 68 [--fair-ytm 19.5] [--protocol файл.md]
  python desk.py log SECID "АКРА подтвердило A-(RU), прогноз стабильный" --source "acra-ratings.ru, 05.11"
  python desk.py remove SECID [--archive]                   # перестать следить (папка сохраняется)
  python desk.py path [SECID]                               # путь к хранилищу / папке выпуска

Хранилище: ~/bonds-desk (переменная BONDS_DESK; при INVEST_VAULT — INVEST_VAULT/bonds). Структура — references/desk-structure.md.
"""
import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _iss import (load_watchlist, save_watchlist, ticker_dir, desk_root, append_journal, today, date, num)  # noqa: E402
import wiki  # noqa: E402  база знаний Obsidian: хаб-заметки, эмитенты, index, log (references/wiki.md)

SUBDIRS = ("market", "reports", "news", "forums", "analyses")

PROFILE = """---
type: profile
entity: {secid}
up: "[[{secid}/{secid}|{secid}]]"
tags: [desk/bonds, type/profile]
created: {date}
updated: {date}
---
# {secid} — {name}

> Карточка выпуска. Создана {date} по данным MOEX ISS; агент дополняет её при разборе (структура, обеспечение, ковенанты).

| Поле | Значение · Источник: MOEX ISS на {date} |
|---|---|
| SECID / ISIN | {secid} / {isin} |
| Эмитент / ИНН | {emitent} / {inn} |
| Тип, купон | {bond_type}; {coupon} |
| Погашение / оферта | {maturity} / {offer} |
| Листинг, квал | {listlevel}; только для квалов: {qual} |
| Карточка на бирже | https://www.moex.com/ru/issue.aspx?code={secid} |
| Раскрытие | https://www.e-disclosure.ru (поиск по ИНН {inn}) |
| РСБУ (ГИР БО) | https://bo.nalog.gov.ru/search?query={inn} |
| Зачем следим | {note} |

## Структура выпуска
_Старший/суборд, обеспечение, поручители, ковенанты, put/call, амортизация, место в графике погашений всего долга._

## Рейтинги
_Агентство — рейтинг — прогноз — дата — ссылка на пресс-релиз._

## Календарь
_Купоны, оферты, амортизации, отчётность эмитента._
"""

THESIS = """---
type: thesis
entity: {secid}
up: "[[{secid}/{secid}|{secid}]]"
verdict:
tags: [desk/bonds, type/thesis]
created: {date}
updated: {date}
---
# Кредитный тезис: {secid}

> Живой документ. Обновляется после каждого разбора. Старые версии — в analyses/.

**Статус:** разбор ещё не проводился.

## Почему выпуск интересен (доходность, премия к КБД и аналогам)
## Что может пойти не так (кредитные и рыночные риски)
## Справедливая доходность и для кого подходит
## Триггеры пересмотра (рейтинг, ковенанты, отчётность, суды, оферта, ставка ЦБ)
## Что проверить в следующем отчёте эмитента
"""


def card(q):
    from moex_bond import card as _card
    return _card(q)


def cmd_add(a):
    wl = load_watchlist()
    for q in a.ids:
        c = card(q)
        secid, d, m = c["secid"], c["description"], c["market"]
        if secid in wl["tickers"]:
            print(f"{secid} уже под наблюдением: {ticker_dir(secid, create=False)}")
            continue
        root = ticker_dir(secid)
        for s in SUBDIRS:
            os.makedirs(os.path.join(root, s), exist_ok=True)
        coupon = c.get("coupon_details") or (f"{m.get('coupon_%')}%" if m.get("coupon_%") else "—")
        if d.get("COUPON_BENCHMARK"):
            coupon = f"флоатер: {d.get('COUPON_BENCHMARK')} + {d.get('COUPON_BENCHMARK_SPREAD')} п.п."
        info = {"secid": secid, "isin": d.get("ISIN"), "name": d.get("NAME") or secid, "emitent": d.get("EMITTER"),
                "inn": d.get("INN"), "board": c.get("board"), "maturity": d.get("MATDATE"),
                "offer": m.get("offer_date") or "—", "coupon_type": c.get("bond_subtype") or c.get("bond_type"),
                "listlevel": d.get("LISTLEVEL")}
        fields = {**info, "date": today(), "note": a.note or "_заполнить_", "bond_type": c.get("bond_type") or "—",
                  "coupon": coupon, "qual": d.get("ISQUALIFIEDINVESTORS")}
        for name, tpl in (("README.md", PROFILE), ("thesis.md", THESIS)):
            p = os.path.join(root, name)
            if not os.path.exists(p):
                with open(p, "w", encoding="utf-8") as f:
                    f.write(tpl.format(**{k: ("—" if v is None else v) for k, v in fields.items()}))
        jp = os.path.join(root, "journal.md")
        if not os.path.exists(jp):
            with open(jp, "w", encoding="utf-8") as f:
                f.write(f"---\ntype: journal\nentity: {secid}\nup: \"[[{secid}/{secid}|{secid}]]\"\n"
                        f"tags: [desk/bonds, type/journal]\n---\n# Хронология: {secid}\n\n")
        append_journal(secid, "Начато наблюдение" + (f": {a.note}" if a.note else ""))
        wl["tickers"][secid] = {**info, "added": today(), "note": a.note, "last_analysis": None}
        save_watchlist(wl)
        from moex_bond import save_snapshot
        save_snapshot(c)
        wiki.safe_log(f"Начато наблюдение: {info['name']} ({info['emitent']})" + (f" — {a.note}" if a.note else ""),
                      secid, "источник", "MOEX ISS")
        wiki.safe_sync([secid])
        print(f"✅ {secid} ({info['name']}, {info['emitent']}, ИНН {info['inn']}) — под наблюдением. Папка: {root}")
        print("   Дальше: разбор выпуска (SKILL.md, процедура A), итог — desk.py analysed.")


def cmd_list(a):
    wl = load_watchlist()["tickers"]
    if not wl:
        print("Список наблюдения пуст. Добавьте: python desk.py add RU000A10XXXX")
        return
    print(f"Хранилище: {desk_root()}")
    for s, x in sorted(wl.items()):
        la = x.get("last_analysis") or {}
        print(f"  {s:<14} {x.get('name')} | {x.get('emitent')} | погашение {x.get('maturity')} | с {x['added']} | "
              f"разбор: {la.get('date', 'не было')} {la.get('verdict', '')}"
              + (f" скоринг {la['score']}" if la.get("score") is not None else ""))


def cmd_status(a):
    wl = load_watchlist()["tickers"]
    ids = a.ids or sorted(wl)
    if not ids:
        raise SystemExit("Список наблюдения пуст. Добавьте: python desk.py add RU000A10XXXX")
    t = dt.date.today()
    for s in ids:
        x = wl.get(s)
        if not x:
            print(f"{s}: не под наблюдением (python desk.py add {s})")
            continue
        c = card(s)
        m, y, d = c["market"], c["moex_yields"], c["description"]
        la = x.get("last_analysis") or {}
        flags = []
        if not la:
            flags.append("нужен разбор")
        elif la.get("date") and (t - date(la["date"])).days > 90:
            flags.append(f"разбор устарел ({(t - date(la['date'])).days} дн.)")
        if la.get("price") and m.get("price_%"):
            dp = m["price_%"] - la["price"]
            if abs(dp) >= 3:
                flags.append(f"цена {dp:+.1f} п.п. с разбора")
        if la.get("ytm") and num(y.get("effective_yield_%")):
            dy = num(y["effective_yield_%"]) - la["ytm"]
            if abs(dy) >= 1.5:
                flags.append(f"YTM {dy:+.1f} п.п. с разбора")
        for label, key in (("оферта", m.get("offer_date")), ("погашение", d.get("MATDATE")),
                           ("put", m.get("put_date")), ("call", m.get("call_date"))):
            dd = date(key)
            if dd and t <= dd <= t + dt.timedelta(days=60):
                flags.append(f"{label} {dd}")
        if d.get("HASDEFAULT") in (1, "1") or d.get("HASTECHNICALDEFAULT") in (1, "1"):
            flags.append("ДЕФОЛТ/тех. дефолт по данным MOEX")
        print(f"{s:<14} цена {m.get('price_%') or '—'}% | YTM {y.get('effective_yield_%') or '—'}% | "
              f"дюрация {y.get('duration_days') or '—'} дн. | G-спред {y.get('g_spread_bp') or '—'} б.п."
              + (f" | вердикт: {la.get('verdict')}" if la.get("verdict") else "")
              + (" | ⚑ " + "; ".join(flags) if flags else " | без изменений"))


def cmd_show(a):
    root = ticker_dir(a.id, create=False)
    if not os.path.isdir(root):
        raise SystemExit(f"Папки {root} нет. Сначала: python desk.py add {a.id}")
    print(f"Папка: {root}")
    for dirpath, _, files in sorted(os.walk(root)):
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if rel != ".":
            print("  " * depth + f"{os.path.basename(dirpath)}/")
        for fn in sorted(files)[-12:]:
            print("  " * (depth + 1) + fn)
    j = os.path.join(root, "journal.md")
    if os.path.exists(j):
        with open(j, encoding="utf-8") as f:
            lines = [ln.rstrip() for ln in f if ln.startswith("- ")]
        print("\nПоследние записи хронологии:\n" + "\n".join(lines[-15:]))


def cmd_analysed(a):
    wl = load_watchlist()
    s = a.id
    if s not in wl["tickers"]:
        raise SystemExit(f"{s} не под наблюдением")
    c = card(s)
    price, ytm = c["market"].get("price_%"), num(c["moex_yields"].get("effective_yield_%"))
    wl["tickers"][s]["last_analysis"] = {"date": today(), "price": price, "ytm": ytm, "verdict": a.verdict,
                                         "score": a.score, "target": a.fair_ytm}
    save_watchlist(wl)
    adir = ticker_dir(s, "analyses")
    proto = a.protocol
    if not proto:
        files = sorted(f for f in os.listdir(adir) if f.endswith(".md"))
        proto = files[-1] if files else None
    if proto and not os.path.exists(os.path.join(adir, proto)):
        print(f"⚠ протокол analyses/{proto} не найден", file=sys.stderr)
        proto = None
    text = (f"Разбор: {a.verdict}" + (f", кредитный скоринг {a.score}" if a.score is not None else "")
            + (f", справедливая YTM {a.fair_ytm}%" if a.fair_ytm else "") + f" при цене {price}% и YTM {ytm}%")
    append_journal(s, text, f"analyses/{proto}" if proto else "протокол не сохранён")
    wiki.safe_log(text, s, "вывод", f"analyses/{proto}" if proto else "")
    wiki.safe_sync([s])
    print(f"Записано: {s} {a.verdict} @ {price}% (YTM {ytm}%)")


def cmd_log(a):
    append_journal(a.id, a.text, a.source or "")
    wiki.safe_sync([a.id])
    print("Записано в journal.md")


def cmd_remove(a):
    wl = load_watchlist()
    s = a.id
    if wl["tickers"].pop(s, None) is None:
        raise SystemExit(f"{s} не под наблюдением")
    save_watchlist(wl)
    append_journal(s, "Наблюдение прекращено")
    root = ticker_dir(s, create=False)
    if a.archive and os.path.isdir(root):
        dst = os.path.join(desk_root(), "_archive", s)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.replace(root, dst)
        root = dst
    wiki.safe_sync()
    print(f"{s} снят с наблюдения; данные сохранены в {root}")


def cmd_path(a):
    print(ticker_dir(a.id, create=False) if a.id else desk_root())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("add")
    p.add_argument("ids", nargs="+")
    p.add_argument("--note")
    p.set_defaults(fn=cmd_add)
    sp.add_parser("list").set_defaults(fn=cmd_list)
    p = sp.add_parser("status")
    p.add_argument("ids", nargs="*")
    p.set_defaults(fn=cmd_status)
    p = sp.add_parser("show")
    p.add_argument("id")
    p.set_defaults(fn=cmd_show)
    p = sp.add_parser("analysed")
    p.add_argument("id")
    p.add_argument("--verdict", required=True)
    p.add_argument("--score", type=int)
    p.add_argument("--fair-ytm", type=float, help="справедливая доходность, % годовых")
    p.add_argument("--protocol", help="имя файла в analyses/ (по умолчанию — самый свежий)")
    p.set_defaults(fn=cmd_analysed)
    p = sp.add_parser("log")
    p.add_argument("id")
    p.add_argument("text")
    p.add_argument("--source")
    p.set_defaults(fn=cmd_log)
    p = sp.add_parser("remove")
    p.add_argument("id")
    p.add_argument("--archive", action="store_true")
    p.set_defaults(fn=cmd_remove)
    p = sp.add_parser("path")
    p.add_argument("id", nargs="?")
    p.set_defaults(fn=cmd_path)
    a = ap.parse_args()
    for k in ("id",):
        if getattr(a, k, None):
            setattr(a, k, a.id.strip().upper())
    if getattr(a, "ids", None):
        a.ids = [i.strip().upper() for i in a.ids]
    a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
