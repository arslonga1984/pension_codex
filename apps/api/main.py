from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field, model_validator

from apps.api.reporting import build_report_filename, generate_report_pdf
from packages.engine.v0 import EngineInput, run_engine_v0

app = FastAPI(title="Pension Codex API", version="0.1.0")

ROOT = Path(__file__).resolve().parents[2]
UNIVERSE_PATH = ROOT / "data" / "universe.csv"
RETURNS_PATH = ROOT / "data" / "returns_monthly.parquet"


class RecommendRequest(BaseModel):
    current_balance_krw: float = Field(ge=0)
    monthly_contribution_krw: float = Field(ge=0)
    start_date: str
    retirement_age: int | None = Field(default=None, ge=55)
    retirement_date: str | None = None
    target_cagr: float
    max_mdd: float = Field(gt=0, lt=100)
    fee_annual: float = Field(default=0.004, ge=0)
    inflation: float = Field(default=0.025, ge=0)
    current_age: int | None = Field(default=None, ge=0)

    withdrawal_mode: Literal["target_years", "fixed_monthly"] = "target_years"
    target_years: int = Field(default=20, ge=1)
    fixed_monthly_withdrawal_krw: float | None = Field(default=None, ge=0)
    retirement_return_haircut_pct: float = Field(default=1.0, ge=0)
    retirement_fee_annual: float = Field(default=0.004, ge=0)

    @model_validator(mode="after")
    def validate_rules(self) -> "RecommendRequest":
        if self.retirement_age is None and self.retirement_date is None:
            raise ValueError("Either retirement_age (>=55) or retirement_date must be provided.")
        if self.withdrawal_mode == "fixed_monthly" and not self.fixed_monthly_withdrawal_krw:
            raise ValueError("fixed_monthly_withdrawal_krw is required when withdrawal_mode=fixed_monthly")
        return self


def _missing_data_error(missing_paths: list[Path]) -> HTTPException:
    missing = [str(path.relative_to(ROOT)) for path in missing_paths]
    detail = {
        "message": "필수 데이터 파일이 없습니다. 엔진 실행 전 데이터 설치/생성을 완료하세요.",
        "missing_files": missing,
        "install_guide": [
            "1) 유니버스 파일 준비: data/universe.csv (ticker 컬럼 포함)",
            "2) 자산군 보강: python -m packages.data.enrich_universe",
            "3) 월 수익률 생성: python -m packages.data.build_returns",
            "4) 생성 확인: data/returns_monthly.parquet 존재 여부 확인",
        ],
    }
    return HTTPException(status_code=503, detail=detail)


def _ensure_data_files() -> None:
    missing_paths = [path for path in [UNIVERSE_PATH, RETURNS_PATH] if not path.exists()]
    if missing_paths:
        raise _missing_data_error(missing_paths)


def _build_engine_input(request: RecommendRequest) -> EngineInput:
    return EngineInput(
        current_balance_krw=request.current_balance_krw,
        monthly_contribution_krw=request.monthly_contribution_krw,
        start_date=request.start_date,
        retirement_age=request.retirement_age,
        retirement_date=request.retirement_date,
        current_age=request.current_age,
        target_cagr=request.target_cagr,
        max_mdd=request.max_mdd,
        fee_annual=request.fee_annual,
        inflation=request.inflation,
        withdrawal_mode=request.withdrawal_mode,
        target_years=request.target_years,
        fixed_monthly_withdrawal_krw=request.fixed_monthly_withdrawal_krw,
        retirement_return_haircut_pct=request.retirement_return_haircut_pct,
        retirement_fee_annual=request.retirement_fee_annual,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/recommend")
def recommend(request: RecommendRequest) -> dict:
    _ensure_data_files()
    try:
        return run_engine_v0(_build_engine_input(request))
    except FileNotFoundError as exc:
        if "returns_monthly.parquet" in str(exc):
            raise _missing_data_error([RETURNS_PATH]) from exc
        raise HTTPException(status_code=500, detail={"message": str(exc)}) from exc
    except ModuleNotFoundError as exc:
        if "pandas" in str(exc):
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "필수 의존성 누락: pandas",
                    "install_guide": [
                        "python -m pip install pandas pyarrow",
                        "python -m packages.data.enrich_universe",
                        "python -m packages.data.build_returns",
                    ],
                },
            ) from exc
        raise HTTPException(status_code=500, detail={"message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc


@app.post("/report")
def report(request: RecommendRequest) -> Response:
    result = recommend(request)
    payload = request.model_dump()
    pdf_bytes = generate_report_pdf(payload, result)
    filename = build_report_filename()
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)
