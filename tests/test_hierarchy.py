import pytest

from cachesim.config import build_hierarchy
from cachesim.trace import read_trace


def make(l2=True, l1d_write="wb"):
    # L1: 64 B, 16 B blocks, direct-mapped (4 sets). L2: 256 B, 2-way (8 sets).
    # Timing: L1 hit 1, L2 hit +10, memory +100.
    cfg = {
        "timing": {"l1_hit": 1, "l2_hit": 10, "memory": 100},
        "l1i": {"size": 64, "block_size": 16, "assoc": 1},
        "l1d": {"size": 64, "block_size": 16, "assoc": 1,
                "write_policy": l1d_write},
    }
    if l2:
        cfg["l2"] = {"size": 256, "block_size": 16, "assoc": 2}
    return build_hierarchy(cfg)


def test_cold_miss_then_hit_then_l2_hit():
    h = make()
    assert h.access(0, 0x00).cycles == 111   # L1 miss + L2 miss: 1 + 10 + 100
    assert h.access(0, 0x04).cycles == 1     # same block, L1 hit
    assert h.access(0, 0x40).cycles == 111   # maps to the same L1 set as 0x00
    assert h.access(0, 0x00).cycles == 11    # L1 miss, but L2 still has it: 1 + 10
    assert h.total_cycles == 234
    assert h.mem_reads == 2
    assert h.amat == 234 / 4


def test_dirty_writeback_goes_to_l2():
    h = make()
    assert h.access(1, 0x00).cycles == 111   # write miss, block loaded and dirty
    # read 0x40: 1 + 10 + 100 for the fetch, +10 to write the dirty block into L2
    assert h.access(0, 0x40).cycles == 121
    assert h.l1d.writebacks == 1
    assert h.mem_writes == 0
    assert h.l2.hits == 1 and h.l2.misses == 2


def test_no_l2():
    h = make(l2=False)
    assert h.l2 is None
    assert h.access(0, 0x00).cycles == 101   # 1 + 100
    assert h.access(0, 0x04).cycles == 1
    assert h.total_cycles == 102
    assert h.mem_reads == 1


def test_unified_l2_shared_by_instruction_and_data():
    h = make()
    assert h.access(2, 0x00).cycles == 111   # instruction fetch fills L1I and L2
    assert h.access(0, 0x00).cycles == 11    # L1D misses, L2 already has the block
    assert h.l1i.misses == 1 and h.l1d.misses == 1
    assert h.l2.hits == 1


def test_write_through_l1():
    h = make(l1d_write="wt")
    # write miss: L1 not filled, the word goes to L2, L2 allocates (fetches
    # the block from memory): 1 + 10 + 100
    assert h.access(1, 0x00).cycles == 111
    assert h.access(0, 0x00).cycles == 11    # L1 never got it, L2 has it
    assert h.mem_reads == 1
    assert h.mem_writes == 0


def test_trace_reader(tmp_path):
    p = tmp_path / "t.din"
    p.write_text("# comment\n0 0x10\n\n1 20\n2 0xFF  # trailing note\n")
    assert list(read_trace(p)) == [(0, 0x10), (1, 0x20), (2, 0xFF)]


def test_trace_reader_rejects_bad_type(tmp_path):
    p = tmp_path / "bad.din"
    p.write_text("5 0x10\n")
    with pytest.raises(ValueError):
        list(read_trace(p))


def test_l2_block_smaller_than_l1_rejected():
    cfg = {
        "l1i": {"size": 64, "block_size": 32, "assoc": 1},
        "l1d": {"size": 64, "block_size": 32, "assoc": 1},
        "l2": {"size": 256, "block_size": 16, "assoc": 2},
    }
    with pytest.raises(ValueError):
        build_hierarchy(cfg)