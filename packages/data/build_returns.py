import logging
from pathlib import Path
from typing import Iterable

import pandas as pd
import yfinance as yf


LOGGER = logging.getLogger("build_returns")
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
UNIVERSE_PATH = DATA_DIR / "universe.csv"
PRICES_OUT = DATA_DIR / "prices_monthly.parquet"
RETURNS_OUT = DATA_DIR / "returns_monthly.parquet"
MIN_MONTHS = 24


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def load_tickers(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"Universe file not found: {path}")

    universe = pd.read_csv(path)
    if "ticker" not in universe.columns:
        raise ValueError(f"Expected 'ticker' column in {path}")

    tickers = sorted({str(t).strip().upper() for t in universe["ticker"] if pd.notna(t) and str(t).strip()})
    if not tickers:
        raise ValueError("No valid tickers found in universe.csv")

    return tickers


def month_end_prices(ticker: str) -> pd.DataFrame:
    raw = yf.download(
        ticker,
        period="max",
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=False,
    )

    if raw.empty:
        return pd.DataFrame(columns=["ticker", "date", "price"])

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    close = raw["Close"].dropna()
    monthly = close.resample("ME").last().dropna()

    out = monthly.rename("price").to_frame()
    out["ticker"] = ticker
    out = out.reset_index(names="date")
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    return out[["ticker", "date", "price"]]


def build_tables(tickers: Iterable[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    price_frames: list[pd.DataFrame] = []
    return_frames: list[pd.DataFrame] = []

    for ticker in tickers:
        prices = month_end_prices(ticker)
        if prices.empty:
            LOGGER.warning("%s: no data fetched; skipping.", ticker)
            continue

        prices = prices.sort_values("date")
        n_prices = len(prices)
        start_date = prices["date"].iloc[0].date()
        end_date = prices["date"].iloc[-1].date()

        if n_prices < MIN_MONTHS:
            LOGGER.warning(
                "%s: %d monthly prices (%s -> %s), below minimum %d months; excluded.",
                ticker,
                n_prices,
                start_date,
                end_date,
                MIN_MONTHS,
            )
            continue

        rets = prices.copy()
        rets["return"] = rets["price"].pct_change()
        rets = rets.dropna(subset=["return"])
        n_returns = len(rets)

        if n_returns < (MIN_MONTHS - 1):
            LOGGER.warning(
                "%s: %d monthly returns after pct_change, below minimum %d; excluded.",
                ticker,
                n_returns,
                MIN_MONTHS - 1,
            )
            continue

        LOGGER.info(
            "%s: using %d monthly prices (%s -> %s), %d monthly returns.",
            ticker,
            n_prices,
            start_date,
            end_date,
            n_returns,
        )
        price_frames.append(prices)
        return_frames.append(rets[["ticker", "date", "return"]])

    if not price_frames:
        raise RuntimeError("No tickers with at least 24 months of monthly data.")

    prices_all = pd.concat(price_frames, ignore_index=True)
    returns_all = pd.concat(return_frames, ignore_index=True) if return_frames else pd.DataFrame(columns=["ticker", "date", "return"])

    return prices_all, returns_all


def log_sample_output(prices: pd.DataFrame, returns: pd.DataFrame) -> None:
    top5 = sorted(prices["ticker"].unique())[:5]
    if not top5:
        LOGGER.warning("No tickers available for sample output.")
        return

    sample_prices = (
        prices[prices["ticker"].isin(top5)]
        .sort_values(["ticker", "date"])
        .groupby("ticker", group_keys=False)
        .tail(3)
    )
    sample_returns = (
        returns[returns["ticker"].isin(top5)]
        .sort_values(["ticker", "date"])
        .groupby("ticker", group_keys=False)
        .tail(3)
    )

    LOGGER.info("Sample monthly prices (top 5 tickers, latest 3 months each):\n%s", sample_prices.to_string(index=False))
    LOGGER.info("Sample monthly returns (top 5 tickers, latest 3 months each):\n%s", sample_returns.to_string(index=False))


def main() -> None:
    configure_logging()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    tickers = load_tickers(UNIVERSE_PATH)
    LOGGER.info("Loaded %d tickers from %s", len(tickers), UNIVERSE_PATH)

    prices, returns = build_tables(tickers)
    prices.to_parquet(PRICES_OUT, index=False)
    returns.to_parquet(RETURNS_OUT, index=False)

    LOGGER.info("Saved %d rows to %s", len(prices), PRICES_OUT)
    LOGGER.info("Saved %d rows to %s", len(returns), RETURNS_OUT)

    log_sample_output(prices, returns)


if __name__ == "__main__":
    main()
