"""DataMate package."""

from __future__ import annotations


def main() -> None:
    """Run the development API server."""

    import uvicorn

    uvicorn.run("datamate.api.app:app", host="0.0.0.0", port=8000)
