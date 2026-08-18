"""Tests for the three-tier router + usage-based retention."""

from __future__ import annotations

from fullspace import Capability, HashEmbedder, Manifold, UsageTracker
from fullspace.engine.router import Router


def _manifold() -> Manifold:
    m = Manifold(HashEmbedder(dim=64))
    m.register(Capability("alpha", "alpha beta gamma"))
    return m


# ─────────────── three-tier routing ───────────────

def test_merge_zone_reuses_instead_of_spawning():
    # "alpha beta delta" shares 2/3 tokens with "alpha beta gamma": score ~0.66.
    m = _manifold()
    spawned = []

    def materializer(desc, score):
        spawned.append(desc)
        return Capability(f"cap{len(spawned)}", desc)

    # Without a merge zone: 0.66 < 0.9 -> spawns (legacy two-tier behaviour).
    r = Router(m, threshold=0.9, materializer=materializer)
    d = r.route("alpha beta delta")
    assert d.capability.id == "cap1" and len(spawned) == 1

    # With merge_threshold=0.5: 0.66 falls in the merge zone -> reuse, no spawn.
    m2 = _manifold()
    r2 = Router(m2, threshold=0.9, merge_threshold=0.5, materializer=materializer)
    d2 = r2.route("alpha beta delta")
    assert d2.capability.id == "alpha" and len(spawned) == 1  # nothing new
    assert d2.capability.id in m2 and len(m2) == 1


def test_materializer_can_decline_spawn():
    m = _manifold()
    r = Router(m, threshold=0.99, materializer=lambda desc, score: None)
    d = r.route("completely unrelated zebra quantum")
    assert d.capability is not None and d.capability.id == "alpha"  # best-effort
    assert len(m) == 1  # nothing registered


def test_max_materialized_hard_cap():
    m = _manifold()
    r = Router(m, threshold=0.99, max_materialized=1,
               materializer=lambda desc, score: Capability(f"cap_{desc[:12]}", desc))
    r.route("zebra one runs fast")      # spawns (1/1 budget used)
    assert r.materialized_count == 1 and len(m) == 2
    d = r.route("quantum flux diverges")  # budget exhausted -> fallback
    assert d.capability.id == "alpha" and r.materialized_count == 1
    assert len(m) == 2  # no second spawn


# ─────────────── UsageTracker ───────────────

class FakeClock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance_days(self, days):
        self.t += days * 86400


def test_usage_score_respects_window():
    clock = FakeClock()
    u = UsageTracker(window_days=30, clock=clock)
    for _ in range(5):
        u.record("a")
    assert u.score("a") == 5

    clock.advance_days(31)               # outside the window -> counts expire
    assert u.score("a") == 0
    u.record("a")                        # ...but new uses start counting again
    assert u.score("a") == 1


def test_enforce_evicts_least_used_materialized_only():
    clock = FakeClock()
    u = UsageTracker(window_days=30, top_k=2, clock=clock)
    m = Manifold(HashEmbedder(dim=16))

    def add(cid, desc, materialized, hits):
        m.register(Capability(cid, desc))
        if materialized:
            u.mark_materialized(cid)
        for _ in range(hits):
            u.record(cid)

    add("core", "core handwritten capability", materialized=False, hits=0)
    add("hot1", "materialized hot one topic", True, 10)
    add("hot2", "materialized hot two topic", True, 8)
    add("cold1", "materialized cold one", True, 1)   # over cap by one

    evicted = u.enforce(m)
    assert evicted == ["cold1"]                    # least-used materialized out
    assert "cold1" not in m and len(m) == 3
    assert "core" in m                              # handwritten never touched
    assert u.materialized_ids == {"hot1", "hot2"}

    # Still within cap after eviction: enforce is a no-op.
    assert u.enforce(m) == []

    # Going over cap again evicts the least-used materialized capability —
    # cold2 (0 hits) ranks below hot2 (8) and hot1 (10).
    add("cold2", "materialized cold two", True, 0)
    assert u.enforce(m) == ["cold2"]
    assert u.materialized_ids == {"hot1", "hot2"} and "core" in m


def test_enforce_within_cap_is_noop():
    clock = FakeClock()
    u = UsageTracker(top_k=5, clock=clock)
    m = Manifold(HashEmbedder(dim=16))
    for i in range(3):
        m.register(Capability(f"c{i}", f"capability topic {i}"))
        u.mark_materialized(f"c{i}")
        u.record(f"c{i}")
    assert u.enforce(m) == [] and len(m) == 3


def test_recency_breaks_ties():
    clock = FakeClock()
    u = UsageTracker(top_k=1, clock=clock)
    m = Manifold(HashEmbedder(dim=16))
    for cid in ("older", "newer"):
        m.register(Capability(cid, f"topic {cid}"))
        u.mark_materialized(cid)
    u.record("older")                  # used early...
    clock.advance_days(10)
    u.record("newer")                  # ...newer used more recently
    assert u.enforce(m) == ["older"]   # same count (1 vs 1), older evicted


# ─────────────── router ↔ tracker integration ───────────────

def test_router_records_hits_and_enforces_retention():
    clock = FakeClock()
    u = UsageTracker(window_days=30, top_k=1, clock=clock)
    m = _manifold()
    r = Router(m, threshold=0.99, usage=u,
               materializer=lambda desc, score: Capability(desc[:10], desc))

    r.route("alpha beta gamma")            # tier-1 hit on 'alpha'
    assert u.score("alpha") == 1

    r.route("zebra quantum flux diverges")  # near-miss -> spawn, marked, enforced
    assert r.materialized_count == 1
    spawned = [c for c in m.capabilities if c != "alpha"]
    assert len(spawned) == 1
    assert spawned[0] in u.materialized_ids
    assert u.score(spawned[0]) >= 1        # the spawn counts as its first use

    # Second spawn exceeds top_k=1 -> retention fires immediately: the older
    # (equal-count, less recent) materialized capability is evicted, keeping
    # exactly one materialized capability alongside handwritten 'alpha'.
    clock.advance_days(1)                  # ensure the second spawn is "newer"
    r.route("unrelated taco recipe beans")
    assert r.materialized_count == 2
    assert len(u.materialized_ids) == 1    # one materialized survivor
    assert len(m) == 2                     # survivor + handwritten 'alpha'
    assert "alpha" in m                    # handwritten survives everything
