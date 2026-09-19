# 1단계 · 카카오 개발자 앱 설정 (사용자 직접 진행)

목표: `REST API 키` + `Client Secret` + `리프레시 토큰` 3개를 얻는 것.
이 3개만 있으면 이후 발송은 전부 자동입니다.

> **먼저 알아둘 것 — 앱 키는 Redirect URI 와 무관합니다.**
> REST API 키는 앱을 만드는 순간 자동 발급됩니다. 플랫폼 등록이나 Redirect URI
> 등록은 앱 키의 선행 조건이 **아닙니다**. Redirect URI 는 5번(인가코드 받기)
> 에서만 쓰입니다. 그러니 URL 등록이 막혀도 키는 이미 손에 있습니다.

---

## 1. 앱 만들기 → REST API 키 복사

1. https://developers.kakao.com 접속 → 카카오계정으로 로그인
2. 상단 **내 애플리케이션** → **애플리케이션 추가하기**
   - 앱 이름: `청년정책 브리핑`
   - 사업자명: 본인 이름 (개인 사용이므로 아무거나)
3. 생성된 앱 클릭 → **앱 설정 → 플랫폼 키**(구 "앱 키") → **REST API 키** 복사
4. `.env` 의 `KAKAO_REST_API_KEY=` 뒤에 붙여넣기

> ⚠️ REST API 키는 비밀값입니다. 캡처·공유 금지.

## 1-1. Client Secret 복사 (필수)

카카오는 이제 **REST API 키 생성 시 클라이언트 시크릿이 기본 활성화**됩니다.
활성화 상태면 토큰 발급 요청에 `client_secret` 이 반드시 들어가야 합니다.

- **앱 설정 → 플랫폼 키 → REST API 키** 항목에서 **Client Secret** 확인·복사
  (또는 **제품 설정 → 카카오 로그인 → 보안**)
- `.env` 의 `KAKAO_CLIENT_SECRET=` 뒤에 붙여넣기

---

## 2. 플랫폼 등록 — **경로 없이, 스킴 포함**

좌측 **앱 설정 → 플랫폼** → **Web 플랫폼 등록**

- 사이트 도메인: `http://localhost:3000`

`유효하지 않은 URL` 오류가 나는 경우는 대부분 아래 셋 중 하나입니다.

| 입력한 값 | 결과 | 이유 |
|---|---|---|
| `localhost:3000` | ❌ | **스킴(`http://`)이 없음** — 가장 흔한 원인 |
| `http://localhost:3000/oauth` | ❌ | 사이트 도메인 칸에는 **경로를 넣을 수 없음** |
| `http://localhost:3000/` | ❌ | 끝의 슬래시 제거 |
| `http://localhost:3000` | ✅ | 스킴 + 호스트 + 포트만 |

---

## 3. 카카오 로그인 활성화 → Redirect URI 등록

좌측 **제품 설정 → 카카오 로그인**

1. **활성화 설정**을 먼저 **ON** (ON 하기 전에는 Redirect URI 칸이 막혀 있어
   무엇을 넣어도 등록되지 않습니다)
2. **Redirect URI 등록** 클릭 → `http://localhost:3000/oauth` 입력 후 저장
   - 이 칸은 사이트 도메인과 달리 **경로를 포함해야 정상**입니다
   - 여기도 `http://` 를 반드시 붙입니다

> 서버를 띄울 필요는 없습니다. 5번에서 브라우저가 이 주소로 튕겨 나갈 때
> **주소창에 찍힌 `code=` 값만 읽어 오면** 되기 때문에, 접속 실패 페이지가
> 떠도 정상입니다.

---

## 4. 동의항목 설정

좌측 **제품 설정 → 카카오 로그인 → 동의항목**

- **카카오톡 메시지 전송 (`talk_message`)** 찾아서 **설정** 클릭
- 상태를 **이용 중 동의**로 변경 후 저장

> "나에게 보내기"는 앱 소유자 본인 계정으로만 쓰는 것이라 비즈앱 전환이나 검수 없이 바로 됩니다.

---

## 5. 인가 코드 받기

아래 주소의 `{REST_API_KEY}` 자리에 1번에서 복사한 키를 넣고, 브라우저 주소창에 붙여넣습니다.

```
https://kauth.kakao.com/oauth/authorize?client_id={REST_API_KEY}&redirect_uri=http://localhost:3000/oauth&response_type=code&scope=talk_message
```

동의 화면에서 **동의하고 계속하기**를 누르면 접속 실패 페이지로 넘어가는데, **주소창**을 보면 이렇게 되어 있습니다.

```
http://localhost:3000/oauth?code=여기가_인가코드입니다
```

`code=` 뒤의 문자열 전체를 복사합니다. **이 코드는 몇 분 안에 만료되니 바로 다음 단계로 넘어가세요.**

> `KOE006` 오류가 뜨면 3번의 Redirect URI 가 위 주소의 `redirect_uri` 와
> 글자 하나까지 같은지 확인하세요 (끝 슬래시, http/https 포함).

---

## 5-0. (선택) 설정 상태 미리 진단

```bash
python3 scripts/kakao_token.py check
```

`✅ REST API 키·Client Secret 정상` 이 나오면 5번으로 진행합니다.
`KOE004` 가 나오면 3번의 활성화 설정이 아직 OFF 입니다.

## 6. 토큰 발급

```bash
cd ~/Desktop/asher-dev/youth-info
python3 scripts/kakao_token.py init --code 붙여넣은_인가코드
python3 scripts/kakao_token.py show      # scope 에 talk_message 확인
```

성공하면 `data/kakao_token.json` 에 리프레시 토큰이 저장되고, 이후로는 자동 갱신됩니다.

> `KOE010` (client_secret 불일치/누락) 이 뜨면 1-1 의 Client Secret 이
> `.env` 에 들어갔는지 확인하세요.

---

## 체크리스트

- [ ] REST API 키를 `.env` 의 `KAKAO_REST_API_KEY` 에 넣었다
- [ ] Client Secret 을 `.env` 의 `KAKAO_CLIENT_SECRET` 에 넣었다
- [ ] 웹 플랫폼 사이트 도메인 `http://localhost:3000` 등록했다 (경로 없이)
- [ ] 카카오 로그인 ON 후 Redirect URI `http://localhost:3000/oauth` 등록했다
- [ ] `talk_message` 동의항목을 이용 중 동의로 바꿨다
- [ ] `kakao_token.py init` 이 성공했다
