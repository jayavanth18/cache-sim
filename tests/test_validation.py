"""
Checks the simulator against results worked out by hand (no simulator
involved in the predictions). These are the numbers quoted in the
validation section of the report.
"""
from cachesim.config import build_hierarchy
from cachesim.tracegen import matmul, sequential, strided


def make(l1_size=32768):
    return build_hierarchy({
        "timing": {"l1_hit": 1, "l2_hit": 10, "memory": 100},
        "l1i": {"size": l1_size, "block_size": 64, "assoc": 4},
        "l1d": {"size": l1_size, "block_size": 64, "assoc": 4},
        "l2": {"size": 262144, "block_size": 64, "assoc": 8},
    })


def test_sequential_scan():
    h = make()
    h.run(sequential())          # 256 KB array read front to back, twice
    # 256 KB = 4096 blocks of 64 B, 16 words each. The array is much bigger
    # than the 32 KB L1D, so LRU throws every block out before the second pass
    # reaches it: 4096 misses per pass.
    assert h.l1d.misses == 2 * 4096
    assert h.l1d.hits == 131072 - 2 * 4096
    # L2 is exactly 256 KB, so pass 1 fills it from memory and pass 2 hits.
    assert h.l2.misses == 4096
    assert h.l2.hits == 4096
    # cycles = L1 hits + (L1 miss, L2 hit) + (L1 miss, L2 miss, memory)
    assert h.total_cycles == 122880 * 1 + 4096 * 11 + 4096 * 111


def test_strided_conflict_misses():
    h = make()
    h.run(strided())             # 512 blocks touched, 50 passes
    # 512 blocks is exactly what a 32 KB L1D holds, but a 256 B stride only
    # reaches every 4th set: 32 of the 128 sets x 4 ways = 128 blocks. Each of
    # those sets is asked for 16 blocks in a cycle, so LRU never hits.
    assert h.l1d.hits == 0
    assert h.l1d.compulsory == 512
    assert h.l1d.capacity == 0
    assert h.l1d.conflict == 50 * 512 - 512


def test_matmul_ikj_miss_count():
    h = make(l1_size=4096)
    h.run(matmul("ikj"))         # 64 x 64 matrices, 16 KB each
    # A and C are used one row at a time, so each of their 256 blocks misses
    # only once (compulsory). B is 16 KB and does not fit in 4 KB: for every
    # (i, k) pair its row k (4 blocks) is fetched again.
    #   B misses = 64 * 64 * 4 = 16384, A + C misses = 2 * 256 = 512
    assert h.l1d.misses == 16384 + 512