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

# 인터벌별 보관 상한 (행 수). 5분 60000 = 약 208일치.
CAP = {"5": 60000, "15": 40000, "60": 20000, "240": 10000, "D": 5000}

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

# ---------------------------------------------------------------- 이어붙이기
def merge(path, new_rows, cap):
    """기존 CSV와 신규 응답을 time 기준으로 합친다.
    같은 time이면 신규가 이긴다 — 직전 저장 때 미완성이던 봉이 확정본으로 갱신된다.
    기존 파일이 없거나 깨져 있으면 신규만 저장한다.
    """
    old = {}
    if os.path.exists(path):
        try:
            with open(path, newline="") as f:
                for r in csv.DictReader(f):
                    t = r.get("time")
                    if t and str(t).strip().isdigit():
                        old[int(t)] = r
        except Exception as e:
            print(f"  기존 파일 무시 {os.path.basename(path)}: {e}", file=sys.stderr)
            old = {}

    before = len(old)
    for r in new_rows:
        old[int(r["time"])] = r

    rows = [old[k] for k in sorted(old)]
    if cap and len(rows) > cap:
        rows = rows[-cap:]

    cols = list(new_rows[0].keys())
    tmp = path + ".tmp"
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    os.replace(tmp, path)          # 원자적 교체 — 중간에 죽어도 원본 안 깨짐
    return len(rows), len(rows) - before

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

            total, added = merge(os.path.join(OUT, name), rows, CAP.get(iv))

            with open(os.path.join(OUT, name), newline="") as f:
                allrows = list(csv.DictReader(f))
            manifest["files"].append({"file": name, "symbol": sym, "interval": iv,
                "source": src, "bars": total, "added": added,
                "first": allrows[0]["datetime_kst"], "last": allrows[-1]["datetime_kst"]})
            print(f"OK {name:20s} {total:6d}봉 (+{added:3d})  {src:8s} "
                  f"{allrows[0]['datetime_kst']} ~ {allrows[-1]['datetime_kst']}")
            time.sleep(0.4)
    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\n총 {len(manifest['files'])}개 저장")
    if not manifest["files"]:
        sys.exit("전부 실패")

if __name__ == "__main__":
    main()
