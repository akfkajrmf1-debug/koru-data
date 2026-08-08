import csv, json, os, sys, time
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request

BASE = "https://api.bybit.com/v5/market/kline"
KST = timezone(timedelta(hours=9))
SYMBOLS = [("KORUUSDT", "linear"), ("SOXLUSDT", "linear")]
INTERVALS = ["5", "15", "60", "240", "D"]
LIMITS = {"5": 1000, "15": 1000, "60": 1000, "240": 500, "D": 400}
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

def get(url, tries=4):
    last = None
    for i in range(tries):
        try:
            req = Request(url, headers={"User-Agent": "koru-data/1.0"})
            with urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"fetch failed: {url} :: {last}")

def fetch(symbol, category, interval, limit):
    url = f"{BASE}?category={category}&symbol={symbol}&interval={interval}&limit={limit}"
    d = get(url)
    if d.get("retCode") != 0:
        raise RuntimeError(f"{symbol} {interval}: {d.get('retMsg')}")
    rows = d["result"]["list"]
    rows.reverse()
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

def main():
    os.makedirs(OUT, exist_ok=True)
    manifest = {"updated_kst": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"), "files": []}
    for symbol, category in SYMBOLS:
        for iv in INTERVALS:
            name = f"{symbol}_{iv}.csv"
            try:
                rows = fetch(symbol, category, iv, LIMITS.get(iv, 500))
                with open(os.path.join(OUT, name), "w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                    w.writeheader()
                    w.writerows(rows)
                manifest["files"].append({
                    "file": name, "symbol": symbol, "interval": iv, "bars": len(rows),
                    "first": rows[0]["datetime_kst"], "last": rows[-1]["datetime_kst"],
                })
                print(f"OK {name} {len(rows)} bars")
            except Exception as e:
                print(f"FAIL {name} {e}", file=sys.stderr)
            time.sleep(0.3)
    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    if not manifest["files"]:
        sys.exit("모든 요청 실패")

if __name__ == "__main__":
    main()
