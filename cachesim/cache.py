import random
from collections import OrderedDict, namedtuple

# What one access tells the next level of the hierarchy:
#   hit            - was the block found in this cache
#   fetch          - the block must be brought in from the next level
#   writeback_addr - address of a dirty block pushed out (or None)
#   write_through  - the write also has to go to the next level
AccessResult = namedtuple(
    "AccessResult", ["hit", "fetch", "writeback_addr", "write_through"]
)


def is_power_of_two(n):
    return n > 0 and (n & (n - 1)) == 0


class ShadowLRU:
    """
    A fully associative LRU cache of the same size, run alongside the real
    cache. It only tracks which blocks are present. A miss in the real cache
    that would have been a hit here is a conflict miss; a miss here too is a
    capacity miss.
    """

    def __init__(self, num_blocks, allocate_on_write):
        self.capacity = num_blocks
        self.allocate_on_write = allocate_on_write
        self.blocks = OrderedDict()

    def access(self, block, is_write):
        if block in self.blocks:
            self.blocks.move_to_end(block)
            return True
        if is_write and not self.allocate_on_write:
            return False
        if len(self.blocks) >= self.capacity:
            self.blocks.popitem(last=False)
        self.blocks[block] = True
        return False


class Cache:
    """
    One cache level.

    size, block_size : in bytes (powers of two)
    assoc            : 1 = direct-mapped, N = N-way, "full" = fully associative
    policy           : "LRU", "FIFO" or "RANDOM"
    write_policy     : "wb" = write-back + write-allocate
                       "wt" = write-through + no-write-allocate
    classify         : track compulsory/capacity/conflict misses
    """

    def __init__(self, name, size, block_size, assoc, policy="LRU",
                 write_policy="wb", seed=0, classify=True):
        policy = policy.upper()
        if policy not in ("LRU", "FIFO", "RANDOM"):
            raise ValueError("policy must be LRU, FIFO or RANDOM")
        if write_policy not in ("wb", "wt"):
            raise ValueError("write_policy must be 'wb' or 'wt'")
        if not is_power_of_two(size) or not is_power_of_two(block_size):
            raise ValueError("size and block_size must be powers of two")
        if block_size > size:
            raise ValueError("block_size cannot be bigger than size")

        total_blocks = size // block_size
        if assoc == "full":
            assoc = total_blocks
        if not is_power_of_two(assoc) or assoc > total_blocks:
            raise ValueError("assoc must be a power of two <= number of blocks")

        self.name = name
        self.size = size
        self.block_size = block_size
        self.assoc = assoc
        self.policy = policy
        self.write_policy = write_policy
        self.num_sets = total_blocks // assoc
        self.offset_bits = block_size.bit_length() - 1
        self.index_bits = self.num_sets.bit_length() - 1

        # Each set maps tag -> dirty flag. The first entry is the next victim
        # for LRU (least recently used) and FIFO (oldest).
        self.sets = [OrderedDict() for _ in range(self.num_sets)]
        self.rng = random.Random(seed)

        # statistics
        self.reads = 0
        self.writes = 0
        self.hits = 0
        self.misses = 0
        self.read_misses = 0
        self.write_misses = 0
        self.evictions = 0
        self.writebacks = 0
        self.compulsory = 0
        self.capacity = 0
        self.conflict = 0

        # for the 3C classification
        self.seen = set()
        self.shadow = None
        if classify:
            self.shadow = ShadowLRU(total_blocks, write_policy == "wb")

    def _block_addr(self, tag, index):
        return ((tag << self.index_bits) | index) << self.offset_bits

    def access(self, addr, is_write=False):
        block = addr >> self.offset_bits
        index = block & (self.num_sets - 1)
        tag = block >> self.index_bits
        lines = self.sets[index]

        if is_write:
            self.writes += 1
        else:
            self.reads += 1

        first_time = block not in self.seen
        self.seen.add(block)
        shadow_hit = None
        if self.shadow is not None:
            shadow_hit = self.shadow.access(block, is_write)

        # ---- hit ----
        if tag in lines:
            self.hits += 1
            if self.policy == "LRU":
                lines.move_to_end(tag)
            write_through = False
            if is_write:
                if self.write_policy == "wb":
                    lines[tag] = True
                else:
                    write_through = True
            return AccessResult(True, False, None, write_through)

        # ---- miss ----
        self.misses += 1
        if is_write:
            self.write_misses += 1
        else:
            self.read_misses += 1

        if self.shadow is not None:
            if first_time:
                self.compulsory += 1
            elif not shadow_hit:
                self.capacity += 1
            else:
                self.conflict += 1

        # write-through + no-write-allocate: send the write down, don't fill
        if is_write and self.write_policy == "wt":
            return AccessResult(False, False, None, True)

        writeback_addr = None
        if len(lines) >= self.assoc:
            if self.policy == "RANDOM":
                victim_tag = list(lines)[self.rng.randrange(len(lines))]
            else:
                victim_tag = next(iter(lines))   # LRU and FIFO: front of the set
            victim_dirty = lines.pop(victim_tag)
            self.evictions += 1
            if victim_dirty:
                self.writebacks += 1
                writeback_addr = self._block_addr(victim_tag, index)

        lines[tag] = is_write
        return AccessResult(False, True, writeback_addr, False)

    @property
    def miss_rate(self):
        total = self.hits + self.misses
        return self.misses / total if total else 0.0

    def summary(self):
        return {
            "name": self.name,
            "accesses": self.hits + self.misses,
            "hits": self.hits,
            "misses": self.misses,
            "miss_rate": round(self.miss_rate, 4),
            "compulsory": self.compulsory,
            "capacity": self.capacity,
            "conflict": self.conflict,
            "evictions": self.evictions,
            "writebacks": self.writebacks,
        }