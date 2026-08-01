"""Entrypoint ``ntruth-api`` vincolato al loopback locale."""

from __future__ import annotations


def run() -> None:
    try:
        import uvicorn
    except ModuleNotFoundError as exc:  # pragma: no cover - dipende dall'extra installato
        raise SystemExit("Uvicorn non installato: usare `pip install 'ntruth[api]'`") from exc

    from ntruth.api.app import app

    if app is None:  # pragma: no cover - uvicorn implica normalmente FastAPI
        raise SystemExit("FastAPI non installato: usare `pip install 'ntruth[api]'`")
    uvicorn.run(app, host="127.0.0.1", port=8765, access_log=False)
