from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .classify_asset_class import classify_asset_class

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
UNIVERSE_PATH = DATA_DIR / "universe.csv"
ENRICHED_PATH = DATA_DIR / "universe_enriched.csv"


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def load_universe(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Universe file not found: {path}")

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("Universe file has no header row")
        if "ticker" not in reader.fieldnames:
            raise ValueError("Universe file must contain 'ticker' column")
        return list(reader)


def enrich_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    enriched: list[dict[str, str]] = []
    for row in rows:
        item = dict(row)
        item.setdefault("name_kr", "")
        item["asset_class"] = classify_asset_class(item.get("name_kr"))
        enriched.append(item)
    return enriched


def save_enriched(rows: list[dict[str, str]], path: Path) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fields:
                fields.append(key)

    if "asset_class" not in fields:
        fields.append("asset_class")

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def print_report(rows: list[dict[str, str]]) -> None:
    counts = Counter(row.get("asset_class", "unknown") or "unknown" for row in rows)

    print("=== Universe Enrichment Report ===")
    print(f"Total rows: {len(rows)}")
    print("\n[Counts by asset_class]")
    for asset_class, cnt in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        print(f"- {asset_class}: {cnt}")

    unknown_rows = [r for r in rows if (r.get("asset_class") or "unknown") == "unknown"]
    print("\n[Unknown top 20]")
    for row in unknown_rows[:20]:
        print(f"- {row.get('ticker', '').strip()} | {row.get('name_kr', '').strip()}")

    by_class: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_class[row.get("asset_class", "unknown")].append(row)

    print("\n[AUM top 5 by asset_class]")
    for asset_class in sorted(by_class.keys()):
        ranked = sorted(
            by_class[asset_class],
            key=lambda r: (
                -_to_float(r.get("aum_krw"), 0.0),
                _to_float(r.get("expense_ratio"), 999.0),
                str(r.get("ticker", "")),
            ),
        )[:5]
        print(f"- {asset_class}")
        for row in ranked:
            print(
                "  * "
                f"{row.get('ticker', '').strip()} | {row.get('name_kr', '').strip()} | "
                f"aum_krw={_to_float(row.get('aum_krw'), 0.0):,.0f} | "
                f"expense_ratio={_to_float(row.get('expense_ratio'), 0.0):.4f}"
            )


def main() -> None:
    rows = load_universe(UNIVERSE_PATH)
    enriched = enrich_rows(rows)
    save_enriched(enriched, ENRICHED_PATH)
    print_report(enriched)
    print(f"\nSaved: {ENRICHED_PATH}")


if __name__ == "__main__":
    main()
