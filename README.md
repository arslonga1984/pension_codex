# pension_codex

## API 실행

```bash
uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
```

## Health check

```bash
curl -s http://127.0.0.1:8000/health
```

## 추천 요청 예시

```bash
curl -s -X POST http://127.0.0.1:8000/recommend \
  -H 'Content-Type: application/json' \
  -d '{
    "current_balance_krw": 15000000,
    "monthly_contribution_krw": 700000,
    "start_date": "2026-01-01",
    "retirement_date": "2040-01-01",
    "target_cagr": 6.5,
    "max_mdd": 22.0,
    "fee_annual": 0.004,
    "inflation": 0.025
  }'
```

## 데이터 준비

`/recommend` 호출 전 아래 파일이 필요합니다.

- `data/universe.csv`
- `data/returns_monthly.parquet`

생성 커맨드:

```bash
python -m packages.data.build_returns
```

## 데모 사용법(스크린샷 없이도)

1. API 서버 실행

```bash
python -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
```

2. 웹 UI 실행(정적 파일)

```bash
python -m http.server 4173 --directory apps/web
```

3. 브라우저에서 접속

- `http://127.0.0.1:4173`
- 입력 폼 작성 후 **추천 받기** 클릭
- 결과 카드/테이블/차트가 렌더링되며, 새로고침해도 localStorage 기반으로 유지됩니다.

4. 데이터 파일이 없을 때

- `/recommend`는 500 대신 설치 가이드 포함 에러를 반환합니다.
- 아래 커맨드로 수익률 데이터 생성 후 다시 시도합니다.

```bash
python -m packages.data.build_returns
```

## 유니버스 구축/보강 후 엔진 사용

1. 유니버스 준비 (`data/universe.csv`)

- 권장 컬럼: `ticker,name_kr,aum_krw,expense_ratio`
- 최소 `ticker`만 있어도 동작하지만, `name_kr/aum_krw`가 있으면 자산군 분류와 대표 ETF 선택이 더 안정적입니다.

2. 자산군 보강 실행

```bash
python -m packages.data.enrich_universe
```

- 출력 파일: `data/universe_enriched.csv` (`asset_class` 자동 추가)

3. 월 수익률 생성

```bash
python -m packages.data.build_returns
```

4. API/엔진 사용

```bash
python -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
```


## PDF 리포트 생성

- API: `POST /report` (요청 body는 `/recommend`와 동일)
- 응답: `application/pdf` 바이너리
- 웹 UI 결과 화면의 **PDF 리포트 다운로드** 버튼으로 호출 가능

예시:

```bash
curl -X POST http://127.0.0.1:8000/report \
  -H 'Content-Type: application/json' \
  -d '{"current_balance_krw":10000000,"monthly_contribution_krw":500000,"start_date":"2026-01-01","retirement_date":"2040-01-01","target_cagr":6.0,"max_mdd":20.0}' \
  --output retirement_report.pdf
```
