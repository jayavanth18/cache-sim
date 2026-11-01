from cachesim import experiments
from cachesim.config import build_hierarchy
from cachesim.tracegen import sequential, write_trace


def test_default_config_builds():
    h = build_hierarchy(experiments.make_config())
    assert h.l1d.size == 32 * 1024 and h.l1d.assoc == 4
    assert h.l2.size == 256 * 1024 and h.l2.assoc == 8
    assert h.t_mem == 100


def test_memory_latency_grows_with_block_size():
    assert experiments.mem_latency(64) == 100     # matches the default
    assert experiments.mem_latency(16) == 70
    assert experiments.mem_latency(256) == 220


def test_run_one_on_small_trace(tmp_path, monkeypatch):
    # 256 B array = 4 blocks of 64 B, read twice: 4 compulsory misses, rest hits
    write_trace(tmp_path / "tiny.din", sequential(array_bytes=256, passes=2))
    monkeypatch.setattr(experiments, "TRACE_DIR", tmp_path)
    row = experiments.run_one("tiny", experiments.make_config())
    assert row["accesses"] == 128
    assert row["l1d_miss_rate"] == 4 / 128
    assert row["l1d_compulsory"] == 4