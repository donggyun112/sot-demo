from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

import jwt

from sot.identity.domain import AuthTokenInvalid
from sot.shared.clock import Clock
from sot.shared.ids import UserId


class SOTAccessTokenCodec:
    def __init__(self, secret: str, clock: Clock, lifetime: timedelta) -> None:
        if len(secret.encode()) < 32 or lifetime.total_seconds() <= 0:
            raise ValueError("Access token configuration is invalid")
        self._secret, self._clock, self._lifetime = secret, clock, lifetime

    def encode(self, user_id: UserId) -> str:
        now = self._clock.now()
        return jwt.encode(
            {
                "sub": str(user_id),
                "iat": int(now.timestamp()),
                "exp": int((now + self._lifetime).timestamp()),
                "iss": "sot",
                "jti": str(uuid4()),
            },
            self._secret,
            algorithm="HS256",
        )

    def decode(self, token: str) -> UserId:
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                issuer="sot",
                options={
                    "require": ["sub", "iat", "exp", "iss", "jti"],
                    "verify_exp": False,
                    "verify_iat": False,
                },
            )
            now = self._clock.now().timestamp()
            if (
                type(claims["iat"]) is not int
                or type(claims["exp"]) is not int
                or claims["iat"] > now
                or claims["exp"] <= now
                or claims["exp"] <= claims["iat"]
                or not claims["jti"]
            ):
                raise AuthTokenInvalid()
            return UserId(UUID(claims["sub"]))
        except (jwt.PyJWTError, ValueError, TypeError, AttributeError):
            raise AuthTokenInvalid() from None
