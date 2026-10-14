from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    max_upload_mb: int = 100
    request_timeout_seconds: float = 300.0
    allowed_origins: tuple[str, ...] = (
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "https://cleitonpn.github.io",
    )

    @classmethod
    def from_env(cls) -> "Settings":
        try:
            max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "100"))
        except ValueError as exc:
            raise RuntimeError("MAX_UPLOAD_MB deve ser um numero inteiro.") from exc

        allowed_origins = tuple(
            origin.strip().rstrip("/")
            for origin in os.getenv(
                "ALLOWED_ORIGINS",
                "http://localhost:8000,http://127.0.0.1:8000,https://cleitonpn.github.io",
            ).split(",")
            if origin.strip()
        )

        return cls(
            max_upload_mb=max_upload_mb,
            allowed_origins=allowed_origins,
        )

