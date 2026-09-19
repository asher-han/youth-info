#!/usr/bin/env python3
"""data/latest.json → data/brief.json (카카오 발송용 브리핑)

  python3 scripts/build_brief.py             # 기본
  python3 scripts/build_brief.py --max 8     # 건수 제한
  python3 scripts/build_brief.py --new-only  # 신규만
"""
import argparse
import datetime as dt
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, load_config, read_json, write_json, die  # noqa: E402

LATEST = DATA / "latest.json"
BRIEF = DATA / "brief.json"
SUMMARY_LIMIT = 70


def week_label(today: dt.date) -> str:
    """'9월 2주차' — 그 달 1일이 속한 주를 1주차로 센다."""
    first = today.replace(day=1)
    week = (today.day + first.weekday()) // 7 + 1
    return f"{today.month}월 {week}주차"


def normalize_url(url: str) -> str:
    """'www.kaia.re.kr' 처럼 스킴 없는 링크는 카톡에서 자동 링크가 안 되므로 https:// 보정."""
    url = (url or "").strip()
    if not url or url.startswith(("http://", "https://")):
        return url
    return "https://" + url


def summarize(item: dict) -> str:
    body = (item.get("body") or "").strip()
    title = (item.get("title") or "").strip()
    if not body or body == title:
        return ""
    body = " ".join(body.split())
    if body.startswith(title):
        body = body[len(title):].strip(" -·,")
    if len(body) <= SUMMARY_LIMIT:
        return body
    return body[: SUMMARY_LIMIT - 1].rstrip() + "…"


def build(max_items: int, new_only: bool) -> dict:
    latest = read_json(LATEST)
    if latest is None:
        die(f"{LATEST} 가 없습니다. 먼저 python3 scripts/fetch.py 를 실행하세요.")

    items = latest.get("items") or []
    if new_only:
        items = [i for i in items if i.get("is_new")]
    picked = items[:max_items]

    res = latest.get("resident") or load_config()["resident"]
    today = dt.date.today()
    counts = Counter(i.get("interest", "기타") for i in picked)
    breakdown = " · ".join(f"{k} {v}" for k, v in counts.most_common())

    header = (f"📮 {week_label(today)} 청년정책 {len(picked)}건 "
              f"({res['sigungu']}·{res['age_min']}~{res['age_max']}세)")
    if breakdown:
        header += f"\n{breakdown}"

    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source_generated_at": latest.get("generated_at"),
        "header": header,
        "empty_message": (f"{res['sigungu']} {res['age_min']}~{res['age_max']}세 조건에 맞는 "
                          "새 청년정책 공고가 없습니다."),
        "items": [{
            "key": i["key"],
            "title": i["title"],
            "summary": summarize(i),
            "agency": i.get("agency") or i.get("source", ""),
            "period": i.get("period") or i.get("posted") or "",
            "url": normalize_url(i.get("url", "")),
            "interest": i.get("interest", ""),
            "is_new": bool(i.get("is_new")),
        } for i in picked],
    }


if __name__ == "__main__":
    cfg = load_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=int(cfg.get("max_items_per_message", 12)))
    ap.add_argument("--new-only", action="store_true", help="신규 항목만 담기")
    a = ap.parse_args()

    brief = build(a.max, a.new_only)
    write_json(BRIEF, brief)
    print(f"✅ 브리핑 {len(brief['items'])}건 → {BRIEF}")
