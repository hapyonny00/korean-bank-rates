"""
한국 은행 예·적금 금리 대시보드 (Streamlit)
데이터: 금융감독원 금융상품통합비교공시 오픈API (매일 갱신)
실행:  streamlit run app.py   (FSS_API_KEY 환경변수 또는 사이드바 입력)
"""
import importlib.util
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# ── 기존 스킬의 조회 로직 재사용 (../scripts/fetch_rates.py) ──────────────
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts" / "fetch_rates.py"
spec = importlib.util.spec_from_file_location("fetch_rates", SCRIPTS)
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)

BANKS_ORDER = ["국민은행", "우리은행", "농협은행", "하나은행",
               "카카오뱅크", "기업은행", "수협은행"]

st.set_page_config(page_title="은행 예·적금 금리 대시보드",
                   page_icon="🏦", layout="wide")


@st.cache_data(ttl=60 * 60 * 6, show_spinner="금리 조회 중…")
def load(product_key: str, auth: str) -> pd.DataFrame:
    """product_key: 'deposit' | 'saving'. 7개 은행 전체 조회."""
    service = fr.PRODUCTS[product_key][0]
    rows = fr.collect(service, auth, fr.DEFAULT_BANKS, None)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["base_rate"] = pd.to_numeric(df["base_rate"], errors="coerce")
    df["max_rate"] = pd.to_numeric(df["max_rate"], errors="coerce")
    df["term_months"] = pd.to_numeric(df["term_months"], errors="coerce")
    return df


# ── 사이드바 ──────────────────────────────────────────────────────────────
st.sidebar.header("⚙️ 설정")
auth = os.environ.get("FSS_API_KEY", "")
if not auth:
    auth = st.sidebar.text_input("FSS 인증키", type="password",
                                 help="finlife.fss.or.kr 에서 무료 발급")
product_label = st.sidebar.radio("상품", ["정기예금", "적금"], horizontal=True)
product_key = "deposit" if product_label == "정기예금" else "saving"

banks = st.sidebar.multiselect("은행 (다중 선택, 비우면 전체)",
                               BANKS_ORDER, default=[])
if st.sidebar.button("🔄 새로고침 (캐시 초기화)"):
    st.cache_data.clear()
    st.rerun()

# ── 본문 ──────────────────────────────────────────────────────────────────
st.title("🏦 한국 은행 예·적금 금리 대시보드")

if not auth:
    st.info("왼쪽 사이드바에 **FSS 인증키**를 입력하면 데이터가 표시됩니다. "
            "무료 발급: https://finlife.fss.or.kr/finlife/api/apiList.do")
    st.stop()

df = load(product_key, auth)
if df.empty:
    st.warning("조회된 상품이 없습니다.")
    st.stop()

if banks:
    df = df[df["bank"].isin(banks)]

dcls = df["dcls_month"].dropna().iloc[0] if not df["dcls_month"].dropna().empty else "-"
st.caption(f"공시기준 {dcls} · 출처: 금융감독원 금융상품통합비교공시 · 금리는 매일 갱신")

# KPI
c1, c2, c3 = st.columns(3)
top = df.loc[df["max_rate"].idxmax()]
c1.metric("최고 우대금리", f"{top['max_rate']:.2f}%",
          f"{top['bank']} · {top['product']}")
c2.metric("평균 최고우대금리", f"{df['max_rate'].mean():.2f}%")
c3.metric("상품 수", f"{df['product'].nunique()}개",
          f"옵션 {len(df)}건")

tab1, tab2, tab3 = st.tabs(["📊 기간별 비교표", "📈 차트", "📋 전체 데이터"])

with tab1:
    term_opts = sorted(int(t) for t in df["term_months"].dropna().unique())
    pivot = df.pivot_table(index=["bank", "product", "reserve_type"],
                           columns="term_months", values="max_rate",
                           aggfunc="max")
    pivot = pivot.sort_values(by=pivot.columns.tolist(),
                              ascending=False, na_position="last")
    pivot.columns = [f"{int(c)}개월" for c in pivot.columns]
    pivot.index.names = ["은행", "상품명", "적립유형"]
    st.dataframe(pivot.style.format("{:.2f}%", na_rep="·")
                 .background_gradient(cmap="Greens", axis=None),
                 use_container_width=True)
    st.caption("값 = 최고우대금리(%). 색이 진할수록 고금리.")

with tab2:
    term_pick = st.selectbox("기간 선택", term_opts,
                             index=term_opts.index(12) if 12 in term_opts else 0)
    sub = (df[df["term_months"] == term_pick]
           .sort_values("max_rate", ascending=False))
    if sub.empty:
        st.info("해당 기간 상품이 없습니다.")
    else:
        chart_df = sub.set_index("product")[["base_rate", "max_rate"]]
        chart_df.columns = ["기본금리", "최고우대금리"]
        st.bar_chart(chart_df, height=420)
        st.caption(f"{term_pick}개월 기준 · 상품별 기본/최고우대 금리")

with tab3:
    show = df[["bank", "product", "reserve_type", "term_months",
               "base_rate", "max_rate", "special"]].copy()
    show.columns = ["은행", "상품명", "적립유형", "기간(개월)",
                    "기본금리", "최고우대", "우대조건"]
    show = show.sort_values("최고우대", ascending=False)
    st.dataframe(show, use_container_width=True, hide_index=True)
    st.download_button("⬇️ CSV 다운로드",
                       show.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"금리_{product_label}_{dcls}.csv",
                       mime="text/csv")
