"""
Trace generators. Every generator yields (type, address) pairs where
type 0 = data read, 1 = data write, 2 = instruction fetch.

Run  python -m cachesim.tracegen  to write the standard traces into traces/.
All traces are deterministic (fixed seeds), so anyone can regenerate them.
"""
import argparse
import random
from pathlib import Path

READ, WRITE, IFETCH = 0, 1, 2
WORD = 4                      # bytes per element (a 32-bit int/float)
CODE_BASE = 0x00400000
DATA_BASE = 0x10000000


def sequential(array_bytes=256 * 1024, passes=2, base=DATA_BASE):
    """Read an array front to back, several times."""
    for _ in range(passes):
        for off in range(0, array_bytes, WORD):
            yield READ, base + off


def strided(stride=256, array_bytes=128 * 1024, passes=50, base=DATA_BASE):
    """Read one word every `stride` bytes, over and over."""
    for _ in range(passes):
        for off in range(0, array_bytes, stride):
            yield READ, base + off


def random_access(working_set=512 * 1024, count=200_000, seed=1, base=DATA_BASE):
    """Random word reads inside a working set."""
    rng = random.Random(seed)
    words = working_set // WORD
    for _ in range(count):
        yield READ, base + rng.randrange(words) * WORD


def vector_add(n=16384, passes=2, spacing=0x100000):
    """
    c[i] = a[i] + b[i], with a 6-instruction loop body.
    The three arrays sit `spacing` bytes apart (1 MB), like separate
    large allocations, so a[i], b[i] and c[i] land in the same cache set.
    """
    a = DATA_BASE
    b = a + spacing
    c = b + spacing
    for _ in range(passes):
        for i in range(n):
            off = i * WORD
            yield IFETCH, CODE_BASE          # lw  a[i]
            yield READ, a + off
            yield IFETCH, CODE_BASE + 4      # lw  b[i]
            yield READ, b + off
            yield IFETCH, CODE_BASE + 8      # add
            yield IFETCH, CODE_BASE + 12     # sw  c[i]
            yield WRITE, c + off
            yield IFETCH, CODE_BASE + 16     # i++
            yield IFETCH, CODE_BASE + 20     # branch


def matmul(order="ijk", n=64, tile=8):
    """
    C = A x B for n x n matrices stored row by row, 4 bytes per element.
    The statement is C[i][j] += A[i][k] * B[k][j] with nothing kept in
    registers, so every order does the same 4 accesses per (i, j, k):
    read A, read B, read C, write C. Only the loop order changes.
    order: "ijk", "ikj" or "blocked" (tiles of tile x tile).
    """
    a = DATA_BASE
    b = a + n * n * WORD
    c = b + n * n * WORD

    def step(i, j, k):
        yield READ, a + (i * n + k) * WORD
        yield READ, b + (k * n + j) * WORD
        yield READ, c + (i * n + j) * WORD
        yield WRITE, c + (i * n + j) * WORD

    if order == "ijk":
        for i in range(n):
            for j in range(n):
                for k in range(n):
                    yield from step(i, j, k)
    elif order == "ikj":
        for i in range(n):
            for k in range(n):
                for j in range(n):
                    yield from step(i, j, k)
    elif order == "blocked":
        if n % tile:
            raise ValueError("n must be a multiple of tile")
        for ii in range(0, n, tile):
            for jj in range(0, n, tile):
                for kk in range(0, n, tile):
                    for i in range(ii, ii + tile):
                        for j in range(jj, jj + tile):
                            for k in range(kk, kk + tile):
                                yield from step(i, j, k)
    else:
        raise ValueError("order must be ijk, ikj or blocked")


def write_trace(path, accesses):
    """Write accesses to a trace file. Returns the number of lines written."""
    count = 0
    with open(path, "w") as f:
        for kind, addr in accesses:
            f.write(f"{kind} 0x{addr:08x}\n")
            count += 1
    return count


# name -> function that builds the access stream
STANDARD_TRACES = {
    "sequential": lambda: sequential(),
    "strided": lambda: strided(),
    "random": lambda: random_access(),
    "vecadd": lambda: vector_add(),
    "matmul_ijk": lambda: matmul("ijk"),
    "matmul_ikj": lambda: matmul("ikj"),
    "matmul_blocked": lambda: matmul("blocked"),
}


def main():
    parser = argparse.ArgumentParser(description="Generate the standard traces")
    parser.add_argument("--out", default="traces", help="output folder")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(exist_ok=True)
    for name, make in STANDARD_TRACES.items():
        path = out / f"{name}.din"
        n = write_trace(path, make())
        print(f"{path}  {n} accesses  {path.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()