"""Exception hierarchy for CoWork Shield."""


class CoWorkShieldError(Exception):
    """Base exception for all CoWork Shield errors."""


class UnsupportedFormatError(CoWorkShieldError):
    """File format not supported."""

    def __init__(self, extension: str):
        self.extension = extension
        super().__init__(f"Unsupported file format: {extension}")


class WorkspaceNotFoundError(CoWorkShieldError):
    """Referenced workspace does not exist."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Workspace not found: {name}")


class WorkspaceExpiredError(CoWorkShieldError):
    """Workspace TTL has elapsed."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Workspace has expired: {name}")


class VaultCorruptedError(CoWorkShieldError):
    """Vault file failed decryption or JSON parsing."""


class KeychainError(CoWorkShieldError):
    """Failed to read/write macOS Keychain."""


class IntegrityError(CoWorkShieldError):
    """HMAC verification failed. One or more mappings may be corrupted."""


class IncompleteRestorationError(CoWorkShieldError):
    """Tokens remain in the restored document. Restoration aborted."""

    def __init__(self, remaining_tokens: list[str]):
        self.remaining_tokens = remaining_tokens
        super().__init__(
            f"Found {len(remaining_tokens)} unrestored tokens. "
            f"Restoration aborted. Tokens: {remaining_tokens}"
        )


class DetectionError(CoWorkShieldError):
    """Presidio failed to initialize or analyze."""


class HallucinationDetectedError(CoWorkShieldError):
    """AI-generated or mutated tokens found in restored text."""

    def __init__(self, flags: list):
        self.flags = flags
        super().__init__(
            f"Found {len(flags)} hallucinated/mutated tokens in restored text."
        )


class AttestationAbortedError(CoWorkShieldError):
    """User aborted the attestation review."""


class BackupError(CoWorkShieldError):
    """Vault backup or recovery failed."""


class ModelHashMismatchError(CoWorkShieldError):
    """Detection model hash does not match the locked version."""

    def __init__(self, expected: str, actual: str):
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Model hash mismatch: expected {expected[:12]}..., got {actual[:12]}..."
        )


class IPCError(CoWorkShieldError):
    """IPC protocol communication error."""
