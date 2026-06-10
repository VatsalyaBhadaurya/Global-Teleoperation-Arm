import pytest

from teleop_protocol.validation import (
    OwnershipError,
    ProtocolVersionError,
    SequenceError,
    SequenceTracker,
    check_ownership,
    check_protocol_version,
    is_stale,
    packet_age_ms,
)


def test_sequence_tracker_accepts_increasing():
    tracker = SequenceTracker()
    tracker.accept(1)
    tracker.accept(2)
    tracker.accept(10)
    assert tracker.last_seq == 10


def test_sequence_tracker_rejects_replay_and_out_of_order():
    tracker = SequenceTracker()
    tracker.accept(5)
    with pytest.raises(SequenceError):
        tracker.accept(5)
    with pytest.raises(SequenceError):
        tracker.accept(3)


def test_sequence_tracker_reset():
    tracker = SequenceTracker()
    tracker.accept(5)
    tracker.reset()
    tracker.accept(1)


def test_is_stale():
    now = 1000.0
    assert not is_stale(999.5, max_age_s=1.0, now=now)
    assert is_stale(998.0, max_age_s=1.0, now=now)


def test_packet_age_ms():
    now = 1000.0
    assert packet_age_ms(999.5, now=now) == pytest.approx(500.0)
    assert packet_age_ms(1000.5, now=now) == 0.0


def test_check_ownership():
    check_ownership("op_001", "op_001")
    with pytest.raises(OwnershipError):
        check_ownership("op_002", "op_001")
    with pytest.raises(OwnershipError):
        check_ownership("op_001", None)


def test_check_protocol_version():
    check_protocol_version(1, 1)
    with pytest.raises(ProtocolVersionError):
        check_protocol_version(2, 1)
