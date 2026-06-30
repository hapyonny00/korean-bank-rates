"""
한국 은행 예·적금 금리 대시보드 (Streamlit)
디자인: 금리표_latest.html 과 동일 (Microsoft Fluent 2 + Pretendard)
데이터: 금융감독원 금융상품통합비교공시 오픈API (매일 갱신)
실행:  streamlit run app.py   (FSS_API_KEY 환경변수 또는 사이드바 입력)
"""
import importlib.util
import os
import re
from collections import Counter
from html import escape
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

# ── 기존 스킬의 조회 로직 / 폰트 임베드 재사용 ─────────────────────────────
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts" / "fetch_rates.py"
spec = importlib.util.spec_from_file_location("fetch_rates", SCRIPTS)
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)

BANKS_ORDER = ["국민은행", "우리은행", "농협은행", "하나은행",
               "카카오뱅크", "기업은행", "수협은행"]

# 우대조건 키워드 분석용 (의미있는 조건 키워드 → 표기명)
KEYWORDS = {
    "급여이체": ["급여이체", "급여 이체", "급여"],
    "자동이체": ["자동이체", "자동 이체"],
    "카드실적": ["카드", "신용카드", "체크카드"],
    "첫거래/신규": ["첫거래", "첫 거래", "신규", "처음"],
    "비대면": ["비대면", "인터넷", "모바일", "스마트"],
    "마케팅동의": ["마케팅", "광고성", "동의"],
    "재예치/만기": ["재예치", "만기", "자동재예치"],
    "오픈뱅킹": ["오픈뱅킹"],
    "공과금/관리비": ["공과금", "관리비", "지로"],
    "청년/연령": ["청년", "만 19", "만 34", "만 35", "1934", "미성년", "어린이"],
    "추천/친구": ["추천", "친구"],
    "주택청약": ["청약", "주택청약"],
    "예금/적금 동시": ["예금", "적금"],
}

st.set_page_config(page_title="은행 예·적금 금리 대시보드",
                   page_icon="🏦", layout="wide")


# ── Fluent 2 + Pretendard 디자인 주입 (리포트와 동일 톤) ───────────────────
def inject_design():
    fontcss = fr._font_face_css() or ""   # 로컬 Pretendard base64 @font-face
    st.markdown(fontcss + """
<style>
 :root{
  --neutralFg1:#242424; --neutralFg2:#424242; --neutralFg3:#616161;
  --neutralBg2:#fafafa; --neutralBg3:#f5f5f5;
  --neutralStroke1:#d1d1d1; --neutralStroke2:#e0e0e0; --brandFg:#0f6cbd;
  --radiusMd:4px; --radiusLg:6px; --radiusXl:8px; --radiusPill:999px;
  --shadow2:0 1px 2px rgba(0,0,0,.14),0 0 2px rgba(0,0,0,.12);
 }
 html,body,[class*="st-"],.stApp,button,input,textarea,[data-testid]{
  font-family:'Pretendard','Apple SD Gothic Neo','Segoe UI',sans-serif !important;}
 .stApp{background:#fff;color:var(--neutralFg1)}
 .block-container{padding-top:2.2rem;max-width:1200px}
 h1.app-title{display:flex;align-items:center;gap:10px;font-size:28px;
  font-weight:700;margin:0 0 2px;line-height:1.25;color:var(--neutralFg1)}
 h1.app-title svg{width:30px;height:30px;color:var(--brandFg)}
 .app-meta{color:var(--neutralFg3);font-size:13px;margin:0 0 6px}

 /* st.pills 를 리포트 칩처럼 */
 [data-testid="stPills"] button{border-radius:var(--radiusPill) !important;
  border:1px solid var(--neutralStroke2) !important;font-weight:600 !important}
 [data-testid="stPills"] button[aria-checked="true"],
 [data-testid="stPills"] button[kind="pillsActive"]{
  background:var(--brandFg) !important;border-color:var(--brandFg) !important;
  color:#fff !important}

 /* 리포트와 동일한 피벗표 */
 .wrap{overflow-x:auto;border:1px solid var(--neutralStroke2);
  border-radius:var(--radiusXl);box-shadow:var(--shadow2)}
 table.rate{border-collapse:separate;border-spacing:0;width:100%;font-size:15px}
 table.rate th,table.rate td{padding:11px 14px;text-align:left;
  border-bottom:1px solid var(--neutralStroke2);vertical-align:top}
 table.rate thead th{background:var(--neutralBg3);color:var(--neutralFg2);
  font-weight:600;font-size:14px;border-bottom:1px solid var(--neutralStroke1)}
 table.rate .num{text-align:center;white-space:nowrap}
 table.rate .num .b{display:block;font-size:18px;color:var(--neutralFg1)}
 table.rate .num .m{display:block;font-size:13px;color:var(--neutralFg3);margin-top:2px}
 table.rate .num.cempty{color:var(--neutralStroke1)}
 table.rate .bank{font-weight:600;white-space:nowrap;color:var(--neutralFg1)}
 table.rate .prod{color:var(--neutralFg2);min-width:180px}
 table.rate .spcl{color:var(--neutralFg3);font-size:13px;line-height:1.5;
  min-width:240px;max-width:420px;white-space:normal}
 table.rate .tag{font-size:12px;color:var(--neutralFg2);background:var(--neutralBg3);
  border:1px solid var(--neutralStroke2);border-radius:var(--radiusMd);
  padding:1px 6px;margin-left:6px}
 table.rate tr.rowsep td{border-top:1px solid var(--neutralStroke1)}
 table.rate tbody tr:hover td{background:var(--neutralBg2)}
</style>""", unsafe_allow_html=True)


BANK_SVG = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M3 9.5 12 4l9 5.5"/>'
            '<path d="M5 10v8M9.5 10v8M14.5 10v8M19 10v8"/>'
            '<path d="M3.5 21h17"/></svg>')


@st.cache_data(ttl=60 * 60 * 6, show_spinner="금리 조회 중…")
def load(product_key: str, auth: str) -> pd.DataFrame:
    service = fr.PRODUCTS[product_key][0]
    rows = fr.collect(service, auth, fr.DEFAULT_BANKS, None)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["base_rate"] = pd.to_numeric(df["base_rate"], errors="coerce")
    df["max_rate"] = pd.to_numeric(df["max_rate"], errors="coerce")
    df["term_months"] = pd.to_numeric(df["term_months"], errors="coerce")
    return df


def pivot_html(df: pd.DataFrame, show_bank: bool) -> str:
    """리포트(금리표_latest.html)와 동일한 마크업의 피벗표 HTML."""
    d = df.dropna(subset=["term_months"]).copy()
    d["term_months"] = d["term_months"].astype(int)
    terms = sorted(d["term_months"].unique())

    groups = {}
    for _, r in d.iterrows():
        key = (r["bank"], r["product"], r["reserve_type"] or "")
        g = groups.setdefault(key, {"cells": {}, "spcl": ""})
        t = r["term_months"]
        base, mx = r["base_rate"], r["max_rate"]
        prev = g["cells"].get(t)
        if not prev or (mx or 0) > (prev[1] or 0):
            g["cells"][t] = (base, mx)
        sp = (r["special"] or "").strip()
        if len(sp) > len(g["spcl"]):
            g["spcl"] = sp

    def best(item):
        return max((c[1] or 0) for c in item[1]["cells"].values())
    ordered = sorted(groups.items(), key=best, reverse=True)

    def fmt(v):
        return "-" if v is None or pd.isna(v) else f"{v:g}"

    ths = "".join(f'<th class="num">{t}개월</th>' for t in terms)
    bank_th = "<th>은행</th>" if show_bank else ""
    trs, prev_bank = [], None
    for (bank, prod, rsv), g in ordered:
        sep = " rowsep" if show_bank and prev_bank and bank != prev_bank else ""
        prev_bank = bank
        tag = f' <span class="tag">{escape(rsv)}</span>' if rsv else ""
        cells = []
        for t in terms:
            c = g["cells"].get(t)
            if not c:
                cells.append(f'<td class="num cempty">·</td>')
                continue
            base, mx = c
            cells.append(f'<td class="num"><span class="b">{fmt(base)}</span>'
                         f'<span class="m">최고 {fmt(mx)}</span></td>')
        bank_td = f'<td class="bank">{escape(bank)}</td>' if show_bank else ""
        trs.append(f'<tr class="{sep.strip()}">{bank_td}'
                   f'<td class="prod">{escape(prod)}{tag}</td>{"".join(cells)}'
                   f'<td class="spcl">{escape(g["spcl"] or "-")}</td></tr>')
    return (f'<div class="wrap"><table class="rate"><thead><tr>{bank_th}'
            f'<th>상품명</th>{ths}<th>우대조건</th></tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table></div>')


def keyword_counts(specials) -> pd.DataFrame:
    rows = []
    texts = [s or "" for s in specials]
    for label, kws in KEYWORDS.items():
        n = sum(1 for t in texts if any(k in t for k in kws))
        if n:
            rows.append({"키워드": label, "상품수": n})
    return pd.DataFrame(rows).sort_values("상품수", ascending=False)


# ════════════════════════════ UI ════════════════════════════
inject_design()

st.markdown(f'<h1 class="app-title">{BANK_SVG} 한국 은행 예·적금 금리 대시보드</h1>',
            unsafe_allow_html=True)

auth = os.environ.get("FSS_API_KEY", "")
with st.sidebar:
    st.header("⚙️ 설정")
    if not auth:
        auth = st.text_input("FSS 인증키", type="password",
                             help="finlife.fss.or.kr 무료 발급")
    if st.button("🔄 새로고침 (캐시 초기화)", width="stretch"):
        st.cache_data.clear()
        st.rerun()

if not auth:
    st.info("왼쪽 사이드바에 **FSS 인증키**를 입력하면 데이터가 표시됩니다. "
            "무료 발급: https://finlife.fss.or.kr/finlife/api/apiList.do")
    st.stop()

# 칩(컨트롤) — 리포트와 동일하게 예금/적금 + 은행 다중선택
product_label = st.pills("상품", ["정기예금", "적금"], default="정기예금",
                         selection_mode="single") or "정기예금"
product_key = "deposit" if product_label == "정기예금" else "saving"
banks = st.pills("은행 (다중 선택 · 비우면 전체)", BANKS_ORDER,
                 selection_mode="multi", default=[])

df = load(product_key, auth)
if df.empty:
    st.warning("조회된 상품이 없습니다.")
    st.stop()
if banks:
    df = df[df["bank"].isin(banks)]

dcls = df["dcls_month"].dropna().iloc[0] if not df["dcls_month"].dropna().empty else "-"
st.markdown(f'<p class="app-meta">공시기준 {dcls} · 출처: 금융감독원 금융상품통합비교공시 '
            f'· 금리는 매일 갱신 · 큰 숫자=기본금리, 작은 숫자=최고우대</p>',
            unsafe_allow_html=True)

# KPI
c1, c2, c3 = st.columns(3)
top = df.loc[df["max_rate"].idxmax()]
c1.metric("최고 우대금리", f"{top['max_rate']:.2f}%", f"{top['bank']} · {top['product']}")
c2.metric("평균 최고우대금리", f"{df['max_rate'].mean():.2f}%")
c3.metric("상품 수", f"{df['product'].nunique()}개", f"옵션 {len(df)}건")

tabs = st.tabs(["📊 기간별 비교표", "🏦 은행별 비교",
                "🔑 우대조건 키워드 분석", "📋 전체 데이터"])

# 1) 기간별 비교표 (리포트와 동일 디자인)
with tabs[0]:
    show_bank = len(banks) != 1
    st.html(pivot_html(df, show_bank))

# 2) 은행별 비교
with tabs[1]:
    grp = (df.groupby("bank")
             .agg(최고우대=("max_rate", "max"), 평균최고=("max_rate", "mean"),
                  기본평균=("base_rate", "mean"))
             .reindex([b for b in BANKS_ORDER if b in df["bank"].unique()])
             .reset_index().rename(columns={"bank": "은행"}))
    base = alt.Chart(grp).encode(
        x=alt.X("은행:N", sort=list(grp["은행"]), title=None))
    bar = base.mark_bar(color="#0f6cbd", cornerRadiusTopLeft=3,
                        cornerRadiusTopRight=3).encode(
        y=alt.Y("최고우대:Q", title="최고우대금리(%)"),
        tooltip=["은행", alt.Tooltip("최고우대:Q", format=".2f"),
                 alt.Tooltip("평균최고:Q", format=".2f")])
    txt = base.mark_text(dy=-6, color="#242424", fontWeight="bold").encode(
        y="최고우대:Q", text=alt.Text("최고우대:Q", format=".2f"))
    st.altair_chart((bar + txt).properties(height=340)
                    .configure(font="Pretendard"), use_container_width=True)
    st.caption("은행별 최고 우대금리. (선택한 상품 기준)")

    # 은행 × 기간 히트맵
    hd = df.dropna(subset=["term_months"]).copy()
    hd["기간"] = hd["term_months"].astype(int).astype(str) + "개월"
    heat = (alt.Chart(hd).mark_rect().encode(
        x=alt.X("기간:O", sort=[f"{t}개월" for t in
                sorted(hd["term_months"].astype(int).unique())], title="기간"),
        y=alt.Y("bank:N", sort=list(grp["은행"]), title="은행"),
        color=alt.Color("max(max_rate):Q", scale=alt.Scale(scheme="blues"),
                        title="최고금리(%)"),
        tooltip=["bank", "기간", alt.Tooltip("max(max_rate):Q", format=".2f")])
        .properties(height=300).configure(font="Pretendard"))
    st.altair_chart(heat, use_container_width=True)
    st.caption("은행 × 기간별 최고금리 히트맵.")

# 3) 우대조건 키워드 분석
with tabs[2]:
    kc = keyword_counts(df["special"].tolist())
    if kc.empty:
        st.info("우대조건 데이터가 없습니다.")
    else:
        chart = (alt.Chart(kc).mark_bar(color="#0f6cbd",
                 cornerRadiusEnd=3).encode(
            x=alt.X("상품수:Q", title="해당 조건 상품 수"),
            y=alt.Y("키워드:N", sort="-x", title=None),
            tooltip=["키워드", "상품수"]).properties(height=380)
            .configure(font="Pretendard"))
        st.altair_chart(chart, use_container_width=True)
        st.caption("우대조건 문구에 자주 등장하는 조건 키워드 빈도. "
                   "최고금리를 받으려면 충족해야 하는 조건을 한눈에 파악하세요.")
        # 원문 토큰 상위 (참고)
        tokens = []
        for s in df["special"].dropna():
            tokens += [w for w in re.split(r"[^가-힣A-Za-z0-9]+", s)
                       if len(w) >= 2]
        stop = {"이상", "경우", "우대", "금리", "가입", "고객", "조건", "은행",
                "상품", "해당", "또는", "사용", "이용", "신규", "예금", "적금"}
        common = [(w, n) for w, n in Counter(tokens).most_common(40)
                  if w not in stop][:15]
        if common:
            with st.expander("원문 단어 빈도 TOP 15 (참고)"):
                st.dataframe(pd.DataFrame(common, columns=["단어", "빈도"]),
                             width="stretch", hide_index=True)

# 4) 전체 데이터
with tabs[3]:
    show = df[["bank", "product", "reserve_type", "term_months",
               "base_rate", "max_rate", "special"]].copy()
    show.columns = ["은행", "상품명", "적립유형", "기간(개월)",
                    "기본금리", "최고우대", "우대조건"]
    show = show.sort_values("최고우대", ascending=False)
    st.dataframe(show, width="stretch", hide_index=True)
    st.download_button("⬇️ CSV 다운로드",
                       show.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"금리_{product_label}_{dcls}.csv",
                       mime="text/csv")
