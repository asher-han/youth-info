#!/usr/bin/env python3
"""카카오톡 '나에게 보내기' 발송.

브리핑 전체를 **메시지 1건**으로 보냅니다. 정책마다 "번호. 제목 (기관 · 기간)" 한 줄과
URL 한 줄. 기본 템플릿의 버튼 링크는 앱 플랫폼에 등록된 도메인만 열리기 때문에,
정책별 링크는 버튼이 아니라 본문에 직접 넣어 카톡이 자동 링크 처리하게 합니다.
문서상 텍스트 템플릿 권장 길이는 200자지만 API 는 그 이상도 받습니다(실측 900자+).

  python3 scripts/kakao_send.py --brief data/brief.json
  python3 scripts/kakao_send.py --text "테스트입니다"
  python3 scripts/kakao_send.py --brief data/brief.json --dry-run
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import http, read_json, die  # noqa: E402
from kakao_token import access_token  # noqa: E402

SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
# 안전 상한. 카카오가 문서화한 200자는 강제되지 않지만 무제한도 아닐 테니 여유 있게 둔다.
TEXT_LIMIT = 4000
FALLBACK_LINK = "https://www.youthcenter.go.kr/youthPolicy/ythPlcyTotalSearch"


def clip(text: str, limit: int = TEXT_LIMIT) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def with_scheme(url: str) -> str:
    """'www.example.com' 처럼 스킴이 없으면 https:// 를 붙인다. 카톡 자동 링크 조건."""
    url = (url or "").strip()
    if not url or url.startswith(("http://", "https://")):
        return url
    return "https://" + url


def format_brief(brief: dict) -> str:
    """브리핑 → 카톡 본문 1건. 헤더 첫 줄 + 빈 줄 + 정책마다 2줄(한 줄 설명, URL)."""
    items = brief.get("items") or []
    header = (brief.get("header") or f"📮 이번 주 청년정책 {len(items)}건").split("\n")[0]
    lines = [header, ""]
    for i, it in enumerate(items, 1):
        meta = " · ".join(x for x in [it.get("agency"), it.get("period")] if x)
        lines.append(f"{i}. {it['title']}" + (f" ({meta})" if meta else ""))
        url = with_scheme(it.get("url"))
        if url:
            lines.append(url)
    return "\n".join(lines)


def send_text(text: str, link_url: str | None = None,
              button_title: str | None = None, dry_run: bool = False) -> None:
    template = {
        "object_type": "text",
        "text": clip(text),
        "link": {"web_url": link_url or FALLBACK_LINK,
                 "mobile_web_url": link_url or FALLBACK_LINK},
    }
    if button_title:
        template["button_title"] = button_title[:14]

    if dry_run:
        print("-" * 46)
        print(template["text"])
        print("-" * 46)
        print(f"({len(template['text'])}자)")
        return

    status, body = http(
        SEND_URL,
        data={"template_object": json.dumps(template, ensure_ascii=False)},
        headers={"Authorization": f"Bearer {access_token()}"},
    )
    if status != 200:
        die(f"발송 실패 (HTTP {status}): {body[:300]}")
    result = json.loads(body or "{}")
    if result.get("result_code") != 0:
        die(f"발송 실패: {body[:300]}")


def send_brief(brief: dict, dry_run: bool = False) -> int:
    """브리핑을 메시지 1건으로 발송. 반환값은 발송 건수(항상 1)."""
    items = brief.get("items") or []
    if not items:
        send_text(brief.get("empty_message")
                  or "이번 주는 조건에 맞는 새 청년정책 공고가 없었습니다. 다음 주에 다시 확인할게요.",
                  dry_run=dry_run)
        return 1
    send_text(format_brief(brief), dry_run=dry_run)
    return 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--brief", help="브리핑 JSON 경로")
    ap.add_argument("--text", help="단일 텍스트 메시지")
    ap.add_argument("--link", help="--text 와 함께 쓸 링크")
    ap.add_argument("--dry-run", action="store_true", help="발송하지 않고 출력만")
    a = ap.parse_args()

    if a.text:
        send_text(a.text, link_url=a.link, dry_run=a.dry_run)
        print("✅ 1건 " + ("출력" if a.dry_run else "발송"))
    elif a.brief:
        brief = read_json(a.brief)
        if brief is None:
            die(f"브리핑 파일을 읽을 수 없습니다: {a.brief}")
        n = send_brief(brief, dry_run=a.dry_run)
        print(f"✅ {n}건 " + ("출력" if a.dry_run else "발송"))
    else:
        ap.error("--brief 또는 --text 중 하나가 필요합니다")
