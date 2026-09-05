from typing import Literal

type AuthReason = Literal[
    "token_malformed",
    "token_too_large",
    "header_invalid",
    "algorithm_rejected",
    "kid_missing",
    "kid_unknown",
    "signature_invalid",
    "issuer_mismatch",
    "audience_mismatch",
    "subject_invalid",
    "time_claim_invalid",
    "token_not_yet_valid",
    "token_expired",
    "token_lifetime_exceeded",
    "client_identity_invalid",
    "scope_invalid",
]


class AuthenticationError(Exception):
    """Base class for authentication failures safe to classify by type."""


class CredentialMissing(AuthenticationError):
    """Raised when no usable credential was provided."""


class InvalidToken(AuthenticationError):
    """Raised with a bounded reason code when a credential is invalid."""

    def __init__(self, reason: AuthReason) -> None:
        super().__init__(reason)
        self.reason = reason


class KeySourceUnavailable(AuthenticationError):
    """Raised when no usable verification-key source is available."""
