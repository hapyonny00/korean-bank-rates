#!/usr/bin/env bash
# 대시보드 서버 실행 래퍼 (launchd/수동 공용)
# - 8501 포트의 기존 인스턴스를 정리한 뒤 새로 띄움
# - 잠시 후 브라우저로 자동 오픈
cd "$(dirname "$0")" || exit 1

PORT="${DASH_PORT:-8501}"
lsof -ti "tcp:${PORT}" | xargs kill 2>/dev/null
sleep 1

# 부팅되면 브라우저 열기 (백그라운드)
( for i in $(seq 1 30); do
    if curl -s -o /dev/null "http://localhost:${PORT}/_stcore/health"; then
      open "http://localhost:${PORT}"; break
    fi
    sleep 1
  done ) &

exec ./.venv/bin/streamlit run app.py \
  --server.port "${PORT}" --server.headless true
