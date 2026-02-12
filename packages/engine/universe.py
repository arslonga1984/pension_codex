from __future__ import annotations

from typing import Any


def _to_float(value: Any, default: float) -> float:
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def _rows_from_universe(universe_df: Any) -> list[dict[str, Any]]:
    if isinstance(universe_df, list):
        return [dict(r) for r in universe_df]

    to_dict = getattr(universe_df, "to_dict", None)
    if callable(to_dict):
        try:
            return [dict(r) for r in to_dict(orient="records")]
        except TypeError:
            pass

    raise TypeError("universe_df must be a list[dict] or a DataFrame-like object")


def select_representative_etfs(
    universe_df: Any,
    asset_class: str,
    top_k: int = 1,
    min_aum_krw: float = 0.0,
) -> list[dict[str, Any]]:
    if top_k <= 0:
        return []

    rows = _rows_from_universe(universe_df)
    filtered = [
        row
        for row in rows
        if str(row.get("asset_class", "")).strip() == asset_class and _to_float(row.get("aum_krw"), 0.0) >= min_aum_krw
    ]

    filtered.sort(
        key=lambda row: (
            -_to_float(row.get("aum_krw"), 0.0),
            _to_float(row.get("expense_ratio"), 999.0),
            str(row.get("ticker", "")),
        )
    )
    return filtered[:top_k]
