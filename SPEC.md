# Cache Memory Simulator: Specification

## What this project does
A trace-driven, cycle-accurate simulator of a cache hierarchy for a single in-order processor. We feed it memory access traces, and it reports hit/miss behavior, total cycles and average memory access time (AMAT).

## Out of scope
Multicore/coherence, out-of-order execution, virtual memory and TLBs, DRAM internals, prefetching.

## Trace format
One access per line: <type> <hex address> 0 = data read, 1 = data write, 2 = instruction fetch 32-bit byte addresses.

## Hierarchy
- Split L1 (instruction cache + data cache)
- Unified L2
- Main memory
- Default: L1 = 32 KB, 4-way, 64 B blocks. L2 = 256 KB, 8-way, 64 B blocks
- Every parameter is configurable

## Mapping techniques
Direct-mapped, N-way set-associative, fully associative.

## Replacement policies
LRU, FIFO, Random (fixed seed so runs are repeatable).

## Write policies
- Write-back + write-allocate
- Write-through + no-write-allocate

## Timing model (cycles)
- L1 hit: 1
- L2 hit after an L1 miss: +10
- Main memory access after an L2 miss: +100
- Writing back a dirty block costs the access time of the next level
- Accesses are handled one at a time (blocking), no overlap
- Write-through sends one 4-byte word to the next level (traces carry no size)
- A dirty L1 block written back into L2 is a full-block overwrite, so an L2 miss on it does not fetch from memory
- L2 block size must be at least as large as the L1 block size

## Metrics
- Hits, misses, miss rate for every cache
- Total cycles and AMAT
- Writebacks and memory traffic
- Miss types (3C model): compulsory, capacity, conflict

## Experiments
1. Cache size vs miss rate
2. Associativity vs miss rate
3. Block size vs miss rate and AMAT
4. Replacement policy comparison
5. Write-back vs write-through (cycles and memory traffic)
6. Effect of adding L2 on AMAT
7. Matrix multiply: loop order (ijk vs ikj) and blocking

## Validation
Small traces worked out by hand, with unit tests checking the simulator gives the same answers.