#!/usr/bin/env python3
"""
Data preparation — continuous (or sparse) L2 from HuggingFace
Joseph3222/polymarket-orderbook (orderbook_1min only).

Downloads ONE UTC day at a time (~1–2GB), DuckDB-filters to the allowlist
YES tokens from data/top_reward_markets.json, writes slim caches under
data/slim_days/, then deletes the raw day file immediately.

Never stages the full ~90×2GB corpus at once.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
from datetime import date, datetime, timedelta, timezone
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

# Continuous window (archives end 2026-08-10; Jun 12–17 missing)
CONTINUOUS_START = "2026-05-14"
CONTINUOUS_END = "2026-08-10"
SKIP_DAYS = {
    "2026-06-12",
    "2026-06-13",
    "2026-06-14",
    "2026-06-15",
    "2026-06-16",
    "2026-06-17",
}

# Legacy sparse fallback
DEFAULT_SPARSE_DAYS = [
    "2026-05-14",
    "2026-06-01",
    "2026-06-25",
    "2026-07-20",
    "2026-08-06",
]

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


def daterange(start: str, end: str, skip: set[str] | None = None) -> list[str]:
    skip = skip or set()
    d0 = date.fromisoformat(start)
    d1 = date.fromisoformat(end)
    out: list[str] = []
    cur = d0
    while cur <= d1:
        s = cur.isoformat()
        if s not in skip:
            out.append(s)
        cur += timedelta(days=1)
    return out


def allowlist_fingerprint(yes_tokens: list[str]) -> str:
    h = hashlib.sha1(",".join(sorted(yes_tokens)).encode()).hexdigest()[:12]
    return h


def load_allowlist_markets(path: Path | None = None) -> list[dict[str, Any]]:
    """Load curated top-reward markets; fall back to discovering from file."""
    path = path or (DATA / "top_reward_markets.json")
    if not path.exists():
        raise SystemExit(
            f"Missing {path}. Run discovery first or pass --allowlist."
        )
    with open(path) as f:
        raw = json.load(f)
    markets_in = raw.get("markets") or []
    markets: list[dict[str, Any]] = []
    for i, m in enumerate(markets_in):
        yes = str(m.get("yes_token") or "")
        if not yes:
            continue
        markets.append(
            {
                "market_id": str(m.get("market_id") or m.get("condition_id") or yes),
                "condition_id": str(m.get("condition_id") or m.get("market_id") or ""),
                "question": m.get("question"),
                "yes_token": yes,
                "no_token": m.get("no_token"),
                "slug_key": m.get("slug_key") or (m.get("slug") or f"m{i}")[:40],
                "rewards_min_size": float(m.get("rewards_min_size") or 50),
                "rewards_max_spread": float(m.get("rewards_max_spread") or 4.5),
                "daily_reward_pool": float(m.get("daily_reward_pool") or 0),
                "competition_q": max(800.0, float(m.get("rewards_min_size") or 50) * 30.0),
                "volume_num": float(m.get("volume_num") or 0),
                "start_date": m.get("start_date"),
                "end_date": m.get("end_date"),
                "overlap_days": m.get("overlap_days"),
                "rewards_note": (
                    "Using current Gamma/CLOB rewardsDailyRate held constant; "
                    "historical rates may have differed."
                ),
            }
        )
    return markets


def download_day(day: str) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    print(f"[prepare] downloading HF orderbook_1min date={day} ...", flush=True)
    t0 = time.time()
    path = hf_hub_download(
        repo_id=HF_REPO,
        repo_type="dataset",
        filename=f"{HF_CONFIG_PREFIX}/date={day}/data_0.parquet",
        local_dir=str(RAW),
        local_dir_use_symlinks=False,
    )
    p = Path(path)
    print(
        f"[prepare]   got {p} ({p.stat().st_size / 1e9:.2f} GB) in {time.time()-t0:.0f}s",
        flush=True,
    )
    return p


def filter_day(day_path: Path, day: str, yes_tokens: list[str]) -> Path:
    """DuckDB-filter full day parquet → slim parquet for allowlist tokens only."""
    SLIM.mkdir(parents=True, exist_ok=True)
    out = SLIM / f"{day}.parquet"
    token_list_sql = ",".join(f"'{t}'" for t in yes_tokens)

    con = duckdb.connect()
    cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{day_path}')").fetchall()]
    print(f"[prepare]   schema cols ({len(cols)}): {cols[:12]}...", flush=True)

    ts_col = "minute_ts" if "minute_ts" in cols else ("ts" if "ts" in cols else None)
    asset_col = "asset_id" if "asset_id" in cols else ("asset" if "asset" in cols else None)
    if not ts_col or not asset_col:
        raise RuntimeError(f"Unexpected schema, cannot find ts/asset columns: {cols}")

    bid_col = "best_bid" if "best_bid" in cols else None
    ask_col = "best_ask" if "best_ask" in cols else None
    if "mid" in cols:
        mid_expr = "mid"
    elif "mid_price" in cols:
        mid_expr = "mid_price"
    elif bid_col and ask_col:
        mid_expr = f"({bid_col} + {ask_col}) / 2.0"
    else:
        raise RuntimeError(f"No mid/best_bid/best_ask in schema: {cols}")

    bids_col = (
        "bids_json" if "bids_json" in cols
        else ("bids" if "bids" in cols else ("bid_levels" if "bid_levels" in cols else None))
    )
    asks_col = (
        "asks_json" if "asks_json" in cols
        else ("asks" if "asks" in cols else ("ask_levels" if "ask_levels" in cols else None))
    )

    extra_select = []
    extra_select.append(f"{bid_col} AS best_bid" if bid_col else "NULL::DOUBLE AS best_bid")
    extra_select.append(f"{ask_col} AS best_ask" if ask_col else "NULL::DOUBLE AS best_ask")
    extra_select.append("spread AS spread" if "spread" in cols else "NULL::DOUBLE AS spread")
    extra_select.append(f"{bids_col} AS bids_raw" if bids_col else "NULL AS bids_raw")
    extra_select.append(f"{asks_col} AS asks_raw" if asks_col else "NULL AS asks_raw")

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
    n_assets = con.execute(
        f"SELECT COUNT(DISTINCT asset_id) FROM read_parquet('{out}')"
    ).fetchone()[0]
    print(
        f"[prepare]   slim {out.name}: {n} rows, {n_assets} assets "
        f"({out.stat().st_size / 1e6:.2f} MB)",
        flush=True,
    )
    con.close()
    return out


def delete_raw(day_path: Path) -> None:
    try:
        if day_path.exists():
            print(f"[prepare]   deleting raw {day_path} to free disk", flush=True)
            day_path.unlink()
        # Also purge nested HF cache copies if present under RAW/orderbook_1min
        nested = RAW / HF_CONFIG_PREFIX / f"date={day_path.parent.name.split('=')[-1] if 'date=' in str(day_path.parent) else ''}"
        # Best-effort: remove empty date dirs and any leftover parquet under RAW
        for p in RAW.rglob("data_0.parquet"):
            try:
                print(f"[prepare]   deleting leftover raw {p}", flush=True)
                p.unlink()
            except Exception:
                pass
    except Exception as e:
        print(f"[prepare]   warn: could not delete raw: {e}", flush=True)


def competition_from_book(row: pd.Series, max_spread_cents: float) -> float:
    mid = float(row["mid"]) if pd.notna(row["mid"]) else None
    if mid is None or mid <= 0:
        return 800.0
    v = max_spread_cents
    bids_raw = row.get("bids_raw")
    asks_raw = row.get("asks_raw")

    def score_levels(levels, is_bid: bool) -> float:
        total = 0.0
        if levels is None or (isinstance(levels, float) and pd.isna(levels)):
            return 0.0
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
                    px = float(lv.get("price") or lv.get("p") or 0)
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
    if q_bid > 0 and q_ask > 0:
        q = max(min(q_bid, q_ask), max(q_bid, q_ask) / 3.0)
    else:
        q = max(q_bid, q_ask) / 3.0

    if q <= 0:
        bb = row.get("best_bid")
        ba = row.get("best_ask")
        if pd.notna(bb) and pd.notna(ba):
            half_c = (float(ba) - float(bb)) * 50.0
            if 0 <= half_c < v:
                q = ((v - half_c) / v) ** 2 * 200.0
    return float(max(q, 50.0))


def assemble_prices(slim_paths: list[Path], markets: list[dict]) -> pd.DataFrame:
    """Vectorized assemble; competition_q uses spread-based fallback (fast).

    Full L2 quadratic competition is expensive over millions of rows; we use a
    spread-tightness proxy here and keep per-market competition_q as floor.
    """
    token_to_m = {m["yes_token"]: m for m in markets}
    frames = []
    for pth in slim_paths:
        if not pth.exists() or pth.stat().st_size == 0:
            continue
        df = pd.read_parquet(pth)
        if len(df) == 0:
            continue
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    raw = pd.concat(frames, ignore_index=True)
    raw["asset_id"] = raw["asset_id"].astype(str)

    if pd.api.types.is_datetime64_any_dtype(raw["ts"]):
        raw["ts"] = (raw["ts"].astype("int64") // 10**9).astype("int64")
    else:
        ts = raw["ts"].astype("int64")
        raw["ts"] = ts.where(ts < 10_000_000_000, ts // 1000)

    raw = raw[raw["asset_id"].isin(token_to_m.keys())].copy()
    mid = raw["mid"].astype(float)
    raw = raw[(mid > 0.0) & (mid < 1.0)].copy()
    if raw.empty:
        return pd.DataFrame()

    raw["market_id"] = raw["asset_id"].map(lambda a: token_to_m[a]["market_id"])
    raw["max_spread"] = raw["asset_id"].map(lambda a: float(token_to_m[a]["rewards_max_spread"]))
    raw["base_comp"] = raw["asset_id"].map(lambda a: float(token_to_m[a].get("competition_q") or 800.0))

    bb = raw["best_bid"].astype(float)
    ba = raw["best_ask"].astype(float)
    mid = raw["mid"].astype(float)
    half_c = (ba - bb) * 50.0
    v = raw["max_spread"].astype(float)
    # spread-tightness proxy in [50, ...]
    frac = ((v - half_c) / v).clip(lower=0.0, upper=1.0)
    comp = (frac ** 2) * 200.0
    comp = comp.where((half_c >= 0) & (half_c < v), 50.0)
    raw["competition_q"] = comp.clip(lower=50.0).combine(raw["base_comp"], max)

    out = pd.DataFrame(
        {
            "ts": raw["ts"].astype("int64"),
            "market_id": raw["market_id"],
            "asset_id": raw["asset_id"],
            "mid": mid,
            "yes_mid": mid,
            "no_mid": 1.0 - mid,
            "best_bid": bb.fillna(mid - 0.01),
            "best_ask": ba.fillna(mid + 0.01),
            "competition_q": raw["competition_q"].astype(float),
        }
    )
    out = out.sort_values(["ts", "market_id"]).drop_duplicates(["ts", "market_id"], keep="last")
    return out.reset_index(drop=True)


def write_manifest(
    *,
    mode: str,
    days: list[str],
    completed_days: list[str],
    pending_days: list[str],
    markets: list[dict],
    prices: pd.DataFrame | None,
    fp: str,
    notes: str,
) -> dict:
    manifest: dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "hf_repo": HF_REPO,
        "hf_config": HF_CONFIG_PREFIX,
        "allowlist_fingerprint": fp,
        "allowlist_path": "data/top_reward_markets.json",
        "days": completed_days,
        "target_days": days,
        "pending_days": pending_days,
        "n_days_completed": len(completed_days),
        "n_days_target": len(days),
        "n_markets": len(markets),
        "n_price_rows": int(len(prices)) if prices is not None and len(prices) else 0,
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
            "https://gamma-api.polymarket.com",
            "https://clob.polymarket.com/sampling-simplified-markets",
            "data/top_reward_markets.json",
        ],
        "notes": notes,
        "resume": {
            "next_day": pending_days[0] if pending_days else None,
            "command": (
                f"python prepare.py --continuous --resume"
                if mode.startswith("continuous")
                else "python prepare.py"
            ),
        },
    }
    if prices is not None and len(prices) > 0:
        manifest["start_ts"] = int(prices["ts"].min())
        manifest["end_ts"] = int(prices["ts"].max())
        manifest["start_iso"] = datetime.fromtimestamp(
            int(prices["ts"].min()), timezone.utc
        ).isoformat()
        manifest["end_iso"] = datetime.fromtimestamp(
            int(prices["ts"].max()), timezone.utc
        ).isoformat()
    with open(DATA / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def slim_matches_allowlist(day_parquet: Path, yes_tokens: set[str]) -> bool:
    """True if slim file already contains (subset of) current allowlist tokens."""
    try:
        con = duckdb.connect()
        assets = {
            str(r[0])
            for r in con.execute(
                f"SELECT DISTINCT CAST(asset_id AS VARCHAR) FROM read_parquet('{day_parquet}')"
            ).fetchall()
        }
        con.close()
        # Reuse only if it has a meaningful fraction of allowlist (or any overlap with current set)
        # Old 7-token caches must be rebuilt when allowlist expanded.
        if not assets:
            return False
        # If slim has tokens outside allowlist only, or far fewer than expected, rebuild
        overlap = assets & yes_tokens
        if len(overlap) < min(5, len(yes_tokens)):
            # Might be sparse day with few markets present — OK if all assets ⊆ allowlist
            return assets <= yes_tokens and len(overlap) >= 1
        return assets <= yes_tokens or len(overlap) >= 5
    except Exception:
        return False


def process_days(
    days: list[str],
    markets: list[dict],
    *,
    mode: str,
    keep_raw: bool,
    max_days: int | None,
    reassemble_every: int,
    force_refilter: bool,
) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    SLIM.mkdir(parents=True, exist_ok=True)

    yes_tokens = [m["yes_token"] for m in markets]
    yes_set = set(yes_tokens)
    fp = allowlist_fingerprint(yes_tokens)

    # Resume: load prior completed if fingerprint matches
    completed: list[str] = []
    prior_path = DATA / "manifest.json"
    if prior_path.exists():
        try:
            prior = json.loads(prior_path.read_text())
            if prior.get("allowlist_fingerprint") == fp:
                completed = list(prior.get("days") or [])
                print(
                    f"[prepare] resume: {len(completed)} days already done (fp={fp})",
                    flush=True,
                )
            else:
                print(
                    f"[prepare] allowlist fingerprint changed "
                    f"({prior.get('allowlist_fingerprint')} → {fp}); "
                    f"will refilter slim caches as needed",
                    flush=True,
                )
        except Exception:
            pass

    pending = [d for d in days if d not in completed]
    # Also re-check slim validity
    really_done: list[str] = []
    for d in completed:
        sp = SLIM / f"{d}.parquet"
        if sp.exists() and not force_refilter and slim_matches_allowlist(sp, yes_set):
            really_done.append(d)
        else:
            print(f"[prepare] will refilter {d} (slim missing/stale)", flush=True)
    completed = really_done
    pending = [d for d in days if d not in completed]

    print(
        f"[prepare] mode={mode} target={len(days)} done={len(completed)} pending={len(pending)} "
        f"markets={len(markets)} fp={fp}",
        flush=True,
    )
    for m in markets[:12]:
        print(
            f"  ${m['daily_reward_pool']:.0f}/d  min={m['rewards_min_size']} "
            f"spr={m['rewards_max_spread']} | {(m.get('question') or '')[:55]}",
            flush=True,
        )
    if len(markets) > 12:
        print(f"  ... +{len(markets)-12} more", flush=True)

    n_processed = 0
    for day in pending:
        if max_days is not None and n_processed >= max_days:
            print(f"[prepare] hit --max-days={max_days}; stopping for resume", flush=True)
            break

        existing = SLIM / f"{day}.parquet"
        if (
            existing.exists()
            and existing.stat().st_size > 0
            and not force_refilter
            and slim_matches_allowlist(existing, yes_set)
        ):
            print(f"[prepare] reusing slim cache {existing}", flush=True)
            completed.append(day)
            n_processed += 1
        else:
            if existing.exists():
                existing.unlink()
            day_path = download_day(day)
            try:
                filter_day(day_path, day, yes_tokens)
                completed.append(day)
                n_processed += 1
            except Exception as e:
                print(f"[prepare] ERROR day={day}: {e}", flush=True)
                # Leave day pending for resume
            finally:
                if not keep_raw:
                    delete_raw(day_path)

        # Incremental manifest (resume-friendly) every day
        still_pending = [d for d in days if d not in completed]
        prices_partial = None
        do_assemble = (n_processed % max(1, reassemble_every) == 0) or (not still_pending)
        if do_assemble:
            slim_paths = [SLIM / f"{d}.parquet" for d in completed]
            print(f"[prepare] assembling prices from {len(slim_paths)} slim days...", flush=True)
            prices_partial = assemble_prices(slim_paths, markets)
            if prices_partial is not None and len(prices_partial) > 0:
                with open(DATA / "markets.json", "w") as f:
                    json.dump(markets, f, indent=2)
                prices_partial.to_parquet(DATA / "prices.parquet", index=False)
                pd.DataFrame(columns=["ts", "market_id", "price", "size", "side"]).to_parquet(
                    DATA / "trades.parquet", index=False
                )
                print(
                    f"[prepare] wrote prices.parquet rows={len(prices_partial)}",
                    flush=True,
                )

        # If we skipped assemble, reload existing prices for accurate manifest stats
        if prices_partial is None and (DATA / "prices.parquet").exists():
            try:
                prices_partial = pd.read_parquet(DATA / "prices.parquet")
            except Exception:
                prices_partial = None

        write_manifest(
            mode=mode,
            days=days,
            completed_days=completed,
            pending_days=still_pending,
            markets=markets,
            prices=prices_partial,
            fp=fp,
            notes=(
                f"{mode}: day-at-a-time HF orderbook_1min → allowlist filter → slim cache; "
                f"raw deleted. Skip {sorted(SKIP_DAYS)}. "
                "Reward rates from current Gamma/CLOB held constant."
            ),
        )
        print(
            f"[prepare] progress {len(completed)}/{len(days)} "
            f"(disk free check...)",
            flush=True,
        )

    # Final assemble if needed
    still_pending = [d for d in days if d not in completed]
    slim_paths = [SLIM / f"{d}.parquet" for d in completed if (SLIM / f"{d}.parquet").exists()]
    print(f"[prepare] final assemble from {len(slim_paths)} days...", flush=True)
    prices = assemble_prices(slim_paths, markets)
    if prices is None or prices.empty:
        write_manifest(
            mode=mode,
            days=days,
            completed_days=completed,
            pending_days=still_pending,
            markets=markets,
            prices=None,
            fp=fp,
            notes="INCOMPLETE: no price rows yet — resume prepare.",
        )
        print("[prepare] WARNING: no price rows yet; resume later", flush=True)
        return

    with open(DATA / "markets.json", "w") as f:
        json.dump(markets, f, indent=2)
    prices.to_parquet(DATA / "prices.parquet", index=False)
    pd.DataFrame(columns=["ts", "market_id", "price", "size", "side"]).to_parquet(
        DATA / "trades.parquet", index=False
    )
    write_manifest(
        mode=mode if not still_pending else f"{mode}_partial",
        days=days,
        completed_days=completed,
        pending_days=still_pending,
        markets=markets,
        prices=prices,
        fp=fp,
        notes=(
            f"{'COMPLETE' if not still_pending else 'PARTIAL'} continuous L2. "
            f"Completed {len(completed)}/{len(days)} days, {len(markets)} markets. "
            f"Raw day files deleted after filter. Skip {sorted(SKIP_DAYS)}."
        ),
    )
    slim_mb = sum(p.stat().st_size for p in SLIM.glob("*.parquet")) / 1e6
    print(
        f"[prepare] done: prices rows={len(prices)} markets={len(markets)} "
        f"days={len(completed)}/{len(days)} slim≈{slim_mb:.1f}MB "
        f"pending={len(still_pending)}",
        flush=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--continuous",
        action="store_true",
        help=f"Full day range {CONTINUOUS_START}→{CONTINUOUS_END} (skip Jun 12–17)",
    )
    ap.add_argument("--start", type=str, default=CONTINUOUS_START)
    ap.add_argument("--end", type=str, default=CONTINUOUS_END)
    ap.add_argument(
        "--days",
        type=str,
        default="",
        help="Comma-separated UTC days YYYY-MM-DD (overrides continuous/sparse)",
    )
    ap.add_argument(
        "--quick",
        action="store_true",
        help="Only two days (2026-05-14, 2026-07-20)",
    )
    ap.add_argument("--sparse", action="store_true", help="Legacy 5 sparse days")
    ap.add_argument("--keep-raw", action="store_true")
    ap.add_argument("--max-days", type=int, default=None, help="Process at most N pending days")
    ap.add_argument("--resume", action="store_true", help="Continue from manifest.json")
    ap.add_argument("--force-refilter", action="store_true")
    ap.add_argument("--reassemble-every", type=int, default=5)
    ap.add_argument(
        "--allowlist",
        type=str,
        default=str(DATA / "top_reward_markets.json"),
    )
    args = ap.parse_args()

    markets = load_allowlist_markets(Path(args.allowlist))
    if not markets:
        raise SystemExit("Allowlist empty")

    if args.days:
        days = [d.strip() for d in args.days.split(",") if d.strip()]
        mode = "custom_days_l2"
    elif args.quick:
        days = ["2026-05-14", "2026-07-20"]
        mode = "quick_l2"
    elif args.sparse:
        days = list(DEFAULT_SPARSE_DAYS)
        mode = "sparse_day_l2"
    elif args.continuous or args.resume:
        days = daterange(args.start, args.end, SKIP_DAYS)
        mode = "continuous_l2"
    else:
        # Default: continuous (user request)
        days = daterange(args.start, args.end, SKIP_DAYS)
        mode = "continuous_l2"

    process_days(
        days,
        markets,
        mode=mode,
        keep_raw=args.keep_raw,
        max_days=args.max_days,
        reassemble_every=args.reassemble_every,
        force_refilter=args.force_refilter,
    )


if __name__ == "__main__":
    main()
