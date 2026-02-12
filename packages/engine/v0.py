from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import pstdev
from typing import Any

import csv

from .universe import select_representative_etfs

ROOT = Path(__file__).resolve().parents[2]
RETURNS_PATH = ROOT / "data" / "returns_monthly.parquet"
UNIVERSE_ENRICHED_PATH = ROOT / "data" / "universe_enriched.csv"

TARGET_BLEND_WEIGHT_HISTORY = 0.6
TARGET_BLEND_WEIGHT_USER = 0.4
DEFAULT_FEE_ANNUAL = 0.004
DEFAULT_INFLATION = 0.025

EQUITY_PRIORITY = ["SPY", "VOO", "IVV", "VTI", "QQQ", "IWM", "EFA", "EEM"]
BOND_PRIORITY = ["IEF", "VGSH", "SHY", "BIL", "TLT", "AGG", "LQD"]
REIT_PRIORITY = ["VNQ", "SCHH", "IYR"]

ETF_NAME_KR = {
    "SPY": "미국 S&P500 ETF",
    "VOO": "미국 S&P500 ETF",
    "IVV": "미국 S&P500 ETF",
    "VTI": "미국 전체주식 ETF",
    "QQQ": "미국 나스닥100 ETF",
    "IWM": "미국 중소형주 ETF",
    "EFA": "선진국 주식 ETF",
    "EEM": "신흥국 주식 ETF",
    "IEF": "미국 중기국채 ETF",
    "VGSH": "미국 단기국채 ETF",
    "SHY": "미국 단기국채 ETF",
    "BIL": "미국 초단기국채 ETF",
    "TLT": "미국 장기국채 ETF",
    "AGG": "미국 종합채권 ETF",
    "LQD": "미국 회사채 ETF",
    "VNQ": "미국 리츠 ETF",
    "SCHH": "미국 리츠 ETF",
    "IYR": "미국 리츠 ETF",
}


@dataclass
class EngineInput:
    current_balance_krw: float
    monthly_contribution_krw: float
    start_date: str
    target_cagr: float
    max_mdd: float
    retirement_date: str | None = None
    retirement_age: int | None = None
    current_age: int | None = None
    fee_annual: float = DEFAULT_FEE_ANNUAL
    inflation: float = DEFAULT_INFLATION


def _parse_date(iso_date: str) -> date:
    return date.fromisoformat(iso_date)


def _month_ends_between(start: date, end: date) -> list[date]:
    if end <= start:
        return []

    y, m = start.year, start.month
    months: list[date] = []
    while (y, m) <= (end.year, end.month):
        next_month_start = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
        month_end = date.fromordinal(next_month_start.toordinal() - 1)
        if start < month_end <= end:
            months.append(month_end)
        y, m = next_month_start.year, next_month_start.month
    return months


def _resolve_retirement_date(input_data: EngineInput, warnings: list[str]) -> date:
    start = _parse_date(input_data.start_date)
    if input_data.retirement_date:
        resolved = _parse_date(input_data.retirement_date)
        if resolved <= start:
            raise ValueError("retirement_date must be after start_date")
        return resolved

    if input_data.retirement_age is None:
        raise ValueError("Either retirement_date or retirement_age is required.")
    if input_data.retirement_age < 55:
        raise ValueError("retirement_age must be >= 55")

    current_age = input_data.current_age if input_data.current_age is not None else 35
    if input_data.current_age is None:
        warnings.append("current_age not provided; assumed 35 for retirement_age conversion.")

    years = input_data.retirement_age - current_age
    if years <= 0:
        raise ValueError("retirement_age must be greater than current_age")

    return date(start.year + years, start.month, start.day)


def _load_returns(path: Path = RETURNS_PATH) -> dict[str, list[tuple[str, float]]]:
    import pandas as pd

    if not path.exists():
        raise FileNotFoundError(f"Returns parquet not found: {path}")

    df = pd.read_parquet(path)
    required = {"ticker", "date", "return"}
    if not required.issubset(df.columns):
        raise ValueError(f"returns_monthly.parquet must contain columns: {required}")

    grouped: dict[str, list[tuple[str, float]]] = {}
    for ticker, g in df.groupby("ticker"):
        rows = sorted(
            [
                (pd.to_datetime(r["date"]).date().isoformat(), float(r["return"]))
                for _, r in g.dropna(subset=["return"]).iterrows()
            ],
            key=lambda x: x[0],
        )
        if rows:
            grouped[str(ticker)] = rows
    return grouped


def _load_enriched_universe_rows() -> list[dict[str, str]]:
    if not UNIVERSE_ENRICHED_PATH.exists():
        return []

    with UNIVERSE_ENRICHED_PATH.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _pick_assets(returns_by_ticker: dict[str, list[tuple[str, float]]], warnings: list[str]) -> dict[str, list[str]]:
    return_universe = set(returns_by_ticker.keys())

    enriched_rows = _load_enriched_universe_rows()
    enriched_rows = [row for row in enriched_rows if row.get("ticker") in return_universe]

    equities: list[str] = []
    bonds: list[str] = []
    reits: list[str] = []

    if enriched_rows:
        equity_rows = (
            select_representative_etfs(enriched_rows, "us_equity", top_k=2)
            + select_representative_etfs(enriched_rows, "global_equity", top_k=2)
            + select_representative_etfs(enriched_rows, "korea_equity", top_k=2)
        )
        seen: set[str] = set()
        for row in equity_rows:
            ticker = str(row.get("ticker", "")).strip()
            if ticker and ticker not in seen:
                seen.add(ticker)
                equities.append(ticker)
            if len(equities) >= 2:
                break

        bond_rows = (
            select_representative_etfs(enriched_rows, "korea_treasury", top_k=2)
            + select_representative_etfs(enriched_rows, "korea_short", top_k=2)
            + select_representative_etfs(enriched_rows, "korea_credit", top_k=2)
        )
        seen = set()
        for row in bond_rows:
            ticker = str(row.get("ticker", "")).strip()
            if ticker and ticker not in seen:
                seen.add(ticker)
                bonds.append(ticker)
            if len(bonds) >= 2:
                break

        reit_rows = select_representative_etfs(enriched_rows, "reits", top_k=1)
        reits = [str(row.get("ticker", "")).strip() for row in reit_rows if str(row.get("ticker", "")).strip()]

    if not equities:
        equities = [t for t in EQUITY_PRIORITY if t in return_universe][:2]
    if not bonds:
        bonds = [t for t in BOND_PRIORITY if t in return_universe][:2]
    if not reits:
        reits = [t for t in REIT_PRIORITY if t in return_universe][:1]

    if len(equities) < 1 or len(bonds) < 1:
        raise ValueError("Not enough ETF coverage in returns data (need >=1 equity and >=1 bond).")

    if not reits:
        warnings.append("REIT ETF not available in universe; REIT allocation fixed at 0%.")

    return {"equities": equities, "bonds": bonds, "reits": reits}


def _series_map(rows: list[tuple[str, float]]) -> dict[str, float]:
    return {d: r for d, r in rows}


def _portfolio_monthly_returns(weights: dict[str, float], returns_by_ticker: dict[str, list[tuple[str, float]]]) -> list[float]:
    maps = {t: _series_map(returns_by_ticker[t]) for t in weights}
    common_dates = sorted(set.intersection(*[set(m.keys()) for m in maps.values()]))
    return [sum(weights[t] * maps[t][d] for t in weights) for d in common_dates]


def _annualized_return(monthly_returns: list[float]) -> float:
    if not monthly_returns:
        return 0.0
    wealth = 1.0
    for r in monthly_returns:
        wealth *= 1.0 + r
    return wealth ** (12.0 / len(monthly_returns)) - 1.0


def _annualized_vol(monthly_returns: list[float]) -> float:
    if len(monthly_returns) < 2:
        return 0.0
    return pstdev(monthly_returns) * math.sqrt(12.0)


def _mdd(monthly_returns: list[float]) -> float:
    wealth = 1.0
    peak = 1.0
    worst = 0.0
    for r in monthly_returns:
        wealth *= 1.0 + r
        peak = max(peak, wealth)
        drawdown = wealth / peak - 1.0
        worst = min(worst, drawdown)
    return abs(worst)


def _expand_weights(stock_w: float, bond_w: float, reit_w: float, selected: dict[str, list[str]]) -> dict[str, float]:
    out: dict[str, float] = {}
    eqs = selected["equities"]
    bds = selected["bonds"]
    rts = selected["reits"]

    if len(eqs) == 1:
        out[eqs[0]] = stock_w
    else:
        out[eqs[0]] = round(stock_w * 0.6, 10)
        out[eqs[1]] = round(stock_w * 0.4, 10)

    if len(bds) == 1:
        out[bds[0]] = bond_w
    else:
        out[bds[0]] = round(bond_w * 0.7, 10)
        out[bds[1]] = round(bond_w * 0.3, 10)

    if reit_w > 0 and rts:
        out[rts[0]] = reit_w

    total = sum(out.values())
    if total != 1.0:
        first = next(iter(out))
        out[first] += 1.0 - total
    return out


def _optimize(
    selected: dict[str, list[str]],
    returns_by_ticker: dict[str, list[tuple[str, float]]],
    target_cagr: float,
    max_mdd: float,
    warnings: list[str],
) -> tuple[dict[str, float], dict[str, float]]:
    candidates: list[tuple[float, float, float, dict[str, float], dict[str, float]]] = []
    reit_grid = [0.0, 0.05, 0.10] if selected["reits"] else [0.0]

    for stock in [i / 100 for i in range(20, 95, 5)]:
        for reit in reit_grid:
            bond = 1.0 - stock - reit
            if bond < 0.10:
                continue

            weights = _expand_weights(stock, bond, reit, selected)
            monthly = _portfolio_monthly_returns(weights, returns_by_ticker)
            if len(monthly) < 24:
                continue

            hist_ret = _annualized_return(monthly)
            exp_return = TARGET_BLEND_WEIGHT_HISTORY * hist_ret + TARGET_BLEND_WEIGHT_USER * target_cagr
            vol = _annualized_vol(monthly)
            est_mdd = _mdd(monthly)
            metrics = {"exp_return": exp_return, "vol": vol, "est_mdd": est_mdd}

            if est_mdd <= max_mdd:
                candidates.append((abs(exp_return - target_cagr), vol, -exp_return, weights, metrics))

    if candidates:
        candidates.sort(key=lambda x: (x[0], x[1], x[2]))
        _, _, _, weights, metrics = candidates[0]
        return weights, metrics

    warnings.append("No portfolio met max_mdd constraint; selected minimum-MDD fallback.")
    fallback: tuple[float, float, dict[str, float], dict[str, float]] | None = None
    for stock in [i / 100 for i in range(20, 95, 5)]:
        reit = 0.0 if not selected["reits"] else 0.05
        bond = 1.0 - stock - reit
        if bond < 0.10:
            continue

        weights = _expand_weights(stock, bond, reit, selected)
        monthly = _portfolio_monthly_returns(weights, returns_by_ticker)
        if len(monthly) < 24:
            continue

        hist_ret = _annualized_return(monthly)
        exp_return = TARGET_BLEND_WEIGHT_HISTORY * hist_ret + TARGET_BLEND_WEIGHT_USER * target_cagr
        metrics = {
            "exp_return": exp_return,
            "vol": _annualized_vol(monthly),
            "est_mdd": _mdd(monthly),
        }

        key = (metrics["est_mdd"], metrics["vol"])
        if fallback is None or key < (fallback[0], fallback[1]):
            fallback = (key[0], key[1], weights, metrics)

    if fallback is None:
        raise ValueError("Unable to construct candidate portfolio (insufficient return history).")
    return fallback[2], fallback[3]


def _simulate_accumulation(
    current_balance_krw: float,
    monthly_contribution_krw: float,
    monthly_return: float,
    months: list[date],
) -> list[dict[str, float | str]]:
    balance = float(current_balance_krw)
    principal = float(current_balance_krw)
    series: list[dict[str, float | str]] = []

    for month_end in months:
        balance *= 1.0 + monthly_return
        balance += monthly_contribution_krw
        principal += monthly_contribution_krw
        series.append(
            {
                "date": month_end.isoformat(),
                "balance": round(balance, 2),
                "principal": round(principal, 2),
                "gain": round(balance - principal, 2),
            }
        )
    return series


def run_engine_v0(input_data: EngineInput, returns_by_ticker: dict[str, list[tuple[str, float]]] | None = None) -> dict[str, Any]:
    warnings: list[str] = []

    if input_data.max_mdd <= 0 or input_data.max_mdd >= 100:
        raise ValueError("max_mdd must be in (0, 100) percent")
    if input_data.target_cagr <= -100:
        raise ValueError("target_cagr must be > -100 percent")

    series = returns_by_ticker if returns_by_ticker is not None else _load_returns()
    selected = _pick_assets(series, warnings)

    target_cagr = input_data.target_cagr / 100.0
    max_mdd = input_data.max_mdd / 100.0
    weights, metrics = _optimize(selected, series, target_cagr, max_mdd, warnings)

    monthly_net_return = (1.0 + metrics["exp_return"] - input_data.fee_annual) ** (1.0 / 12.0) - 1.0
    if input_data.inflation > 0:
        inflation_monthly = (1.0 + input_data.inflation) ** (1.0 / 12.0) - 1.0
        if ((1.0 + monthly_net_return) / (1.0 + inflation_monthly) - 1.0) <= 0:
            warnings.append("Expected real monthly return is non-positive after inflation.")

    retirement = _resolve_retirement_date(input_data, warnings)
    months = _month_ends_between(_parse_date(input_data.start_date), retirement)
    accumulation = _simulate_accumulation(
        input_data.current_balance_krw,
        input_data.monthly_contribution_krw,
        monthly_net_return,
        months,
    )

    portfolio = [
        {"ticker": ticker, "name_kr": ETF_NAME_KR.get(ticker, ticker), "weight": round(weight, 4)}
        for ticker, weight in sorted(weights.items(), key=lambda item: item[1], reverse=True)
    ]
    result = {
        "portfolio": portfolio,
        "metrics": {
            "exp_return": round(metrics["exp_return"], 6),
            "vol": round(metrics["vol"], 6),
            "est_mdd": round(metrics["est_mdd"], 6),
        },
        "accumulation_series": accumulation,
        "warnings": warnings,
    }
    json.dumps(result, ensure_ascii=False)
    return result
