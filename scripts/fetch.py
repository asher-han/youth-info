#!/usr/bin/env python3
"""청년정책 수집 → 필터 → data/latest.json

  python3 scripts/fetch.py            # 수집 후 저장
  python3 scripts/fetch.py --verbose  # 소스별 원본 개수까지 출력
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, die, get_json, http, load_config, load_env, read_json, write_json  # noqa: E402

LATEST = DATA / "latest.json"
SEEN = DATA / "seen.json"

YOUTH_API = "https://www.youthcenter.go.kr/go/ythip/getPlcy"


# ---------------------------------------------------------------- 유틸

def strip_tags(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def item_key(source: str, ident: str) -> str:
    return hashlib.sha1(f"{source}:{ident}".encode()).hexdigest()[:16]


def fmt_period(start: str, end: str) -> str:
    def f(x):
        x = (x or "").strip()
        if re.fullmatch(r"\d{8}", x):
            return f"{x[4:6]}.{x[6:8]}"
        return x
    a, b = f(start), f(end)
    if a and b:
        return f"{a}~{b}"
    return b and f"~{b}" or a or "상시"


# ---------------------------------------------------------------- 소스 1: 온통청년 OpenAPI

# 온통청년 OpenAPI 코드표. 실제 응답의 제목과 대조해 확인 (2026-09-18: 국방부 4건 → 0014007,
# 석·박사 R&D → 0049008, 미취업자 인턴 → 0013003 등). "제한없음" 코드만 무조건 통과.
YC_CODES = {
    "specialization": {   # sbizCd 특화분야
        "0014001": "중소기업", "0014002": "여성", "0014003": "기초생활수급자",
        "0014004": "한부모가정", "0014005": "장애인", "0014006": "농업인", "0014007": "군인",
        "0014008": "지역인재", "0014009": "기타", "0014010": "제한없음",
    },
    "job": {              # jobCd 취업상태
        "0013001": "재직자", "0013002": "자영업자", "0013003": "미취업자", "0013004": "프리랜서",
        "0013005": "일용근로자", "0013006": "(예비)창업자", "0013007": "단기근로자",
        "0013008": "영농종사자", "0013009": "기타", "0013010": "제한없음",
    },
    "education": {        # schoolCd 학력
        "0049001": "고졸 미만", "0049002": "고교 재학", "0049003": "고졸 예정", "0049004": "고교 졸업",
        "0049005": "대학 재학", "0049006": "대졸 예정", "0049007": "대학 졸업", "0049008": "석·박사",
        "0049009": "기타", "0049010": "제한없음",
    },
    "major": {            # plcyMajorCd 전공
        "0011001": "인문계열", "0011002": "사회계열", "0011003": "상경계열", "0011004": "이학계열",
        "0011005": "공학계열", "0011006": "예체능계열", "0011007": "농산업계열", "0011008": "기타",
        "0011009": "제한없음",
    },
    "marriage": {"0055001": "기혼", "0055002": "미혼", "0055003": "제한없음"},   # mrgSttsCd
}
YC_FIELD = {"specialization": "sbizCd", "job": "jobCd", "education": "schoolCd",
            "major": "plcyMajorCd", "marriage": "mrgSttsCd"}
APLY_OPEN, APLY_ALWAYS, APLY_CLOSED = "0057001", "0057002", "0057003"   # aplyPrdSeCd
INST_CENTRAL = "0054001"                                                 # pvsnInstGroupCd (0054002 = 지자체)
YC_MAX_PAGES = 6

# zipCd 는 지자체가 전국 코드를 통째로 넣는 경우가 흔해(화순군 정책에 256개 코드 등) 믿을 수
# 없다. 등록·주관 기관명이 다른 시도로 시작하면 타지역 정책으로 본다.
SIDO_ABBR = {"충청북도": "충북", "충청남도": "충남", "전라북도": "전북", "전라남도": "전남",
             "경상북도": "경북", "경상남도": "경남", "강원특별자치도": "강원",
             "전북특별자치도": "전북", "제주특별자치도": "제주", "세종특별자치시": "세종"}
SIDO_PREFIXES = {"서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원",
                 "충북", "충남", "전북", "전남", "경북", "경남", "제주"}
NO_APPLY_WORDS = ("해당없음", "해당 없음", "없음")


def _sido_of(name: str) -> str | None:
    """기관명 → 시도 약칭. '전남광주통합특별시 화순군…' → '전남', '국무조정실' → None."""
    name = (name or "").strip()
    for full, abbr in SIDO_ABBR.items():
        if name.startswith(full):
            return abbr
    return name[:2] if name[:2] in SIDO_PREFIXES else None


def _other_sido(names: list[str], my_sido: str) -> bool:
    mine = _sido_of(my_sido)
    return any(s and s != mine for s in map(_sido_of, names))


def _not_applicable(r: dict) -> bool:
    """상시인데 신청 방법이 비었거나 '해당없음'이면 시민이 신청할 수 있는 사업이 아니라
    부처 내부 제도 과제(위원회 설치, 실태조사, 플랫폼 고도화 등)로 본다."""
    if (r.get("aplyPrdSeCd") or "").strip() != APLY_ALWAYS:
        return False
    how = " ".join(str(r.get("plcyAplyMthdCn") or "").split())
    return not how or how in NO_APPLY_WORDS


def _codes(raw: str) -> list[str]:
    return [c.strip() for c in str(raw or "").split(",") if c.strip()]


def _aply_ranges(raw: str) -> list[tuple[str, str]]:
    """'20260416 ~ 20260430' 또는 여러 구간이 '\\N' 으로 이어진 문자열 → [(시작, 끝)]."""
    return re.findall(r"(\d{8})\s*~\s*(\d{8})", str(raw or ""))


def _pick_range(ranges: list[tuple[str, str]], today: str) -> tuple[str, str] | None:
    """진행 중 구간 → 다음 예정 구간 → 마지막 구간 순으로 고른다."""
    if not ranges:
        return None
    for a, b in ranges:
        if a <= today <= b:
            return a, b
    upcoming = [r for r in ranges if r[0] > today]
    return min(upcoming) if upcoming else max(ranges, key=lambda r: r[1])


def profile_ok(targets: dict, profile: dict, warned: set) -> str | None:
    """정책의 대상 코드가 내 프로필과 맞지 않으면 걸린 차원 이름을 돌려준다 (맞으면 None).

    profile[차원] 이 None 이면 그 차원은 보지 않는다. 리스트면 '제한없음' 정책은 통과,
    특정 대상으로 한정된 정책은 내 라벨과 하나라도 겹쳐야 통과한다.
    """
    for dim, table in YC_CODES.items():
        mine = profile.get(dim)
        if mine is None:
            continue
        codes = targets.get(dim) or []
        labels = {table.get(c, c) for c in codes}
        if not labels or "제한없음" in labels:
            continue
        unknown = set(mine) - set(table.values())
        if unknown and dim not in warned:
            warned.add(dim)
            print(f"⚠️  profile.{dim} 에 없는 라벨: {', '.join(sorted(unknown))} "
                  f"(가능: {', '.join(table.values())})")
        if not labels & set(mine):
            return dim
    return None


def fetch_youthcenter(cfg: dict, api_key: str, verbose=False) -> list[dict]:
    """내 시군구에 해당하는 정책을 최신 등록순으로 훑어, 지역·기간·대상 조건으로 거른다.

    zipCd 에 시군구 코드를 주면 전국 정책(모든 시군구 나열) + 시도 정책 + 우리 구 정책이
    함께 오고 다른 지역 한정 정책은 빠진다. 시도 코드(예: 11)는 API 가 무시하므로 쓰지 않는다.
    """
    if not api_key:
        print("⚠️  YOUTH_API_KEY 미설정 — 온통청년 건너뜀")
        return []

    res = cfg["resident"]
    profile = cfg.get("profile") or {}
    today = dt.date.today()
    today_s = today.strftime("%Y%m%d")
    cutoff = (today - dt.timedelta(days=int(cfg.get("lookback_days", 14)))).strftime("%Y%m%d")
    sigungu = str(res.get("sigungu_code") or "").strip()

    out, seen_no, warned = [], set(), set()
    drop = {"지역 외": 0, "타지역 기관": 0, "마감": 0, "기간 지남": 0, "오래됨": 0,
            "신청 불가": 0, "대상 불일치": 0}
    stop = False

    for page in range(1, YC_MAX_PAGES + 1):
        params = {"apiKeyNm": api_key, "pageNum": page, "pageSize": 100, "rtnType": "json"}
        if sigungu:
            params["zipCd"] = sigungu
        try:
            data = get_json(YOUTH_API, params=params)
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  온통청년 조회 실패 (page={page}): {e}")
            break
        result = data.get("result") or {}
        rows = result.get("youthPolicyList") or []
        if verbose:
            tot = (result.get("pagging") or {}).get("totCount")
            print(f"   온통청년 zipCd={sigungu or '전국'} p{page}: {len(rows)}건 (전체 {tot})")
        if not rows:
            break

        for r in rows:
            no = r.get("plcyNo")
            if not no or no in seen_no:
                continue
            seen_no.add(no)

            reg = re.sub(r"\D", "", str(r.get("frstRegDt") or ""))[:8]
            if reg and reg < cutoff:
                stop = True             # 최신 등록순이므로 이후 페이지는 전부 기간 밖

            zips = _codes(r.get("zipCd"))
            if sigungu and zips and sigungu not in zips:
                drop["지역 외"] += 1
                continue
            if _other_sido([r.get("rgtrHghrkInstCdNm"), r.get("sprvsnInstCdNm")], res.get("sido", "")):
                drop["타지역 기관"] += 1
                continue

            status = (r.get("aplyPrdSeCd") or "").strip()
            ranges = _aply_ranges(r.get("aplyYmd"))
            if status == APLY_CLOSED:
                drop["마감"] += 1
                continue
            if ranges and max(b for _, b in ranges) < today_s:
                drop["기간 지남"] += 1
                continue
            # 최근 등록됐거나, 신청 구간이 최근 시작했거나 앞으로 시작하는 것만
            recent = (reg >= cutoff) or any(a >= cutoff for a, _ in ranges)
            if not recent:
                drop["오래됨"] += 1
                continue

            if _not_applicable(r):
                drop["신청 불가"] += 1
                continue

            targets = {dim: _codes(r.get(field)) for dim, field in YC_FIELD.items()}
            if profile_ok(targets, profile, warned):
                drop["대상 불일치"] += 1
                continue

            chosen = _pick_range(ranges, today_s)
            if chosen:
                period, end_ymd = fmt_period(*chosen), chosen[1]
            else:
                period, end_ymd = "상시", ""
            central = (r.get("pvsnInstGroupCd") or "").strip() == INST_CENTRAL
            out.append({
                "source": "온통청년",
                "id": str(no),
                "title": strip_tags(r.get("plcyNm")),
                "body": strip_tags(f"{r.get('plcyExplnCn', '')} {r.get('plcySprtCn', '')}"),
                "agency": (r.get("sprvsnInstCdNm") or r.get("operInstCdNm") or "").strip(),
                "period": period,
                "end_ymd": end_ymd,
                "age_min": r.get("sprtTrgtMinAge"),
                "age_max": r.get("sprtTrgtMaxAge"),
                "category": (r.get("lclsfNm") or "").strip(),
                "url": (r.get("refUrlAddr1") or r.get("refUrlAddr2")
                        or f"https://www.youthcenter.go.kr/youthPolicy/ythPlcyTotalSearch?plcyNo={no}"),
                # 중앙부처(전국) 정책은 지자체 정책보다 뒤로
                "priority": 2 if central else 1,
            })
        if len(rows) < 100 or stop:
            break

    if verbose:
        dropped = ", ".join(f"{k} {v}" for k, v in drop.items() if v)
        print(f"   온통청년 필터 통과 {len(out)}건" + (f" (제외: {dropped})" if dropped else ""))
    return out


# ---------------------------------------------------------------- 소스 2~4: 게시판 크롤링

SEOUL = "https://youth.seoul.go.kr"
DONGJAK = "https://www.dongjak.go.kr"

# 청년몽땅정보통 정책목록(서울시/자치구)의 공통 행 패턴.
# 첫 <span> 이 서울시 목록에선 분야, 자치구 목록에선 구 이름이라 그룹명만 바꿔 씁니다.
_POLICY_ROW = (
    r'<li>\s*<span class="bg-[\w-]+">\s*(?P<{tag}>[^<]*?)\s*</span>\s*'
    r'<div class="txt">\s*'
    r"<a\b[^>]*goView\('(?P<id>[^']+)'\)[^>]*>(?P<title>.*?)</a>\s*"
    r'<em[^>]*>(?P<body>.*?)</em>'
)

BOARDS = [
    {
        "name": "서울시 청년정책",
        "enabled": True,
        "requires_sido": "서울특별시",
        "list_url": SEOUL + "/infoData/plcyInfo/ctList.do"
                            "?key=2309150002&tabKind=002&blueWorksYn=N",
        "page_param": "pageIndex",
        "pages": 5,                                   # 5건/페이지
        "scope_pattern": r'<ul class="policy-list">(.*?)</ul>',
        "row_pattern": _POLICY_ROW.format(tag="category"),
        "detail_url": SEOUL + "/infoData/plcyInfo/view.do"
                              "?key=2309150002&tabKind=001&plcyBizId={id}",
        "agency": "서울특별시",
        "priority": 1,
    },
    {
        "name": "자치구 청년정책",
        "enabled": True,
        "requires_sido": "서울특별시",
        "list_url": SEOUL + "/infoData/plcyInfo/guList.do"
                            "?key=2309150002&tabKind=003&blueWorksYn=N",
        "page_param": "pageIndex",
        "pages": 5,
        "scope_pattern": r'<ul class="policy-list">(.*?)</ul>',
        "row_pattern": _POLICY_ROW.format(tag="region"),
        "detail_url": SEOUL + "/infoData/plcyInfo/view.do"
                              "?key=2309150002&tabKind=001&plcyBizId={id}",
        # 우리 구 + 구 표기 없는 시 전체 건 (구 이름은 config/env 에서)
        "region_allow_resident": True,
        "agency": "서울시 자치구",
        "priority": 0,
    },
    {
        "name": "서울 청년지원정보",
        "enabled": True,
        "requires_sido": "서울특별시",
        "list_url": SEOUL + "/infoData/sprtInfo/list.do?key=2309130006",
        "page_param": "pageIndex",
        "pages": 3,                                   # 8건/페이지
        "row_split": 'class="feed-item"',
        "row_pattern": (
            r"goView\('(?P<id>\d+)'\).*?"
            r'<span class="cate">\s*(?P<category>[^<]*?)\s*</span>\s*'
            r'<div class="name[^"]*">(?P<title>.*?)</div>'
            r'(?:.*?<span class="state[^"]*">\s*(?P<period>[^<]*?)\s*</span>)?'
        ),
        "detail_url": SEOUL + "/infoData/sprtInfo/view.do"
                              "?key=2309130006&sprtInfoId={id}",
        "agency": "서울특별시",
        "priority": 1,
    },
    {
        "name": "동작구 알려드립니다",
        "enabled": True,
        "local_board_key": "dongjak",
        "list_url": DONGJAK + "/portal/bbs/B0000022/list.do?menuNo=200641",
        "page_param": "pageIndex",
        "pages": 8,                                   # 10건/페이지, lookback 도달 시 조기 종료
        "base": DONGJAK,
        "scope_pattern": r'<div class="bdList">(.*?)</table>',
        "row_pattern": (
            r'<td class="title"><a href="(?P<href>[^"]+)">(?P<title>.*?)</a></td>\s*'
            r'<td>\s*(?P<agency>[^<]*?)\s*</td>\s*'
            r'<td>\s*(?P<date>\d{4}-\d{2}-\d{2})\s*</td>'
        ),
        "use_lookback": True,
        "priority": 0,
    },
    # 동작구 고시·공고 / 채용공고는 본문이 dongjak.eminwon.seoul.kr iframe 으로
    # 들어가는데 해당 도메인이 이그레스 허용목록에 없어 접근 불가(2026-09-12).
    # youthjob.dongjak.go.kr 도 동일하게 차단됨. 허용되면 enabled 를 켜고 패턴을 채울 것.
    {"name": "동작구 고시·공고", "enabled": False, "list_url": "",
     "note": "https://dongjak.eminwon.seoul.kr/emwp/jsp/ofr/OfrNotAncmtLSub.jsp"
             "?not_ancmt_se_code=01,04 — 이그레스 차단"},
]


def _page_url(url: str, param: str, page: int) -> str:
    if not param:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{param}={page}"


def _chunks(board: dict, text: str) -> list[str]:
    """행 정규식을 적용할 구간으로 잘라 낸다 (인접 항목 간 오매칭 방지)."""
    if board.get("row_split"):
        return text.split(board["row_split"])[1:]
    if board.get("scope_pattern"):
        return [m.group(1) for m in re.finditer(board["scope_pattern"], text, re.S)]
    return [text]


def fetch_board(board: dict, cfg: dict, verbose=False) -> list[dict]:
    if not board.get("enabled") or not board.get("list_url"):
        if verbose:
            print(f"   {board['name']}: 비활성 — 건너뜀")
        return []

    res = cfg["resident"]
    need_sido = board.get("requires_sido")
    if need_sido and res.get("sido") != need_sido:
        if verbose:
            print(f"   {board['name']}: {need_sido} 전용 — 건너뜀 (현재 {res.get('sido')})")
        return []

    key = board.get("local_board_key")
    if key and cfg.get("local_board") != key:
        if verbose:
            print(f"   {board['name']}: local_board={cfg.get('local_board')!r} — 건너뜀")
        return []

    cutoff = (dt.date.today()
              - dt.timedelta(days=int(cfg.get("lookback_days", 14)))).strftime("%Y-%m-%d")
    allow = [res["sigungu"], ""] if board.get("region_allow_resident") else None
    out: list[dict] = []
    seen_ids: set[str] = set()
    stop = False

    for page in range(1, int(board.get("pages", 1)) + 1):
        url = _page_url(board["list_url"], board.get("page_param"), page)
        try:
            status, text = http(url)
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  {board['name']} p{page} 요청 실패: {e}")
            break
        if status != 200:
            print(f"⚠️  {board['name']} p{page} HTTP {status}")
            break

        rows = 0
        for chunk in _chunks(board, text):
            for m in re.finditer(board["row_pattern"], chunk, re.S):
                g = m.groupdict()
                rows += 1

                posted = (g.get("date") or "").strip()
                if board.get("use_lookback") and posted and posted < cutoff:
                    stop = True          # 목록이 최신순이므로 이후는 전부 기간 밖
                    continue

                if allow is not None and (g.get("region") or "").strip() not in allow:
                    continue

                ident = (g.get("id") or g.get("href") or "").strip()
                if not ident or ident in seen_ids:
                    continue
                seen_ids.add(ident)

                href = (g.get("href") or "").strip()
                if not href and board.get("detail_url"):
                    href = board["detail_url"].format(id=ident)
                if href and not href.startswith("http"):
                    href = board.get("base", "") + ("" if href.startswith("/") else "/") + href

                title = strip_tags(g.get("title"))
                out.append({
                    "source": board["name"],
                    "id": ident,
                    "title": title,
                    "body": strip_tags(g.get("body")) or title,
                    "agency": strip_tags(g.get("agency")) or board.get("agency", ""),
                    "period": strip_tags(g.get("period") or ""),
                    "end_ymd": "",
                    "posted": posted,
                    "age_min": None,
                    "age_max": None,
                    "category": strip_tags(g.get("category") or g.get("region") or ""),
                    "url": href,
                    "priority": int(board.get("priority", 1)),
                })

        if verbose:
            print(f"   {board['name']} p{page}: 행 {rows}건 → 누적 수집 {len(out)}건")
        if rows == 0 or stop:
            break
    return out


# ---------------------------------------------------------------- 필터

def match_interest(item: dict, cfg: dict) -> str | None:
    text = f"{item['title']} {item['body']} {item['category']}"
    for group in cfg["interests"]:
        if any(k in text for k in group["keywords"]):
            return group["label"]
    return None


def age_ok(item: dict, cfg: dict) -> bool:
    res = cfg["resident"]
    lo, hi = item.get("age_min"), item.get("age_max")
    try:
        lo = int(lo) if lo not in (None, "", 0, "0") else None
        hi = int(hi) if hi not in (None, "", 0, "0") else None
    except (TypeError, ValueError):
        return True
    if lo is None and hi is None:
        return True                      # 연령 무관
    lo = lo if lo is not None else 0
    hi = hi if hi is not None else 200
    return not (hi < res["age_min"] or lo > res["age_max"])   # 구간 겹침


def not_expired(item: dict) -> bool:
    end = item.get("end_ymd") or ""
    if not re.fullmatch(r"\d{8}", end):
        return True
    return end >= dt.date.today().strftime("%Y%m%d")


def apply_filters(items: list[dict], cfg: dict) -> list[dict]:
    out = []
    for it in items:
        if any(bad in it["title"] for bad in cfg.get("exclude_keywords", [])):
            continue
        if not age_ok(it, cfg) or not not_expired(it):
            continue
        label = match_interest(it, cfg)
        if not label:
            continue
        it = dict(it, interest=label, key=item_key(it["source"], it["id"]))
        out.append(it)
    return out


def mark_new(items: list[dict]) -> list[dict]:
    seen = set(read_json(SEEN, default=[]) or [])
    for it in items:
        it["is_new"] = it["key"] not in seen
    return items


# ---------------------------------------------------------------- main

def main(verbose=False):
    cfg, env = load_config(), load_env()
    raw = fetch_youthcenter(cfg, env.get("YOUTH_API_KEY", ""), verbose)
    for b in BOARDS:
        raw += fetch_board(b, cfg, verbose)

    filtered = mark_new(apply_filters(raw, cfg))
    # 신규 먼저 → 우리 구 > 시도 > 중앙부처 순 → 마감 임박 순 (상시는 맨 뒤)
    filtered.sort(key=lambda x: (not x["is_new"], x.get("priority", 1),
                                 x.get("end_ymd") or "99999999"))

    payload = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "raw_count": len(raw),
        "matched_count": len(filtered),
        "new_count": sum(1 for x in filtered if x["is_new"]),
        "resident": cfg["resident"],
        "items": filtered,
    }
    write_json(LATEST, payload)
    print(f"✅ 원본 {len(raw)}건 → 조건 일치 {len(filtered)}건 "
          f"(신규 {payload['new_count']}건) → {LATEST}")
    return payload


BRIEF = DATA / "brief.json"


def commit_seen(brief_path=None):
    """발송까지 끝난 뒤 호출 — **실제로 보낸** 항목만 '본 것'으로 기록.

    수집된 것 전부를 기록하면, 건수 제한(max_items_per_message)에 밀려
    이번에 못 보낸 항목이 '이미 본 것'이 되어 영영 발송되지 않습니다.
    """
    brief = read_json(brief_path or BRIEF, default=None)
    if brief is None:
        die(f"브리핑 파일이 없습니다: {brief_path or BRIEF}. "
            "build_brief.py 를 먼저 실행하세요.")

    sent = {it["key"] for it in brief.get("items", []) if it.get("key")}
    if not sent:
        print("기록할 발송 항목이 없습니다 — seen.json 을 그대로 둡니다.")
        return

    seen = set(read_json(SEEN, default=[]) or [])
    before = len(seen)
    seen |= sent
    write_json(SEEN, sorted(seen))
    print(f"✅ seen.json 갱신 (발송 {len(sent)}건 추가, {before} → {len(seen)}건)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--commit-seen", action="store_true",
                    help="발송 완료 후 중복방지 기록 갱신 (data/brief.json 기준)")
    ap.add_argument("--brief", help="--commit-seen 이 읽을 브리핑 경로")
    a = ap.parse_args()
    if a.commit_seen:
        commit_seen(a.brief)
    else:
        main(a.verbose)
