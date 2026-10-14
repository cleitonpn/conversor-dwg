from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    aspose_client_id: str
    aspose_client_secret: str
    max_upload_mb: int = 100
    request_timeout_seconds: float = 300.0

    @classmethod
    def from_env(cls) -> "Settings":
        try:
            max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "100"))
        except ValueError as exc:
            raise RuntimeError("MAX_UPLOAD_MB deve ser um numero inteiro.") from exc

        return cls(
            aspose_client_id=os.getenv("ASPOSE_CLIENT_ID", "").strip(),
            aspose_client_secret=os.getenv("ASPOSE_CLIENT_SECRET", "").strip(),
            max_upload_mb=max_upload_mb,
        )

    def validate_credentials(self) -> None:
        if not self.aspose_client_id or not self.aspose_client_secret:
            raise RuntimeError(
                "Configure ASPOSE_CLIENT_ID e ASPOSE_CLIENT_SECRET antes de converter."
            )

