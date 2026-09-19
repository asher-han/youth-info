# 청년정책 카톡 브리핑

> ### 📝 먼저 읽어 보세요 — 따라 하기 쉬운 블로그 글
> **[\[GitHub Actions\] 청년정책 공고, 카톡으로 자동 안내받기](https://velog.io/@berry_good/GitHub-Actions-%EC%B2%AD%EB%85%84%EC%A0%95%EC%B1%85-%EA%B3%B5%EA%B3%A0-%EC%B9%B4%ED%86%A1%EC%9C%BC%EB%A1%9C-%EC%9E%90%EB%8F%99-%EB%B0%B0%EB%8B%AC%EB%B0%9B%EA%B8%B0)**
>
> 포크부터 첫 카톡 수신까지의 과정을 화면과 함께 순서대로 설명한 글입니다.
> **처음 설정한다면 이 글을 보면서 따라 하는 쪽이 훨씬 빠릅니다.**
> 아래 README 는 설정 항목을 빠짐없이 적어 둔 참고 문서에 가깝습니다.

공공 청년정책 공고를 모아 조건에 맞는 것만 골라 **카카오톡 "나에게 보내기"로**
보내 주는 파이프라인. GitHub Actions 위에서 돌기 때문에 **내 컴퓨터가 꺼져 있어도**
동작합니다.

포크해서 `.env`(로컬) 또는 저장소 Secrets/Variables(Actions)에 본인 정보만 넣으면
바로 쓸 수 있습니다. 파이썬 표준 라이브러리만 사용해 설치할 의존성이 없습니다.

## 동작 방식

```
[최초 1회 · 사람이 직접]
  카카오 로그인 → 동의
        ↓
  Authorization Code
        ↓
  Access Token + Refresh Token
        ↓
  Refresh Token 을 저장소 Secret 에 저장
        │
        ▼
[이후 자동 · GitHub Actions]
  REST API Key + Client Secret + Refresh Token
        ↓
  Access Token 갱신
        ↓
  정책 수집 → 조건 필터 → 중복 제거
        ↓
  나에게 메시지 API → 카톡 수신
```

브라우저 동의가 필요한 건 **맨 처음 한 번뿐**입니다. 이후에는 Refresh Token 으로
Access Token 을 갱신해 씁니다.

> **Refresh Token 은 조용히 바뀝니다.** 유효기간이 2개월인데, 남은 기간이 1개월
> 미만이 되면 갱신 응답에 새 값이 함께 내려오고 이전 값은 폐기됩니다. 이 워크플로는
> 새 값을 감지하면 `KAKAO_REFRESH_TOKEN` Secret 을 자동으로 덮어씁니다(아래 `GH_PAT`).
> 대신 **한 달에 한 번 이상은 워크플로가 돌아야** 체인이 끊기지 않습니다.

## 수집 소스

| 소스 | 범위 | 필요 조건 |
|---|---|---|
| 온통청년 OpenAPI | 전국 + 시도 + 시군구 | `YOUTH_API_KEY` |
| 서울시 청년정책 | 서울 전역 | `YOUTH_SIDO=서울특별시` |
| 자치구 청년정책 | 내 자치구 | `YOUTH_SIDO=서울특별시` |
| 서울 청년지원정보 | 서울 전역 | `YOUTH_SIDO=서울특별시` |
| 동작구 알려드립니다 | 동작구 | `YOUTH_LOCAL_BOARD=dongjak` |

서울이 아니면 서울 전용 소스 3종은 자동으로 꺼지고 온통청년만 남습니다.

온통청년은 `YOUTH_SIGUNGU_CODE` 로 조회해 **내 시군구에 해당하는 정책만** 받고(전국·시도
정책 포함, 타지역 한정 정책 제외), 그중 **마감·신청기간 종료·오래된 정책을 제외**하고,
군인·농업인처럼 **특정 대상 한정 정책은 내 프로필(`YOUTH_JOB` 등)과 맞을 때만** 남깁니다.
등록 기관명이 다른 시도로 시작하는 정책(지자체가 전국 코드를 잘못 넣은 경우)과, 상시인데
신청 방법이 없는 부처 내부 과제(위원회 설치·실태조사 등)도 제외합니다.
`python3 scripts/fetch.py --verbose` 가 단계별 제외 건수를 보여 줍니다.
내 지역 게시판을 붙이는 방법은 아래 "다른 지자체 게시판 추가" 참고.

## 설치

### 1. 포크 후 카카오 앱 설정

[`docs/01-kakao-setup.md`](docs/01-kakao-setup.md) 를 따라 진행합니다.
`REST API 키`, `Client Secret`, `Refresh Token` 세 개를 얻는 게 목표입니다.

`docs/02-youth-api-key.md` 의 온통청년 키는 선택입니다. 없으면 해당 소스만 건너뜁니다.

### 2. 저장소에 값 등록

**Settings → Secrets and variables → Actions**

`Secrets` 탭 (비밀값):

| 이름 | 필수 | 설명 |
|---|---|---|
| `KAKAO_REST_API_KEY` | ✅ | 앱 설정 → 플랫폼 키 |
| `KAKAO_CLIENT_SECRET` | ✅ | 같은 화면. 기본 활성화라 사실상 필수 |
| `KAKAO_REFRESH_TOKEN` | ✅ | `kakao_token.py init` 으로 발급 |
| `YOUTH_API_KEY` | | 온통청년 OpenAPI |
| `GH_PAT` | | 토큰 회전 자동 반영용. 아래 참고 |

`Variables` 탭 (비밀 아님 · 비우면 `config.json` 기본값):

| 이름 | 기본값 | 설명 |
|---|---|---|
| `YOUTH_SIDO` / `YOUTH_SIDO_CODE` | 서울특별시 / 11 | 시·도 |
| `YOUTH_SIGUNGU` / `YOUTH_SIGUNGU_CODE` | 동작구 / 11590 | 시·군·구 |
| `YOUTH_AGE_MIN` / `YOUTH_AGE_MAX` | 25 / 35 | 나이 범위 |
| `YOUTH_INTERESTS` | (전체) | 남길 분야만 콤마로. 주거 / 금융·자산 / 일자리 / 교육·문화 / 복지·건강 |
| `YOUTH_SPECIALIZATION` | none | 온통청년 특화분야. `none`=제한없음 정책만, `*`=안 봄, 또는 `군인,농업인` 처럼 내 해당 라벨 |
| `YOUTH_JOB` / `YOUTH_EDUCATION` / `YOUTH_MAJOR` / `YOUTH_MARRIAGE` | `*` | 취업상태 / 학력 / 전공 / 결혼. 예: `미취업자,재직자` · `대학 졸업` · `미혼`. 라벨 목록은 `.env.example` |
| `YOUTH_LOCAL_BOARD` | dongjak | 지자체 게시판. 해당 없으면 `none` |
| `YOUTH_LOOKBACK_DAYS` | 14 | 며칠 이내 공고까지 |
| `YOUTH_MAX_ITEMS` | 12 | 한 번에 보낼 최대 건수 |

법정동 코드는 [행정표준코드관리시스템](https://www.code.go.kr)에서 찾을 수 있습니다.

### 3. 동작 확인

**Actions → 청년정책 브리핑 → Run workflow**.
`dry_run` 을 켠 채로 먼저 돌려서 발송 없이 내용만 확인하고, 괜찮으면 끄고 다시 실행합니다.
결과는 실행 요약(Summary)에도 목록으로 남습니다.

## 발송 주기 바꾸기

`.github/workflows/brief.yml` 의 cron 을 고칩니다. **UTC 기준**입니다.

```yaml
- cron: '0 22 * * *'   # 매일 07:00 KST
- cron: '0 22 * * 0'   # 매주 월요일 07:00 KST
```

07:00 KST = 22:00 UTC(전날)입니다. 스케줄 실행은 GitHub 부하에 따라 몇 분에서
길게는 한 시간까지 밀릴 수 있습니다. 정확한 시각이 필요하면 Actions 대신
본인 서버의 cron 을 쓰세요.

## 토큰 회전 (`GH_PAT`)

`GH_PAT` 이 없으면 Refresh Token 이 회전하는 시점에 워크플로가 **일부러 실패**해서
알림을 보냅니다. 그때 수동으로 `kakao_token.py init` 을 다시 해도 되지만,
자동으로 처리하려면 fine-grained PAT 을 만들어 넣으세요.

- Settings → Developer settings → Personal access tokens → Fine-grained tokens
- Repository access: 이 저장소만
- Permissions: **Secrets → Read and write**
- 만들어진 토큰을 `GH_PAT` Secret 으로 등록

`GITHUB_TOKEN` 으로는 Secret 을 쓸 수 없어 PAT 이 따로 필요합니다.

### 토큰이 완전히 만료됐다면

Refresh Token 이 만료되면 서버 간 통신만으로는 복구할 수 없습니다.
`docs/01-kakao-setup.md` 의 6~7번(브라우저 동의 → `init`)을 다시 하고
새 Refresh Token 을 Secret 에 넣으세요. 워크플로가 한 달에 한 번 이상 돌면
이 상황은 오지 않습니다.

## 로컬에서 실행

```bash
cp .env.example .env     # 값 채우기
python3 scripts/kakao_token.py init --code <인가코드>
python3 scripts/fetch.py --verbose
python3 scripts/build_brief.py --new-only
python3 scripts/kakao_send.py --brief data/brief.json --dry-run   # 확인
python3 scripts/kakao_send.py --brief data/brief.json             # 실제 발송
python3 scripts/fetch.py --commit-seen --brief data/brief.json
```

로컬에서는 `data/kakao_token.json` 이 토큰 저장소로 쓰여 `KAKAO_REFRESH_TOKEN`
환경변수가 없어도 됩니다.

## 다른 지자체 게시판 추가

`scripts/fetch.py` 의 `BOARDS` 에 항목을 추가합니다. 대부분의 지자체 게시판은
`<table>` 목록이라 아래 형태로 붙습니다.

```python
{
    "name": "○○구 공지사항",
    "enabled": True,
    "local_board_key": "○○",          # YOUTH_LOCAL_BOARD 값과 일치시킬 것
    "list_url": "https://.../list.do?menuNo=...",
    "base": "https://...",
    "page_param": "pageIndex",
    "pages": 8,
    "scope_pattern": r'<div class="bdList">(.*?)</table>',   # 목록 구간
    "row_pattern": (                                          # 행 1건
        r'<td class="title"><a href="(?P<href>[^"]+)">(?P<title>.*?)</a></td>\s*'
        r'<td>\s*(?P<agency>[^<]*?)\s*</td>\s*'
        r'<td>\s*(?P<date>\d{4}-\d{2}-\d{2})\s*</td>'
    ),
    "use_lookback": True,     # date 그룹이 있으면 기간 지난 시점에 조기 종료
}
```

인식하는 이름 있는 그룹: `id` `href` `title` `body` `agency` `category` `region`
`period` `date`. `detail_url` 에 `{id}` 를 쓰면 상세 링크를 조립해 줍니다.

> 본문이 `<iframe>` 안에 있는 게시판(예: 동작구 고시·공고)은 iframe 의 `src`
> 주소를 `list_url` 로 직접 지정해야 합니다.

## 알아둘 점

- **스케줄 자동 비활성**: GitHub 은 저장소 활동이 60일 없으면 스케줄 워크플로를
  끕니다. 꺼지면 메일이 오고 Actions 탭에서 다시 켤 수 있습니다. 이 워크플로는
  발송할 때마다 `data/seen.json` 을 커밋해 활동을 남깁니다.
- **커밋되지 않는 것**: `.env`(및 `.env.*` 변형), `data/kakao_token.json`,
  `data/latest.json`, `data/brief.json`. `.gitignore` 에서 `data/` 전체를 막고
  `seen.json` 과 예시 파일만 되살립니다.
- **발송 형식**: 브리핑 전체를 **메시지 1건**으로 보냅니다. 정책마다
  `번호. 제목 (기관 · 기간)` 한 줄과 URL 한 줄. 카카오 기본 템플릿의 버튼 링크는
  앱 플랫폼에 등록된 도메인만 열리기 때문에 정책 링크는 본문에 직접 넣습니다
  (카톡이 자동으로 링크 처리). 문서상 200자 제한은 API 에서 강제되지 않습니다
  (12건 약 900자 실측 발송 확인).
- **신규 0건인 날**: 기본적으로 발송을 건너뜁니다. 수동 실행 시
  `send_when_empty` 로 바꿀 수 있습니다.

## 공개 저장소로 쓸 때 알아둘 것

비밀값은 전부 Secrets 와 `.env` 에 있고 저장소에는 올라가지 않습니다. 다만 **공개**
저장소라면 아래 세 가지가 그대로 노출된다는 점을 알고 시작하세요. 신경 쓰인다면
저장소를 **private 으로 두면 됩니다.** 스케줄 실행과 발송은 private 에서도 똑같이 됩니다.

| 공개되는 것 | 내용 |
|---|---|
| `config.json` 의 `resident` | 사는 시·군·구와 나이 범위. 기본값은 동작구 · 25~35세 |
| `data/seen.json` | 발송 기록. sha1 해시지만 **원본이 공개 정책 목록이라 되돌릴 수 있습니다**. 실제로 57개 중 46개가 공개 데이터만으로 복원됐습니다 |
| Actions 로그와 실행 요약 | 공개 저장소는 **누구나 볼 수 있습니다.** 발송한 정책 제목이 그대로 남습니다 |

개인 조건을 숨기고 싶으면 `config.json` 은 중립값으로 두고 실제 값은 `.env`(로컬)와
Variables(Actions)에만 넣으세요. Variables 도 공개 저장소에서는 값이 보이지 않습니다.

토큰과 키는 로그로 새지 않습니다. Secrets 는 GitHub 이 자동 마스킹하고, 회전된
refresh token 은 `::add-mask::` 로 가리며, 스크립트는 토큰 값을 출력하지 않습니다.
온통청년 키가 URL 에 실려 오류 메시지로 나가던 문제도 `common.py` 에서 가립니다.

> **포크해서 쓴다면** Actions 워크플로가 저장소 Secrets 에 쓰기 권한이 있는 `GH_PAT`
> 을 다룹니다. `uses:` 액션이 태그(`@v4`)로 고정돼 있어, 더 엄격하게 가려면 커밋 SHA
> 로 핀 고정하세요.

## 문서

- [`docs/01-kakao-setup.md`](docs/01-kakao-setup.md) — 카카오 앱 설정과 토큰 발급
- [`docs/02-youth-api-key.md`](docs/02-youth-api-key.md) — 온통청년 OpenAPI 키
