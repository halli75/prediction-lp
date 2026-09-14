"""Live Polymarket CLOB/Gamma feed for paper trading (read-only)."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

CLOB = "https://clob.polymarket.com"
GAMMA = "https://gamma-api.polymarket.com"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "polymarket-lp-paper/0.1 (simulate-only)"})

MIN_POOL_DEFAULT = 110.0


def _get_json(url: str, params: dict | None = None, timeout: float = 45.0) -> Any:
    r = SESSION.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _pool_from_clob_rewards(rewards: dict | None) -> float:
    if not rewards:
        return 0.0
    total = 0.0
    for rr in rewards.get("rates") or []:
        try:
            total += float(rr.get("rewards_daily_rate") or 0)
        except (TypeError, ValueError):
            pass
    return total


def _yes_no_tokens(tokens: list[dict] | None) -> tuple[str | None, str | None]:
    yes = no = None
    for t in tokens or []:
        outcome = str(t.get("outcome") or "").lower()
        tid = str(t.get("token_id") or "")
        if not tid:
            continue
        if outcome in ("yes", "y"):
            yes = tid
        elif outcome in ("no", "n"):
            no = tid
    if yes is None and tokens:
        yes = str(tokens[0].get("token_id") or "") or None
    if no is None and tokens and len(tokens) > 1:
        no = str(tokens[1].get("token_id") or "") or None
    return yes, no


def _parse_end_date(raw: Any) -> datetime | None:
    if raw is None or raw == "":
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        try:
            return datetime.fromtimestamp(float(s), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None


def _is_ended(m: dict, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    if m.get("closed") is True:
        return True
    if m.get("active") is False:
        return True
    if m.get("accepting_orders") is False:
        return True
    end = _parse_end_date(m.get("end_date") or m.get("endDate"))
    if end is not None and end < now:
        return True
    return False


def fetch_all_sampling_markets(max_pages: int = 25) -> list[dict]:
    """Paginate CLOB /sampling-simplified-markets."""
    out: list[dict] = []
    cursor: str | None = None
    for _ in range(max_pages):
        params = {}
        if cursor:
            params["next_cursor"] = cursor
        data = _get_json(f"{CLOB}/sampling-simplified-markets", params=params or None)
        batch = data.get("data") or []
        out.extend(batch)
        cursor = data.get("next_cursor")
        if not cursor or cursor == "LTE=" or not batch:
            break
        time.sleep(0.05)
    return out


def enrich_gamma(condition_ids: list[str], chunk: int = 20) -> dict[str, dict]:
    """Map condition_id -> gamma market dict (question, endDate, etc.)."""
    by_id: dict[str, dict] = {}
    for i in range(0, len(condition_ids), chunk):
        part = condition_ids[i : i + chunk]
        # Gamma accepts comma-separated condition_ids
        try:
            raw = _get_json(
                f"{GAMMA}/markets",
                params={"condition_ids": ",".join(part), "limit": len(part)},
            )
        except Exception:
            # fallback one-by-one
            raw = []
            for cid in part:
                try:
                    one = _get_json(f"{GAMMA}/markets", params={"condition_ids": cid})
                    if isinstance(one, list):
                        raw.extend(one)
                except Exception:
                    continue
        if isinstance(raw, list):
            for m in raw:
                cid = str(m.get("conditionId") or m.get("condition_id") or "")
                if cid:
                    by_id[cid] = m
        time.sleep(0.05)
    return by_id


def discover_reward_markets(
    min_pool: float = MIN_POOL_DEFAULT,
    *,
    skip_ended: bool = True,
) -> list[dict[str, Any]]:
    """
    Discover open reward markets with daily_reward_pool >= min_pool.

    Prefer CLOB sampling-simplified-markets; enrich with Gamma for question/end.
    """
    now = datetime.now(timezone.utc)
    raw = fetch_all_sampling_markets()
    candidates: list[dict[str, Any]] = []
    for m in raw:
        if not m.get("active") or m.get("closed") or m.get("archived"):
            continue
        if not m.get("accepting_orders", True):
            continue
        rewards = m.get("rewards") or {}
        pool = _pool_from_clob_rewards(rewards)
        if pool < float(min_pool):
            continue
        yes, no = _yes_no_tokens(m.get("tokens"))
        if not yes:
            continue
        cid = str(m.get("condition_id") or "")
        candidates.append(
            {
                "market_id": cid or yes,
                "condition_id": cid,
                "yes_token": yes,
                "no_token": no,
                "daily_reward_pool": float(pool),
                "rewards_min_size": float(rewards.get("min_size") or 50),
                "rewards_max_spread": float(rewards.get("max_spread") or 3.5),
                "active": True,
                "closed": False,
                "accepting_orders": True,
            }
        )

    gamma = enrich_gamma([c["condition_id"] for c in candidates if c.get("condition_id")])
    markets: list[dict[str, Any]] = []
    for c in candidates:
        g = gamma.get(c["condition_id"]) or {}
        c["question"] = g.get("question") or c.get("question") or c["condition_id"][:16]
        c["end_date"] = g.get("endDate") or g.get("end_date_iso") or g.get("endDateIso")
        c["slug_key"] = (g.get("slug") or c["condition_id"][:20])[:40]
        c["volume_num"] = float(g.get("volumeNum") or g.get("volume") or 0 or 0)
        if g.get("closed") is True:
            c["closed"] = True
        if g.get("active") is False:
            c["active"] = False
        # competition proxy (same as prepare allowlist)
        c["competition_q"] = max(800.0, float(c["rewards_min_size"]) * 30.0)
        if skip_ended and _is_ended(c, now):
            continue
        markets.append(c)

    markets.sort(key=lambda x: (-float(x["daily_reward_pool"]), x["market_id"]))
    return markets


def save_markets_live(markets: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "n_markets": len(markets),
        "min_daily_reward_pool": MIN_POOL_DEFAULT,
        "markets": markets,
    }
    path.write_text(json.dumps(payload, indent=2))


def load_markets_live(path: Path) -> list[dict]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text())
    return list(raw.get("markets") or [])


def fetch_book(token_id: str) -> dict[str, Any]:
    return _get_json(f"{CLOB}/book", params={"token_id": token_id})


def fetch_midpoint(token_id: str) -> float | None:
    try:
        data = _get_json(f"{CLOB}/midpoint", params={"token_id": token_id})
        mid = data.get("mid") if isinstance(data, dict) else data
        if mid is None:
            return None
        return float(mid)
    except Exception:
        return None


def bbo_from_book(book: dict) -> tuple[float | None, float | None, float | None]:
    """Return (best_bid, best_ask, mid) from a CLOB book response."""
    bids = book.get("bids") or []
    asks = book.get("asks") or []
    best_bid = max((float(x["price"]) for x in bids), default=None)
    best_ask = min((float(x["price"]) for x in asks), default=None)
    mid = None
    if best_bid is not None and best_ask is not None and best_ask >= best_bid:
        mid = 0.5 * (best_bid + best_ask)
    return best_bid, best_ask, mid


def fetch_market_snapshot(yes_token: str) -> dict[str, Any]:
    """Fetch live BBO + mid for a YES token (read-only)."""
    out: dict[str, Any] = {
        "yes_token": yes_token,
        "best_bid": None,
        "best_ask": None,
        "mid": None,
        "ok": False,
        "error": None,
    }
    try:
        book = fetch_book(yes_token)
        bb, ba, mid = bbo_from_book(book)
        out["best_bid"] = bb
        out["best_ask"] = ba
        out["mid"] = mid
        if mid is None:
            mid2 = fetch_midpoint(yes_token)
            out["mid"] = mid2
        out["ok"] = out["mid"] is not None
        out["book_ts"] = book.get("timestamp")
    except Exception as e:
        out["error"] = str(e)
        try:
            mid2 = fetch_midpoint(yes_token)
            if mid2 is not None:
                out["mid"] = mid2
                out["ok"] = True
                out["error"] = f"book_failed:{e}"
        except Exception as e2:
            out["error"] = f"{e}; midpoint:{e2}"
    return out
