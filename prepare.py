#!/usr/bin/env python3
"""
Fixed data preparation — sparse-day L2 from HuggingFace Joseph3222/polymarket-orderbook
(orderbook_1min only). Does NOT download the raw TB-scale orderbook stream.

Downloads selected UTC day files (~1–2GB each), DuckDB-filters to the curated YES
token set, writes slim caches under data/, then deletes full day files.

This is sparse-day sampling across ~3 calendar months — NOT continuous 90-day L2.
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import requests
from huggingface_hub import hf_hub_download

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RAW = DATA / "raw_hf"
SLIM = DATA / "slim_days"
GAMMA = "https://gamma-api.polymarket.com"

HF_REPO = "Joseph3222/polymarket-orderbook"
HF_CONFIG_PREFIX = "orderbook_1min"

# Sparse days spanning May–Aug 2026 (skip Jun 12–17 missing). Archives end 2026-08-10.
DEFAULT_DAYS = [
    "2026-05-14",
    "2026-06-01",
    "2026-06-25",
    "2026-07-20",
    "2026-08-06",
]

# YES token asset_ids (Fed Sep 2026 + geopolitics)
YES_TOKENS = {
    # Fed -50+
    "97186030785608128217926542396950266594898339988989015155120280107165449433603": {
        "slug_key": "fed_m50",
        "event_slug": "fed-decision-in-september-762",
    },
    # Fed -25
    "57748138085022719760345772310040703848567377822400132842014290209986511882046": {
        "slug_key": "fed_m25",
        "event_slug": "fed-decision-in-september-762",
    },
    # Fed no change (~1000 daily)
    "5615282760875985231868508008056959876238536896643315063916840237042205273721": {
        "slug_key": "fed_0",
        "event_slug": "fed-decision-in-september-762",
    },
    # Fed +25 (~1000 daily)
    "63842529068710005716169325380315470359047749786610778647370693404952498013178": {
        "slug_key": "fed_p25",
        "event_slug": "fed-decision-in-september-762",
    },
    # Fed +50+
    "88912926533493988427719291698947688154042720958310632316541141466409683822293": {
        "slug_key": "fed_p50",
        "event_slug": "fed-decision-in-september-762",
    },
    # US invade Iran before 2027 (~400)
    "55115078421062885512539156303747803058407616201213034911037320915726138659123": {
        "slug_key": "iran",
        "event_slug": None,
        "condition_id": "0x5db999fad322cea2914535aae5517060c3f80ad6d8c0231cde2124a434d16846",
    },
    # Trump out before 2027
    "59252515735652674747158950210016502214756531287333895140318848923768750410355": {
        "slug_key": "trump_out",
        "event_slug": "trump-out-as-president-before-2027",
    },
}

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "polymarket-lp-autoresearch/0.1"})


def get_json(url: str, params: dict | None = None) -> Any:
    r = SESSION.get(url, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def parse_token_ids(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        try:
            v = json.loads(raw)
            if isinstance(v, list):
                return [str(x) for x in v]
        except json.JSONDecodeError:
            pass
    return []


def daily_rate_from_gamma(m: dict) -> float:
    total = 0.0
    for rr in m.get("clobRewards") or []:
        try:
            total += float(rr.get("rewardsDailyRate") or 0)
        except Exception:
            pass
    return total


def fetch_market_meta() -> list[dict[str, Any]]:
    """Resolve Gamma metadata for each YES token; rewards from current Gamma fields."""
    by_token: dict[str, dict] = {}

    # Fed event batch
    ev = get_json(f"{GAMMA}/events/slug/fed-decision-in-september-762")
    for m in ev.get("markets") or []:
        toks = parse_token_ids(m.get("clobTokenIds"))
        if not toks:
            continue
        yes = toks[0]
        if yes in YES_TOKENS:
            by_token[yes] = m

    # Trump event
    ev2 = get_json(f"{GAMMA}/events/slug/trump-out-as-president-before-2027")
    for m in ev2.get("markets") or []:
        toks = parse_token_ids(m.get("clobTokenIds"))
        if toks and toks[0] in YES_TOKENS:
            by_token[toks[0]] = m

    # Iran by condition
    iran_cid = YES_TOKENS[
        "55115078421062885512539156303747803058407616201213034911037320915726138659123"
    ]["condition_id"]
    rows = get_json(f"{GAMMA}/markets", {"condition_ids": iran_cid})
    if rows:
        toks = parse_token_ids(rows[0].get("clobTokenIds"))
        if toks:
            by_token[toks[0]] = rows[0]

    markets: list[dict] = []
    for yes, meta0 in YES_TOKENS.items():
        g = by_token.get(yes)
        if not g:
            print(f"[prepare] WARNING: no gamma meta for {meta0['slug_key']} ({yes[:16]}...)")
            continue
        toks = parse_token_ids(g.get("clobTokenIds"))
        daily = daily_rate_from_gamma(g)
        # Defaults when Gamma has no active clobRewards entry
        if daily <= 0:
            defaults = {
                "fed_m50": 50.0,
                "fed_m25": 100.0,
                "fed_0": 1000.0,
                "fed_p25": 1000.0,
                "fed_p50": 50.0,
                "iran": 400.0,
                "trump_out": 1.0,
            }
            daily = defaults.get(meta0["slug_key"], 50.0)
        min_size = float(g.get("rewardsMinSize") or 50)
        max_spread = float(g.get("rewardsMaxSpread") or 4.5)
        markets.append(
            {
                "market_id": str(g.get("conditionId") or yes),
                "condition_id": str(g.get("conditionId") or ""),
                "question": g.get("question"),
                "yes_token": yes,
                "no_token": toks[1] if len(toks) > 1 else None,
                "slug_key": meta0["slug_key"],
                "rewards_min_size": min_size,
                "rewards_max_spread": max_spread,
                "daily_reward_pool": daily,
                # Fallback competition; overwritten per-row from L2 when available
                "competition_q": max(800.0, min_size * 30.0),
                "volume_num": float(g.get("volumeNum") or 0),
                "start_date": g.get("startDate"),
                "end_date": g.get("endDate"),
                "rewards_note": (
                    "Using current Gamma rewardsMinSize/rewardsMaxSpread/rewardsDailyRate "
                    "as a constant schedule; historical rates may have differed."
                ),
            }
        )
    return markets


def download_day(day: str) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    print(f"[prepare] downloading HF orderbook_1min date={day} ...")
    path = hf_hub_download(
        repo_id=HF_REPO,
        repo_type="dataset",
        filename=f"{HF_CONFIG_PREFIX}/date={day}/data_0.parquet",
        local_dir=str(RAW),
        local_dir_use_symlinks=False,
    )
    p = Path(path)
    print(f"[prepare]   got {p} ({p.stat().st_size / 1e9:.2f} GB)")
    return p


def filter_day(day_path: Path, day: str, yes_tokens: list[str], token_to_market: dict[str, str]) -> Path:
    """DuckDB-filter full day parquet → slim parquet for our tokens only."""
    SLIM.mkdir(parents=True, exist_ok=True)
    out = SLIM / f"{day}.parquet"
    token_list_sql = ",".join(f"'{t}'" for t in yes_tokens)

    con = duckdb.connect()
    # Discover columns once
    cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{day_path}')").fetchall()]
    print(f"[prepare]   schema cols ({len(cols)}): {cols[:20]}...")

    # Flexible column names across archive versions
    ts_col = "minute_ts" if "minute_ts" in cols else ("ts" if "ts" in cols else None)
    asset_col = "asset_id" if "asset_id" in cols else ("asset" if "asset" in cols else None)
    if not ts_col or not asset_col:
        raise RuntimeError(f"Unexpected schema, cannot find ts/asset columns: {cols}")

    bid_col = "best_bid" if "best_bid" in cols else None
    ask_col = "best_ask" if "best_ask" in cols else None
    mid_expr = None
    if "mid" in cols:
        mid_expr = "mid"
    elif "mid_price" in cols:
        mid_expr = "mid_price"
    elif bid_col and ask_col:
        mid_expr = f"({bid_col} + {ask_col}) / 2.0"
    else:
        raise RuntimeError(f"No mid/best_bid/best_ask in schema: {cols}")

    # Depth arrays (HF schema: bids_json / asks_json)
    bids_col = (
        "bids_json" if "bids_json" in cols
        else ("bids" if "bids" in cols else ("bid_levels" if "bid_levels" in cols else None))
    )
    asks_col = (
        "asks_json" if "asks_json" in cols
        else ("asks" if "asks" in cols else ("ask_levels" if "ask_levels" in cols else None))
    )

    # Also try bid_depth/ask_depth aggregates
    extra_select = []
    if bid_col:
        extra_select.append(f"{bid_col} AS best_bid")
    else:
        extra_select.append("NULL::DOUBLE AS best_bid")
    if ask_col:
        extra_select.append(f"{ask_col} AS best_ask")
    else:
        extra_select.append("NULL::DOUBLE AS best_ask")
    if "spread" in cols:
        extra_select.append("spread AS spread")
    else:
        extra_select.append("NULL::DOUBLE AS spread")
    if bids_col:
        extra_select.append(f"{bids_col} AS bids_raw")
    else:
        extra_select.append("NULL AS bids_raw")
    if asks_col:
        extra_select.append(f"{asks_col} AS asks_raw")
    else:
        extra_select.append("NULL AS asks_raw")

    sql = f"""
    COPY (
      SELECT
        {ts_col} AS ts,
        CAST({asset_col} AS VARCHAR) AS asset_id,
        ({mid_expr})::DOUBLE AS mid,
        {', '.join(extra_select)}
      FROM read_parquet('{day_path}')
      WHERE CAST({asset_col} AS VARCHAR) IN ({token_list_sql})
    ) TO '{out}' (FORMAT PARQUET)
    """
    con.execute(sql)
    n = con.execute(f"SELECT COUNT(*) FROM read_parquet('{out}')").fetchone()[0]
    print(f"[prepare]   slim {out.name}: {n} rows ({out.stat().st_size / 1e6:.2f} MB)")
    con.close()
    return out


def competition_from_book(row: pd.Series, max_spread_cents: float) -> float:
    """Approximate competing Q from observed L2 depth within max spread of mid."""
    mid = float(row["mid"]) if pd.notna(row["mid"]) else None
    if mid is None or mid <= 0:
        return 800.0
    v = max_spread_cents
    # Prefer explicit best sizes if depth arrays missing
    q = 0.0
    bids_raw = row.get("bids_raw")
    asks_raw = row.get("asks_raw")

    def score_levels(levels, is_bid: bool) -> float:
        total = 0.0
        if levels is None or (isinstance(levels, float) and pd.isna(levels)):
            return 0.0
        # levels may be list of dicts, list of [price,size], or JSON string
        parsed = levels
        if isinstance(levels, str):
            try:
                parsed = json.loads(levels)
            except Exception:
                return 0.0
        if not isinstance(parsed, (list, tuple)):
            return 0.0
        for lv in parsed:
            try:
                if isinstance(lv, dict):
                    px = float(lv.get("price") or lv.get("p") or lv.get(0) or 0)
                    sz = float(lv.get("size") or lv.get("s") or lv.get("quantity") or 0)
                elif isinstance(lv, (list, tuple)) and len(lv) >= 2:
                    px, sz = float(lv[0]), float(lv[1])
                else:
                    continue
            except Exception:
                continue
            if is_bid:
                spread_c = (mid - px) * 100.0
            else:
                spread_c = (px - mid) * 100.0
            if spread_c < 0 or spread_c >= v:
                continue
            total += ((v - spread_c) / v) ** 2 * sz
        return total

    q_bid = score_levels(bids_raw, True)
    q_ask = score_levels(asks_raw, False)
    # Two-sided competition mass ≈ min-style blend
    if q_bid > 0 and q_ask > 0:
        q = max(min(q_bid, q_ask), max(q_bid, q_ask) / 3.0)
    else:
        q = max(q_bid, q_ask) / 3.0

    # Fallback: use spread tightness × dummy size if no depth
    if q <= 0:
        bb = row.get("best_bid")
        ba = row.get("best_ask")
        if pd.notna(bb) and pd.notna(ba):
            half_c = (float(ba) - float(bb)) * 50.0
            if 0 <= half_c < v:
                q = ((v - half_c) / v) ** 2 * 200.0  # assume ~200 sh near touch
    return float(max(q, 50.0))


def assemble_prices(slim_paths: list[Path], markets: list[dict]) -> pd.DataFrame:
    token_to_m = {m["yes_token"]: m for m in markets}
    frames = []
    for p in slim_paths:
        df = pd.read_parquet(p)
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    raw = pd.concat(frames, ignore_index=True)

    # Normalize ts to unix seconds
    if pd.api.types.is_datetime64_any_dtype(raw["ts"]):
        raw["ts"] = (raw["ts"].astype("int64") // 10**9).astype("int64")
    else:
        # may be ms
        ts = raw["ts"].astype("int64")
        raw["ts"] = ts.where(ts < 10_000_000_000, ts // 1000)

    rows = []
    for _, r in raw.iterrows():
        asset = str(r["asset_id"])
        m = token_to_m.get(asset)
        if not m:
            continue
        mid = float(r["mid"])
        if not (0.0 < mid < 1.0):
            continue
        comp = competition_from_book(r, float(m["rewards_max_spread"]))
        rows.append(
            {
                "ts": int(r["ts"]),
                "market_id": m["market_id"],
                "asset_id": asset,
                "mid": mid,
                "yes_mid": mid,
                "no_mid": 1.0 - mid,
                "best_bid": float(r["best_bid"]) if pd.notna(r.get("best_bid")) else mid - 0.01,
                "best_ask": float(r["best_ask"]) if pd.notna(r.get("best_ask")) else mid + 0.01,
                "competition_q": comp,
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.sort_values(["ts", "market_id"]).drop_duplicates(["ts", "market_id"], keep="last")
    return out.reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--days",
        type=str,
        default="",
        help="Comma-separated UTC days YYYY-MM-DD (default: curated sparse set)",
    )
    ap.add_argument(
        "--quick",
        action="store_true",
        help="Only two days (2026-05-14, 2026-07-20) for a fast first baseline",
    )
    ap.add_argument("--keep-raw", action="store_true", help="Keep full HF day files")
    args = ap.parse_args()

    DATA.mkdir(parents=True, exist_ok=True)

    if args.days:
        days = [d.strip() for d in args.days.split(",") if d.strip()]
    elif args.quick:
        days = ["2026-05-14", "2026-07-20"]
    else:
        days = list(DEFAULT_DAYS)

    print(f"[prepare] sparse days: {days}")
    markets = fetch_market_meta()
    print(f"[prepare] resolved {len(markets)} markets:")
    for m in markets:
        print(
            f"  {m['slug_key']}: pool=${m['daily_reward_pool']:.0f}/d "
            f"min={m['rewards_min_size']} spread={m['rewards_max_spread']} | {(m['question'] or '')[:60]}"
        )

    yes_tokens = [m["yes_token"] for m in markets]
    token_to_market = {m["yes_token"]: m["market_id"] for m in markets}

    slim_paths: list[Path] = []
    for day in days:
        existing = SLIM / f"{day}.parquet"
        if existing.exists() and existing.stat().st_size > 0:
            print(f"[prepare] reusing slim cache {existing}")
            slim_paths.append(existing)
            continue
        day_path = download_day(day)
        try:
            slim = filter_day(day_path, day, yes_tokens, token_to_market)
            slim_paths.append(slim)
        finally:
            if not args.keep_raw:
                # Remove the full day file (and empty parents under RAW)
                try:
                    # hf_hub_download may nest under RAW/orderbook_1min/date=...
                    if day_path.exists():
                        print(f"[prepare]   deleting raw {day_path} to free disk")
                        day_path.unlink()
                except Exception as e:
                    print(f"[prepare]   warn: could not delete raw: {e}")

    prices = assemble_prices(slim_paths, markets)
    if prices.empty:
        raise SystemExit("No rows after filter — check tokens/days presence in archive")

    # Empty trades placeholder (L2 mid-cross fills; no separate tape in this path)
    trades = pd.DataFrame(columns=["ts", "market_id", "price", "size", "side"])

    with open(DATA / "markets.json", "w") as f:
        json.dump(markets, f, indent=2)
    prices.to_parquet(DATA / "prices.parquet", index=False)
    trades.to_parquet(DATA / "trades.parquet", index=False)

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "sparse_day_l2",
        "hf_repo": HF_REPO,
        "hf_config": HF_CONFIG_PREFIX,
        "days": days,
        "start_ts": int(prices["ts"].min()),
        "end_ts": int(prices["ts"].max()),
        "start_iso": datetime.fromtimestamp(int(prices["ts"].min()), timezone.utc).isoformat(),
        "end_iso": datetime.fromtimestamp(int(prices["ts"].max()), timezone.utc).isoformat(),
        "n_markets": len(markets),
        "n_price_rows": int(len(prices)),
        "n_trade_rows": 0,
        "markets": [
            {
                "market_id": m["market_id"],
                "slug_key": m["slug_key"],
                "question": m["question"],
                "yes_token": m["yes_token"],
                "daily_reward_pool": m["daily_reward_pool"],
                "rewards_min_size": m["rewards_min_size"],
                "rewards_max_spread": m["rewards_max_spread"],
            }
            for m in markets
        ],
        "data_sources": [
            f"hf://datasets/{HF_REPO}/{HF_CONFIG_PREFIX}/date=YYYY-MM-DD/data_0.parquet",
            "https://gamma-api.polymarket.com (reward params, metadata)",
        ],
        "notes": (
            "SPARSE-DAY sampling (not continuous 90-day L2). "
            "Full HF day files filtered to curated YES tokens then discarded. "
            "Reward rates from current Gamma fields held constant over the window. "
            "CLOB prices-history was NOT used for May–Jul (insufficient lookback overlap)."
        ),
    }
    with open(DATA / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    slim_mb = sum(p.stat().st_size for p in SLIM.glob("*.parquet")) / 1e6
    cache_mb = sum(p.stat().st_size for p in DATA.glob("*") if p.is_file()) / 1e6
    print(f"[prepare] prices rows={len(prices)} markets={len(markets)}")
    print(f"[prepare] slim days ≈ {slim_mb:.2f} MB; top-level data files ≈ {cache_mb:.2f} MB")
    print("[prepare] done")


if __name__ == "__main__":
    main()
