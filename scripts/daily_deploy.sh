#!/usr/bin/env bash
# 매일 아침 자동 실행: 금리 재조회 → 로컬 리포트 갱신 → index.html 갱신 →
# 변경이 있으면 GitHub에 커밋·푸시(= GitHub Pages 라이브 링크 자동 갱신)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

export FSS_API_KEY="${FSS_API_KEY:-1720b09493ab7f4b2336141200bcdefa}"
DATE="$(date +%Y-%m-%d\ %H:%M:%S)"
echo "===== [$DATE] daily_deploy 시작 ====="

# 1) 로컬 최신본(브라우저 자동오픈 없이)
python3 scripts/fetch_rates.py --html 금리표_latest.html --no-open
STATUS1=$?

# 2) GitHub Pages 배포용 index.html
python3 scripts/fetch_rates.py --html index.html --no-open
STATUS2=$?

if [ $STATUS1 -ne 0 ] || [ $STATUS2 -ne 0 ]; then
  echo "[오류] 금리 조회/HTML 생성 실패 (local=$STATUS1 index=$STATUS2) — git 배포는 건너뜁니다."
  exit 1
fi

# 3) 변경사항이 있을 때만 커밋·푸시 (금리 미변동일 때 빈 커밋 방지)
if ! git diff --quiet -- index.html history.json 2>/dev/null \
   || ! git diff --cached --quiet -- index.html history.json 2>/dev/null; then
  git add index.html history.json
  git commit -m "일일 금리 자동 갱신 $(date +%Y-%m-%d)" >/dev/null
  if git push origin main >/dev/null 2>&1; then
    echo "[배포 완료] https://hapyonny00.github.io/korean-bank-rates/ 갱신됨"
  else
    echo "[경고] git push 실패 — 원격 변경사항과 충돌했을 수 있습니다. 다음 실행 때 재시도됩니다."
  fi
else
  echo "[변경 없음] 오늘 금리가 어제와 동일해 배포를 건너뜁니다."
fi

echo "===== [$DATE] daily_deploy 종료 ====="
