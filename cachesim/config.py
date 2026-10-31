import tomllib

from .cache import Cache
from .hierarchy import Hierarchy


def _make_cache(name, c):
    return Cache(
        name,
        c["size"],
        c["block_size"],
        c["assoc"],
        policy=c.get("policy", "LRU"),
        write_policy=c.get("write_policy", "wb"),
        seed=c.get("seed", 0),
    )


def build_hierarchy(cfg):
    """Build a Hierarchy from a plain dict (same layout as the TOML files)."""
    for key in ("l1i", "l1d"):
        if key not in cfg:
            raise ValueError(f"config is missing the [{key}] section")
    t = cfg.get("timing", {})
    l2 = _make_cache("L2", cfg["l2"]) if "l2" in cfg else None
    return Hierarchy(
        _make_cache("L1I", cfg["l1i"]),
        _make_cache("L1D", cfg["l1d"]),
        l2,
        t_l1=t.get("l1_hit", 1),
        t_l2=t.get("l2_hit", 10),
        t_mem=t.get("memory", 100),
    )


def load_hierarchy(path):
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    return build_hierarchy(cfg)