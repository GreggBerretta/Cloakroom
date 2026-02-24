"""Exception hierarchy for Cloakroom."""


class CloakroomError(Exception):
    """Base exception for all Cloakroom errors."""


class UnsupportedFormatError(CloakroomError):
    """File format not supported."""

    def __init__(self, extension: str):
        self.extension = extension
        super().__init__(f"Unsupported file format: {extension}")


class WorkspaceNotFoundError(CloakroomError):
    """Referenced workspace does not exist."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Workspace not found: {name}")


class WorkspaceExpiredError(CloakroomError):
    """Workspace TTL has elapsed."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Workspace has expired: {name}")


class VaultCorruptedError(CloakroomError):
    """Vault file failed decryption or JSON parsing."""


class KeychainError(CloakroomError):
    """Failed to read/write macOS Keychain."""


class IntegrityError(CloakroomError):
    """HMAC verification failed. One or more mappings may be corrupted."""


class IncompleteRestorationError(CloakroomError):
    """Tokens remain in the restored document. Restoration aborted."""

    def __init__(self, remaining_tokens: list[str]):
        self.remaining_tokens = remaining_tokens
        super().__init__(
            f"Found {len(remaining_tokens)} unrestored tokens. "
            f"Restoration aborted. Tokens: {remaining_tokens}"
        )


class DetectionError(CloakroomError):
    """Presidio failed to initialize or analyze."""


class HallucinationDetectedError(CloakroomError):
    """AI-generated or mutated tokens found in restored text."""

    def __init__(self, flags: list, details: str = ""):
        self.flags = flags
        self.details = details
        message = f"Found {len(flags)} hallucinated/mutated tokens in restored text."
        if details:
            message = f"{message}\n{details}"
        super().__init__(message)


class AttestationAbortedError(CloakroomError):
    """User aborted the attestation review."""


class BackupError(CloakroomError):
    """Vault backup or recovery failed."""


class ModelHashMismatchError(CloakroomError):
    """Detection model hash does not match the locked version."""

    def __init__(self, expected: str, actual: str):
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Model hash mismatch: expected {expected[:12]}..., got {actual[:12]}..."
        )


class ReplayMismatchError(CloakroomError):
    """Deterministic replay check failed for identical input."""

    def __init__(self, expected: str, actual: str):
        self.expected = expected
        self.actual = actual
        super().__init__(
            "Deterministic replay mismatch: expected "
            f"{expected[:12]}..., got {actual[:12]}..."
        )


class XLSXContentLossRiskError(CloakroomError):
    """XLSX contains content openpyxl may silently drop."""


class RecoveryKeyError(CloakroomError):
    """Recovery key export/import payload is invalid or cannot be decrypted."""


class IPCError(CloakroomError):
    """IPC protocol communication error."""


class PdfExtractionError(CloakroomError):
    """PDF extraction failed before anonymization."""


class PdfInputOnlyError(CloakroomError):
    """PDF is an input-only format and cannot be restored directly."""

    def __init__(self):
        super().__init__(
            "PDF is input-only. Restore from tokenized Markdown (.md) or DOCX (.docx), "
            "not from .pdf."
        )


class ColumnSelectionError(CloakroomError):
    """Column selection is invalid for the current file."""


class LicenseKeyInvalidError(CloakroomError):
    """Provided license key is syntactically invalid or unauthorized."""


class LicenseFeatureError(CloakroomError):
    """Requested feature is not available for the active license tier."""


class LicenseLimitExceededError(CloakroomError):
    """Free-tier operation quota exceeded."""
