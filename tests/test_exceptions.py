"""Tests for the exception hierarchy."""

from __future__ import annotations

from cowork_shield.exceptions import (
    AttestationAbortedError,
    BackupError,
    CoWorkShieldError,
    HallucinationDetectedError,
    IPCError,
    ModelHashMismatchError,
)


class TestExceptionHierarchy:
    def test_all_inherit_from_base(self):
        """All custom exceptions should inherit from CoWorkShieldError."""
        assert issubclass(HallucinationDetectedError, CoWorkShieldError)
        assert issubclass(AttestationAbortedError, CoWorkShieldError)
        assert issubclass(BackupError, CoWorkShieldError)
        assert issubclass(ModelHashMismatchError, CoWorkShieldError)
        assert issubclass(IPCError, CoWorkShieldError)


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
