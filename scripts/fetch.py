import csv, json, os, sys, time
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request

KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
      "Accept": "application/json"}

SYMBOLS = ["KORUUSDT", "SOXLUSDT"]
INTERVALS = {"5": ("min5","5m"), "15": ("min15","15m"), "60": ("hour1","1h"),
             "240": ("hour4","4h"), "D": ("day1","1d")}
LIMIT = 500
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

def get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            with urlopen(Request(url, headers=UA), timeout=25) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            last = e; time.sleep(1.5*(i+1))
    raise RuntimeError(str(last))

def norm(ms, o, h, l, c, v):
    dt = datetime.fromtimestamp(int(ms)/1000, KST)
    return {"time": int(ms)//1000, "datetime_kst": dt.strftime("%Y-%m-%d %H:%M:%S"),
            "open": o, "high": h, "low": l, "close": c, "volume": v}

def from_bigone(sym, iv):
    per = INTERVALS[iv][0]
    for tpl in (f"https://big.one/api/contract/v2/instruments/{sym}/mcandles?limit={LIMIT}&period={per}",
                f"https://big.one/api/contract/v2/instruments/{sym}/candles?limit={LIMIT}&period={per}"):
        try:
            d = get(tpl)
        except Exception:
            continue
        rows = d.get("data", d) if isinstance(d, dict) else d
        if not isinstance(rows, list) or not rows:
            continue
        out = []
        for r in rows:
            if isinstance(r, dict):
                ts = r.get("time") or r.get("timestamp") or r.get("t")
                ms = int(ts) if int(ts) > 10**12 else int(ts)*1000
                out.append(norm(ms, r.get("open"), r.get("high"), r.get("low"),
                                r.get("close"), r.get("volume", r.get("vol", 0))))
            else:
                ms = int(r[0]) if int(r[0]) > 10**12 else int(r[0])*1000
                out.append(norm(ms, r[1], r[2], r[3], r[4], r[5] if len(r) > 5 else 0))
        out.sort(key=lambda x: x["time"])
        if out:
            return out, "BigONE"
    raise RuntimeError("BigONE 파싱 실패")

def from_gate(sym, iv):
    gsym = sym.replace("USDT", "_USDT")
    url = (f"https://api.gateio.ws/api/v4/futures/usdt/candlesticks"
           f"?contract={gsym}&interval={INTERVALS[iv][1]}&limit={LIMIT}")
    rows = get(url)
    out = [norm(int(r["t"])*1000, r["o"], r["h"], r["l"], r["c"], r.get("v", 0)) for r in rows]
    out.sort(key=lambda x: x["time"])
    if not out:
        raise RuntimeError("Gate 빈 응답")
    return out, "Gate.io"

def main():
    os.makedirs(OUT, exist_ok=True)
    manifest = {"updated_kst": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"), "files": []}
    for sym in SYMBOLS:
        for iv in INTERVALS:
            name = f"{sym}_{iv}.csv"
            rows = src = None
            for fn in (from_bigone, from_gate):
                try:
                    rows, src = fn(sym, iv); break
                except Exception as e:
                    print(f"  {fn.__name__} 실패 {name}: {e}", file=sys.stderr)
            if not rows:
                print(f"FAIL {name}", file=sys.stderr); continue
            with open(os.path.join(OUT, name), "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)
            manifest["files"].append({"file": name, "symbol": sym, "interval": iv,
                "source": src, "bars": len(rows), "first": rows[0]["datetime_kst"],
                "last": rows[-1]["datetime_kst"]})
            print(f"OK {name:20s} {len(rows):4d}봉  {src:8s} {rows[0]['datetime_kst']} ~ {rows[-1]['datetime_kst']}")
            time.sleep(0.4)
    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\n총 {len(manifest['files'])}개 저장")
    if not manifest["files"]:
        sys.exit("전부 실패")

if __name__ == "__main__":
    main()
