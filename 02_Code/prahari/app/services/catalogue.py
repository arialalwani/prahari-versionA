"""Sentinel catalogue client. Camera ids change; JSON fields are the contract.

Live portal (2026-09-03): session cookie, GET /cameras.json as [{id, name}].
HLS at https://<web-host>/<id>/index.m3u8 (browser User-Agent required).
RTSP/WHEP on the public IP from the live /resource page, not on the TLS host.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app import config

FIXTURE_PATH = config.ROOT / "tests" / "fixtures" / "catalogue_sample.json"
CACHE_PATH = config.REPO_ROOT / "03_Data" / "sentinel_catalogue" / "catalogue.last.json"

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

_ALIASES = {
    "id": ("id", "camera_id", "cameraid", "camid"),
    "location": ("location", "name", "site", "place"),
    "codec": ("codec", "video_codec", "encoding"),
    "live": ("live", "is_live", "online", "status"),
    "width": ("width", "w"),
    "height": ("height", "h"),
    "fps_declared": ("fps_declared", "fps", "frame_rate", "framerate"),
    "rtsp": ("rtsp", "rtsp_url", "rtspurl"),
    "whep": ("whep", "whep_url", "whepurl"),
    "hls": ("hls", "hlsurl", "hls_url", "m3u8"),
}

_SESSION: dict[str, Any] = {"client": None, "base": ""}

# The sandbox slows down under load near the deadline. 20s was too tight to log in
# and pull the manifest; SENTINEL_TIMEOUT_S tunes it without a code change.
DEFAULT_TIMEOUT_S = 60.0


def _timeout_s() -> float:
    try:
        value = float(config.getenv("SENTINEL_TIMEOUT_S", "") or DEFAULT_TIMEOUT_S)
    except ValueError:
        return DEFAULT_TIMEOUT_S
    return value if value > 0 else DEFAULT_TIMEOUT_S


def _fold(raw: dict[str, Any]) -> dict[str, Any]:
    return {str(k).lower().replace("-", "_"): v for k, v in raw.items()}


def _pick(folded: dict[str, Any], field: str) -> Any:
    for alias in _ALIASES[field]:
        if alias in folded:
            return folded[alias]
    return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "live", "online", "yes"}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalise_camera(raw: dict[str, Any]) -> dict[str, Any]:
    folded = _fold(raw)
    live_val = _pick(folded, "live")
    if isinstance(live_val, str) and live_val.lower() in {"offline", "down"}:
        live = False
    else:
        live = _as_bool(live_val) if live_val is not None else True
    cam_id = _pick(folded, "id")
    return {
        "id": str(cam_id) if cam_id is not None else "",
        "location": str(_pick(folded, "location") or ""),
        "codec": str(_pick(folded, "codec") or "").lower(),
        "live": live,
        "width": _as_int(_pick(folded, "width")),
        "height": _as_int(_pick(folded, "height")),
        "fps_declared": _as_float(_pick(folded, "fps_declared")),
        "rtsp": str(_pick(folded, "rtsp") or ""),
        "whep": str(_pick(folded, "whep") or ""),
        "hls": str(_pick(folded, "hls") or ""),
        "raw": raw,
    }


def parse_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        cameras = payload.get("cameras") or payload.get("Cameras") or payload.get("data") or []
    elif isinstance(payload, list):
        cameras = payload
    else:
        cameras = []
    return [normalise_camera(c) for c in cameras if isinstance(c, dict)]


def web_base(host: str) -> str:
    host = (host or "").strip()
    if not host:
        return ""
    if "://" in host:
        return host.rstrip("/")
    return "https://" + host.rstrip("/")


def origin_allowed(url: str, host: str | None = None) -> bool:
    parsed = urlparse(url)
    netloc = (parsed.hostname or "").lower()
    if not netloc:
        return False
    allowed: set[str] = {"cctv.corp8.cloud"}
    configured = (host if host is not None else config.getenv("SENTINEL_HOST", "")).strip()
    if configured:
        if "://" in configured:
            allowed.add((urlparse(configured).hostname or "").lower())
        else:
            allowed.add(configured.lower())
    rtsp_host = config.getenv("SENTINEL_RTSP_HOST", "").strip().lower()
    if rtsp_host:
        allowed.add(rtsp_host)
    return netloc in allowed


def apply_origin_urls(cam: dict[str, Any], web: str, rtsp_host: str = "") -> dict[str, Any]:
    """Fill HLS/RTSP/WHEP only when the catalogue row omitted them.

    Camera identity still comes from JSON. The live /resource page documents
    these origins; ids are never invented here.
    """
    cid = cam.get("id") or ""
    web = (web or "").rstrip("/")
    rtsp_host = (rtsp_host or "").strip()
    if cid and web and not cam.get("hls"):
        cam["hls"] = web + "/" + cid + "/index.m3u8"
    if cid and rtsp_host and not cam.get("rtsp"):
        cam["rtsp"] = "rtsp://" + rtsp_host + ":8554/stream/" + cid
    if cid and rtsp_host and not cam.get("whep"):
        cam["whep"] = "http://" + rtsp_host + ":8889/stream/" + cid + "/whep"
    return cam


def _looks_json(response: httpx.Response) -> bool:
    if str(response.url.path).rstrip("/").endswith("login"):
        return False
    ctype = (response.headers.get("content-type") or "").lower()
    text = response.text.lstrip()
    if text.lower().startswith("<!doctype") or text.lower().startswith("<html"):
        return False
    if "json" in ctype:
        return True
    return text.startswith("{") or text.startswith("[")


def _is_login_page(response: httpx.Response) -> bool:
    path = str(response.url.path).lower()
    if "login" in path:
        return True
    head = response.text[:800].lower()
    return "sign in" in head and "<html" in head


def _login(client: httpx.Client, base: str) -> httpx.Response | None:
    """Portal form is email + access password. Session cookie is set on success.

    Bearer / Basic are not the live contract. A password-only POST stays on
    /auth/login with HTML 'Email or access password is incorrect.'
    """
    password = config.getenv("SENTINEL_PASSWORD", "").strip()
    email = (
        config.getenv("SENTINEL_USER", "").strip()
        or config.getenv("SENTINEL_EMAIL", "").strip()
    )
    if not password:
        return None
    data = {"password": password}
    if email:
        data["email"] = email
    response = client.post(
        base + "/auth/login",
        data=data,
        headers={"Referer": base + "/auth/login", "Origin": base},
    )
    return response


def session(host: str | None = None) -> tuple[httpx.Client, str]:
    host = (host if host is not None else config.getenv("SENTINEL_HOST", "")).strip()
    base = web_base(host)
    if _SESSION["client"] is not None and _SESSION["base"] == base:
        return _SESSION["client"], base
    if _SESSION["client"] is not None:
        _SESSION["client"].close()
    client = httpx.Client(
        timeout=_timeout_s(),
        follow_redirects=True,
        headers={"User-Agent": BROWSER_UA, "Referer": base + "/", "Accept": "*/*"},
    )
    _login(client, base)
    _SESSION["client"] = client
    _SESSION["base"] = base
    return client, base


def origin_get(url: str, host: str | None = None) -> httpx.Response:
    if not origin_allowed(url, host):
        return httpx.Response(403, text="hls origin not pinned")
    client, _ = session(host)
    response = client.get(url)
    if response.status_code in {401, 403} or (
        response.status_code == 200 and "sign in" in response.text[:400].lower()
    ):
        _login(client, _SESSION["base"])
        response = client.get(url)
    return response


def load_fixture(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or FIXTURE_PATH
    payload = json.loads(target.read_text(encoding="utf-8"))
    return parse_payload(payload)


def save_cache(payload: Any) -> Path:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not isinstance(payload, (dict, list)):
        payload = {"cameras": payload}
    CACHE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return CACHE_PATH


def fetch(host: str | None = None) -> list[dict[str, Any]]:
    host = (host if host is not None else config.getenv("SENTINEL_HOST", "")).strip()
    if not host:
        return load_fixture()
    client, base = session(host)
    configured = config.getenv("SENTINEL_CATALOGUE_PATH", "/cameras.json") or "/cameras.json"
    if not configured.startswith("/"):
        configured = "/" + configured
    candidates = [configured]
    if "/cameras.json" not in candidates:
        candidates.append("/cameras.json")
    last_error = "catalogue unreachable"
    payload: Any = None
    email = (
        config.getenv("SENTINEL_USER", "").strip()
        or config.getenv("SENTINEL_EMAIL", "").strip()
    )
    password = config.getenv("SENTINEL_PASSWORD", "").strip()
    for path in candidates:
        response = client.get(base + path)
        if response.status_code == 404:
            last_error = f"{path} HTTP 404"
            continue
        if _is_login_page(response) or not _looks_json(response):
            if not password:
                raise RuntimeError(
                    "catalogue is session-gated HTML login; set SENTINEL_PASSWORD in .env"
                )
            if not email:
                raise RuntimeError(
                    "catalogue login form requires email + access password; "
                    "set SENTINEL_USER (or SENTINEL_EMAIL) and SENTINEL_PASSWORD. "
                    "GET /cameras.json redirected to /auth/login (HTML), not JSON."
                )
            login_resp = _login(client, base)
            response = client.get(base + path)
            if _is_login_page(response) or not _looks_json(response):
                hint = "login still HTML"
                if login_resp is not None and "incorrect" in login_resp.text.lower():
                    hint = "email or access password rejected"
                last_error = (
                    f"{path} HTTP {response.status_code} {hint} "
                    f"(final path {response.url.path}, content-type "
                    f"{response.headers.get('content-type')})"
                )
                continue
        payload = response.json()
        break
    if payload is None:
        raise RuntimeError(last_error)
    save_cache(payload)
    cams = parse_payload(payload)
    rtsp_host = config.getenv("SENTINEL_RTSP_HOST", "").strip()
    return [apply_origin_urls(c, base, rtsp_host) for c in cams if c.get("id")]


def to_registry_row(cam: dict[str, Any]) -> dict[str, Any]:
    protocol = "rtsp"
    url = cam.get("rtsp") or ""
    if not url and cam.get("hls"):
        protocol = "hls"
        url = cam["hls"]
    health = "live" if cam.get("live") else "offline"
    return {
        "camera_id": cam["id"],
        "department": "Sentinel",
        "ownership": "Gov",
        "consent": 1,
        "lat": 0.0,
        "lon": 0.0,
        "protocol": protocol,
        "url": url,
        "retention_days": 0,
        "cam_type": "sandbox",
        "health": health,
        "location": cam.get("location") or "",
        "codec": cam.get("codec") or "",
        "width": cam.get("width") or 0,
        "height": cam.get("height") or 0,
        "rtsp": cam.get("rtsp") or "",
        "whep": cam.get("whep") or "",
        "hls": cam.get("hls") or "",
        "extra_json": json.dumps({"fps_declared": cam.get("fps_declared"), "source": "catalogue"}),
    }
