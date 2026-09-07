from sot.identity.domain import VerifiedIdentity


class LocalSkipAdapter:
    """Issues a stable local identity when Google SSO is skipped."""

    async def verify(self, credential: str) -> VerifiedIdentity:
        name = credential.strip() or "Local"
        return VerifiedIdentity(
            "https://sot.local/skip",
            "local-skip",
            "local@sot.test",
            name,
        )
