#!/usr/bin/env bash
# 은행 금리 Streamlit 대시보드 실행
# 사용: ./run.sh   (FSS_API_KEY 환경변수 권장; 없으면 앱 사이드바에서 입력)
cd "$(dirname "$0")"
exec ./.venv/bin/streamlit run app.py
