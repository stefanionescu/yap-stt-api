"""Network and WebSocket utilities."""
from __future__ import annotations
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def ws_url(server: str, secure: bool) -> str:
    """Generate WebSocket URL for Yap server ASR streaming endpoint.

    If a full ws:// or wss:// URL is provided, use it as-is; 
    otherwise build one and append '/api/asr-streaming'.
    """
    server = server or ""
    if server.startswith(("ws://", "wss://")):
        return server
    scheme = "wss" if secure else "ws"
    host = server.rstrip("/")
    return f"{scheme}://{host}/api/asr-streaming"


def append_auth_query(url: str, api_key: str, override: bool = False) -> str:
    """Append the auth query parameter expected by the server.

    - When override=False (warmup behavior), only sets if missing.
    - When override=True (bench behavior), always sets/replaces.
    """
    parsed = urlparse(url)
    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if override or ("auth_id" not in query_params):
        query_params["auth_id"] = api_key
    new_query = urlencode(query_params)
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )


def is_runpod_host(server: str) -> bool:
    """Check if server is a RunPod host."""
    s = (server or "").strip().lower()
    return "runpod.net" in s
