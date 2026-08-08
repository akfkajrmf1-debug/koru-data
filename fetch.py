#!/usr/bin/env python3
"""
Bybit 공개 API에서 캔들을 받아 CSV로 저장한다.
API 키 불필요. 서버 불필요. GitHub Actions에서 실행된다.
"""
import csv, json, os, sys, time
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

BASE = "https://api.bybit.com/v5/market/kline"
KST = timezone(timedelta(hours=9))

# (심볼, 카테고리) — linear = USDT 무기한
SYMBOLS = [
    ("KORUUSDT", "linear"),
    ("SOXLUSDT", "linear"),
]

# 인터벌: 분 단위 문자열. D = 일봉, W = 주봉
INTERVALS = ["5", "15", "60", "240", "D"]

# 인터벌별로 받아올 봉 개수 (Bybit 1회 최대 1000)
LIMITS = {"5": 1000, "15": 1000, "60": 1000, "240": 500, "D": 400}

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def get(url, tries=4):
    last = None
    for i in range(tries):
        try:
            req = Request(url, headers={"User-Agent": "koru-data/1.0"})
            with urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except (URLError, HTTPError, TimeoutError) as e:
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"fetch failed: {url} :: {last}")


def fetch(symbol, category, interval, limit):
    url = f"{BASE}?category={category}&symbol={symbol}&interval={interval}&limit={limit}"
    d = get(url)
    if d.get("retCode") != 0:
        raise RuntimeError(f"{symbol} {interval}: {d.get('retMsg')}")
    rows = d["result"]["list"]          # 최신순으로 온다
    rows.reverse()                       # 과거 -> 최신
    out = []
    for r in rows:
        ms = int(r[0])
        dt = datetime.fromtimestamp(ms / 1000, KST)
        out.append({
            "time": ms // 1000,
            "datetime_kst": dt.strftime("%Y-%m-%d %H:%M:%S"),
            "open": r[1], "high": r[2], "low": r[3], "close": r[4],
            "volume": r[5], "turnover": r[6],
        })
    return out


def write(path, rows):
    if not rows:
        return 0
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def main():
    os.makedirs(OUT, exist_ok=True)
    manifest = {
        "updated_kst": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
        "files": [],
    }
    failed = []

    for symbol, category in SYMBOLS:
        for iv in INTERVALS:
            name = f"{symbol}_{iv}.csv"
            try:
                rows = fetch(symbol, category, iv, LIMITS.get(iv, 500))
                n = write(os.path.join(OUT, name), rows)
                manifest["files"].append({
                    "file": name, "symbol": symbol, "interval": iv, "bars": n,
                    "first": rows[0]["datetime_kst"], "last": rows[-1]["datetime_kst"],
                })
                print(f"OK   {name:24s} {n:5d} bars  {rows[0]['datetime_kst']} ~ {rows[-1]['datetime_kst']}")
            except Exception as e:
                failed.append(f"{name}: {e}")
                print(f"FAIL {name:24s} {e}", file=sys.stderr)
            time.sleep(0.3)   # 레이트리밋 여유

    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    if not manifest["files"]:
        sys.exit("모든 요청 실패")
    if failed:
        print(f"\n일부 실패 {len(failed)}건 — 나머지는 저장됨", file=sys.stderr)


if __name__ == "__main__":
    main()
