from collections import namedtuple

AccessInfo = namedtuple("AccessInfo", ["l1_hit", "l2_hit", "cycles"])

WORD_BYTES = 4
MAX_STATE_SETS = 64          # --state only makes sense for small caches

COLORS = {"green": "\033[32m", "red": "\033[31m", "dim": "\033[2m"}
RESET = "\033[0m"


def paint(text, color, on):
    """Wrap text in an ANSI colour code if colour is switched on."""
    return f"{COLORS[color]}{text}{RESET}" if on and color else text


def format_set(entries):
    """[(block address, dirty), ...] -> '[0x10000040 0x10000080*]' (* = dirty)."""
    if not entries:
        return "[empty]"
    return "[" + " ".join(f"0x{addr:08x}{'*' if dirty else ''}"
                          for addr, dirty in entries) + "]"


class Hierarchy:
    """
    Split L1 (instruction + data), optional unified L2, then main memory.
    Accesses are blocking: the cycle cost of each access is simply added up.
    """

    def __init__(self, l1i, l1d, l2=None, t_l1=1, t_l2=10, t_mem=100):
        if l2 is not None and l2.block_size < max(l1i.block_size, l1d.block_size):
            raise ValueError("L2 block size must be at least the L1 block size")
        self.l1i = l1i
        self.l1d = l1d
        self.l2 = l2
        self.t_l1 = t_l1
        self.t_l2 = t_l2
        self.t_mem = t_mem

        self.accesses = 0
        self.total_cycles = 0
        self.counts = {0: 0, 1: 0, 2: 0}   # reads, writes, instruction fetches
        self.mem_reads = 0
        self.mem_writes = 0
        self.mem_read_bytes = 0
        self.mem_write_bytes = 0

    def caches(self):
        return [c for c in (self.l1i, self.l1d, self.l2) if c is not None]

    # ---- main memory ----
    def _mem_read(self, nbytes):
        self.mem_reads += 1
        self.mem_read_bytes += nbytes
        return self.t_mem

    def _mem_write(self, nbytes):
        self.mem_writes += 1
        self.mem_write_bytes += nbytes
        return self.t_mem

    # ---- everything below L1 ----
    def _read_below(self, addr, nbytes):
        """An L1 miss needs a block. Returns (extra cycles, l2_hit)."""
        if self.l2 is None:
            return self._mem_read(nbytes), None
        r2 = self.l2.access(addr, False)
        cycles = self.t_l2
        if r2.fetch:
            cycles += self._mem_read(self.l2.block_size)
        if r2.writeback_addr is not None:
            cycles += self._mem_write(self.l2.block_size)
        return cycles, r2.hit

    def _write_below(self, addr, nbytes, full_block):
        """A write has to reach the next level. Returns extra cycles."""
        if self.l2 is None:
            return self._mem_write(nbytes)
        r2 = self.l2.access(addr, True)
        cycles = self.t_l2
        if r2.fetch and not full_block:
            # partial write into an L2 that allocates: fetch the block first
            cycles += self._mem_read(self.l2.block_size)
        if r2.writeback_addr is not None:
            cycles += self._mem_write(self.l2.block_size)
        if r2.write_through:
            cycles += self._mem_write(nbytes)
        return cycles

    # ---- one access from the processor ----
    def access(self, kind, addr):
        if kind not in (0, 1, 2):
            raise ValueError("kind must be 0 (read), 1 (write) or 2 (ifetch)")
        is_write = kind == 1
        l1 = self.l1i if kind == 2 else self.l1d

        cycles = self.t_l1
        l2_hit = None
        r = l1.access(addr, is_write)

        if r.fetch:
            extra, l2_hit = self._read_below(addr, l1.block_size)
            cycles += extra
        if r.writeback_addr is not None:
            cycles += self._write_below(r.writeback_addr, l1.block_size, True)
        if r.write_through:
            cycles += self._write_below(addr, WORD_BYTES, False)

        self.accesses += 1
        self.total_cycles += cycles
        self.counts[kind] += 1
        return AccessInfo(r.hit, l2_hit, cycles)

    def _state_lines(self, before, after, color):
        """Describe every cache set that the last access changed."""
        lines = []
        for cache, old_sets, new_sets in zip(self.caches(), before, after):
            for index, (old, new) in enumerate(zip(old_sets, new_sets)):
                if old == new:
                    continue
                text = (f"{cache.name:<4} set {index}: "
                        f"{format_set(old)} -> {format_set(new)}")
                gone = [(a, d) for a, d in old if a not in dict(new)]
                for addr, dirty in gone:
                    what = "dirty, written back" if dirty else "clean"
                    text += f"   evicted 0x{addr:08x} ({what})"
                lines.append(" " * 9 + paint(text, "dim", color))
        return lines

    def run(self, trace, verbose=False, state=False, color=False):
        """
        Feed a trace through the hierarchy.
        verbose: print one line per access
        state:   also print every cache set that access changed
        color:   green hits, red misses (ANSI colours)
        """
        if state:
            for cache in self.caches():
                if cache.num_sets > MAX_STATE_SETS:
                    raise ValueError(
                        f"--state needs small caches (at most {MAX_STATE_SETS} sets), "
                        f"{cache.name} has {cache.num_sets}. Try configs/tiny.toml")
            verbose = True
            print("Cache contents are listed oldest -> newest (the left block is "
                  "evicted first), * = dirty\n")
        names = {0: "R", 1: "W", 2: "I"}
        for n, (kind, addr) in enumerate(trace, 1):
            before = [c.snapshot() for c in self.caches()] if state else None
            info = self.access(kind, addr)
            if verbose:
                l1name = "L1I" if kind == 2 else "L1D"
                l1 = paint("hit " if info.l1_hit else "miss",
                           "green" if info.l1_hit else "red", color)
                if info.l2_hit is None:
                    l2 = "-   "
                else:
                    l2 = paint("hit " if info.l2_hit else "miss",
                               "green" if info.l2_hit else "red", color)
                print(f"{n:6d}  {names[kind]}  0x{addr:08x}  "
                      f"{l1name} {l1}  L2 {l2}  {info.cycles:4d} cycles")
            if state:
                after = [c.snapshot() for c in self.caches()]
                for line in self._state_lines(before, after, color):
                    print(line)

    # ---- results ----
    @property
    def amat(self):
        return self.total_cycles / self.accesses if self.accesses else 0.0

    def summary(self):
        return {
            "accesses": self.accesses,
            "total_cycles": self.total_cycles,
            "amat": round(self.amat, 4),
            "mem_reads": self.mem_reads,
            "mem_writes": self.mem_writes,
            "mem_read_bytes": self.mem_read_bytes,
            "mem_write_bytes": self.mem_write_bytes,
            "l1i": self.l1i.summary(),
            "l1d": self.l1d.summary(),
            "l2": self.l2.summary() if self.l2 else None,
        }

    def report(self):
        c = self.counts
        lines = [
            f"Accesses     : {self.accesses}  "
            f"(reads {c[0]}, writes {c[1]}, ifetch {c[2]})",
            f"Total cycles : {self.total_cycles}",
            f"AMAT         : {self.amat:.3f} cycles",
            "",
            f"{'cache':<6}{'accesses':>10}{'hits':>10}{'misses':>10}"
            f"{'miss rate':>11}{'compuls.':>10}{'capacity':>10}"
            f"{'conflict':>10}{'writebacks':>12}",
        ]
        for cache in self.caches():
            s = cache.summary()
            lines.append(
                f"{s['name']:<6}{s['accesses']:>10}{s['hits']:>10}{s['misses']:>10}"
                f"{s['miss_rate']:>11.4f}{s['compulsory']:>10}{s['capacity']:>10}"
                f"{s['conflict']:>10}{s['writebacks']:>12}"
            )
        lines.append("")
        lines.append(
            f"Main memory  : {self.mem_reads} reads ({self.mem_read_bytes} bytes), "
            f"{self.mem_writes} writes ({self.mem_write_bytes} bytes)"
        )
        return "\n".join(lines)