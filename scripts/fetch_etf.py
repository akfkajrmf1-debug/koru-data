#!/usr/bin/env python3
"""
원본 ETF 일봉을 받아 저장하고 주봉으로 리샘플한다.
무기한 계약(2026-07-22 상장)에 없는 장기 구조를 여기서 얻는다.

소스를 순서대로 시도하고 처음 성공한 것을 쓴다.
  1. Yahoo Finance  (JSON, 무키, 히스토리 길고 분할조정 포함)
  2. Yahoo 대체 호스트
  3. Stooq          (CSV, 무키)
  4. Nasdaq         (JSON, 무키)
어디가 막혔는지 로그에 전부 남는다. 전부 실패해도 기존 CSV는 건드리지 않는다.
표준 라이브러리만 사용.
"""
import csv, io, json, os, sys, time
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request

KST = timezone(timedelta(hours=9))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

TICKERS = [
    ("KORU", "KORU_ETF"),
    ("EWY",  "EWY_ETF"),
    ("SOXL", "SOXL_ETF"),
    ("SOXX", "SOXX_ETF"),
    ("QQQ",  "QQQ_ETF"),
    ("TQQQ", "TQQQ_ETF"),
    ("SMH",  "SMH_ETF"),
    ("NVDA", "NVDA_ETF"),
]

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
MIN_ROWS = 100          # 이보다 적으면 실패로 본다


def raw(url, headers=None, tries=2, timeout=30):
    h = {"User-Agent": UA, "Accept": "*/*",
         "Accept-Language": "en-US,en;q=0.9", "Connection": "close"}
    if headers:
        h.update(headers)
    last = None
    for i in range(tries):
        try:
            with urlopen(Request(url, headers=h), timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            time.sleep(1.2 * (i + 1))
    raise RuntimeError(f"{type(last).__name__}: {last}")


def row(ts, o, h, l, c, v):
    """유닉스초 -> 표준 행. 결측이 하나라도 있으면 버린다."""
    if None in (o, h, l, c):
        return None
    d = datetime.fromtimestamp(int(ts), timezone.utc)
    return {"time": int(ts),
            "datetime_kst": d.strftime("%Y-%m-%d") + " 00:00:00",
            "open": f"{float(o):.4f}", "high": f"{float(h):.4f}",
            "low": f"{float(l):.4f}", "close": f"{float(c):.4f}",
            "volume": f"{float(v or 0):.0f}"}


# ------------------------------------------------------------------ 소스들
def src_yahoo(sym, host="query1"):
    url = (f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}"
           f"?range=10y&interval=1d&events=div%2Csplit")
    d = json.loads(raw(url))
    res = (d.get("chart") or {}).get("result")
    if not res:
        raise RuntimeError(f"결과 없음 {(d.get('chart') or {}).get('error')}")
    r0 = res[0]
    ts = r0.get("timestamp") or []
    q = r0["indicators"]["quote"][0]
    adj = None
    ac = r0["indicators"].get("adjclose")
    if ac and ac[0].get("adjclose"):
        adj = ac[0]["adjclose"]
    out = []
    for i, t in enumerate(ts):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if adj and c and adj[i]:
            k = adj[i] / c
            o, h, l, c = (x * k if x else x for x in (o, h, l, c))
        rr = row(t, o, h, l, c, v)
        if rr:
            out.append(rr)
    return out, f"Yahoo/{host}"


def src_yahoo2(sym):
    return src_yahoo(sym, host="query2")


def src_stooq(sym):
    txt = raw(f"https://stooq.com/q/d/l/?s={sym.lower()}.us&i=d")
    if "Date" not in txt.split("\n")[0]:
        raise RuntimeError(f"CSV 아님: {txt[:60]!r}")
    out = []
    for r in csv.DictReader(io.StringIO(txt)):
        try:
            d = datetime.strptime(r["Date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            rr = row(int(d.timestamp()), r["Open"], r["High"], r["Low"],
                     r["Close"], r.get("Volume") or 0)
            if rr:
                out.append(rr)
        except (ValueError, KeyError):
            continue
    return out, "Stooq"


def src_nasdaq(sym):
    to = datetime.now(timezone.utc).date()
    fr = to - timedelta(days=365 * 10)
    url = (f"https://api.nasdaq.com/api/quote/{sym}/historical"
           f"?assetclass=etf&fromdate={fr}&todate={to}&limit=9999")
    d = json.loads(raw(url, headers={"Accept": "application/json",
                                     "Referer": "https://www.nasdaq.com/"}))
    rows = (((d.get("data") or {}).get("tradesTable") or {}).get("rows")) or []
    if not rows:
        raise RuntimeError(f"행 없음 {str(d)[:60]}")
    cl = lambda x: float(str(x).replace("$", "").replace(",", "") or 0)
    out = []
    for r in rows:
        try:
            d0 = datetime.strptime(r["date"], "%m/%d/%Y").replace(tzinfo=timezone.utc)
            rr = row(int(d0.timestamp()), cl(r["open"]), cl(r["high"]),
                     cl(r["low"]), cl(r["close"]),
                     str(r.get("volume", "0")).replace(",", ""))
            if rr:
                out.append(rr)
        except (ValueError, KeyError, TypeError):
            continue
    return out, "Nasdaq"


SOURCES = [src_yahoo, src_yahoo2, src_stooq, src_nasdaq]


def fetch_daily(sym):
    errs = []
    for fn in SOURCES:
        try:
            rows, name = fn(sym)
            uniq = {r["time"]: r for r in rows}
            rows = [uniq[k] for k in sorted(uniq)]
            if len(rows) < MIN_ROWS:
                raise RuntimeError(f"행 수 부족 {len(rows)}")
            if errs:
                print(f"     건너뜀: {'; '.join(errs)}")
            return rows, name
        except Exception as e:
            errs.append(f"{fn.__name__.replace('src_', '')} {e}")
    raise RuntimeError(" | ".join(errs))


def to_weekly(daily):
    """ISO 주 단위. 주 라벨은 그 주 마지막 거래일."""
    b, order = {}, []
    for r in daily:
        k = datetime.fromtimestamp(r["time"], timezone.utc).isocalendar()[:2]
        if k not in b:
            b[k] = []
            order.append(k)
        b[k].append(r)
    out = []
    for k in order:
        g = b[k]
        out.append({"time": g[-1]["time"], "datetime_kst": g[-1]["datetime_kst"],
                    "open": g[0]["open"],
                    "high": f"{max(float(x['high']) for x in g):.4f}",
                    "low":  f"{min(float(x['low']) for x in g):.4f}",
                    "close": g[-1]["close"],
                    "volume": f"{sum(float(x['volume']) for x in g):.0f}",
                    "days": len(g)})
    return out


def write(path, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)
    return len(rows)


def main():
    os.makedirs(OUT, exist_ok=True)
    man = {"updated_kst": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"), "files": []}
    ok = 0
    for sym, prefix in TICKERS:
        try:
            daily, src = fetch_daily(sym)
            weekly = to_weekly(daily)
            nd = write(os.path.join(OUT, f"{prefix}_D.csv"), daily)
            nw = write(os.path.join(OUT, f"{prefix}_W.csv"), weekly)
            for nm, n, rws in ((f"{prefix}_D.csv", nd, daily), (f"{prefix}_W.csv", nw, weekly)):
                man["files"].append({"file": nm, "source": src, "bars": n,
                                     "first": rws[0]["datetime_kst"],
                                     "last": rws[-1]["datetime_kst"]})
            ok += 1
            print(f"OK   {prefix:10s} 일봉 {nd:5d}  주봉 {nw:4d}  [{src}]  "
                  f"{daily[0]['datetime_kst'][:10]} ~ {daily[-1]['datetime_kst'][:10]}")
        except Exception as e:
            print(f"FAIL {prefix:10s} {e}", file=sys.stderr)
        time.sleep(1.0)

    if man["files"]:
        with open(os.path.join(OUT, "manifest_etf.json"), "w") as f:
            json.dump(man, f, indent=2, ensure_ascii=False)
    if ok == 0:
        sys.exit("ETF 전부 실패 — 기존 CSV는 그대로 유지됨")
    print(f"\n{ok}/{len(TICKERS)} 성공")


if __name__ == "__main__":
    main()
