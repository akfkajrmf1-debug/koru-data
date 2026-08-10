#!/usr/bin/env python3
"""
Stooq에서 원본 ETF 일봉을 받아 저장하고, 주봉으로 리샘플한다.
무기한 계약(2026-07-22 상장)에는 없는 장기 구조를 여기서 얻는다.
API 키 불필요. 표준 라이브러리만 사용.
"""
import csv, io, json, os, sys, time
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request

KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

# (stooq 심볼, 출력 접두사)
TICKERS = [
    ("koru.us", "KORU_ETF"),   # 원본 3x ETF — 레벨용
    ("ewy.us",  "EWY_ETF"),    # 1x 한국 — 감쇠 없는 추세 판정용
    ("soxl.us", "SOXL_ETF"),
    ("soxx.us", "SOXX_ETF"),   # 1x 반도체
]

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
MIN_ROWS = 100   # 이보다 적게 오면 실패로 간주 (stooq가 빈 응답을 200으로 주는 경우 있음)


def get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            with urlopen(Request(url, headers=UA), timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(str(last))


def fetch_daily(sym):
    txt = get(f"https://stooq.com/q/d/l/?s={sym}&i=d")
    if "Date" not in txt.split("\n")[0]:
        raise RuntimeError(f"예상치 못한 응답: {txt[:120]!r}")
    rows = []
    for r in csv.DictReader(io.StringIO(txt)):
        try:
            d = datetime.strptime(r["Date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            rows.append({
                "time": int(d.timestamp()),
                "datetime_kst": r["Date"] + " 00:00:00",
                "open": r["Open"], "high": r["High"],
                "low": r["Low"], "close": r["Close"],
                "volume": r.get("Volume", "0") or "0",
            })
        except (ValueError, KeyError):
            continue          # 빈 줄 / 결측 행 건너뜀
    rows.sort(key=lambda x: x["time"])
    if len(rows) < MIN_ROWS:
        raise RuntimeError(f"행 수 부족 {len(rows)}")
    return rows


def to_weekly(daily):
    """ISO 주 단위로 묶는다. 주 라벨은 그 주의 마지막 거래일."""
    buckets = {}
    order = []
    for r in daily:
        d = datetime.fromtimestamp(r["time"], timezone.utc)
        key = d.isocalendar()[:2]          # (연, 주차)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(r)

    out = []
    for key in order:
        g = buckets[key]
        out.append({
            "time": g[-1]["time"],
            "datetime_kst": g[-1]["datetime_kst"],
            "open": g[0]["open"],
            "high": f"{max(float(x['high']) for x in g):.4f}",
            "low":  f"{min(float(x['low'])  for x in g):.4f}",
            "close": g[-1]["close"],
            "volume": f"{sum(float(x['volume'] or 0) for x in g):.0f}",
            "days": len(g),                # 미완성 주 판별용
        })
    return out


def write(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def main():
    os.makedirs(OUT, exist_ok=True)
    mpath = os.path.join(OUT, "manifest_etf.json")
    manifest = {"updated_kst": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
                "source": "stooq.com", "files": []}
    failed = []

    for sym, prefix in TICKERS:
        try:
            daily = fetch_daily(sym)
            weekly = to_weekly(daily)
            nd = write(os.path.join(OUT, f"{prefix}_D.csv"), daily)
            nw = write(os.path.join(OUT, f"{prefix}_W.csv"), weekly)
            for nm, n, rws in ((f"{prefix}_D.csv", nd, daily), (f"{prefix}_W.csv", nw, weekly)):
                manifest["files"].append({
                    "file": nm, "bars": n,
                    "first": rws[0]["datetime_kst"], "last": rws[-1]["datetime_kst"],
                })
            print(f"OK   {prefix:10s} 일봉 {nd:5d}  주봉 {nw:4d}   "
                  f"{daily[0]['datetime_kst'][:10]} ~ {daily[-1]['datetime_kst'][:10]}")
        except Exception as e:
            failed.append(f"{sym}: {e}")
            print(f"FAIL {prefix:10s} {e}", file=sys.stderr)
        time.sleep(1.0)       # stooq 예의

    with open(mpath, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    if not manifest["files"]:
        sys.exit("ETF 전부 실패 — 기존 CSV는 유지됨")
    if failed:
        print(f"\n일부 실패 {len(failed)}건", file=sys.stderr)


if __name__ == "__main__":
    main()
