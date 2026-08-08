import json
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

TESTS = [
    ("Binance  KORUUSDT 5m", "https://fapi.binance.com/fapi/v1/klines?symbol=KORUUSDT&interval=5m&limit=3"),
    ("Binance  SOXLUSDT 5m", "https://fapi.binance.com/fapi/v1/klines?symbol=SOXLUSDT&interval=5m&limit=3"),
    ("Binance  심볼목록", "https://fapi.binance.com/fapi/v1/exchangeInfo"),
    ("Bybit    KORUUSDT 5m", "https://api.bybit.com/v5/market/kline?category=linear&symbol=KORUUSDT&interval=5&limit=3"),
    ("BigONE   심볼목록", "https://big.one/api/contract/v2/instruments"),
    ("OKX      심볼목록", "https://www.okx.com/api/v5/public/instruments?instType=SWAP"),
    ("Gate.io  심볼목록", "https://api.gateio.ws/api/v4/futures/usdt/contracts"),
    ("Stooq    KORU 일봉", "https://stooq.com/q/d/l/?s=koru.us&i=d"),
]

def probe(label, url):
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "*/*",
    })
    try:
        with urlopen(req, timeout=20) as r:
            body = r.read(400).decode("utf-8", "replace")
            print(f"[{r.status}] {label}")
            print(f"      {body[:220]}")
            return True
    except HTTPError as e:
        try:
            msg = e.read(200).decode("utf-8", "replace")
        except Exception:
            msg = ""
        print(f"[{e.code}] {label}   {msg[:150]}")
    except URLError as e:
        print(f"[ERR] {label}   {e.reason}")
    except Exception as e:
        print(f"[ERR] {label}   {type(e).__name__}: {e}")
    return False

def main():
    ok = []
    for label, url in TESTS:
        if probe(label, url):
            ok.append(label)
        print("-" * 70)
    print()
    print("접근 성공:", ", ".join(ok) if ok else "없음")

if __name__ == "__main__":
    main()
