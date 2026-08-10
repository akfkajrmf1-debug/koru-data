#!/usr/bin/env python3
"""
셋업을 기록하고, 시간이 지나면 CSV로 결과를 자동 판정한다.
사후 수정이 불가능하도록 커밋 시각이 증거가 된다.

  python scripts/record.py add '<json>'   셋업 1건 기록
  python scripts/record.py resolve        미판정 건 결과 채움
  python scripts/record.py stats          누적 성적 출력
"""
import csv, json, os, sys
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
LOG = os.path.join(DATA, "setups.jsonl")
FMT = "%Y-%m-%d %H:%M:%S"

REQUIRED = ["id", "ts", "sym", "dir", "entry", "stop", "tp"]


def load():
    if not os.path.exists(LOG):
        return []
    out = []
    with open(LOG) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def save(rows):
    tmp = LOG + ".tmp"
    with open(tmp, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, LOG)


def add(payload):
    s = json.loads(payload)
    for k in REQUIRED:
        if k not in s:
            sys.exit(f"필수 항목 없음: {k}")
    if s["dir"] not in ("long", "short"):
        sys.exit("dir은 long 또는 short")
    s.setdefault("horizon_h", 24)
    s.setdefault("result", None)
    rows = load()
    if any(r["id"] == s["id"] for r in rows):
        sys.exit(f"중복 id: {s['id']}")
    rows.append(s)
    save(rows)
    print(f"기록됨 {s['id']}  {s['dir']} {s['entry']} 손절 {s['stop']}")


def bars_after(sym, ts_str, interval="5"):
    path = os.path.join(DATA, f"{sym}_{interval}.csv")
    if not os.path.exists(path):
        return []
    t0 = int(datetime.strptime(ts_str, FMT).replace(tzinfo=KST).timestamp())
    out = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            try:
                t = int(r["time"])
            except (ValueError, TypeError, KeyError):
                continue
            if t >= t0:
                out.append((t, float(r["open"]), float(r["high"]),
                            float(r["low"]), float(r["close"])))
    out.sort()
    return out


def judge(s, bars):
    """진입 도달 -> 손절/목표 선착 순으로 판정한다.
    한 봉 안에서 손절과 목표가 같이 닿으면 손절로 센다 (보수적).
    """
    lo, hi = min(s["entry"]), max(s["entry"])
    long = s["dir"] == "long"
    stop, tps = float(s["stop"]), [float(x) for x in s["tp"]]
    risk = abs((lo + hi) / 2 - stop)

    fill_i = None
    for i, (t, o, h, l, c) in enumerate(bars):
        if l <= hi and h >= lo:          # 진입 구간을 관통
            fill_i = i
            fill_t = t
            break
    if fill_i is None:
        return {"outcome": "no_fill", "bars_scanned": len(bars)}

    entry = (lo + hi) / 2
    mfe = mae = 0.0
    hit = None
    for t, o, h, l, c in bars[fill_i:]:
        up, dn = (h - entry), (entry - l)
        mfe = max(mfe, up if long else dn)
        mae = max(mae, dn if long else up)
        stopped = (l <= stop) if long else (h >= stop)
        reached = [j for j, tp in enumerate(tps)
                   if ((h >= tp) if long else (l <= tp))]
        if stopped:
            hit = ("stop", t); break
        if reached:
            hit = (f"tp{max(reached)+1}", t); break

    res = {
        "filled": True,
        "fill_kst": datetime.fromtimestamp(fill_t, KST).strftime(FMT),
        "mfe_R": round(mfe / risk, 2) if risk else None,
        "mae_R": round(mae / risk, 2) if risk else None,
        "bars_scanned": len(bars),
    }
    if hit:
        res["outcome"] = hit[0]
        res["closed_kst"] = datetime.fromtimestamp(hit[1], KST).strftime(FMT)
        if hit[0] == "stop":
            res["R"] = -1.0
        else:
            k = int(hit[0][2:]) - 1
            res["R"] = round(abs(tps[k] - entry) / risk, 2) if risk else None
    else:
        res["outcome"] = "open"
    return res


def resolve():
    rows = load()
    now = datetime.now(KST)
    changed = 0
    for s in rows:
        if s.get("result"):
            continue
        t0 = datetime.strptime(s["ts"], FMT).replace(tzinfo=KST)
        bars = bars_after(s["sym"], s["ts"])
        if not bars:
            continue
        r = judge(s, bars)
        expired = now >= t0 + timedelta(hours=s.get("horizon_h", 24))
        # 확정됐거나 기한이 지났을 때만 결과를 박는다
        if r["outcome"] in ("stop",) or r["outcome"].startswith("tp") or expired:
            if r["outcome"] == "open" and expired:
                r["outcome"] = "expired"
            if r["outcome"] == "no_fill" and not expired:
                continue
            s["result"] = r
            s["resolved_kst"] = now.strftime(FMT)
            changed += 1
            print(f"판정 {s['id']:16s} {r['outcome']:8s} R={r.get('R','-')}")
    if changed:
        save(rows)
    print(f"판정 {changed}건 / 전체 {len(rows)}건")


def stats():
    rows = [r for r in load() if r.get("result")]
    if not rows:
        print("판정된 셋업 없음"); return
    filled = [r for r in rows if r["result"].get("filled")]
    closed = [r for r in filled if r["result"].get("R") is not None]
    print(f"기록 {len(rows)}건 · 체결 {len(filled)}건 "
          f"(체결률 {len(filled)/len(rows)*100:.0f}%) · 종료 {len(closed)}건")
    if closed:
        wins = [r for r in closed if r["result"]["R"] > 0]
        tot = sum(r["result"]["R"] for r in closed)
        print(f"승률 {len(wins)/len(closed)*100:.0f}%  "
              f"누적 {tot:+.2f}R  건당 {tot/len(closed):+.2f}R")
        for d in ("long", "short"):
            g = [r for r in closed if r["dir"] == d]
            if g:
                t = sum(r["result"]["R"] for r in g)
                print(f"  {d:5s} {len(g):3d}건  승률 "
                      f"{sum(1 for r in g if r['result']['R']>0)/len(g)*100:3.0f}%  {t:+.2f}R")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "add" and len(sys.argv) > 2:
        add(sys.argv[2])
    elif cmd == "resolve":
        resolve()
    elif cmd == "stats":
        stats()
    else:
        sys.exit(__doc__)
