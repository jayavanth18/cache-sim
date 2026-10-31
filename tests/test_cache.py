import random

import pytest

from cachesim.cache import Cache


def read_all(cache, addrs):
    for a in addrs:
        cache.access(a, False)


def test_direct_mapped_conflict():
    # 64 B, 16 B blocks, direct-mapped -> 4 sets.
    # 0x00 and 0x40 are different blocks that map to set 0.
    c = Cache("L1", 64, 16, 1)
    read_all(c, [0x00, 0x04, 0x40, 0x00, 0x10])
    # 0x00 miss (first time) | 0x04 hit (same block) | 0x40 miss (first time,
    # evicts 0x00) | 0x00 miss (a fully associative cache would have kept it,
    # so conflict) | 0x10 miss (first time)
    assert c.hits == 1
    assert c.misses == 4
    assert c.compulsory == 3
    assert c.conflict == 1
    assert c.capacity == 0


def test_lru_vs_fifo():
    # 32 B, 16 B blocks, 2-way -> a single set. A, B, C all map to it.
    seq = [0x00, 0x10, 0x00, 0x20, 0x00]  # A B A C A

    lru = Cache("lru", 32, 16, 2, policy="LRU")
    read_all(lru, seq)
    # A miss, B miss, A hit, C miss (evicts B), A hit
    assert (lru.hits, lru.misses) == (2, 3)

    fifo = Cache("fifo", 32, 16, 2, policy="FIFO")
    read_all(fifo, seq)
    # A miss, B miss, A hit, C miss (evicts A, oldest), A miss
    assert (fifo.hits, fifo.misses) == (1, 4)


def test_capacity_miss():
    # Single set of 2 blocks. A B C then A again: A was pushed out because
    # the cache is too small, so this is a capacity miss.
    c = Cache("L1", 32, 16, 2)
    read_all(c, [0x00, 0x10, 0x20, 0x00])
    assert c.compulsory == 3
    assert c.capacity == 1
    assert c.conflict == 0


def test_writeback_dirty_eviction():
    # 32 B, 16 B blocks, direct-mapped -> 2 sets. 0x00 and 0x20 share set 0.
    c = Cache("L1", 32, 16, 1, write_policy="wb")
    r1 = c.access(0x00, True)          # write miss, block is loaded and dirty
    assert not r1.hit and r1.fetch and r1.writeback_addr is None
    r2 = c.access(0x20, False)         # evicts the dirty block
    assert not r2.hit and r2.fetch
    assert r2.writeback_addr == 0x00
    assert c.writebacks == 1


def test_write_through_no_allocate():
    c = Cache("L1", 32, 16, 1, write_policy="wt")
    r1 = c.access(0x00, True)          # write miss: goes down, no fill
    assert not r1.hit and not r1.fetch and r1.write_through
    r2 = c.access(0x00, False)         # still not in cache
    assert not r2.hit and r2.fetch
    r3 = c.access(0x00, True)          # now a hit, but still written through
    assert r3.hit and r3.write_through
    assert c.writebacks == 0


def test_fully_associative_config():
    c = Cache("L1", 64, 16, "full")
    assert c.num_sets == 1
    assert c.assoc == 4


def test_random_is_repeatable():
    rng = random.Random(5)
    addrs = [rng.randrange(0, 1024) & ~3 for _ in range(500)]
    a = Cache("a", 128, 16, 2, policy="RANDOM", seed=7)
    b = Cache("b", 128, 16, 2, policy="RANDOM", seed=7)
    for x in addrs:
        a.access(x)
        b.access(x)
    assert a.hits == b.hits
    assert a.misses == b.misses
    assert a.hits + a.misses == 500


def test_bad_config():
    with pytest.raises(ValueError):
        Cache("x", 100, 16, 2)       # size not a power of two
    with pytest.raises(ValueError):
        Cache("x", 64, 16, 3)        # assoc not a power of two
    with pytest.raises(ValueError):
        Cache("x", 64, 16, 1, policy="MRU")