"""Tests for the exception hierarchy."""

from __future__ import annotations

from cloakroom.exceptions import (
    AttestationAbortedError,
    BackupError,
    CloakroomError,
    HallucinationDetectedError,
    IPCError,
    ModelHashMismatchError,
    RecoveryKeyError,
)


class TestExceptionHierarchy:
    def test_all_inherit_from_base(self):
        """All custom exceptions should inherit from CloakroomError."""
        assert issubclass(HallucinationDetectedError, CloakroomError)
        assert issubclass(AttestationAbortedError, CloakroomError)
        assert issubclass(BackupError, CloakroomError)
        assert issubclass(ModelHashMismatchError, CloakroomError)
        assert issubclass(RecoveryKeyError, CloakroomError)
        assert issubclass(IPCError, CloakroomError)


class TestHallucinationDetectedError:
    def test_stores_flags(self):
        flags = [{"token": "PERSON_99999", "type": "hallucinated"}]
        err = HallucinationDetectedError(flags)
        assert err.flags == flags
        assert "1 hallucinated" in str(err)

    def test_multiple_flags(self):
        flags = [{"t": "a"}, {"t": "b"}, {"t": "c"}]
        err = HallucinationDetectedError(flags)
        assert "3 hallucinated" in str(err)


class TestModelHashMismatchError:
    def test_stores_hashes(self):
        err = ModelHashMismatchError(
            expected="abcdef123456789",
            actual="000000000000000",
        )
        assert err.expected == "abcdef123456789"
        assert err.actual == "000000000000000"
        assert "abcdef123456" in str(err)
        assert "000000000000" in str(err)
