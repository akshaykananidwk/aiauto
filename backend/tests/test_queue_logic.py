"""Queue score ordering: priority first, FIFO within the same priority."""
from app.services.queue import compute_score


def test_higher_priority_pops_first():
    low = compute_score(priority=0, seq=1)
    high = compute_score(priority=5, seq=2)
    assert high < low  # BZPOPMIN pops the lowest score


def test_fifo_within_same_priority():
    first = compute_score(priority=0, seq=10)
    second = compute_score(priority=0, seq=11)
    assert first < second


def test_priority_clamped():
    assert compute_score(99, 1) == compute_score(10, 1)
    assert compute_score(-5, 1) == compute_score(0, 1)


def test_priority_dominates_sequence():
    early_low = compute_score(priority=0, seq=1)
    late_high = compute_score(priority=1, seq=1_000_000)
    assert late_high < early_low
