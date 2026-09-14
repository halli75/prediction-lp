#!/usr/bin/env python3
"""Discover top Polymarket LP reward markets → data/top_reward_markets.json.

Uses CLOB /sampling-simplified-markets + Gamma /markets (paginated).
Ranks by rewardsDailyRate with preference for long overlap vs HF window.
"""
print("Prefer regenerating via the session discovery flow, or re-run the")
print("inline discovery that wrote data/top_reward_markets.json.")
print("Allowlist already at data/top_reward_markets.json")
