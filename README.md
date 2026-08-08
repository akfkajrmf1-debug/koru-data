# koru-data

KORUUSDT · SOXLUSDT 캔들을 Bybit 공개 API에서 받아 CSV로 커밋하는 저장소.
서버 불필요. API 키 불필요. GitHub Actions가 대신 실행한다.

## 세팅 (5분)

1. GitHub에서 새 저장소 생성 — 이름 `koru-data`, **Public**
   - Private으로 만들면 raw 링크에 토큰이 붙어서 Claude가 못 읽는다. 반드시 Public.
   - 시세 데이터라 공개해도 민감정보 없음.

2. 이 폴더의 파일 3개를 그대로 올린다.
   ```
   .github/workflows/fetch.yml
   scripts/fetch.py
   README.md
   ```

3. 저장소 → **Settings → Actions → General → Workflow permissions**
   → `Read and write permissions` 선택 후 Save
   - 이걸 안 하면 액션이 커밋을 push하지 못한다.

4. **Actions** 탭 → `fetch market data` → **Run workflow** 눌러 1회 수동 실행
   - 초록 체크 뜨면 `data/` 폴더에 CSV가 생긴다.

## 생성되는 파일

```
data/KORUUSDT_5.csv     5분봉   1000봉  (약 3.5일)
data/KORUUSDT_15.csv    15분봉  1000봉  (약 10일)
data/KORUUSDT_60.csv    1시간봉 1000봉  (약 41일)
data/KORUUSDT_240.csv   4시간봉  500봉  (약 83일)
data/KORUUSDT_D.csv     일봉     400봉
data/SOXLUSDT_*.csv     동일
data/manifest.json      마지막 갱신 시각 및 봉 수
```

주봉은 일봉 400개로 내가 리샘플하면 되므로 따로 받지 않는다.

## Claude에게 쓰는 법

세팅 후 아래 링크를 한 번만 알려주면 된다. `USERNAME`을 본인 것으로 바꿀 것.

```
https://raw.githubusercontent.com/USERNAME/koru-data/main/data/manifest.json
```

이후에는 "코루 봐줘" 한마디면 최신 데이터를 직접 읽어서 분석한다.
CSV를 매번 첨부할 필요 없음.

## 실행 주기

한국장(08–16 KST)과 미국 프리마켓~정규장(21 KST–05 KST) 시간대에 15분마다 실행.
장 안 여는 시간대는 건너뛴다.

주의: GitHub Actions의 cron은 정확한 시각을 보장하지 않는다.
부하가 몰리면 수 분에서 십수 분 지연될 수 있다.
실시간 체결용이 아니라 분석용 스냅샷이므로 문제되지 않는다.

## 심볼 추가

`scripts/fetch.py` 상단 `SYMBOLS` 리스트에 추가한다.

```python
SYMBOLS = [
    ("KORUUSDT", "linear"),
    ("SOXLUSDT", "linear"),
    ("BTCUSDT",  "linear"),   # 예시
]
```

## 문제 해결

- **액션이 빨간 X** → Actions 탭에서 로그 확인. 대부분 3번(권한) 누락.
- **커밋이 안 생김** → 데이터 변동이 없으면 커밋하지 않는다. 정상.
- **Bybit이 심볼 없다고 함** → `KORUUSDT`가 Bybit TradFi 카테고리라
  `category=linear`가 아닐 수 있다. 그 경우 fetch.py의 `SYMBOLS`에서
  `("KORUUSDT", "spot")`으로 바꿔 시도.
