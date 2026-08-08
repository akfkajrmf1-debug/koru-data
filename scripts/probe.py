import json
from urllib.request import urlopen, Request

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

def get(url):
    return json.loads(urlopen(Request(url, headers=UA), timeout=25).read().decode())

for name, url in [
    ("BigONE",  "https://big.one/api/contract/v2/instruments"),
    ("Gate.io", "https://api.gateio.ws/api/v4/futures/usdt/contracts"),
]:
    print("="*60); print(name)
    try:
        d = get(url)
        items = d if isinstance(d, list) else d.get("data", d)
        txt = json.dumps(items)
        hits = [s for s in items if "KORU" in json.dumps(s).upper() or "SOXL" in json.dumps(s).upper()]
        print(f"  전체 {len(items)}개 / KORU·SOXL 매칭 {len(hits)}개")
        for h in hits[:10]:
            print("   ", json.dumps(h, ensure_ascii=False)[:200])
    except Exception as e:
        print("  ERR", e)
