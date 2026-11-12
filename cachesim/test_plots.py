import csv

import pytest

from cachesim import plots


def test_convert():
    assert plots.convert("4") == 4
    assert plots.convert("0.25") == 0.25
    assert plots.convert("full") == "full"
    assert plots.convert("") == ""


def test_missing_csv_gives_clear_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(plots, "RESULT_DIR", tmp_path)
    with pytest.raises(SystemExit):
        plots.load("exp7_matmul")


def test_figures_are_written(tmp_path, monkeypatch):
    # a tiny hand-made CSV with the columns the matmul figure needs
    rows = [{"l1_kb": kb, "trace": trace, "amat": 1.5, "l1d_miss_rate": 0.1}
            for trace in ("matmul_ijk", "matmul_ikj", "matmul_blocked")
            for kb in (2, 4)]
    with open(tmp_path / "exp7_matmul.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    monkeypatch.setattr(plots, "RESULT_DIR", tmp_path)
    plots.make_figures(["matmul"])
    assert (tmp_path / "report" / "exp7_matmul.pdf").exists()
    assert (tmp_path / "report" / "exp7_matmul.png").exists()
    assert (tmp_path / "slides" / "exp7_matmul.png").exists()