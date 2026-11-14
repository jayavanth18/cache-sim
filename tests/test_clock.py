"""
Clocked mode: the clock is stepped one cycle at a time through the controller
states of every access. These tests check the cycle numbers by hand on the demo
trace, and check that the clock always agrees with the added-up latencies.
"""
from pathlib import Path

import pytest

from cachesim.config import build_hierarchy, load_hierarchy
from cachesim.hierarchy import (L1_LOOKUP, L2_LOOKUP, L2_WRITE, MEM_READ,
                                MEM_WRITE)
from cachesim.trace import read_trace
from cachesim.tracegen import matmul, random_access, strided, vector_add

ROOT = Path(__file__).resolve().parent.parent


def tiny():
    return load_hierarchy(ROOT / "configs" / "tiny.toml")


def demo_trace():
    return read_trace(ROOT / "traces" / "demo.din")


def test_demo_cycle_breakdown_matches_hand_count():
    # demo.din on tiny.toml, 12 accesses, 592 cycles in total (see test_demo.py):
    #   12 accesses, 1 cycle of L1 lookup each                 12
    #   7 L1 misses that search L2 (1 3 6 7 8 9 10), 10 each   70
    #   5 of those also miss in L2, 100 cycles of memory each  500
    #   access 8 writes its dirty victim into L2               10
    h = tiny()
    h.run(demo_trace(), clocked=True)
    assert h.clock == 592 == h.total_cycles
    assert h.state_cycles == {L1_LOOKUP: 12, L2_LOOKUP: 70, L2_WRITE: 10,
                              MEM_READ: 500, MEM_WRITE: 0}


def test_timeline_shows_the_cycles_of_each_step(capsys):
    tiny().run(demo_trace(), timeline=True)
    out = capsys.readouterr().out
    # access 1: cycle 1 in L1, cycles 2-11 in L2, cycles 12-111 waiting for memory
    assert "cycle 1 " in out and "L1 lookup (miss)" in out
    assert "cycles 2-11" in out and "L2 lookup (miss)" in out
    assert "cycles 12-111" in out and "memory read (16 B)" in out
    # access 8 starts at cycle 448 and ends by writing the dirty block into L2
    assert "cycles 559-568      L2 write (dirty block 0x10000000)" in out
    # the last access is a hit in the last cycle
    assert "cycle 592 " in out


def test_one_tick_is_one_cycle():
    h = tiny()
    h.tick(MEM_READ)
    h.tick(MEM_READ)
    h.tick(L1_LOOKUP)
    assert h.clock == 3
    assert h.state_cycles[MEM_READ] == 2 and h.state_cycles[L1_LOOKUP] == 1


@pytest.mark.parametrize("l1d_write,l2_write,l2,policy", [
    ("wb", "wb", True, "LRU"),
    ("wt", "wb", True, "FIFO"),
    ("wt", "wt", True, "RANDOM"),
    ("wb", "wb", False, "LRU"),
    ("wt", "wb", False, "LRU"),
])
def test_clock_agrees_with_added_up_latencies(l1d_write, l2_write, l2, policy):
    cfg = {
        "timing": {"l1_hit": 1, "l2_hit": 10, "memory": 100},
        "l1i": {"size": 256, "block_size": 16, "assoc": 2, "policy": policy},
        "l1d": {"size": 256, "block_size": 16, "assoc": 2, "policy": policy,
                "write_policy": l1d_write},
    }
    if l2:
        cfg["l2"] = {"size": 1024, "block_size": 16, "assoc": 4,
                     "policy": policy, "write_policy": l2_write}
    for make in (lambda: vector_add(n=256, passes=2), lambda: matmul("ijk", n=8),
                 lambda: matmul("blocked", n=8, tile=4),
                 lambda: random_access(working_set=4096, count=2000),
                 lambda: strided(stride=64, array_bytes=2048, passes=5)):
        fast = build_hierarchy(cfg)
        for kind, addr in make():
            fast.access(kind, addr)
        clocked = build_hierarchy(cfg)
        clocked.run(make(), clocked=True)       # raises if the clock disagrees
        assert clocked.clock == fast.total_cycles
        assert sum(clocked.state_cycles.values()) == clocked.clock
        assert clocked.summary()["l1d"] == fast.summary()["l1d"]
        assert fast.clock == 0                  # the fast path never ticks


def test_other_latencies_are_stepped_too():
    cfg = {
        "timing": {"l1_hit": 2, "l2_hit": 7, "memory": 40},
        "l1i": {"size": 64, "block_size": 16, "assoc": 1},
        "l1d": {"size": 64, "block_size": 16, "assoc": 1},
        "l2": {"size": 256, "block_size": 16, "assoc": 2},
    }
    h = build_hierarchy(cfg)
    h.run([(0, 0x00), (0, 0x04)], clocked=True)
    # miss: 2 + 7 + 40, then a hit: 2
    assert h.clock == 51
    assert h.state_cycles[L1_LOOKUP] == 4
    assert h.state_cycles[L2_LOOKUP] == 7
    assert h.state_cycles[MEM_READ] == 40


def test_l2_block_bigger_than_l1_block_fetches_the_rest():
    # L1D: 32 B, 16 B blocks, direct-mapped. L2: 64 B, 32 B blocks, direct-mapped.
    cfg = {
        "timing": {"l1_hit": 1, "l2_hit": 10, "memory": 100},
        "l1i": {"size": 32, "block_size": 16, "assoc": 1},
        "l1d": {"size": 32, "block_size": 16, "assoc": 1},
        "l2": {"size": 64, "block_size": 32, "assoc": 1},
    }
    h = build_hierarchy(cfg)
    assert h.access(1, 0x00).cycles == 111      # write miss, block is dirty in L1
    # Read 0x40: same L1 set and same L2 set as 0x00.
    #   1 + 10 + 100   L1 miss, L2 miss (0x40 replaces 0x00 in L2), memory read
    #   + 10           the dirty 16 B L1 block 0x00 is written into L2 (a miss)
    #   + 100          it is only half of a 32 B L2 block, so L2 has to fetch
    #                  the block from memory before it can take the write
    assert h.access(0, 0x40).cycles == 221
    assert h.mem_reads == 3


def test_equal_block_sizes_still_skip_the_fetch():
    cfg = {
        "timing": {"l1_hit": 1, "l2_hit": 10, "memory": 100},
        "l1i": {"size": 32, "block_size": 16, "assoc": 1},
        "l1d": {"size": 32, "block_size": 16, "assoc": 1},
        "l2": {"size": 32, "block_size": 16, "assoc": 1},
    }
    h = build_hierarchy(cfg)
    assert h.access(1, 0x00).cycles == 111
    # the 16 B L1 block overwrites a whole 16 B L2 block: no memory read for it
    assert h.access(0, 0x20).cycles == 121
    assert h.mem_reads == 2
