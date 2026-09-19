# 다음 세션에서 이어서 할 일

폴더(`~/Desktop/asher-dev/youth-info`)를 연결하고
**"NEXT.md 보고 이어서 진행해줘"** 라고만 하면 됩니다.

## 현재 상태 (2026-09-18)

**실행 방식 결정: GitHub Actions (public 저장소, 포크 가능한 템플릿).**
Cowork 예약작업은 시크릿·상태·회전토큰을 보관할 곳이 없어 제외했습니다.

완료

- 수집 소스 4종 구현·실검증 (원본 80건 → 조건 일치 43건)
  - 온통청년 OpenAPI / 서울시 청년정책 / 자치구 청년정책 / 서울 청년지원정보 / 동작구 알려드립니다
- `scripts/build_brief.py` — `latest.json` → `brief.json` 결정적 변환
- **환경변수 오버라이드** — `.env` 없이 env/Variables 만으로 지역·연령·관심분야 설정
  (`load_env` 가 `.env` 에 있는 키만 읽던 버그 수정. CI 에서 치명적이었음)
- **토큰 처리 개편** — `KAKAO_REFRESH_TOKEN` env 지원, 회전 감지 시
  `KAKAO_ROTATED_TOKEN_FILE` 로 전달, `access` 서브커맨드의 토큰 stdout 노출 제거
- **`--commit-seen` 버그 수정** — 수집 43건 전부가 아니라 **실제 발송한 12건만** 기록.
  이전 동작이면 나머지 31건이 영영 발송되지 않았음
- `.github/workflows/brief.yml` — cron, 수동 dry-run, 0건 skip, seen.json 커밋,
  PAT 으로 secret 자동 갱신. YAML 파싱 + 각 단계 스크립트 실제 실행으로 검증
- `.gitignore` 강화 — `data/` 전체 차단 후 `seen.json` 만 화이트리스트
- README(포크 사용자용) / docs 01·02·03 정비

- `.env` 에 `KAKAO_REST_API_KEY`, `KAKAO_CLIENT_SECRET`, `YOUTH_API_KEY` 등록 완료
- `kakao_token.py check` 서브커맨드 추가 — 토큰 없이도 앱 키·시크릿·로그인 활성화
  상태를 카카오 토큰 엔드포인트 오류코드로 진단
- 로컬 파이썬 3.9 호환 (`from __future__ import annotations`) — macOS 기본
  `python3` 로도 README 명령이 돈다. CI 는 3.12

막혀 있음

- (없음) — 2026-09-18 19:10 로컬에서 **실제 카톡 발송 성공**: 헤더 1 + 정책 12 =
  13건, `seen.json` 에 12건 기록. `YOUTH_API_KEY` 도 실호출 성공(온통청년 600행)
- ~~온통청년 관련성 낮음~~ 필터 강화 완료 (아래 "온통청년 필터" 참고)
- ~~스킴 없는 링크~~ `build_brief.py` `normalize_url` 로 보정 완료

## 새 세션에서 할 일 (순서대로)

1. 카카오 앱 설정 상태 진단 (`✅ ... 정상` 이 나올 때까지 콘솔 설정)

   ```bash
   python3 scripts/kakao_token.py check
   ```

2. ~~인가코드 → 토큰 발급~~ 완료 (`data/kakao_token.json`, 2026-11-17 만료 전 갱신 필요)

3. ~~로컬 테스트 발송~~ 완료. 재실행은 아래 순서

   ```bash
   python3 scripts/fetch.py --verbose
   python3 scripts/build_brief.py --new-only
   python3 scripts/kakao_send.py --brief data/brief.json --dry-run
   python3 scripts/kakao_send.py --brief data/brief.json
   python3 scripts/fetch.py --commit-seen --brief data/brief.json
   ```

4. GitHub 저장소 생성 → push → Secrets/Variables 등록 → Actions 에서
   `dry_run=true` 로 수동 실행 → 확인되면 `dry_run=false`

5. ~~온통청년 응답 필드명 실호출 검증~~ 완료. `aplyBgngYmd`/`aplyEndYmd` 는 존재하지
   않았고 실제는 `aplyYmd`("20260416 ~ 20260430", 복수 구간은 `\N` 구분) — 그래서
   마감 정책이 전부 "상시"로 통과되던 것이 관련성 저하의 주원인이었음.

6. 안정화되면 cron 을 주 1회로 변경: `0 22 * * 0` (월요일 07:00 KST)

## 온통청년 필터 (2026-09-18 강화)

- 조회: `zipCd=<시군구 코드>` 한 종류만. 전국 정책은 모든 시군구를 나열하므로 함께 오고,
  타지역 한정 정책은 빠진다. 시도 코드(`11`)는 API 가 무시함(전국과 totCount 동일) → 제거
- 제외 순서: 지역 외(zipCd) → 타지역 기관(등록·주관 기관명이 다른 시도로 시작. zipCd 는
  지자체가 전국 코드를 통째로 넣는 경우가 많아 단독으로는 못 믿음) →
  `aplyPrdSeCd=0057003`(마감) → 신청구간 전부 종료 → 등록·신청시작이 `lookback_days` 밖 →
  신청 불가(상시인데 신청방법이 비었거나 "해당없음" = 부처 내부 제도과제) →
  대상 코드(특화분야/취업/학력/전공/결혼)가 프로필과 불일치
- 제목 제외어(`config.json` `exclude_keywords`)에 고도화/내실화/실태조사 등 제도과제 단어 추가
- 검증(2026-09-18, zipCd=11590 p1 100건): 통과 6 / 타지역 기관 18 / 신청 불가 16 /
  대상 불일치 5(군인 4, 기타 1) / 기간 지남 26 / 오래됨 29. 사유별 제목 육안 확인, 오탐 없음
- 알려진 트레이드오프: "신청 불가" 규칙이 신청 절차 없이 이용하는 서비스도 떨어뜨림
  (청년 재무상담 운영, STEP AI 훈련). 살리려면 `refUrlAddr1` 이 있는 상시 정책은 통과시키는
  예외를 검토 — 다만 실태조사 등도 URL 이 있어 단순 규칙으론 안 갈림
- 남는 노이즈: 대학생 한정 정책(천원의 아침밥 등)은 `YOUTH_EDUCATION` 을 설정해야 빠짐
- 코드표는 `fetch.py` `YC_CODES`. 실데이터 제목과 대조해 확인했으나 공식 명세와 재대조 권장
- 정렬: 신규 → `priority`(우리 구 0 / 시도·지자체 1 / 중앙부처 2) → 마감 임박

## 보안 검토 (2026-09-19)

- git 저장소가 아직 아님 → 과거 커밋에 비밀값이 남을 위험 없음. **첫 push 전 상태가 깨끗**
- `.env`·`kakao_token.json`·`latest.json`·`brief.json` 은 커밋 대상에서 제외됨을
  임시 저장소에 `git add -A` 로 시뮬레이션해 확인. 실제 키 5개를 커밋 대상 17개 파일과
  전문 대조 → 노출 0건
- `.gitignore` 구멍 막음: `.env.production`, `secrets.json`, `kakao_token.json`(루트)
  등이 통과되던 것을 `.env.*` / `*token*.json` / `*secret*` 으로 차단
- **`seen.json` 은 익명이 아님** — sha1(source:id) 이라 공개 정책 목록으로 재계산하면
  복원됨(57개 중 46개 실제 복원 확인). README·워크플로의 "개인정보가 없습니다" 문구 수정
- `gh secret set` 을 `--body` → stdin 으로 변경 (토큰이 프로세스 인자에 남지 않게)
- 토큰 로그 노출 경로 없음 확인 (Authorization 헤더만 사용, `show`/`check` 는 값 미출력)

미결 (사용자 판단 필요)

- `config.json` 에 실제 거주지(동작구)·나이(25~35)가 들어 있어 공개 시 그대로 노출.
  중립값으로 바꾸면 `.env`/Variables 미설정 시 수집 범위가 조용히 달라져 보류함
- `uses: actions/checkout@v4` 등 태그 핀 → SHA 핀 권장 (GH_PAT 이 Secrets 쓰기 권한)

## 결정사항 (바꾸지 말 것)

- 실행: GitHub Actions, public 저장소, 포크해서 쓰는 템플릿 지향
- 수신자: 본인 1명, 카카오톡 "나에게 보내기"
- 발송 형식: **메시지 1건**에 헤더 + 정책별 `번호. 제목 (기관 · 기간)` + URL.
  버튼 링크는 등록 도메인만 열려서 쓰지 않고 URL 을 본문에 직접 넣는다.
  (200자 제한은 API 에서 강제되지 않음 — 915자 발송 실측 2026-09-18)
- 개인 조건은 하드코딩하지 않고 env/Variables 로 (`config.json` 은 기본값일 뿐)
- 브리핑 생성은 `build_brief.py` 로 고정 (매 실행 결과가 달라지지 않도록)
- `data/` 는 `seen.json` 외 전부 커밋 금지
