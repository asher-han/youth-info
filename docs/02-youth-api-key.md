# 2단계 · 온통청년 OpenAPI 키 신청 (사용자 직접 진행)

전국·지자체 청년정책이 한곳에 모인 공식 DB라 이 파이프라인의 주 데이터 소스입니다.

1. https://www.youthcenter.go.kr 접속 → 회원가입 / 로그인
2. **마이페이지 → OPEN API** (직접 주소: https://www.youthcenter.go.kr/myPage/openapi)
3. **이용 신청** 클릭
   - 활용 목적: `개인 학습 및 개인용 청년정책 알림 서비스`
   - 활용 형태: `웹/앱 서비스` 또는 `개인 활용`
4. 승인 후 발급되는 **인증키**를 복사
5. `.env` 파일의 `YOUTH_API_KEY=` 뒤에 붙여넣기

```bash
# 확인
cd ~/Desktop/asher-dev/youth-info
python3 scripts/fetch.py --verbose
```

> 승인이 즉시 나지 않을 수 있습니다. 키가 없는 동안에도 나머지 파이프라인은 그대로 동작합니다.
