"""Safe access to business data folders."""

from __future__ import annotations

from pathlib import Path


class BusinessNotFoundError(Exception):
    """Raised when a requested business folder is unavailable."""


class BusinessStore:
    """Resolve business folders beneath one configured data root."""

    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root.resolve()

    def resolve(self, business_id: str) -> Path:
        """Return a safe existing business directory."""

        business_path = (self.data_root / business_id).resolve()
        if not business_path.is_relative_to(self.data_root):
            raise BusinessNotFoundError(business_id)
        if not business_path.is_dir():
            raise BusinessNotFoundError(business_id)
        return business_path

    def is_ready(self) -> bool:
        """Return whether the configured data root is available."""

        return self.data_root.is_dir()
