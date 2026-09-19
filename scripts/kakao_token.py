#!/usr/bin/env python3
"""카카오 토큰 발급 / 자동 갱신.

  python3 scripts/kakao_token.py init --code <인가코드>   # 최초 1회 (브라우저 동의 필요)
  python3 scripts/kakao_token.py show                      # 상태 확인 (토큰값은 출력 안 함)
  python3 scripts/kakao_token.py refresh                   # 강제 갱신
  python3 scripts/kakao_token.py check                     # 발송 가능한 상태인지 진단

리프레시 토큰은 두 곳에서 읽습니다.
  1) data/kakao_token.json  — 로컬에서 init 했을 때
  2) KAKAO_REFRESH_TOKEN    — CI 처럼 파일이 없는 환경

카카오 리프레시 토큰은 유효기간이 2개월이고, 남은 기간이 1개월 미만일 때
갱신 응답에 새 값이 함께 내려옵니다. 즉 한 달에 한 번 이상만 갱신하면
체인이 끊기지 않습니다. 단, 새로 내려온 값을 반드시 보관해야 합니다.
CI 에서는 KAKAO_ROTATED_TOKEN_FILE 로 경로를 주면 거기에 새 값을 써 둡니다.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, http, load_env, read_json, write_json, die  # noqa: E402

TOKEN_FILE = DATA / "kakao_token.json"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
REDIRECT_URI = os.environ.get("KAKAO_REDIRECT_URI", "http://localhost:3000/oauth")
# access_token 만료 60초 전에는 미리 갱신
SKEW = 60


def _emit_rotation(new_token: str) -> None:
    """새로 발급된 refresh_token 을 CI 가 주워갈 수 있게 남긴다."""
    if os.environ.get("GITHUB_ACTIONS"):
        # 뒤 단계에서 실수로 출력해도 로그에 찍히지 않도록 마스킹
        print(f"::add-mask::{new_token}")
    path = os.environ.get("KAKAO_ROTATED_TOKEN_FILE")
    if path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(new_token, encoding="utf-8")
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass
        print("🔄 refresh_token 회전됨 → 저장소 secret 갱신이 필요합니다.")
    elif not TOKEN_FILE.exists():
        print("🔄 refresh_token 이 회전됐는데 보관할 곳이 없습니다. "
              "KAKAO_ROTATED_TOKEN_FILE 을 설정하지 않으면 다음 갱신 때 실패합니다.")


def _load_token() -> dict | None:
    """파일 우선, 없으면 환경변수에서 리프레시 토큰을 가져온다."""
    token = read_json(TOKEN_FILE)
    if token and token.get("refresh_token"):
        return token
    env_rt = (load_env().get("KAKAO_REFRESH_TOKEN") or "").strip()
    if env_rt:
        # access_token 은 없으므로 즉시 갱신하도록 만료 처리
        return {"refresh_token": env_rt, "access_expires_at": 0, "from_env": True}
    return None


def _save(payload: dict, previous: dict | None = None) -> dict:
    now = int(time.time())
    prev = previous or {}
    new_rt = payload.get("refresh_token")
    if new_rt and new_rt != prev.get("refresh_token"):
        _emit_rotation(new_rt)

    token = {
        "access_token": payload["access_token"],
        "access_expires_at": now + int(payload.get("expires_in", 21600)),
        # 갱신 응답에는 refresh_token 이 없을 수 있음 → 기존 값 유지
        "refresh_token": new_rt or prev.get("refresh_token"),
        "refresh_expires_at": (
            now + int(payload["refresh_token_expires_in"])
            if payload.get("refresh_token_expires_in")
            else prev.get("refresh_expires_at")
        ),
        "scope": payload.get("scope") or prev.get("scope"),
        "updated_at": now,
    }
    if not token["refresh_token"]:
        die("refresh_token 을 받지 못했습니다. init 부터 다시 진행하세요.")
    write_json(TOKEN_FILE, token)
    return token


def _post_token(form: dict) -> dict:
    env = load_env()
    form = dict(form)
    form["client_id"] = env.get("KAKAO_REST_API_KEY", "")
    if not form["client_id"]:
        die("KAKAO_REST_API_KEY 가 비어 있습니다 (.env 또는 환경변수).")
    if env.get("KAKAO_CLIENT_SECRET"):
        form["client_secret"] = env["KAKAO_CLIENT_SECRET"]
    else:
        # 2025년 이후 발급된 REST API 키는 클라이언트 시크릿이 기본 활성화라
        # 이 값 없이는 KOE010 으로 실패합니다.
        print("⚠️  KAKAO_CLIENT_SECRET 이 비어 있습니다. "
              "실패하면 docs/01-kakao-setup.md 1-1 을 확인하세요.")
    status, text = http(TOKEN_URL, data=form)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        die(f"토큰 응답을 해석할 수 없습니다 (HTTP {status}).")
    if status != 200 or "access_token" not in payload:
        # 응답 본문에 토큰은 없지만, 혹시 몰라 에러 코드/설명만 골라 출력
        code = payload.get("error_code") or payload.get("error") or "?"
        desc = payload.get("error_description") or ""
        die(f"토큰 발급 실패 (HTTP {status}, {code}): {desc}")
    return payload


def init(code: str) -> dict:
    payload = _post_token({
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "code": code,
    })
    token = _save(payload)
    print("✅ 토큰 저장 완료 →", TOKEN_FILE)
    print("   scope:", token.get("scope"))
    if "talk_message" not in (token.get("scope") or ""):
        print("⚠️  scope 에 talk_message 가 없습니다. 동의항목 설정을 확인하세요.")
    return token


def refresh(force: bool = False) -> dict:
    token = _load_token()
    if not token:
        die("리프레시 토큰이 없습니다. docs/01-kakao-setup.md 를 따라 init 을 먼저 하거나, "
            "KAKAO_REFRESH_TOKEN 을 설정하세요.")
    now = int(time.time())
    if not force and token.get("access_expires_at", 0) - SKEW > now:
        return token
    if token.get("refresh_expires_at") and token["refresh_expires_at"] < now:
        die("refresh_token 이 만료됐습니다. 브라우저 동의가 필요합니다 "
            "(docs/01-kakao-setup.md 5~6번).")
    payload = _post_token({
        "grant_type": "refresh_token",
        "refresh_token": token["refresh_token"],
    })
    return _save(payload, previous=token)


def access_token() -> str:
    return refresh()["access_token"]


def show() -> None:
    token = _load_token()
    if not token:
        print("토큰 없음 — init 또는 KAKAO_REFRESH_TOKEN 필요")
        return
    if token.get("from_env"):
        print("출처            : KAKAO_REFRESH_TOKEN 환경변수")
    now = int(time.time())

    def left(ts):
        if not ts:
            return "알 수 없음"
        d = ts - now
        return f"{d // 86400}일 {d % 86400 // 3600}시간 남음" if d > 0 else "만료됨"

    print("scope           :", token.get("scope") or "-")
    print("access_token    :", left(token.get("access_expires_at")))
    print("refresh_token   :", left(token.get("refresh_expires_at")))


# 토큰 엔드포인트가 가짜 인가코드에 돌려주는 오류코드로 앱 설정 상태를 역추적한다.
_CHECK_HINTS = {
    "KOE320": "✅ REST API 키·Client Secret 정상. 남은 것은 브라우저 동의 → init 뿐입니다 "
              "(docs/01-kakao-setup.md 5~6번).",
    "KOE004": "❌ 카카오 로그인 활성화가 OFF 입니다. 키는 정상이니 "
              "제품 설정 → 카카오 로그인 → 활성화 설정 ON (docs/01-kakao-setup.md 3번).",
    "KOE101": "❌ REST API 키가 잘못됐습니다 (docs/01-kakao-setup.md 1번).",
    "KOE010": "❌ Client Secret 누락/불일치 (docs/01-kakao-setup.md 1-1).",
}


def check() -> None:
    """발송 가능한 상태인지 진단. 토큰이 있으면 실제 갱신, 없으면 앱 키만 검증."""
    if _load_token():
        refresh(force=True)
        print("✅ 토큰 갱신 성공 — 발송 가능한 상태입니다.")
        show()
        return
    print("토큰 없음 — REST API 키와 Client Secret 만 검증합니다.")
    env = load_env()
    form = {
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "code": "check",
        "client_id": env.get("KAKAO_REST_API_KEY", ""),
    }
    if not form["client_id"]:
        die("KAKAO_REST_API_KEY 가 비어 있습니다 (.env 또는 환경변수).")
    if env.get("KAKAO_CLIENT_SECRET"):
        form["client_secret"] = env["KAKAO_CLIENT_SECRET"]
    status, text = http(TOKEN_URL, data=form)
    try:
        code = json.loads(text).get("error_code", "?")
    except json.JSONDecodeError:
        code = "?"
    print(_CHECK_HINTS.get(code, f"❓ 예상치 못한 응답 (HTTP {status}, {code}): {text[:200]}"))
    if code != "KOE320":
        sys.exit(1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--code", required=True)
    sub.add_parser("refresh")
    sub.add_parser("show")
    sub.add_parser("check")
    a = ap.parse_args()
    if a.cmd == "init":
        init(a.code.strip())
    elif a.cmd == "refresh":
        refresh(force=True); print("✅ 갱신 완료"); show()
    elif a.cmd == "show":
        show()
    elif a.cmd == "check":
        check()
