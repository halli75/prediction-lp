"""Data loading helpers for cached prepare.py outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
FIXTURES_DIR = ROOT / "fixtures"


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    path = path or (DATA_DIR / "manifest.json")
    with open(path) as f:
        return json.load(f)


def load_prices(path: Path | None = None) -> pd.DataFrame:
    path = path or (DATA_DIR / "prices.parquet")
    df = pd.read_parquet(path)
    df = df.sort_values(["ts", "market_id"]).reset_index(drop=True)
    return df


def load_markets(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or (DATA_DIR / "markets.json")
    with open(path) as f:
        return json.load(f)


def load_trades(path: Path | None = None) -> pd.DataFrame | None:
    path = path or (DATA_DIR / "trades.parquet")
    if not path.exists():
        return None
    return pd.read_parquet(path)


def train_holdout_split(
    prices: pd.DataFrame, holdout_frac: float = 0.25
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Time-based split: first (1-holdout) train, last holdout."""
    ts = prices["ts"].astype("int64")
    t_min, t_max = int(ts.min()), int(ts.max())
    cut = int(t_min + (1.0 - holdout_frac) * (t_max - t_min))
    train = prices[ts < cut].copy()
    holdout = prices[ts >= cut].copy()
    return train, holdout
