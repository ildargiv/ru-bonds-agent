"""Общие помощники для MOEX ISS API (iss.moex.com). Только стандартная библиотека."""
import json
import sys
import urllib.parse
import urllib.request

ISS = "https://iss.moex.com/iss"
UA = {"User-Agent": "Mozilla/5.0 (hermes-ru-bonds)"}

# Основные режимы торгов облигациями
BOARDS = {
    "TQOB": "ОФЗ",
    "TQCB": "Корпоративные/муниципальные/еврооблигации РФ",
    "TQIR": "Сектор повышенного инвестиционного риска (ПИР)",
    "TQOD": "Облигации в валюте (USD/EUR/CNY)",
    "TQOY": "Облигации в юанях",
    "TQOE": "Облигации в евро",
}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def get(path, **params):
    params.setdefault("iss.meta", "off")
    url = f"{ISS}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def table(block):
    """ISS-блок {columns, data} -> список dict."""
    if not block:
        return []
    cols = block["columns"]
    return [dict(zip(cols, row)) for row in block["data"]]


def get_paged(path, key, **params):
    """Выкачивает все страницы блока key (ISS отдаёт по 100 строк)."""
    out, start = [], 0
    while True:
        d = get(path, start=start, **params)
        rows = table(d.get(key))
        out += rows
        cur = table(d.get(f"{key}.cursor"))
        if cur:
            c = cur[0]
            start = c["INDEX"] + c["PAGESIZE"]
            if start >= c["TOTAL"]:
                break
        elif len(rows) < 100:
            break
        else:
            start += len(rows)
    return out


def resolve(query):
    """ISIN / SECID / название -> (SECID, primary_boardid, emitter{id,title,inn})."""
    q = query.strip()
    d = get("/securities.json", q=q, **{"iss.only": "securities"})
    rows = [r for r in table(d.get("securities")) if (r.get("group") or "").startswith("stock_bonds")]
    if not rows:
        raise SystemExit(f"Облигация не найдена на MOEX: {q}")
    exact = [r for r in rows if q.upper() in (str(r.get("secid")).upper(), str(r.get("isin")).upper())]
    r = (exact or rows)[0]
    if not exact and len(rows) > 1:
        print("Найдено несколько бумаг, беру первую. Варианты:", file=sys.stderr)
        for x in rows[:15]:
            print(f"  {x['secid']:<14} {x.get('isin') or '':<14} {x.get('shortname')}", file=sys.stderr)
    emitter = {"id": r.get("emitent_id"), "title": r.get("emitent_title"), "inn": r.get("emitent_inn")}
    return r["secid"], r.get("primary_boardid"), emitter


def num(x, default=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def date(x):
    """Безопасный парсинг дат ISS ('0000-00-00', None -> None)."""
    import datetime as _dt
    try:
        return _dt.date.fromisoformat(str(x)[:10])
    except (TypeError, ValueError):
        return None
