"""Cookie + HTTP Basic auth. Stream tokens never embed RTSP URLs."""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app import config

http_basic = HTTPBasic(auto_error=False)


@dataclass
class User:
    username: str
    role: str
    department: str | None

    @property
    def is_write(self) -> bool:
        return self.role in {"superadmin", "soc_operator"}

    @property
    def is_admin(self) -> bool:
        return self.role == "superadmin"


def _sign(payload: str) -> str:
    secret = config.getenv("SECRET_KEY", "change-me").encode()
    return hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()


def lookup_user(username: str, password: str) -> User | None:
    found = None
    dummy = b"\x00" * 32
    offered = password.encode("utf-8")
    for row in config.users():
        stored = (row["password"] or "").encode("utf-8")
        if len(offered) != len(stored):
            hmac.compare_digest(dummy, dummy)
            match = False
        else:
            match = hmac.compare_digest(offered, stored)
        if row["username"] == username and match:
            found = User(username=username, role=row["role"], department=row["department"])
    return found


def issue_session(user: User, ttl_s: int = 12 * 3600) -> str:
    exp = int(time.time()) + ttl_s
    payload = f"{user.username}|{user.role}|{user.department or ''}|{exp}"
    return f"{payload}|{_sign(payload)}"


def parse_session(token: str | None) -> User | None:
    if not token:
        return None
    parts = token.split("|")
    if len(parts) != 5:
        return None
    username, role, department, exp_s, sig = parts
    payload = f"{username}|{role}|{department}|{exp_s}"
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    try:
        if int(exp_s) < int(time.time()):
            return None
    except ValueError:
        return None
    return User(username=username, role=role, department=department or None)


def issue_stream_token(camera_id: str, actor: str, ttl_s: int | None = None) -> str:
    ttl = ttl_s if ttl_s is not None else config.STREAM_TOKEN_TTL_S
    exp = int(time.time()) + ttl
    payload = f"{camera_id}|{actor}|{exp}"
    return f"{payload}|{_sign(payload)}"


def verify_stream_token(token: str, camera_id: str) -> str:
    parts = token.split("|")
    if len(parts) != 4:
        raise HTTPException(status_code=401, detail="bad stream token")
    cid, actor, exp_s, sig = parts
    payload = f"{cid}|{actor}|{exp_s}"
    if not hmac.compare_digest(sig, _sign(payload)):
        raise HTTPException(status_code=401, detail="bad stream token")
    if cid != camera_id:
        raise HTTPException(status_code=401, detail="token camera mismatch")
    try:
        if int(exp_s) < int(time.time()):
            raise HTTPException(status_code=401, detail="expired stream token")
    except ValueError:
        raise HTTPException(status_code=401, detail="bad stream token")
    return actor


def current_actor() -> str:
    return "anonymous"


#: The web UI sends this header on every request. The UI authenticates by session
#: cookie only: a browser silently re-sends any Basic credentials it once cached,
#: which would make Sign out impossible until the browser is closed.
WEB_CLIENT_HEADER = "x-prahari-client"


def _is_web_client(request: Request) -> bool:
    return request.headers.get(WEB_CLIENT_HEADER, "").lower() == "web"


def get_user(
    request: Request,
    credentials: HTTPBasicCredentials | None = Depends(http_basic),
    prahari_session: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
) -> User | None:
    if credentials and not _is_web_client(request):
        user = lookup_user(credentials.username, credentials.password)
        if user:
            return user
    user = parse_session(prahari_session)
    if user:
        return user
    if authorization and authorization.lower().startswith("bearer "):
        return parse_session(authorization.split(" ", 1)[1].strip())
    return None


def require_user(request: Request, user: User | None = Depends(get_user)) -> User:
    if user is None:
        # No Basic challenge for the web UI: it would pop the browser's native
        # login dialog on top of PRAHARI's own sign-in screen.
        headers = None if _is_web_client(request) else {"WWW-Authenticate": "Basic"}
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="login required",
            headers=headers,
        )
    return user


def require_roles(*roles: str):
    def _inner(user: User = Depends(require_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="forbidden")
        return user

    return _inner


def assert_write(user: User) -> None:
    if user.role == "auditor":
        raise HTTPException(status_code=403, detail="auditor is read-only")
    if user.role == "dept_viewer":
        raise HTTPException(status_code=403, detail="viewer cannot write")


def visible_cameras(rows: list[dict], user: User) -> list[dict]:
    if user.role in {"superadmin", "soc_operator", "auditor"}:
        return rows
    out = []
    for row in rows:
        if row.get("department") != user.department:
            continue
        if row.get("ownership") == "Private-Permitted":
            continue
        out.append(row)
    return out


def can_see_camera(row: dict, user: User) -> bool:
    return bool(visible_cameras([row], user))
