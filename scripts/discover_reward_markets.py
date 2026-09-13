#!/usr/bin/env python3
"""
Build a top-LP-reward YES-token universe from Gamma (+ optional CLOB hints).

Ranks active markets by rewardsDailyRate (sum of clobRewards), then volume.
Keeps names that were listed before the HF archive end (2026-08-10) so they
can appear in the May–Aug 2026 orderbook_1min window.

Writes data/reward_universe.json for prepare.py to merge with the seed list.
Does not download order books.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prepare import (  # noqa: E402
    GAMMA,
    SESSION,
    YES_TOKENS,
    daily_rate_from_gamma,
    parse_token_ids,
)

ARCHIVE_END = "2026-08-10"
CLOB = "https://clob.polymarket.com"
OUT = ROOT / "data" / "reward_universe.json"


def _slug_key(question: str, used: set[str], n: int) -> str:
    raw = "".join(ch if ch.isalnum() else "_" for ch in (question or "mkt").lower())
    raw = "_".join(p for p in raw.split("_") if p)[:28].strip("_") or f"mkt_{n}"
    key = raw
    i = 2
    while key in used:
        key = f"{raw[:24]}_{i}"
        i += 1
    used.add(key)
    return key


def sweep_gamma(max_pages: int = 80) -> list[dict]:
    rows: list[dict] = []
    for offset in range(0, max_pages * 100, 100):
        try:
            page = SESSION.get(
                f"{GAMMA}/markets",
                params={"limit": 100, "offset": offset, "closed": "false"},
                timeout=60,
            )
            page.raise_for_status()
            chunk = page.json()
        except Exception as e:
            print(f"[discover] gamma offset={offset} failed: {e}")
            break
        if not chunk:
            break
        rows.extend(chunk)
        if offset % 1000 == 0:
            print(f"[discover] gamma scanned {len(rows)} markets")
        if len(chunk) < 100:
            break
    return rows


def try_clob_rewards() -> list[dict]:
    """Best-effort extra reward configs; Gamma is the source of truth."""
    extra: list[dict] = []
    for path in ("/rewards", "/rewards/markets", "/rewards/configs"):
        try:
            r = SESSION.get(CLOB + path, timeout=20)
            if r.status_code != 200:
                continue
            body = r.json()
            if isinstance(body, list):
                extra.extend(body)
            elif isinstance(body, dict):
                extra.append(body)
            print(f"[discover] CLOB {path} returned {r.status_code} keys/len={len(body) if hasattr(body,'__len__') else type(body)}")
        except Exception as e:
            print(f"[discover] CLOB {path} skip: {e}")
    return extra


def rank_markets(raw: list[dict], min_rate: float) -> list[dict]:
    ranked: list[dict] = []
    seen: set[str] = set()
    for m in raw:
        toks = parse_token_ids(m.get("clobTokenIds"))
        if not toks:
            continue
        yes = str(toks[0])
        if yes in seen:
            continue
        rate = daily_rate_from_gamma(m)
        if rate < min_rate:
            # also accept rewardsDailyRate on the market itself
            try:
                rate = max(rate, float(m.get("rewardsDailyRate") or 0))
            except Exception:
                pass
        if rate < min_rate:
            continue
        start = str(m.get("startDate") or m.get("createdAt") or "")
        if start >= ARCHIVE_END:
            continue
        seen.add(yes)
        ranked.append(
            {
                "yes_token": yes,
                "no_token": str(toks[1]) if len(toks) > 1 else None,
                "condition_id": m.get("conditionId"),
                "question": m.get("question"),
                "slug": m.get("slug"),
                "event_slug": None,
                "rewardsDailyRate": rate,
                "rewardsMinSize": float(m.get("rewardsMinSize") or 50),
                "rewardsMaxSpread": float(m.get("rewardsMaxSpread") or 4.5),
                "volume_num": float(m.get("volumeNum") or 0),
                "liquidity_num": float(m.get("liquidityNum") or 0),
                "start_date": start,
                "end_date": m.get("endDate"),
            }
        )
    ranked.sort(key=lambda x: (-x["rewardsDailyRate"], -x["volume_num"]))
    return ranked


def to_spec(seed: dict[str, dict], ranked: list[dict], max_tokens: int) -> dict[str, dict]:
    out = dict(seed)
    used = {v["slug_key"] for v in out.values()}
    for m in ranked:
        if len(out) >= max_tokens:
            break
        yes = m["yes_token"]
        if yes in out:
            continue
        key = _slug_key(m.get("question") or m.get("slug") or "mkt", used, len(out))
        out[yes] = {
            "slug_key": key,
            "event_slug": m.get("event_slug"),
            "condition_id": m.get("condition_id"),
            "default_pool": float(m["rewardsDailyRate"]),
            "question": m.get("question"),
            "volume_num": m.get("volume_num"),
            "liquidity_num": m.get("liquidity_num"),
            "start_date": m.get("start_date"),
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-tokens", type=int, default=80)
    ap.add_argument("--min-rate", type=float, default=8.0)
    ap.add_argument("--max-pages", type=int, default=80)
    args = ap.parse_args()

    print(f"[discover] sweeping Gamma (min_rate={args.min_rate}, cap={args.max_tokens})")
    raw = sweep_gamma(max_pages=args.max_pages)
    print(f"[discover] gamma rows={len(raw)}")
    clob = try_clob_rewards()
    print(f"[discover] clob extra blobs={len(clob)}")
    ranked = rank_markets(raw, min_rate=args.min_rate)
    print(f"[discover] ranked reward markets listed before {ARCHIVE_END}: {len(ranked)}")
    for i, m in enumerate(ranked[:15], 1):
        print(
            f"  {i:2d}. ${m['rewardsDailyRate']:.0f}/d  vol={m['volume_num']:.0f}  "
            f"{(m['question'] or '')[:70]}"
        )
    spec = to_spec(YES_TOKENS, ranked, max_tokens=args.max_tokens)
    pools = [float(v.get("default_pool") or 0) for v in spec.values()]
    payload = {
        "created_from": "scripts/discover_reward_markets.py",
        "archive_end": ARCHIVE_END,
        "n_tokens": len(spec),
        "n_seed": len(YES_TOKENS),
        "min_rate": args.min_rate,
        "total_daily_pool_usd": round(sum(pools), 2),
        "yes_tokens": spec,
        "top": [
            {
                "slug_key": spec[t]["slug_key"],
                "question": spec[t].get("question"),
                "default_pool": spec[t].get("default_pool"),
            }
            for t in list(spec)[:20]
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))
    print(
        f"[discover] wrote {OUT} tokens={len(spec)} "
        f"seed={len(YES_TOKENS)} extra={len(spec) - len(YES_TOKENS)} "
        f"sum_pools=${sum(pools):.0f}/d"
    )


if __name__ == "__main__":
    main()
