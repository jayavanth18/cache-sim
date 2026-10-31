from collections import Counter

import pytest

from cachesim.trace import read_trace
from cachesim.tracegen import (DATA_BASE, IFETCH, READ, WRITE, matmul,
                               random_access, sequential, strided,
                               vector_add, write_trace)


def test_sequential_addresses():
    acc = list(sequential(array_bytes=64, passes=2, base=0x1000))
    assert len(acc) == 32                  # 16 words per pass, 2 passes
    assert acc[0] == (READ, 0x1000)
    assert acc[15] == (READ, 0x103C)
    assert acc[16] == (READ, 0x1000)       # second pass starts over


def test_strided_count():
    assert len(list(strided(stride=256, array_bytes=1024, passes=3))) == 12


def test_random_is_repeatable():
    a = list(random_access(working_set=4096, count=100, seed=3))
    b = list(random_access(working_set=4096, count=100, seed=3))
    c = list(random_access(working_set=4096, count=100, seed=4))
    assert a == b
    assert a != c
    assert all(DATA_BASE <= addr < DATA_BASE + 4096 and addr % 4 == 0
               for _, addr in a)


def test_vector_add_counts():
    acc = list(vector_add(n=10, passes=2))
    kinds = Counter(k for k, _ in acc)
    assert len(acc) == 10 * 2 * 9
    assert kinds[IFETCH] == 10 * 2 * 6
    assert kinds[READ] == 10 * 2 * 2
    assert kinds[WRITE] == 10 * 2


def test_matmul_orders_do_the_same_work():
    n = 8
    base = Counter(matmul("ijk", n=n))
    assert sum(base.values()) == 4 * n ** 3
    assert Counter(matmul("ikj", n=n)) == base
    assert Counter(matmul("blocked", n=n, tile=4)) == base
    # same accesses, but really in a different order
    assert list(matmul("ijk", n=n)) != list(matmul("ikj", n=n))


def test_matmul_blocked_needs_matching_tile():
    with pytest.raises(ValueError):
        list(matmul("blocked", n=10, tile=4))


def test_write_trace_roundtrip(tmp_path):
    acc = list(vector_add(n=3, passes=1))
    p = tmp_path / "v.din"
    assert write_trace(p, acc) == len(acc)
    assert list(read_trace(p)) == acc