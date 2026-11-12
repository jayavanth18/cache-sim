from pathlib import Path

import pytest

from cachesim.cache import Cache
from cachesim.config import load_hierarchy
from cachesim.trace import read_trace

ROOT = Path(__file__).resolve().parent.parent


def tiny():
    return load_hierarchy(ROOT / "configs" / "tiny.toml")


def demo_trace():
    return read_trace(ROOT / "traces" / "demo.din")


def test_snapshot_lists_blocks_oldest_first():
    c = Cache("c", 64, 16, 2)             # 2 sets of 2 ways; 0x00 and 0x20 share set 0
    c.access(0x00)
    c.access(0x20)
    assert c.snapshot()[0] == ((0x00, False), (0x20, False))
    c.access(0x00, True)                  # write hit: 0x00 becomes newest and dirty
    assert c.snapshot()[0] == ((0x20, False), (0x00, True))
    assert c.snapshot()[1] == ()


def test_state_view_shows_dirty_eviction(capsys):
    tiny().run(demo_trace(), state=True)
    out = capsys.readouterr().out
    # access 8: the dirty block leaves L1D and arrives in L2 as the newest, dirty block
    assert "evicted 0x10000000 (dirty, written back)" in out
    assert "L2   set 0: [0x00400000 0x10000000] -> [0x00400000 0x10000080 0x10000000*]" in out
    assert "\033" not in out              # no colour codes unless asked for


def test_colour_marks_hits_green_and_misses_red(capsys):
    tiny().run(demo_trace(), verbose=True, color=True)
    out = capsys.readouterr().out
    assert "\033[32mhit" in out
    assert "\033[31mmiss" in out


def test_state_view_refuses_large_caches():
    h = load_hierarchy(ROOT / "configs" / "default.toml")
    with pytest.raises(ValueError):
        h.run([], state=True)