# Cortex — benchmarks

Measured, with the method beside every number. Each figure here comes from a harness in the
platform's repository that writes the result it reports; none is an estimate. Where a result was
bad first, the bad run is kept beside the good one — a before-and-after that discards the before
is a claim, not evidence.

---

## The hardware is deliberately poor

Most results below were measured on a **2017 mobile processor (Intel i7-7700HQ, 4 cores) with
11 GiB of memory and a rotational disk**, running PostgreSQL 16 on stock defaults — 128 MB of
shared buffers, and `random_page_cost` tuned for a spinning platter, which makes the planner less
willing to use an index than it would be on NVMe. Every figure measured there is a **floor**: the
numbers move one way on production hardware.

The latency of the console's reads was measured on the live demonstration: a dedicated
four-vCPU, 16 GiB cloud host running the single-host deployment in production posture.

## The data is shaped like a carrier's

1,000,004 subjects in **deliberately skewed tenants** — 900,000, 95,000, 5,000 and 4 — because a
tenant predicate is only interesting when the tenant is a fraction of the table. The billing
pipeline was also measured on **production-shaped traffic**: a busy hour holding 8.2% of the day
against 0.22% for the quietest (36× peak to trough), the busiest 1% of lines carrying a third of
the records, and session sizes from a 0.42 MB median to a 1,891 MB maximum.

---

## 1. Every read the console makes

The evidence harness walks every screen with a recorded browser trace; every `GET` the interface
made — 67 of them — is then timed twenty times from three tenants at once (the 900,000-, 95,000-
and 5,000-subject carriers, one signed-in operator each, interleaved), by the server's own
duration header. Nearest-rank percentiles.

| Build | p95 over 100 ms | p99 over 100 ms | slowest p99 | p50 range |
| --- | ---: | ---: | ---: | ---: |
| Early alpha, one API process | 40 of 63 | — | — | 48–93 ms |
| Slow-request diagnostics added | 2 of 63 | 28 of 63 | 281 ms | 26–57 ms |
| The serving process freezes its startup heap | 3 of 63 | 18 of 63 | 141 ms | 25–56 ms |
| Tenant guard and role parsing remembered | **0 of 63** | 3 of 63 | 150 ms | 13–27 ms |
| Young collections every 10,000 allocations | **0 of 63** | **0 of 63** | **92 ms** | 12–26 ms |
| One process per container, the proxy choosing the least busy (67 reads) | **0 of 67** | 0–1 of 67 | 114 ms | 13–29 ms |

**What is claimed: p95 under 100 ms on every read, in every run; p99 under 100 ms on every read
in the best run (slowest 96 ms).** Each request over budget logs where its time went — database,
garbage collector, processor, kernel, page faults, preemptions, and the peers it shared its
process with — and each row of the table is what that line said to fix next.

## 2. Reads that do not grow with the estate

The same query against a 900,000-subject tenant and a 5,000-subject one, by buffers touched —
which, unlike milliseconds, is the same on any hardware:

| Query | Plan | Buffers | p50 | p99 |
| --- | --- | ---: | ---: | ---: |
| negative control: unscoped scan | seq scan | 24,993 | 67.14 ms | 71.59 ms |
| tenant-scoped read, 900k tenant | index | **4** | 0.40 ms | 0.62 ms |
| tenant-scoped read, 5k tenant | index | **4** | 0.31 ms | 0.61 ms |
| agent listing, dominant tenant | index | 139 | 0.50 ms | 0.85 ms |
| agent listing, 0.5% tenant | index | 148 | 0.41 ms | 2.45 ms |

A scoped read touches 6,248 times fewer buffers than the scan it replaces, and **its cost does not
depend on how large the estate is**: no point or paginated read plans a sequential scan.

## 3. Real-time charging

Before every call, SMS and data session a switch asks whether it may proceed and for how much.
One authorisation is seven statements, and exactly one of them decides:

```sql
UPDATE balances SET reserved_minor = reserved_minor + :amount
 WHERE id = :id
   AND balance_minor + overdraft_limit_minor - reserved_minor >= :amount
RETURNING balance_minor, reserved_minor
```

Two switches cannot both be told they may spend the same credit, because the condition and the
deduction are one statement and the database serialises them. That holds on any hardware; the
rates below are a spinning disk's.

| Pattern | Rate | p50 | p95 | p99 | Granted | Refused | Errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| one switch, one line | 36/s | 16.64 ms | 25.03 ms | 59.08 ms | 150 | 0 | 0 |
| refused for want of credit | — | 4.42 ms | 9.19 ms | 9.93 ms | 0 | 80 | 0 |
| eight switches, one line | 38/s | 74.92 ms | 251.42 ms | 308.40 ms | 160 | 0 | 0 |
| eight switches, eight lines | 75/s | 54.88 ms | 116.31 ms | 136.92 ms | 160 | 0 | 0 |

Switches serving different subscribers share no row, so the rate rises with workers — the shape a
carrier's load has. A refusal is measured beside a grant on purpose: a prepaid platform spends much
of its day saying no, and one slow to refuse gets slower exactly as a subscriber runs out of credit.

## 4. When the database goes away mid-transaction

Correctness counts, not latencies: whether anything landed twice, and whether anything landed at
all. The failure is induced by terminating the probe's own backend and waiting until it is gone.

| Failure | Attempts | Confirmed kills | Violations | Recovery p50 | Recovery max |
| --- | ---: | ---: | ---: | ---: | ---: |
| killed mid-authorisation, before commit | 20 | 20 | **0** | 45 ms | 143 ms |
| retried after an ambiguous timeout | 45 | 30 | **0** | — | — |
| serving again after a backend dies | 12 | 12 | **0** | 15 ms | 21 ms |

A switch that never heard back retries with the network's own session reference, and gets the
hold it already has rather than a second one.

## 5. The month-end billing pipeline

128,000 records over 243 lines, production-shaped, delivered by eight concurrent workers, then
mediated, rated and billed:

| Stage | Rows | Seconds | Rate |
| --- | ---: | ---: | ---: |
| ingest, 8 workers | 128,000 | 12.02 | **10,649/s** |
| a retransmitted file | 0 new | 3.61 | **0.30×** the cost of a first delivery |
| mediate | 128,000 | 43.16 | **2,965/s** |
| rate | 624 charges | 1.96 | **318 subscriptions/s** |
| emit | 240 documents | 2.42 | **99/s** |
| **whole pipeline** | | **63.17** | |

On uniform data the rebuilt ingest reached 14,276 records a second, 18 times its first
measurement; production-shaped data is slower, which is the right direction — larger rows and a
busy hour concentrated into one slice of the index. Fifty million records a night is about three
hours of ingest and mediation, single-threaded, and both stages parallelise across batches.

## 6. Payroll at headcount

2,000 employees with six paid months behind the run:

| | Before the rebuild | After | |
| --- | ---: | ---: | ---: |
| calculation, database reads | 30,004 | **8** | **3,750×** fewer |
| calculation, wall clock | 33.26 s | **3.96 s** | 8.4× |
| employees per second | 60 | **505** | |
| payslips, reads | 2,002 | **3** | |

The number of reads no longer depends on the headcount: a run reads each kind of thing once, and
only the statutory heads that actually apply in a month add their own.

## 7. The write ceiling, stated rather than discovered

Cortex refuses any mutation it cannot record, so the audit chain's sustained append rate is the
platform's maximum write rate per tenant — the number a capacity plan starts from.

| Concurrent writers, one tenant | Rotational disk | Low-latency durable storage |
| ---: | --- | --- |
| 1 | 102/s | 340/s |
| 3 | 68/s, 29% refused | 247/s, none refused |
| 6 | 69/s, 46% refused | 208/s, none refused |

Across different tenants there is no shared sequence and no contention. The requirement that
follows is a condition of the performance warranty: **the audit datastore runs on storage with
sub-millisecond durable writes** — NVMe, or a controller with a battery-backed cache.

---

*Gonzalo Romero — sole author.*
