from pathlib import Path

from cachesim.config import load_hierarchy
from cachesim.trace import read_trace

ROOT = Path(__file__).resolve().parent.parent


def test_demo_trace_matches_hand_trace():
    # The 12 accesses in traces/demo.din, worked out by hand for configs/tiny.toml:
    #  1 ifetch miss (L1I + L2)        111     7 read, miss, set 0 now full     111
    #  2 ifetch, same block, hit         1     8 read, evicts the dirty block   121
    #  3 read miss (L1D + L2)          111       (111 + 10 to write it into L2)
    #  4 read, same block, hit           1     9 read, L1 miss, L2 hit           11
    #  5 write, same block, hit          1    10 read, L1 miss, L2 hit           11
    #  6 read, next block, miss        111    11 ifetch, same block, hit          1
    #                                         12 read, still in L1, hit            1
    h = load_hierarchy(ROOT / "configs" / "tiny.toml")
    cycles = [h.access(k, a).cycles
              for k, a in read_trace(ROOT / "traces" / "demo.din")]
    assert cycles == [111, 1, 111, 1, 1, 111, 111, 121, 11, 11, 1, 1]
    assert h.total_cycles == 592
    assert h.l1d.writebacks == 1
    assert h.l1d.conflict == 2          # accesses 9 and 10
    assert h.l2.hits == 3               # the writeback, and accesses 9 and 10
    assert h.mem_reads == 5