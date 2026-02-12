from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import pstdev
from typing import Any, Literal

from .universe import select_representative_etfs

ROOT = Path(__file__).resolve().parents[2]
RETURNS_PATH = ROOT / "data" / "returns_monthly.parquet"
UNIVERSE_ENRICHED_PATH = ROOT / "data" / "universe_enriched.csv"

TARGET_BLEND_WEIGHT_HISTORY = 0.6
TARGET_BLEND_WEIGHT_USER = 0.4
DEFAULT_FEE_ANNUAL = 0.004
DEFAULT_INFLATION = 0.025
DEFAULT_WITHDRAWAL_MODE: Literal["target_years", "fixed_monthly"] = "target_years"
DEFAULT_TARGET_YEARS = 20
DEFAULT_RETIREMENT_RETURN_HAIRCUT_PCT = 1.0
DEFAULT_RETIREMENT_FEE_ANNUAL = 0.004

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
    withdrawal_mode: Literal["target_years", "fixed_monthly"] = DEFAULT_WITHDRAWAL_MODE
    target_years: int = DEFAULT_TARGET_YEARS
    fixed_monthly_withdrawal_krw: float | None = None
    retirement_return_haircut_pct: float = DEFAULT_RETIREMENT_RETURN_HAIRCUT_PCT
    retirement_fee_annual: float = DEFAULT_RETIREMENT_FEE_ANNUAL


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


def _future_month_ends(start: date, months: int) -> list[date]:
    out: list[date] = []
    y, m = start.year, start.month
    for _ in range(months):
        next_month_start = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
        month_end = date.fromordinal(next_month_start.toordinal() - 1)
        out.append(month_end)
        y, m = next_month_start.year, next_month_start.month
    return out


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
    enriched_rows = [row for row in _load_enriched_universe_rows() if row.get("ticker") in return_universe]

    equities: list[str] = []
    bonds: list[str] = []
    reits: list[str] = []

    if enriched_rows:
        equity_rows = (
            select_representative_etfs(enriched_rows, "us_equity", top_k=2)
            + select_representative_etfs(enriched_rows, "global_equity", top_k=2)
            + select_representative_etfs(enriched_rows, "korea_equity", top_k=2)
        )
        for row in equity_rows:
            t = str(row.get("ticker", "")).strip()
            if t and t not in equities:
                equities.append(t)
            if len(equities) >= 2:
                break

        bond_rows = (
            select_representative_etfs(enriched_rows, "korea_treasury", top_k=2)
            + select_representative_etfs(enriched_rows, "korea_short", top_k=2)
            + select_representative_etfs(enriched_rows, "korea_credit", top_k=2)
        )
        for row in bond_rows:
            t = str(row.get("ticker", "")).strip()
            if t and t not in bonds:
                bonds.append(t)
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

    if not equities or not bonds:
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
        worst = min(worst, wealth / peak - 1.0)
    return abs(worst)


def _expand_weights(stock_w: float, bond_w: float, reit_w: float, selected: dict[str, list[str]]) -> dict[str, float]:
    out: dict[str, float] = {}
    eqs = selected["equities"]
    bds = selected["bonds"]
    rts = selected["reits"]

    out[eqs[0]] = stock_w if len(eqs) == 1 else round(stock_w * 0.6, 10)
    if len(eqs) > 1:
        out[eqs[1]] = round(stock_w * 0.4, 10)

    out[bds[0]] = bond_w if len(bds) == 1 else round(bond_w * 0.7, 10)
    if len(bds) > 1:
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
        return candidates[0][3], candidates[0][4]

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
        metrics = {"exp_return": exp_return, "vol": _annualized_vol(monthly), "est_mdd": _mdd(monthly)}

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
) -> list[dict[str, int | str]]:
    balance = float(current_balance_krw)
    principal = float(current_balance_krw)
    series: list[dict[str, int | str]] = []

    for month_end in months:
        balance *= 1.0 + monthly_return
        balance += monthly_contribution_krw
        principal += monthly_contribution_krw
        series.append(
            {
                "date": month_end.isoformat(),
                "balance": int(round(balance)),
                "principal": int(round(principal)),
                "gain": int(round(balance - principal)),
            }
        )
    return series


def _pmt_from_pv(balance: float, rm: float, n_months: int) -> float:
    if n_months <= 0:
        return 0.0
    if abs(rm) < 1e-9:
        return balance / n_months
    discount = (1.0 - (1.0 + rm) ** (-n_months)) / rm
    if abs(discount) < 1e-12:
        return balance / n_months
    return balance / discount


def _simulate_retirement(
    start_balance: float,
    start_date: date,
    exp_return_annual: float,
    input_data: EngineInput,
    warnings: list[str],
) -> tuple[list[dict[str, int | str]], dict[str, int]]:
    annual_net = exp_return_annual - (input_data.retirement_return_haircut_pct / 100.0) - input_data.retirement_fee_annual
    rm = (1.0 + annual_net) ** (1.0 / 12.0) - 1.0 if annual_net > -0.999999 else -0.99

    if input_data.withdrawal_mode == "target_years":
        months = max(1, int(input_data.target_years) * 12)
        monthly_withdrawal = _pmt_from_pv(start_balance, rm, months)
        if monthly_withdrawal > start_balance * 0.05:
            warnings.append("Calculated withdrawal exceeds 5% of retirement starting balance per month.")
        sim_months = _future_month_ends(start_date, months)
    elif input_data.withdrawal_mode == "fixed_monthly":
        if input_data.fixed_monthly_withdrawal_krw is None or input_data.fixed_monthly_withdrawal_krw <= 0:
            raise ValueError("fixed_monthly_withdrawal_krw is required and must be positive for fixed_monthly mode")
        monthly_withdrawal = float(input_data.fixed_monthly_withdrawal_krw)
        sim_months = _future_month_ends(start_date, 1200)
    else:
        raise ValueError("withdrawal_mode must be 'target_years' or 'fixed_monthly'")

    series: list[dict[str, int | str]] = []
    balance = float(start_balance)
    principal_ref = float(start_balance)

    for idx, d in enumerate(sim_months, start=1):
        balance *= 1.0 + rm
        withdrawal = min(monthly_withdrawal, balance)
        balance -= withdrawal
        gain = balance - principal_ref
        series.append(
            {
                "date": d.isoformat(),
                "balance": int(round(max(balance, 0.0))),
                "withdrawal": int(round(withdrawal)),
                "gain": int(round(gain)),
            }
        )
        if balance <= 0:
            if input_data.withdrawal_mode == "fixed_monthly" and idx <= 12:
                warnings.append("Withdrawal is too high: portfolio depletes within 12 months after retirement.")
            break

    duration_months = len(series)
    end_balance = int(round(series[-1]["balance"])) if series else int(round(start_balance))
    summary = {
        "start_balance_at_retirement": int(round(start_balance)),
        "monthly_withdrawal": int(round(monthly_withdrawal)),
        "duration_months": int(duration_months),
        "end_balance": max(0, int(round(end_balance))),
    }
    return series, summary


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
    accumulation = _simulate_accumulation(
        input_data.current_balance_krw,
        input_data.monthly_contribution_krw,
        monthly_net_return,
        _month_ends_between(_parse_date(input_data.start_date), retirement),
    )

    retirement_start_balance = accumulation[-1]["balance"] if accumulation else int(round(input_data.current_balance_krw))
    retirement_series, retirement_summary = _simulate_retirement(
        start_balance=retirement_start_balance,
        start_date=retirement,
        exp_return_annual=metrics["exp_return"],
        input_data=input_data,
        warnings=warnings,
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
        "retirement_series": retirement_series,
        "retirement_summary": retirement_summary,
        "warnings": warnings,
    }
    json.dumps(result, ensure_ascii=False)
    return result
