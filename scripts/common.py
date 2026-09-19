"""공통 유틸 - 표준 라이브러리만 사용."""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " \
     "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"


# 이 접두사로 시작하는 환경변수는 .env 없이도 그대로 설정으로 쓰입니다.
# (GitHub Actions 처럼 .env 파일이 아예 없는 환경을 위해 필요)
ENV_PREFIXES = ("KAKAO_", "YOUTH_")


def load_env() -> dict:
    """.env + 실제 환경변수를 합쳐 dict 로 반환. 환경변수가 우선."""
    env = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")

    # .env 에 없던 키도 환경변수에 있으면 채운다 (.env 가 없는 CI 환경 대응).
    for k, v in os.environ.items():
        if v and (k in env or k.startswith(ENV_PREFIXES)):
            env[k] = v
    return env


# config.json 값을 덮어쓰는 환경변수. 포크해서 쓰는 사람이 config.json 을
# 건드리지 않고 .env 또는 GitHub Actions secrets/vars 만으로 설정할 수 있게 합니다.
_ENV_OVERRIDES = {
    "YOUTH_SIDO":          ("resident", "sido",     str),
    "YOUTH_SIDO_CODE":     ("resident", "sido_code", str),
    "YOUTH_SIGUNGU":       ("resident", "sigungu",  str),
    "YOUTH_SIGUNGU_CODE":  ("resident", "sigungu_code", str),
    "YOUTH_AGE_MIN":       ("resident", "age_min",  int),
    "YOUTH_AGE_MAX":       ("resident", "age_max",  int),
    "YOUTH_LOOKBACK_DAYS": (None, "lookback_days",  int),
    "YOUTH_MAX_ITEMS":     (None, "max_items_per_message", int),
}


def load_config() -> dict:
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    env = load_env()

    for name, (section, key, cast) in _ENV_OVERRIDES.items():
        raw = (env.get(name) or "").strip()
        if not raw:
            continue
        try:
            value = cast(raw)
        except (TypeError, ValueError):
            print(f"⚠️  {name}={raw!r} 을 해석할 수 없어 무시합니다.")
            continue
        (cfg[section] if section else cfg)[key] = value

    # YOUTH_INTERESTS: config.json 의 관심분야 중 남길 라벨만 콤마로 나열.
    # 비워 두면 전부 사용합니다.
    wanted = [x.strip() for x in (env.get("YOUTH_INTERESTS") or "").split(",") if x.strip()]
    if wanted:
        kept = [g for g in cfg["interests"] if g["label"] in wanted]
        unknown = sorted(set(wanted) - {g["label"] for g in cfg["interests"]})
        if unknown:
            print(f"⚠️  YOUTH_INTERESTS 에 없는 라벨: {', '.join(unknown)}")
        if kept:
            cfg["interests"] = kept

    # 온통청년 대상 조건(profile). 값: 비움 → config.json 유지, "*" → 그 차원 필터 끔,
    # "none" → 제한없음 정책만, 그 외 → 콤마로 나열한 내 라벨.
    profile = cfg.setdefault("profile", {})
    for dim in ("specialization", "job", "education", "major", "marriage"):
        raw = (env.get(f"YOUTH_{dim.upper()}") or "").strip()
        if not raw:
            continue
        if raw == "*":
            profile[dim] = None
        elif raw.lower() == "none":
            profile[dim] = []
        else:
            profile[dim] = [x.strip() for x in raw.split(",") if x.strip()]

    # 지자체 게시판은 지역마다 구조가 달라 기본은 config.json 의 local_board 값을 따릅니다.
    if (env.get("YOUTH_LOCAL_BOARD") or "").strip():
        cfg["local_board"] = env["YOUTH_LOCAL_BOARD"].strip()
    cfg.setdefault("local_board", "dongjak")
    return cfg


def http(url, data=None, headers=None, method=None, timeout=30):
    """요청을 보내고 (status, body_text) 반환."""
    headers = dict(headers or {})
    headers.setdefault("User-Agent", UA)
    body = None
    if data is not None:
        if isinstance(data, dict):
            body = urllib.parse.urlencode(data).encode()
            headers.setdefault(
                "Content-Type",
                "application/x-www-form-urlencoded;charset=utf-8",
            )
        else:
            body = data if isinstance(data, bytes) else str(data).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


# 오류 메시지에 URL 을 실을 때 키가 담긴 쿼리 파라미터는 가린다 (CI 로그 노출 방지).
_SECRET_PARAMS = ("apiKeyNm", "serviceKey", "key", "token", "client_secret")


def redact_url(url: str) -> str:
    return re.sub(r"(?i)\b(" + "|".join(_SECRET_PARAMS) + r")=[^&#]*", r"\1=***", url)


def get_json(url, params=None, headers=None, timeout=30):
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    status, text = http(url, headers=headers, timeout=timeout)
    shown = redact_url(url)[:120]
    if status != 200:
        raise RuntimeError(f"HTTP {status} from {shown} :: {text[:200]}")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise RuntimeError(f"JSON 아님 ({shown}): {text[:200]}")


def read_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def die(msg, code=1):
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(code)
