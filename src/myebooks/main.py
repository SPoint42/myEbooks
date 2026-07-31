from __future__ import annotations

import os

import uvicorn

from .web import create_app

app = create_app()


def run() -> None:
    raw_port = os.getenv("PORT", "8000")
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ValueError("PORT doit être un entier") from exc
    if not 1 <= port <= 65_535:
        raise ValueError("PORT doit être compris entre 1 et 65535")
    uvicorn.run("myebooks.main:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    run()
