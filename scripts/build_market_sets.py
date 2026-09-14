#!/usr/bin/env python3
"""Build candidate market-universe allowlists under research/market_sets/."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKETS_PATH = ROOT / "data" / "markets.json"
OUT_DIR = ROOT / "research" / "market_sets"

# Hardcoded seed from strategy.py (Fed / Iran geopolitics)
SEED_FED_IRAN = [
    "0xa3b36b2d6104d34af4e6c6215fc818e43352e78a748fbfb0b85e3a35f71dec9a",
    "0x876506d8b2bd7a0d3fa4fe18c024eee6e1dd81ee24c26795dadd6cfe4a7b5d0d",
    "0x5db999fad322cea2914535aae5517060c3f80ad6d8c0231cde2124a434d16846",
    "0x12aa13b3da17ceae1b0a59b5d5b77121e91bb79b4bb0b52bf6543ed3f8d0953b",
    "0xdf9bf27ee5757c55b44b8b9826ddc9ec3a8809aa3278634c45edbb7fc8f1a3e3",
    "0x377e7fe65cf198a7fc4fdae3f2136b74729279267858daaf96718b23bc2a5607",
    "0x059db22dae2d735516017d47d1def0ea43e5d7221259c3aaa60c090d32566d4e",
    "0xd4e77ba6f29fc093509d24f508631abd445ecf506bbdc9c4c80e60256a318527",
    "0x094772b3529f455e881a4483eaf1c24266384f55e97c23f24f638f5726ba9920",
]


def qtext(m: dict) -> str:
    return f"{m.get('question') or ''} {m.get('slug_key') or ''} {m.get('slug') or ''}".lower()


def theme_of(m: dict) -> str:
    q = qtext(m)
    if any(k in q for k in ("fed", "interest rate", "rate hike", "rate cut", "rate hike")):
        return "fed"
    if "prime minister of sweden" in q or "kristersson" in q or "andersson" in q:
        return "sweden_pm"
    if "swedish parliamentary" in q or "sweden democrats" in q or "moderate party" in q:
        return "sweden_parliament"
    if any(k in q for k in ("iran", "hormuz", "bab el-mandeb", "bab el mandeb")):
        return "iran_geo"
    if any(k in q for k in ("israel", "netanyahu", "eizenkot")):
        return "israel"
    if any(k in q for k in ("brazil", "lula", "bolsonaro")):
        return "brazil"
    if any(k in q for k in ("french presidential", "le pen", "édouard philippe", "edouard philippe")):
        return "france"
    if any(k in q for k in ("russia", "united russia", "kprf")):
        return "russia"
    if "clarity act" in q:
        return "us_crypto_law"
    if "lec" in q:
        return "esports_lec"
    if "f1" in q or "drivers' champion" in q or "drivers champion" in q:
        return "f1"
    if "grossing movie" in q or "spider-man" in q:
        return "movies"
    if "emmy" in q:
        return "emmys"
    if "fifa" in q or "world cup" in q:
        return "fifa"
    if "ballon" in q:
        return "ballon_dor"
    if "chess" in q:
        return "chess"
    if any(k in q for k in ("dodgers", "yankees", "rays", "national league")):
        return "mlb"
    if any(k in q for k in ("ipo", "anthropic", "openai", "discord", "consumer hardware")):
        return "tech_ipo"
    if "japan" in q or "cpi" in q:
        return "japan_macro"
    if any(k in q for k in ("berlin", "linke", "mecklenburg", "spd win")):
        return "germany"
    if "alien" in q:
        return "aliens"
    return "other"


def slim(m: dict) -> dict:
    return {
        "market_id": m["market_id"],
        "question": m.get("question"),
        "daily_reward_pool": float(m.get("daily_reward_pool") or 0),
        "volume_num": float(m.get("volume_num") or 0),
        "overlap_days": m.get("overlap_days"),
        "rewards_min_size": m.get("rewards_min_size"),
        "rewards_max_spread": m.get("rewards_max_spread"),
        "theme": theme_of(m),
    }


def write_set(name: str, markets: list[dict], *, kind: str, min_pool: float, note: str) -> dict:
    payload = {
        "name": name,
        "kind": kind,
        "min_pool": float(min_pool),
        "n": len(markets),
        "note": note,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "market_ids": [m["market_id"] for m in markets],
        "markets": [slim(m) for m in markets],
        "total_daily_pool": sum(float(m.get("daily_reward_pool") or 0) for m in markets),
        "total_volume": sum(float(m.get("volume_num") or 0) for m in markets),
    }
    path = OUT_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return payload


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    markets = json.loads(MARKETS_PATH.read_text())
    ranked = sorted(
        markets,
        key=lambda m: (
            -float(m.get("daily_reward_pool") or 0),
            -float(m.get("volume_num") or 0),
            -int(m.get("overlap_days") or 0),
        ),
    )
    by_id = {m["market_id"]: m for m in markets}

    index = []
    for n in (3, 5, 8, 10, 15):
        rec = write_set(
            f"top{n}",
            ranked[:n],
            kind="rank_pool",
            min_pool=0.0,
            note=f"Top {n} by daily_reward_pool, tie-break volume then overlap_days. "
            "Allowlist is binding; pool filter disabled in eval.",
        )
        index.append({"name": rec["name"], "n": rec["n"], "kind": rec["kind"], "min_pool": rec["min_pool"]})

    # Wave2 floors around pool100 champion (+ legacy 50/150/200)
    for thresh in (200, 150, 140, 130, 125, 120, 110, 100, 90, 80, 50):
        subset = [m for m in ranked if float(m.get("daily_reward_pool") or 0) >= thresh]
        rec = write_set(
            f"pool_ge_{thresh}",
            subset,
            kind="pool_threshold",
            min_pool=float(thresh),
            note=f"All markets with daily_reward_pool >= {thresh}. "
            f"Eval sets min_daily_reward_pool={thresh} (champion default is 100).",
        )
        index.append({"name": rec["name"], "n": rec["n"], "kind": rec["kind"], "min_pool": rec["min_pool"]})

    # Band: 100 <= pool < 200 (exclude megapools)
    band = [
        m for m in ranked
        if 100.0 <= float(m.get("daily_reward_pool") or 0) < 200.0
    ]
    rec = write_set(
        "pool_100_to_199",
        band,
        kind="pool_band",
        min_pool=100.0,
        note="Markets with 100 <= daily_reward_pool < 200 (exclude >=200 megapools). "
        "Allowlist binding + min_daily_reward_pool=100.",
    )
    index.append({"name": rec["name"], "n": rec["n"], "kind": rec["kind"], "min_pool": rec["min_pool"]})

    # pool>=100 excluding Emmys (low-vol entertainment theme)
    ex_emmys = [
        m for m in ranked
        if float(m.get("daily_reward_pool") or 0) >= 100.0 and theme_of(m) != "emmys"
    ]
    rec = write_set(
        "pool_ge_100_ex_emmys",
        ex_emmys,
        kind="pool_threshold_ex_theme",
        min_pool=100.0,
        note="daily_reward_pool >= 100 excluding theme=emmys (all Emmy names are low-volume). "
        "Allowlist binding + min_daily_reward_pool=100.",
    )
    index.append({"name": rec["name"], "n": rec["n"], "kind": rec["kind"], "min_pool": rec["min_pool"]})

    seed = [by_id[i] for i in SEED_FED_IRAN if i in by_id]
    rec = write_set(
        "seed_fed_iran",
        seed,
        kind="seed",
        min_pool=0.0,
        note="strategy.py SEED_FED_IRAN_MARKETS (Fed rate + Iran geopolitics). "
        "Allowlist binding; includes two sub-150 pool names.",
    )
    index.append({"name": rec["name"], "n": rec["n"], "kind": rec["kind"], "min_pool": rec["min_pool"]})

    # Diverse: highest-pool market from each identifiable theme
    best_by_theme: dict[str, dict] = {}
    for m in ranked:
        t = theme_of(m)
        if t == "other":
            continue
        if t not in best_by_theme:
            best_by_theme[t] = m
    diverse = sorted(
        best_by_theme.values(),
        key=lambda m: (-float(m.get("daily_reward_pool") or 0), -float(m.get("volume_num") or 0)),
    )
    rec = write_set(
        "diverse_top",
        diverse,
        kind="diverse_theme",
        min_pool=0.0,
        note="Highest daily_reward_pool market from each identifiable theme "
        "(Fed, Sweden PM/parliament, Iran/geo, Israel, Brazil, France, Russia, "
        "US crypto law, esports, F1, movies, Emmys, FIFA, Ballon d'Or, chess, "
        "MLB, tech IPO, Japan macro, Germany, aliens).",
    )
    index.append({"name": rec["name"], "n": rec["n"], "kind": rec["kind"], "min_pool": rec["min_pool"]})

    catalog = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "n_source_markets": len(markets),
        "ranking": "daily_reward_pool desc, volume_num desc, overlap_days desc",
        "sets": index,
        "themes_in_diverse": {t: slim(m) for t, m in best_by_theme.items()},
    }
    (OUT_DIR / "INDEX.json").write_text(json.dumps(catalog, indent=2) + "\n")
    print(json.dumps({"wrote": [s["name"] for s in index], "n_sets": len(index)}, indent=2))


if __name__ == "__main__":
    main()
