# 3단계 · 문제 해결

## 카카오 설정

**`유효하지 않은 URL` (Redirect URI 등록)**
**제품 설정 → 카카오 로그인 → Redirect URI** 에 넣을 값은
`http://localhost:3000/oauth` 입니다. 스킴(`http://`)과 경로(`/oauth`)를 모두
포함해야 하며, 스킴을 빠뜨리는 것이 가장 흔한 원인입니다.

이 칸은 **카카오 로그인 활성화를 ON 한 뒤에야** 입력이 먹습니다.

> 앱 설정 → 플랫폼의 **사이트 도메인 등록은 필요 없습니다.** "나에게 보내기"에는
> 쓰이지 않는 단계라 설정 문서에서 뺐습니다.

**`KOE004`** — 카카오 로그인 활성화가 OFF. 앱 키는 정상이니 키를 다시 만들 필요는
없고, **제품 설정 → 카카오 로그인 → 활성화 설정 ON** 만 하면 됩니다. 인가코드
요청·토큰 발급·발송 전부 이 설정이 켜져야 동작합니다.
`python3 scripts/kakao_token.py check` 로 현재 상태를 바로 진단할 수 있습니다.

**`KOE006`** — Redirect URI 불일치. 인가코드 요청 URL 의 `redirect_uri` 와
콘솔에 등록한 값이 글자 하나까지 같아야 합니다.

**`KOE010`** — Client Secret 누락/불일치. 2025년 이후 생성된 REST API 키는
클라이언트 시크릿이 기본 활성화입니다. `KAKAO_CLIENT_SECRET` 을 확인하세요.

**`KOE320`** — 인가코드가 이미 쓰였거나 만료됨. 코드는 몇 분이면 만료되고
1회용입니다. 6번부터 다시 하세요.

**scope 에 `talk_message` 가 없음** — 동의항목에서 "카카오톡 메시지 전송" 을
**이용 중 동의**로 바꾼 뒤, 인가코드부터 다시 받아야 합니다. 이미 발급된
토큰의 scope 는 나중에 늘어나지 않습니다.

**`insufficient scope` 로 발송 실패** — 위와 같은 원인입니다.

## 토큰

**`refresh_token 이 만료됐습니다`**
유효기간 2개월이 지났습니다. 서버 간 통신으로는 복구가 안 되니
`docs/01-kakao-setup.md` 6~7번을 다시 하고 `KAKAO_REFRESH_TOKEN` Secret 을
새 값으로 바꾸세요. 워크플로가 한 달에 한 번 이상 돌면 이 상황은 오지 않습니다.

**회전했는데 `GH_PAT` 이 없다는 오류**
정상 동작입니다. 알림을 주려고 일부러 실패시킵니다. README 의 "토큰 회전" 을
참고해 PAT 을 넣거나, 수동으로 새 Refresh Token 을 Secret 에 넣으세요.

## 수집

**`⚠️ YOUTH_API_KEY 미설정`** — 온통청년 소스만 건너뛰고 나머지는 정상입니다.
승인에 시간이 걸릴 수 있습니다.

**`{"errorCode":"e001","errorMsg":"invalid api key."}`** — 온통청년 키가
틀렸거나 아직 승인되지 않았습니다.

**수집 0건**
- 서울이 아닌 지역인데 지자체 게시판을 안 붙였다면 정상입니다. 온통청년 키를
  넣으면 전국 정책이 들어옵니다.
- `YOUTH_INTERESTS` 를 너무 좁혀 두지 않았는지 확인하세요.
- 온통청년이 `대상 불일치` 로 많이 빠지면 `YOUTH_JOB` 등 프로필을 넓히거나 `*` 로 끄세요.
  `⚠️ profile.job 에 없는 라벨` 경고가 뜨면 라벨 철자를 `.env.example` 과 맞추세요.
- `python3 scripts/fetch.py --verbose` 로 소스별 수집 건수를 봅니다.

**특정 게시판만 `HTTP 403` 또는 0건**
사이트가 개편되어 HTML 구조가 바뀌었을 수 있습니다. 해당 소스의
`scope_pattern` / `row_pattern` 을 다시 맞춰야 합니다 (README 의
"다른 지자체 게시판 추가" 참고).

## GitHub Actions

**스케줄이 안 돈다**
- 저장소 활동이 60일 없으면 자동으로 꺼집니다. Actions 탭에서 다시 켜세요.
- cron 은 UTC 입니다. 07:00 KST = `0 22 * * *`.
- 포크 직후에는 Actions 가 비활성 상태일 수 있습니다. Actions 탭에서 활성화하세요.
- 스케줄 실행은 부하에 따라 수 분~1시간 밀릴 수 있습니다.

**`KAKAO_REST_API_KEY / KAKAO_REFRESH_TOKEN secret 이 비어 있습니다`**
Secrets 가 아니라 Variables 에 넣었는지 확인하세요. 비밀값은 Secrets 탭입니다.

**`seen.json 커밋` 단계에서 push 실패**
워크플로 권한이 `contents: write` 인지, 저장소 Settings → Actions →
Workflow permissions 가 읽기 전용으로 잠겨 있지 않은지 확인하세요.

## 로컬 실행

**같은 정책이 계속 온다** — `data/seen.json` 이 갱신되지 않았습니다.
발송 후 `python3 scripts/fetch.py --commit-seen --brief data/brief.json` 을
실행해야 합니다.

**한 번에 12건까지만 온다** — 의도된 동작입니다. 남은 건은 다음 회차에
이어서 나갑니다. `YOUTH_MAX_ITEMS` 로 조절하세요.
