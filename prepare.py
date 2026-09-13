#!/usr/bin/env python3
"""
Fixed data preparation — sparse-day L2 from HuggingFace Joseph3222/polymarket-orderbook
(orderbook_1min only). Does NOT download the raw TB-scale orderbook stream.

Downloads selected UTC day files (~0.5–2.5GB each), DuckDB-filters to a curated
YES-token universe (~15–25 outcomes), writes slim caches under data/, then deletes
full day files AND the HuggingFace hub cache so peak disk stays well under 10GB.

This is sparse-day sampling across Feb–Aug 2026 — NOT continuous L2.
Archive starts 2026-02-22, skips Jun 12–17, ends 2026-08-10.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
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
UNIVERSE_PATH = SLIM / "universe.json"
GAMMA = "https://gamma-api.polymarket.com"

HF_REPO = "Joseph3222/polymarket-orderbook"
HF_CONFIG_PREFIX = "orderbook_1min"

# Point HF caches at data/raw_hf so we can delete them after each day.
os.environ.setdefault("HF_HOME", str(RAW / "hf_home"))
os.environ.setdefault("HF_HUB_CACHE", str(RAW / "hub_cache"))

# Prefer more days over denser hours. Sizes chosen so the sum of raw day files
# is ~9.8GB (under the 10GB download+cache budget). Skip Jun 12–17 (missing).
# Replaced huge 2026-08-06 (~2.5GB) with archive-end 2026-08-10 (~0.12GB).
DEFAULT_DAYS = [
    "2026-02-22",
    "2026-03-08",
    "2026-03-29",
    "2026-04-05",
    "2026-04-12",
    "2026-05-14",
    "2026-06-01",
    "2026-06-18",
    "2026-06-25",
    "2026-07-20",
    "2026-08-10",
]

# Hard cap on raw+cache footprint while a day is on disk.
MAX_DATA_GB = 10.0

# YES token asset_ids. Phase-1 seed (Fed Sep + Iran + Trump) plus phase-2
# Gamma-discovered high rewardsDailyRate / liquid names that were listed
# before the archive window (so they can appear in Feb–Aug 2026 books).
YES_TOKENS = {
    # --- phase-1 seed ---
    "97186030785608128217926542396950266594898339988989015155120280107165449433603": {
        "slug_key": "fed_m50",
        "event_slug": "fed-decision-in-september-762",
        "default_pool": 50.0,
    },
    "57748138085022719760345772310040703848567377822400132842014290209986511882046": {
        "slug_key": "fed_m25",
        "event_slug": "fed-decision-in-september-762",
        "default_pool": 100.0,
    },
    "5615282760875985231868508008056959876238536896643315063916840237042205273721": {
        "slug_key": "fed_0",
        "event_slug": "fed-decision-in-september-762",
        "default_pool": 1000.0,
    },
    "63842529068710005716169325380315470359047749786610778647370693404952498013178": {
        "slug_key": "fed_p25",
        "event_slug": "fed-decision-in-september-762",
        "default_pool": 1000.0,
    },
    "88912926533493988427719291698947688154042720958310632316541141466409683822293": {
        "slug_key": "fed_p50",
        "event_slug": "fed-decision-in-september-762",
        "default_pool": 50.0,
    },
    "55115078421062885512539156303747803058407616201213034911037320915726138659123": {
        "slug_key": "iran",
        "event_slug": None,
        "condition_id": "0x5db999fad322cea2914535aae5517060c3f80ad6d8c0231cde2124a434d16846",
        "default_pool": 400.0,
    },
    "59252515735652674747158950210016502214756531287333895140318848923768750410355": {
        "slug_key": "trump_out",
        "event_slug": "trump-out-as-president-before-2027",
        "default_pool": 1.0,
    },
    # --- phase-2: high rewardsDailyRate + volume/liquidity, live in archive window ---
    "52487256270918227930942830546248720603566203568229607048093730748840489555808": {
        "slug_key": "eizenkot_pm",
        "event_slug": "who-will-be-the-next-prime-minister-of-israel-after-the-next-election",
        "condition_id": "0xdbe93b5a701f36076a560fa4b9ba59e365a6e8e2ea6a83764640010657277ca4",
        "default_pool": 298.0,
    },
    "109876868437950584369987384406356259939519193117253465815665152916226511121427": {
        "slug_key": "flavio_br",
        "event_slug": "brazil-presidential-election",
        "condition_id": "0x1a01bf78f56a507fcb666d564d8c8b91b0750679163ed6e96746102c9b7d285d",
        "default_pool": 253.0,
    },
    "30630994248667897740988010928640156931882346081873066002335460180076741328029": {
        "slug_key": "lula_br",
        "event_slug": "brazil-presidential-election",
        "condition_id": "0xdf8e2dc5860027decbe6164555c3c1c9645c3bd33e16b9dc57ca87125047d4a8",
        "default_pool": 247.0,
    },
    "55764212211467781322980371912612507865974994976253196346176314491480419639168": {
        "slug_key": "lepen_fr",
        "event_slug": "next-french-presidential-election",
        "condition_id": "0x8126317d621047fb13d508a2651eecc8d38305904671822a62309c5aabd353aa",
        "default_pool": 242.0,
    },
    "32950178421556833525068948927823594772134813180063196823389171317494746105102": {
        "slug_key": "antonelli_f1",
        "event_slug": "2026-f1-drivers-champion",
        "condition_id": "0xcd2640464754b9a894ffec98ac11554fdd507ea89ca01237eabb3a6de4a606e6",
        "default_pool": 200.0,
    },
    "84846382165343032223975853870946110241285484772019446686866815597350660955868": {
        "slug_key": "philippe_fr",
        "event_slug": "next-french-presidential-election",
        "condition_id": "0x46f2f457e14ee9021ebd0ef4c27eacd98fdceaf7f2938b484e2551e9e3275ae8",
        "default_pool": 186.0,
    },
    "20006732765674855733524007935991362439352594042415161039767275461950712817548": {
        "slug_key": "netanyahu_pm",
        "event_slug": "who-will-be-the-next-prime-minister-of-israel-after-the-next-election",
        "condition_id": "0x7586a96520578acaaaa4ea84a2582f197f84255da1f3392a7aa300386c187b37",
        "default_pool": 172.0,
    },
    "72710166409980712002774407052535905861151156175854323762835102340552522606004": {
        "slug_key": "kane_ballon",
        "event_slug": "ballon-dor-winner-2026",
        "condition_id": "0x12dc2b61723b2a54fc1947a307389b5f32038e7a29a0e936ad1fe410b969d06a",
        "default_pool": 131.0,
    },
    "12403602920039269077597917340921667997547115084613238528792639013246536343316": {
        "slug_key": "no_fed_cuts",
        "event_slug": "how-many-fed-rate-cuts-in-2026",
        "condition_id": "0xd4e77ba6f29fc093509d24f508631abd445ecf506bbdc9c4c80e60256a318527",
        "default_pool": 116.0,
    },
    "107505882767731489358349912513945399560393482969656700824895970500493757150417": {
        "slug_key": "aliens",
        "event_slug": "will-the-us-confirm-that-aliens-exist-before-2027",
        "condition_id": "0x747dc809fb79e1b05be09c42d6179459a58de2ef3e40f02484a4e1260f741f75",
        "default_pool": 100.0,
    },
    "40081275558852222228080198821361202017557872256707631666334039001378518619916": {
        "slug_key": "vance_gop",
        "event_slug": "republican-presidential-nominee-2028",
        "condition_id": "0x18b1c135d0a40c5894da9412e77311827d9caf16cf4cd6591b247a34730af919",
        "default_pool": 79.0,
    },
    "350977769852917329387037893294763093471844346281449484439085576212613048126": {
        "slug_key": "putin_out",
        "event_slug": "putin-out-before-2027",
        "condition_id": "0x6bd56627aa21311850825edb27e53434a0e17a4f782be0086bc07f71eee00d0d",
        "default_pool": 70.0,
    },
    "10991849228756847439673778874175365458450913336396982752046655649803657501964": {
        "slug_key": "iran_regime",
        "event_slug": "will-the-iranian-regime-fall-by-the-end-of-2026",
        "condition_id": "0xbb4d51e6364066d92eb6f9b8413dd7193de70966736044463b205834805a1f3b",
        "default_pool": 70.0,
    },
    "113379839734351069617987084078322474966003108854908079701423911002443710490196": {
        "slug_key": "one_fed_cut",
        "event_slug": "how-many-fed-rate-cuts-in-2026",
        "condition_id": "0x5e082f0b57f47a29044aa35b4c5658393122e659d5feae521c06b57cdd7f905c",
        "default_pool": 66.0,
    },
    "94559586571241563470235664821564670251180951772614764383113614156422396181162": {
        "slug_key": "china_taiwan",
        "event_slug": "will-china-invade-taiwan-before-2027",
        "condition_id": "0xd9fb1184af0064e5e34b129f5b79afa5a17b7e32f2953ab05efed82315fee6d4",
        "default_pool": 50.0,
    },
}

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "polymarket-lp-autoresearch/0.2"})


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


def fetch_market_meta(token_spec: dict[str, dict] | None = None) -> list[dict[str, Any]]:
    """Resolve Gamma metadata for each YES token; rewards from current Gamma fields."""
    token_spec = token_spec or YES_TOKENS
    by_token: dict[str, dict] = {}
    event_cache: dict[str, dict] = {}

    def ingest_event(slug: str) -> None:
        if not slug or slug in event_cache:
            return
        try:
            ev = get_json(f"{GAMMA}/events/slug/{slug}")
        except Exception as e:
            print(f"[prepare] WARNING: event {slug} fetch failed: {e}")
            event_cache[slug] = {}
            return
        event_cache[slug] = ev
        for m in ev.get("markets") or []:
            toks = parse_token_ids(m.get("clobTokenIds"))
            if toks and toks[0] in token_spec:
                by_token[toks[0]] = m

    for yes, meta0 in token_spec.items():
        if meta0.get("event_slug"):
            ingest_event(str(meta0["event_slug"]))
        if yes in by_token:
            continue
        cid = meta0.get("condition_id")
        if not cid:
            continue
        try:
            rows = get_json(f"{GAMMA}/markets", {"condition_ids": cid})
        except Exception as e:
            print(f"[prepare] WARNING: condition {cid[:16]}... fetch failed: {e}")
            continue
        if rows:
            toks = parse_token_ids(rows[0].get("clobTokenIds"))
            if toks:
                by_token[toks[0]] = rows[0]

    markets: list[dict] = []
    for yes, meta0 in token_spec.items():
        g = by_token.get(yes)
        if not g:
            print(f"[prepare] WARNING: no gamma meta for {meta0['slug_key']} ({yes[:16]}...)")
            continue
        toks = parse_token_ids(g.get("clobTokenIds"))
        daily = daily_rate_from_gamma(g)
        if daily <= 0:
            daily = float(meta0.get("default_pool") or 50.0)
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
                "liquidity_num": float(g.get("liquidityNum") or 0),
                "start_date": g.get("startDate"),
                "end_date": g.get("endDate"),
                "rewards_note": (
                    "Using current Gamma rewardsMinSize/rewardsMaxSpread/rewardsDailyRate "
                    "as a constant schedule; historical rates may have differed."
                ),
            }
        )
    return markets


def discover_extra_tokens(seed: dict[str, dict], max_tokens: int = 25) -> dict[str, dict]:
    """
    Optional Gamma sweep for additional high-reward active markets.
    Only used with --discover; default path uses the curated YES_TOKENS list.
    """
    out = dict(seed)
    if len(out) >= max_tokens:
        return out
    scored: list[tuple[float, str, dict]] = []
    for offset in range(0, 1500, 100):
        try:
            rows = get_json(f"{GAMMA}/markets", {"limit": 100, "offset": offset, "closed": "false"})
        except Exception as e:
            print(f"[prepare] discover page {offset} failed: {e}")
            break
        if not rows:
            break
        for m in rows:
            toks = parse_token_ids(m.get("clobTokenIds"))
            if not toks:
                continue
            yes = toks[0]
            if yes in out:
                continue
            rate = daily_rate_from_gamma(m)
            vol = float(m.get("volumeNum") or 0)
            liq = float(m.get("liquidityNum") or 0)
            if rate < 40 or vol < 5e5 or liq < 5e4:
                continue
            start = str(m.get("startDate") or "")
            # Must have existed during the archive window (listed before 2026-08-10)
            if start >= "2026-08-10":
                continue
            scored.append((rate + 0.000001 * vol, yes, m))
        if len(rows) < 100:
            break
    scored.sort(key=lambda x: -x[0])
    for _score, yes, m in scored:
        if len(out) >= max_tokens:
            break
        q = (m.get("question") or "mkt")[:40]
        slug = "".join(ch if ch.isalnum() else "_" for ch in q.lower())[:24].strip("_") or f"disc_{len(out)}"
        out[yes] = {
            "slug_key": slug,
            "event_slug": None,
            "condition_id": m.get("conditionId"),
            "default_pool": daily_rate_from_gamma(m),
        }
        print(f"[prepare] discover +{slug} rate={daily_rate_from_gamma(m):.0f} {(m.get('question') or '')[:60]}")
    return out


def universe_hash(yes_tokens: list[str]) -> str:
    blob = ",".join(sorted(yes_tokens)).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def invalidate_slim_if_stale(yes_tokens: list[str]) -> None:
    """Rebuild slim days when the token universe changes (old caches lack new assets)."""
    want = universe_hash(yes_tokens)
    prev = None
    if UNIVERSE_PATH.exists():
        try:
            prev = json.loads(UNIVERSE_PATH.read_text()).get("hash")
        except Exception:
            prev = None
    if prev == want:
        return
    if any(SLIM.glob("*.parquet")):
        print(f"[prepare] token universe changed ({prev} -> {want}); dropping stale slim caches")
        for p in SLIM.glob("*.parquet"):
            p.unlink()
    SLIM.mkdir(parents=True, exist_ok=True)
    UNIVERSE_PATH.write_text(
        json.dumps({"hash": want, "n_tokens": len(yes_tokens), "yes_tokens": yes_tokens}, indent=2)
    )


def data_dir_gb() -> float:
    total = 0
    if not DATA.exists():
        return 0.0
    for p in DATA.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total / 1e9


def cleanup_raw() -> None:
    if RAW.exists():
        shutil.rmtree(RAW, ignore_errors=True)


def download_day(day: str) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    used = data_dir_gb()
    if used > MAX_DATA_GB:
        raise SystemExit(f"[prepare] data/ already {used:.2f} GB > {MAX_DATA_GB} GB budget")
    print(f"[prepare] downloading HF orderbook_1min date={day} (data/ {used:.2f} GB) ...")
    kwargs: dict[str, Any] = {
        "repo_id": HF_REPO,
        "repo_type": "dataset",
        "filename": f"{HF_CONFIG_PREFIX}/date={day}/data_0.parquet",
        "cache_dir": str(RAW / "hub_cache"),
    }
    try:
        path = hf_hub_download(**kwargs, local_dir=str(RAW), local_dir_use_symlinks=False)
    except TypeError:
        # huggingface_hub >=1.x dropped local_dir_use_symlinks
        path = hf_hub_download(**kwargs, local_dir=str(RAW))
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


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    if isinstance(row, pd.Series):
        return row.get(key, default)
    return getattr(row, key, default)


def competition_from_book(row: Any, max_spread_cents: float) -> float:
    """Approximate competing Q from observed L2 depth within max spread of mid."""
    mid_v = _row_get(row, "mid")
    mid = float(mid_v) if mid_v is not None and pd.notna(mid_v) else None
    if mid is None or mid <= 0:
        return 800.0
    v = max_spread_cents
    # Prefer explicit best sizes if depth arrays missing
    q = 0.0
    bids_raw = _row_get(row, "bids_raw")
    asks_raw = _row_get(row, "asks_raw")

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
        bb = _row_get(row, "best_bid")
        ba = _row_get(row, "best_ask")
        if bb is not None and ba is not None and pd.notna(bb) and pd.notna(ba):
            half_c = (float(ba) - float(bb)) * 50.0
            if 0 <= half_c < v:
                q = ((v - half_c) / v) ** 2 * 200.0  # assume ~200 sh near touch
    # Tighter observed BBO ⇒ more resting competition at the touch
    bb = _row_get(row, "best_bid")
    ba = _row_get(row, "best_ask")
    if bb is not None and ba is not None and pd.notna(bb) and pd.notna(ba):
        spr_c = (float(ba) - float(bb)) * 100.0
        if 0 < spr_c <= 2.0:
            q *= 1.0 + 0.25 * (2.0 - spr_c) / 2.0
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
    cols = list(raw.columns)
    for r in raw.itertuples(index=False, name="Slim"):
        rec = {c: getattr(r, c) for c in cols}
        asset = str(rec["asset_id"])
        m = token_to_m.get(asset)
        if not m:
            continue
        mid = float(rec["mid"])
        if not (0.0 < mid < 1.0):
            continue
        comp = competition_from_book(rec, float(m["rewards_max_spread"]))
        bb = rec.get("best_bid")
        ba = rec.get("best_ask")
        rows.append(
            {
                "ts": int(rec["ts"]),
                "market_id": m["market_id"],
                "asset_id": asset,
                "mid": mid,
                "yes_mid": mid,
                "no_mid": 1.0 - mid,
                "best_bid": float(bb) if bb is not None and pd.notna(bb) else mid - 0.01,
                "best_ask": float(ba) if ba is not None and pd.notna(ba) else mid + 0.01,
                "competition_q": comp,
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.sort_values(["ts", "market_id"]).drop_duplicates(["ts", "market_id"], keep="last")
    return out.reset_index(drop=True)


def _sanitize_days(days: list[str]) -> list[str]:
    skip = {f"2026-06-{d:02d}" for d in range(12, 18)}
    out: list[str] = []
    for d in days:
        if d in skip:
            print(f"[prepare] skipping {d} (archive gap Jun 12–17)")
            continue
        if d < "2026-02-22" or d > "2026-08-10":
            print(f"[prepare] skipping {d} (outside archive 2026-02-22…2026-08-10)")
            continue
        out.append(d)
    return out


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
    ap.add_argument(
        "--discover",
        action="store_true",
        help="Sweep Gamma for extra high-reward tokens (capped by --max-tokens)",
    )
    ap.add_argument("--max-tokens", type=int, default=25)
    ap.add_argument("--force-refresh", action="store_true", help="Ignore slim caches")
    args = ap.parse_args()

    DATA.mkdir(parents=True, exist_ok=True)

    if args.days:
        days = [d.strip() for d in args.days.split(",") if d.strip()]
    elif args.quick:
        days = ["2026-05-14", "2026-07-20"]
    else:
        days = list(DEFAULT_DAYS)
    days = _sanitize_days(days)

    print(f"[prepare] sparse days: {days}")
    spec = dict(YES_TOKENS)
    if args.discover:
        spec = discover_extra_tokens(spec, max_tokens=int(args.max_tokens))
    markets = fetch_market_meta(spec)
    print(f"[prepare] resolved {len(markets)} markets:")
    for m in markets:
        print(
            f"  {m['slug_key']}: pool=${m['daily_reward_pool']:.0f}/d "
            f"min={m['rewards_min_size']} spread={m['rewards_max_spread']} | {(m['question'] or '')[:60]}"
        )

    yes_tokens = [m["yes_token"] for m in markets]
    token_to_market = {m["yes_token"]: m["market_id"] for m in markets}
    if args.force_refresh:
        for p in SLIM.glob("*.parquet"):
            p.unlink()
        if UNIVERSE_PATH.exists():
            UNIVERSE_PATH.unlink()
    invalidate_slim_if_stale(yes_tokens)

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
                print("[prepare]   deleting raw day + HF cache to free disk")
                cleanup_raw()

    prices = assemble_prices(slim_paths, markets)
    if prices.empty:
        raise SystemExit("No rows after filter — check tokens/days presence in archive")

    # Drop tokens that never appear in the sampled days (no free reward ticks)
    present = set(prices["market_id"].unique())
    missing = [m["slug_key"] for m in markets if m["market_id"] not in present]
    if missing:
        print(f"[prepare] no L2 rows for: {', '.join(missing)} (dropped from universe)")
    markets = [m for m in markets if m["market_id"] in present]

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
            "SPARSE-DAY sampling (not continuous L2). "
            f"{len(days)} UTC days from 2026-02-22 to 2026-08-10; Jun 12–17 missing in archive. "
            "Full HF day files filtered to curated YES tokens then discarded with the HF cache. "
            "Reward rates from current Gamma fields held constant over the window. "
            "CLOB prices-history was NOT used (insufficient lookback overlap with archives)."
        ),
        "phase": 2,
        "n_tokens_requested": len(yes_tokens),
        "dropped_no_l2": missing,
        "data_dir_gb": round(data_dir_gb(), 3),
    }
    with open(DATA / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    slim_mb = sum(p.stat().st_size for p in SLIM.glob("*.parquet")) / 1e6
    print(f"[prepare] prices rows={len(prices)} markets={len(markets)}")
    print(f"[prepare] slim days ≈ {slim_mb:.2f} MB; data/ ≈ {data_dir_gb():.3f} GB")
    print("[prepare] done")


if __name__ == "__main__":
    main()
