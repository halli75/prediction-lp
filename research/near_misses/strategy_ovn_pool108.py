"""Near-miss saved algorithm. Defaults bake the creative overlay.
id=ovn_pool108 sample=783.9748 30d=1598.6235 60d=2540.89
"""
from __future__ import annotations
import importlib.util
from pathlib import Path
OVERLAY = {
    "day_flatten": true,
    "day_flatten_max_net": 8,
    "min_daily_reward_pool": 108.0,
    "overnight_quiet": true,
    "overnight_mode": "reduce_only"
}

_p = Path(__file__).resolve().parents[1] / "creative" / "strategy_creative_base.py"
_spec = importlib.util.spec_from_file_location("creative_base_nm", _p)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

class Strategy(_mod.Strategy):
    def __init__(self, config=None):
        cfg = {**OVERLAY, **(config or {})}
        super().__init__(cfg)
