---
name: korean-bank-rates
description: 한국 은행들이 현재 판매 중인 예금(정기예금)·적금 상품의 매일 갱신되는 금리를 조회한다. 국민·우리·농협·하나·카카오뱅크·기업·수협은행 대상. "예금 금리", "적금 금리", "정기예금 이자율", "예적금 비교" 등을 물으면 사용.
---

# 한국 은행 예·적금 금리 조회 (Korean Bank Rates)

국내 은행이 **현재 판매 중인 정기예금·적금 상품의 금리**를 조회합니다.
데이터는 **금융감독원 금융상품통합비교공시 오픈API**(finlife.fss.or.kr)에서 가져오며,
금리(optionList)는 **매일 갱신**됩니다.

기본 대상 은행: **국민·우리·농협·하나·카카오뱅크·기업(중소기업)·수협은행** (7개).

## 사전 준비 (인증키)

이 API는 무료 인증키가 필요합니다(발급 즉시 사용 가능).

1. https://finlife.fss.or.kr/finlife/api/apiList.do 에서 인증키 발급
2. 환경변수로 등록 (`~/.zshrc`에 한 줄 추가하면 매번 입력 불필요):
   ```bash
   echo 'export FSS_API_KEY="발급받은_32자리_키"' >> ~/.zshrc
   ```
   또는 실행 시 `--auth KEY` 로 직접 전달.

사용자가 인증키를 모르면 위 발급 링크를 안내하세요.

## 사용법

```bash
# 7개 은행 예금+적금 전체 (최고금리 내림차순)
python3 scripts/fetch_rates.py

# 정기예금만
python3 scripts/fetch_rates.py --product deposit

# 적금만, 12개월 상품만
python3 scripts/fetch_rates.py --product saving --term 12

# 특정 은행만 (쉼표 구분)
python3 scripts/fetch_rates.py --banks 카카오뱅크,국민은행

# JSON 출력 (가공·표 작성용)
python3 scripts/fetch_rates.py --json

# 📊 HTML 리포트 생성 후 브라우저로 자동 열기
#   (은행 칩 다중선택 + 예금/적금 전환, 기간별 비교, 반응형, 오프라인 자립)
python3 scripts/fetch_rates.py --html
```

### HTML 리포트 특징
- **은행 칩(다중 선택)**: 7개 은행 칩을 여러 개 눌러 동시 비교. `전체`로 초기화.
- **예금/적금 세그먼트**: 정기예금 ↔ 적금 전환.
- **기간별 비교 피벗표**: 가로축 1·3·6·12·24·36개월. 큰 숫자=기본금리, 작은 숫자=최고우대.
- **반응형**: 좁은 화면(≤720px)에서는 상품별 카드 뷰로 전환.
- **디자인**: Microsoft Fluent 2 토큰 + Fluent 스타일 아이콘.
- **폰트**: Pretendard woff2(`assets/fonts/`)를 HTML에 base64로 임베드 →
  **인터넷 없이 오프라인에서도** 동일하게 표시(파일 1개로 완결, ~3MB).
  폰트 파일이 없으면 자동으로 CDN으로 폴백.

### 옵션
| 옵션 | 설명 |
|------|------|
| `--product deposit\|saving\|both` | 정기예금 / 적금 / 둘 다 (기본 both) |
| `--banks 국민,우리,...` | 조회 은행 한정 (기본 7개 전체) |
| `--term 12` | 저축기간(개월) 필터 |
| `--json` | JSON 출력 |
| `--html [경로]` | 정렬 가능한 HTML 표 리포트 생성 후 브라우저로 열기 |
| `--auth KEY` | 인증키 직접 전달 |

## 동작 방식 / 주의

- `topFinGrpNo=020000`(제1금융권 은행)의 모든 상품을 페이지네이션으로 받아온 뒤,
  응답의 `kor_co_nm`(회사명)을 은행명으로 부분일치 필터링합니다.
  (예: 기업은행 → `중소기업은행`, 수협 → `수협은행`, 농협 → `농협은행주식회사`)
- 출력 금리: `base_rate`(기본금리 `intr_rate`), `max_rate`(최고우대금리 `intr_rate2`).
- 적금은 `reserve_type`(자유적립식/정액적립식)이 함께 표시됩니다.
- 한 상품에 저축기간(6/12/24/36개월 등)별로 여러 행이 나올 수 있습니다.
- 공시 기준월(`dcls_month`)이 함께 표시됩니다. 금리는 영업일마다 갱신될 수 있습니다.

## 매일 자동 생성 (오전 7시)

macOS LaunchAgent로 매일 **오전 7시**에 최신 금리표를 자동 생성합니다.
- 등록 파일: `~/Library/LaunchAgents/com.hapyonny.bankrates.plist`
- 출력 파일: `~/.claude/skills/korean-bank-rates/금리표_latest.html` (매일 덮어씀)
- 로그: 같은 폴더의 `launchd.log`

관리 명령:
```bash
# 즉시 한 번 실행(테스트)
launchctl kickstart -k gui/$(id -u)/com.hapyonny.bankrates
# 자동 실행 끄기 / 다시 켜기
launchctl bootout   gui/$(id -u) ~/Library/LaunchAgents/com.hapyonny.bankrates.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.hapyonny.bankrates.plist
```
> 컴퓨터가 켜져 있어야 실행됩니다. 7시에 꺼져 있었으면 다음 부팅 후 보충 실행됩니다.

## Streamlit 대시보드 (dashboard/)

리포트(`금리표_latest.html`)와 **동일한 디자인**(Fluent 2 + Pretendard)의 인터랙티브 대시보드.

```bash
cd dashboard
./run.sh          # 수동 실행 → http://localhost:8501
```
- 컨트롤: 예금/적금 칩(st.pills), 은행 다중선택 칩
- 탭: ① 기간별 비교표(리포트와 동일 마크업) ② 은행별 비교(막대 + 은행×기간 히트맵)
  ③ 우대조건 키워드 분석(조건 키워드 빈도 + 원문 단어 TOP) ④ 전체 데이터 + CSV
- 의존성: `dashboard/requirements.txt` (venv는 `dashboard/.venv`, git 제외)

### 대시보드 매일 자동 실행 (오전 7:05 + 로그인 시)
- LaunchAgent: `~/Library/LaunchAgents/com.hapyonny.bankdashboard.plist`
- 래퍼: `dashboard/serve.sh` (기존 8501 정리 → 재기동 → 브라우저 자동 오픈)
- 로그: `dashboard/dashboard.log`
```bash
# 즉시 재시작 / 끄기·켜기
launchctl kickstart -k gui/$(id -u)/com.hapyonny.bankdashboard
launchctl bootout   gui/$(id -u) ~/Library/LaunchAgents/com.hapyonny.bankdashboard.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.hapyonny.bankdashboard.plist
```

## 결과 정리 팁

사용자에게 답할 때는 스크립트 출력 표를 그대로 보여주거나, `--json` 결과를 받아
"은행별 최고금리 TOP", "12개월 기준 비교" 같은 형태로 요약해 주세요.
