"""Basit paylaşımlı token doğrulaması.

REST: `X-Auth-Token` header'ı veya `?token=` query parametresi.
WebSocket: `?token=` query parametresi (tarayıcı WS'te header gönderemez).
"""
from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, WebSocket


def _valid(provided: str | None, expected: str) -> bool:
    return provided is not None and secrets.compare_digest(provided, expected)


def require_token(request: Request) -> None:
    expected = request.app.state.config.auth_token
    provided = request.headers.get("x-auth-token") or request.query_params.get("token")
    if not _valid(provided, expected):
        raise HTTPException(status_code=401, detail="Geçersiz veya eksik token")


def check_ws_token(websocket: WebSocket) -> bool:
    expected = websocket.app.state.config.auth_token
    return _valid(websocket.query_params.get("token"), expected)
