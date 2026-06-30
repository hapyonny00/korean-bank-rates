#!/usr/bin/env python3
"""
한국 은행 예금/적금 금리 조회 스크립트
데이터 소스: 금융감독원 금융상품통합비교공시 오픈API (finlife.fss.or.kr)
- depositProductsSearch : 정기예금
- savingProductsSearch  : 적금
응답의 optionList(금리)는 매일 갱신됩니다.

사용법:
  python3 fetch_rates.py [--product deposit|saving|both]
                         [--banks 국민,우리,...]
                         [--term 12] [--json] [--html [PATH]] [--auth KEY]

인증키: 환경변수 FSS_API_KEY 또는 --auth 로 전달.
발급: https://finlife.fss.or.kr/finlife/api/apiList.do  (무료, 발급 즉시 사용)
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error

BASE = "https://finlife.fss.or.kr/finlifeapi"
TOP_FIN_GRP_NO = "020000"  # 은행(제1금융권). 수협은행 포함.

# 사용자 요청 은행: 표시명 -> kor_co_nm 부분일치 키워드
DEFAULT_BANKS = {
    "국민은행": "국민은행",
    "우리은행": "우리은행",
    "농협은행": "농협",
    "하나은행": "하나은행",
    "카카오뱅크": "카카오",
    "기업은행": "기업은행",   # API상 '중소기업은행'에 부분일치
    "수협은행": "수협",
}

PRODUCTS = {
    "deposit": ("depositProductsSearch", "정기예금"),
    "saving": ("savingProductsSearch", "적금"),
}


def fetch_all(service, auth):
    """모든 페이지를 합쳐 baseList / optionList 반환."""
    base_list, option_list = [], []
    page = 1
    while True:
        url = (f"{BASE}/{service}.json?auth={auth}"
               f"&topFinGrpNo={TOP_FIN_GRP_NO}&pageNo={page}")
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            sys.exit(f"[오류] HTTP {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            sys.exit(f"[오류] 네트워크: {e.reason}")

        result = data.get("result", {})
        err = result.get("err_cd")
        if err and err != "000":
            sys.exit(f"[API 오류] {err}: {result.get('err_msg')}")

        base_list += result.get("baseList", []) or []
        option_list += result.get("optionList", []) or []

        max_page = int(result.get("max_page_no", 1) or 1)
        if page >= max_page:
            break
        page += 1
    return base_list, option_list


def collect(service, auth, bank_keywords, term):
    base_list, option_list = fetch_all(service, auth)

    # 상품코드 -> 상품 기본정보
    base_by_cd = {b["fin_prdt_cd"]: b for b in base_list}

    rows = []
    for opt in option_list:
        cd = opt.get("fin_prdt_cd")
        base = base_by_cd.get(cd, {})
        co = base.get("kor_co_nm", "")

        match = next((disp for disp, kw in bank_keywords.items() if kw in co), None)
        if not match:
            continue
        if term and str(opt.get("save_trm")) != str(term):
            continue

        rows.append({
            "bank": match,
            "company": co,
            "product": base.get("fin_prdt_nm", ""),
            "term_months": opt.get("save_trm"),
            "rate_type": opt.get("intr_rate_type_nm", ""),
            "reserve_type": opt.get("rsrv_type_nm", ""),  # 적금만 존재
            "base_rate": opt.get("intr_rate"),
            "max_rate": opt.get("intr_rate2"),
            "join_way": base.get("join_way", ""),
            "special": (base.get("spcl_cnd", "") or "").replace("\n", " ").strip(),
            "dcls_month": base.get("dcls_month", ""),
        })

    def sort_key(r):
        return (-(float(r["max_rate"]) if r["max_rate"] not in (None, "") else 0),
                r["bank"])
    rows.sort(key=sort_key)
    return rows


def print_table(label, rows):
    print(f"\n=== {label} (은행 예·적금, 공시기준 {rows[0]['dcls_month'] if rows else '-'}) ===")
    if not rows:
        print("  (조회된 상품 없음)")
        return
    hdr = f"{'은행':<8}{'기간':>4}  {'기본':>6}  {'최고':>6}  {'유형':<10}{'상품명'}"
    print(hdr)
    print("-" * 78)
    for r in rows:
        rtype = (r["reserve_type"] or r["rate_type"] or "")[:9]
        term = f"{r['term_months']}개월" if r["term_months"] else "-"
        print(f"{r['bank']:<8}{term:>6}  "
              f"{str(r['base_rate']):>5}%  {str(r['max_rate']):>5}%  "
              f"{rtype:<10}{r['product']}")


# HTML 템플릿 (raw 문자열 — JS/CSS 중괄호 그대로 사용). __DATA__ 만 치환.
HTML_TEMPLATE = r'''<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>은행 예·적금 금리</title>
__FONTCSS__
<style>
 /* ===== Microsoft Fluent 2 디자인 토큰 / 폰트: Pretendard ===== */
 :root{
  color-scheme:light;
  --neutralFg1:#242424; --neutralFg2:#424242; --neutralFg3:#616161;
  --neutralBg1:#ffffff; --neutralBg2:#fafafa; --neutralBg3:#f5f5f5;
  --neutralStroke1:#d1d1d1; --neutralStroke2:#e0e0e0;
  --brandFg:#0f6cbd; --brandFgHover:#115ea3;
  --radiusMd:4px; --radiusLg:6px; --radiusXl:8px; --radiusPill:999px;
  --shadow2:0 1px 2px rgba(0,0,0,.14),0 0 2px rgba(0,0,0,.12);
  --fontBase:'Pretendard','Pretendard Variable',-apple-system,
   'Segoe UI Variable','Apple SD Gothic Neo','Malgun Gothic',system-ui,sans-serif;
 }
 *{box-sizing:border-box}
 body{font-family:var(--fontBase);margin:0;padding:24px;
  background:var(--neutralBg1);color:var(--neutralFg1);
  font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased}
 h1{display:flex;align-items:center;gap:10px;
  font-size:28px;font-weight:700;margin:0 0 4px;line-height:1.25}
 h1 svg{width:30px;height:30px;color:var(--brandFg);flex:none}
 h2{font-size:20px;font-weight:700;margin:8px 0 10px;line-height:1.3}
 h2 small{font-weight:400;color:var(--neutralFg3);font-size:13px}
 .meta{color:var(--neutralFg3);font-size:13px;margin:0}

 /* ===== 컨트롤: 예금/적금 세그먼트 + 은행 칩 ===== */
 .controls{display:flex;flex-wrap:wrap;gap:14px;align-items:center;
  margin:18px 0 14px}
 .seg{display:inline-flex;background:var(--neutralBg3);
  border:1px solid var(--neutralStroke2);border-radius:var(--radiusMd);
  padding:3px;gap:2px}
 .seg button{display:inline-flex;align-items:center;gap:7px;border:0;
  background:transparent;color:var(--neutralFg2);font:inherit;font-size:14px;
  font-weight:600;padding:7px 16px;border-radius:var(--radiusMd);cursor:pointer}
 .seg button svg{width:18px;height:18px;flex:none}
 .seg button.on{background:var(--neutralBg1);color:var(--brandFg);
  box-shadow:var(--shadow2)}
 .chips{display:flex;flex-wrap:wrap;gap:8px}
 .chip{border:1px solid var(--neutralStroke2);background:var(--neutralBg1);
  color:var(--neutralFg2);font:inherit;font-size:14px;padding:7px 15px;
  border-radius:var(--radiusPill);cursor:pointer;transition:.12s}
 .chip:hover{background:var(--neutralBg2);border-color:var(--neutralStroke1)}
 .chip.on{background:var(--brandFg);border-color:var(--brandFg);
  color:#fff;font-weight:600}

 /* 스티키 툴바 */
 .stickybar{position:sticky;top:0;z-index:5;background:var(--neutralBg1);
  padding:12px 0 14px;border-bottom:1px solid var(--neutralStroke2)}
 .toolbar{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-bottom:12px}
 .search{flex:1 1 220px;min-width:150px;font:inherit;font-size:14px;
  padding:9px 12px;border:1px solid var(--neutralStroke1);
  border-radius:var(--radiusMd);background:var(--neutralBg1);color:var(--neutralFg1)}
 .search::placeholder{color:var(--neutralFg3)}
 .sort{font:inherit;font-size:14px;padding:9px 12px;cursor:pointer;
  border:1px solid var(--neutralStroke1);border-radius:var(--radiusMd);
  background:var(--neutralBg1);color:var(--neutralFg1)}
 .terms{margin-top:10px}
 .terms .chip{padding:5px 13px;font-size:13px}
 /* 포커스 접근성 (Fluent focus stroke) */
 :focus-visible{outline:2px solid var(--brandFg);outline-offset:2px;
  border-radius:var(--radiusMd)}
 /* BEST 배지 */
 .badge{display:inline-block;font-size:11px;font-weight:700;color:#fff;
  background:var(--brandFg);border-radius:var(--radiusPill);
  padding:1px 8px;margin-left:6px;vertical-align:middle;letter-spacing:.3px}
 /* 히어로(오늘의 베스트) */
 .hero{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:14px 0 4px}
 .hcard{border:1px solid var(--neutralStroke2);border-radius:var(--radiusXl);
  padding:16px 18px;box-shadow:var(--shadow2);
  background:linear-gradient(180deg,var(--neutralBg1),var(--neutralBg2))}
 .hcard .k{font-size:13px;color:var(--neutralFg3);font-weight:600;
  display:flex;align-items:center;gap:6px}
 .hcard .k svg{width:16px;height:16px;color:var(--brandFg);flex:none}
 .hcard .v{font-size:30px;font-weight:700;margin:6px 0 2px;line-height:1.1}
 .hcard .v small{font-size:14px;font-weight:600;color:var(--neutralFg3)}
 .hcard .d{font-size:13px;color:var(--neutralFg2);line-height:1.45}
 .hcard .d b{font-weight:600}
 @media (max-width:560px){.hero{grid-template-columns:1fr}}

 /* 툴바 3단 정리 */
 .barrow{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
 .barrow.primary{justify-content:space-between;margin-bottom:12px}
 .barrow.refine{margin-top:12px}
 .btn-primary{font:inherit;font-size:14px;font-weight:600;cursor:pointer;color:#fff;
  background:var(--brandFg);border:1px solid var(--brandFg);
  border-radius:var(--radiusMd);padding:9px 16px}
 .btn-primary:hover{background:var(--brandFgHover);border-color:var(--brandFgHover)}
 .btn-ghost{font:inherit;font-size:14px;cursor:pointer;color:var(--neutralFg2);
  background:transparent;border:1px solid var(--neutralStroke1);
  border-radius:var(--radiusMd);padding:9px 14px}
 .btn-ghost:hover{background:var(--neutralBg2)}
 /* 담기 버튼 / 예상이자 / 비대면 배지 */
 .add{font:inherit;font-size:12px;cursor:pointer;color:var(--brandFg);
  background:var(--neutralBg1);border:1px solid var(--neutralStroke1);
  border-radius:var(--radiusPill);padding:2px 10px;margin-left:8px;white-space:nowrap}
 .add.on{background:var(--brandFg);color:#fff;border-color:var(--brandFg)}
 .est{display:block;margin-top:4px;font-size:12px;color:#0a7a3c;font-weight:600}
 .est small{color:var(--neutralFg3);font-weight:400}
 .onbadge{font-size:11px;color:var(--brandFg);border:1px solid #bcd9f0;
  background:#eaf3fb;border-radius:var(--radiusPill);padding:1px 7px;margin-left:6px}
 /* 비교 트레이(하단 고정) */
 .tray{position:fixed;left:0;right:0;bottom:0;z-index:20;background:var(--neutralBg1);
  border-top:1px solid var(--neutralStroke1);box-shadow:0 -2px 8px rgba(0,0,0,.08);
  padding:10px 16px}
 .trayinner{display:flex;align-items:center;gap:10px;flex-wrap:wrap;
  max-width:1100px;margin:0 auto}
 .traycount{font-size:13px;font-weight:600;color:var(--neutralFg2);white-space:nowrap}
 .traychips{display:flex;gap:6px;flex-wrap:wrap;flex:1}
 .traychip{font:inherit;font-size:12px;cursor:pointer;color:var(--neutralFg2);
  background:var(--neutralBg3);border:1px solid var(--neutralStroke2);
  border-radius:var(--radiusPill);padding:3px 10px}
 /* 오버레이 / 시트 */
 .overlay{position:fixed;inset:0;z-index:30;background:rgba(0,0,0,.4);display:flex;
  align-items:flex-start;justify-content:center;padding:40px 16px;overflow:auto}
 .sheet{background:var(--neutralBg1);border-radius:var(--radiusXl);width:100%;
  max-width:880px;box-shadow:0 8px 28px rgba(0,0,0,.22);padding:18px 20px}
 .sheet-h{display:flex;justify-content:space-between;align-items:center;
  margin-bottom:14px;font-size:17px}
 .sheet-h small{font-weight:400;color:var(--neutralFg3);font-size:12px}
 .x{font:inherit;font-size:16px;cursor:pointer;border:0;background:transparent;
  color:var(--neutralFg3);padding:4px 8px;border-radius:var(--radiusMd)}
 .x:hover{background:var(--neutralBg2)}
 /* 비교 카드 */
 .ccards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
 .ccard{border:1px solid var(--neutralStroke2);border-radius:var(--radiusLg);padding:12px}
 .cc-h{display:flex;align-items:center;gap:6px;font-size:15px;font-weight:700}
 .cc-h .x{margin-left:auto}
 .cc-p{color:var(--neutralFg2);font-size:13px;margin:4px 0 8px;font-weight:400}
 .cc-t{width:100%;border-collapse:collapse;font-size:13px}
 .cc-t th{text-align:left;color:var(--neutralFg3);font-weight:600;padding:3px 0;width:62px}
 .cc-t td{padding:3px 0}
 .cc-t td.hi{background:#eaf6ef;border-radius:4px;padding:3px 6px}
 .cc-t .b{font-size:15px;color:var(--neutralFg1)}
 .cc-t .m{font-size:12px;color:var(--neutralFg3)}
 .cc-t .cempty{color:var(--neutralStroke1)}
 .cc-s{margin-top:8px;font-size:12px;color:var(--neutralFg3);line-height:1.45;
  border-top:1px solid var(--neutralBg3);padding-top:8px}
 /* 마법사 폼 */
 .wiz{display:grid;grid-template-columns:1fr 1fr;gap:12px}
 .wiz label{display:flex;flex-direction:column;gap:5px;font-size:13px;
  font-weight:600;color:var(--neutralFg2)}
 .wiz select,.wiz input{font:inherit;font-size:14px;font-weight:400;padding:9px 11px;
  border:1px solid var(--neutralStroke1);border-radius:var(--radiusMd);
  background:var(--neutralBg1);color:var(--neutralFg1)}
 .wiz-btns{grid-column:1/-1;display:flex;justify-content:flex-end;gap:8px;margin-top:4px}
 .wiz-note{grid-column:1/-1;font-size:12px;color:var(--neutralFg3);margin:2px 0 0}
 @media (max-width:560px){.wiz{grid-template-columns:1fr}}
 /* 하단 트레이 공간 */
 body{padding-bottom:88px}

 /* ===== 표 ===== */
 .wrap{overflow-x:auto;border:1px solid var(--neutralStroke2);
  border-radius:var(--radiusXl);box-shadow:var(--shadow2)}
 table{border-collapse:separate;border-spacing:0;width:100%;font-size:15px}
 th,td{padding:11px 14px;text-align:left;
  border-bottom:1px solid var(--neutralStroke2);vertical-align:top}
 thead th{background:var(--neutralBg3);position:sticky;top:0;z-index:2;
  color:var(--neutralFg2);font-weight:600;font-size:14px;
  border-bottom:1px solid var(--neutralStroke1)}
 .num{text-align:center;white-space:nowrap}
 /* 기본금리 크게(강조), 최고우대 작게 */
 td.num .b{display:block;font-size:18px;color:var(--neutralFg1)}
 td.num .m{display:block;font-size:13px;color:var(--neutralFg3);margin-top:2px}
 td.num.cempty{color:var(--neutralStroke1)}
 .bank{font-weight:600;white-space:nowrap;color:var(--neutralFg1)}
 .prod{color:var(--neutralFg2);min-width:180px}
 .spcl{color:var(--neutralFg3);font-size:13px;line-height:1.5;
  min-width:260px;max-width:420px;white-space:normal}
 .tag{font-size:12px;color:var(--neutralFg2);background:var(--neutralBg3);
  border:1px solid var(--neutralStroke2);border-radius:var(--radiusMd);
  padding:1px 6px;margin-left:6px;vertical-align:middle}
 tr.rowsep td{border-top:1px solid var(--neutralStroke1)}
 tbody tr:hover td{background:var(--neutralBg2)}
 .empty{color:var(--neutralFg3);padding:20px 2px}
 .legend{font-size:13px;color:var(--neutralFg3);margin-top:14px}
 .legend b{color:var(--neutralFg2);font-weight:600}

 /* ===== 반응형: 좁은 화면(모바일)에서는 상품별 카드로 ===== */
 @media (max-width:720px){
  body{padding:16px}
  h1{font-size:23px} h2{font-size:18px}
  .wrap{border:none;overflow:visible;box-shadow:none}
  table,thead,tbody,tr,td{display:block;width:auto}
  thead{display:none}
  tr{border:1px solid var(--neutralStroke2);border-radius:var(--radiusXl);
   margin:0 0 14px;padding:14px 16px;box-shadow:var(--shadow2)}
  tr.rowsep td{border-top:none}
  td{border:none;padding:4px 0;text-align:left;white-space:normal}
  td.bank{font-size:17px;font-weight:700;padding-top:0}
  td.prod{color:var(--neutralFg3);min-width:0;margin-bottom:8px;
   border-bottom:1px solid var(--neutralStroke2);padding-bottom:8px}
  td.num{display:flex;align-items:baseline;gap:8px;
   border-bottom:1px solid var(--neutralBg3);padding:7px 0}
  td.num::before{content:attr(data-label);color:var(--neutralFg3);
   font-size:14px;font-weight:600;margin-right:auto}
  td.num .b{display:inline;font-size:18px}
  td.num .m{display:inline;margin-top:0;font-size:13px}
  td.num.cempty{display:none}
  td.spcl{margin-top:10px;min-width:0;max-width:none;
   background:var(--neutralBg2);border-radius:var(--radiusLg);padding:10px 12px}
  td.spcl::before{content:'우대조건';display:block;color:var(--neutralFg3);
   font-size:12px;font-weight:600;margin-bottom:4px}
 }
</style></head><body>
<h1><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"
 stroke-linecap="round" stroke-linejoin="round"><path d="M3 9.5 12 4l9 5.5"/>
 <path d="M5 10v8M9.5 10v8M14.5 10v8M19 10v8"/><path d="M3.5 21h17"/></svg>
 한국 은행 예·적금 금리</h1>
<p class="meta" id="meta"></p>
<div id="hero" class="hero" aria-live="polite"></div>

<div class="stickybar">
 <div class="barrow primary">
  <div class="seg" id="seg" role="tablist" aria-label="상품 종류">
  <button data-p="deposit"><svg viewBox="0 0 24 24" fill="none"
   stroke="currentColor" stroke-width="1.7" stroke-linecap="round"
   stroke-linejoin="round"><rect x="2.5" y="6.5" width="19" height="11" rx="2"/>
   <circle cx="12" cy="12" r="2.4"/></svg>예금</button>
  <button data-p="saving"><svg viewBox="0 0 24 24" fill="none"
   stroke="currentColor" stroke-width="1.7" stroke-linecap="round"
   stroke-linejoin="round"><ellipse cx="12" cy="6.5" rx="6.5" ry="2.6"/>
   <path d="M5.5 6.5v5c0 1.4 2.9 2.6 6.5 2.6s6.5-1.2 6.5-2.6v-5"/>
   <path d="M5.5 11.5v5c0 1.4 2.9 2.6 6.5 2.6s6.5-1.2 6.5-2.6v-5"/></svg>적금</button>
  </div>
  <button id="wizOpen" class="btn-primary" type="button">✨ 내 조건으로 찾기</button>
 </div>
 <div class="chips" id="chips" role="group" aria-label="은행 선택"></div>
 <div class="barrow refine">
  <input id="q" class="search" type="search" placeholder="상품·은행 검색"
   aria-label="상품 검색" autocomplete="off">
  <select id="term-sel" class="sort" aria-label="기간 선택"></select>
  <select id="sort" class="sort" aria-label="정렬 기준">
   <option value="max">최고우대금리순</option>
   <option value="base">기본금리순</option>
   <option value="name">상품명순</option>
  </select>
 </div>
</div>

<div id="view"></div>

<p class="legend">큰 숫자=<b>기본금리(%)</b>, 작은 숫자=최고우대금리(%) ·
 은행 칩은 여러 개 동시 선택, 기간·정렬 드롭다운과 검색으로 좁히고,
 <b>＋담기</b>로 2~4개를 골라 <b>나란히 비교</b>하세요 ·
 <span class="badge">BEST</span>=현재 목록 중 최고우대 1위 · 빈칸(·)은 해당 기간 미판매</p>
<p class="legend">※ 표시 금리는 세전·연이율이며 우대금리는 조건 충족 시 적용됩니다.
 상품별 단리/복리·과세 조건이 다를 수 있으니 가입 전 각 은행 약관을 확인하세요.</p>

<div id="tray" class="tray" hidden></div>
<div id="overlay" class="overlay" hidden><div class="sheet" id="sheet"></div></div>

<script>
const APP = __DATA__;
const state = {product:'deposit', banks:new Set(), term:'전체', q:'', sort:'max',
  compare:[], modal:null, online:false, amount:0};
const esc = s => String(s==null?'':s).replace(/[&<>"]/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const isNum = v => /^\d+$/.test(String(v));
const bestMax = g => Math.max(0, ...Object.values(g.cells).map(c => c.mx||0));
const ICON_DEP = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="2.5" y="6.5" width="19" height="11" rx="2"/><circle cx="12" cy="12" r="2.4"/></svg>';
const ICON_SAV = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="6.5" rx="6.5" ry="2.6"/><path d="M5.5 6.5v5c0 1.4 2.9 2.6 6.5 2.6s6.5-1.2 6.5-2.6v-5"/><path d="M5.5 11.5v5c0 1.4 2.9 2.6 6.5 2.6s6.5-1.2 6.5-2.6v-5"/></svg>';

function heroBest(list){
 let best = null;
 for(const r of list){
  const mx = parseFloat(r.max_rate); if(isNaN(mx)) continue;
  if(!best || mx > best.mx) best = {mx, base:parseFloat(r.base_rate), bank:r.bank,
    product:r.product, term:r.term_months, rsv:r.reserve_type||''};
 }
 return best;
}
function renderHero(){
 const mk = (label, icon, b) => b ? `<div class="hcard"><div class="k">${icon}${label}</div>`+
   `<div class="v">${b.mx}<small>%</small></div>`+
   `<div class="d"><b>${esc(b.bank)}</b> · ${esc(b.product)} · ${b.term}개월`+
   `${b.rsv?' · '+esc(b.rsv):''} · 기본 ${isNaN(b.base)?'-':b.base}%</div></div>` : '';
 document.getElementById('hero').innerHTML =
   mk('오늘의 최고 예금', ICON_DEP, heroBest(APP.deposit)) +
   mk('오늘의 최고 적금', ICON_SAV, heroBest(APP.saving));
}

// ===== 비교 트레이 · 마법사 · 예상이자 =====
function isOnline(jw){ return /인터넷|스마트폰|모바일|비대면|폰뱅킹|온라인/.test(jw||''); }
function allGroups(product){ return pivot(APP[product]||[]).arr; }
function groupByKey(product,key){ return allGroups(product).find(g => g.key===key) || null; }
function won(n){ return n==null?'':('약 '+Number(n).toLocaleString('ko-KR')+'원'); }
function estInterest(product, base, term, amount){
 if(!base || !amount || !term) return null;
 const r = base/100;
 if(product==='deposit') return Math.round(amount*r*term/12);          // 예금 단리 세전
 return Math.round(amount*r*(term*(term+1)/2)/12);                     // 적금 단리 세전
}
function toggleCompare(key){
 const i = state.compare.indexOf(key);
 if(i>=0) state.compare.splice(i,1);
 else { if(state.compare.length>=4){ alert('최대 4개까지 비교할 수 있어요.'); return; }
   state.compare.push(key); }
 render();
}
function renderTray(){
 const el = document.getElementById('tray');
 if(!state.compare.length){ el.hidden = true; el.innerHTML=''; return; }
 el.hidden = false;
 const chips = state.compare.map(k => {
  const g = groupByKey(state.product,k); const nm = g?g.product:k;
  return `<button class="traychip" data-k="${esc(k)}" title="빼기">${esc(nm)} ✕</button>`;
 }).join('');
 el.innerHTML = `<div class="trayinner"><span class="traycount">비교함 ${state.compare.length}/4</span>`+
  `<div class="traychips">${chips}</div>`+
  `<button class="btn-primary" id="cmpOpen" type="button">나란히 비교 →</button>`+
  `<button class="btn-ghost" id="cmpClear" type="button">비우기</button></div>`;
 el.querySelectorAll('.traychip').forEach(b => b.onclick = () => toggleCompare(b.dataset.k));
 document.getElementById('cmpOpen').onclick = () => { state.modal='compare'; renderOverlay(); };
 document.getElementById('cmpClear').onclick = () => { state.compare=[]; render(); };
}
function renderOverlay(){
 const ov = document.getElementById('overlay'), sheet = document.getElementById('sheet');
 if(!state.modal){ ov.hidden = true; sheet.innerHTML=''; return; }
 ov.hidden = false;
 sheet.innerHTML = state.modal==='compare' ? compareHTML() : wizardHTML();
 ov.onclick = e => { if(e.target===ov) closeOverlay(); };
 sheet.querySelectorAll('[data-close]').forEach(b => b.onclick = closeOverlay);
 sheet.querySelectorAll('[data-rm]').forEach(b => b.onclick = () => {
  const i = state.compare.indexOf(b.dataset.rm); if(i>=0) state.compare.splice(i,1);
  if(!state.compare.length){ closeOverlay(); render(); } else { renderOverlay(); render(); }
 });
 const form = document.getElementById('wizForm');
 if(form) form.onsubmit = e => {
  e.preventDefault();
  const f = new FormData(form);
  state.product = f.get('product');
  state.term = f.get('term');
  state.online = f.get('online')==='1';
  state.amount = parseInt(f.get('amount'),10) || 0;
  state.compare = [];
  closeOverlay(); render();
  document.getElementById('view').scrollIntoView({behavior:'smooth', block:'start'});
 };
}
function closeOverlay(){ state.modal = null; renderOverlay(); }
function compareHTML(){
 const groups = state.compare.map(k => groupByKey(state.product,k)).filter(Boolean);
 if(!groups.length) return `<div class="sheet-h"><b>나란히 비교</b>`+
   `<button class="x" data-close>✕</button></div><p class="empty">담은 상품이 없습니다.</p>`;
 const terms = [...new Set(groups.flatMap(g => Object.keys(g.cells).map(Number)))].sort((a,b)=>a-b);
 const bestPer = {};
 terms.forEach(t => { let mv=-1; groups.forEach(g => { const c=g.cells[t]; if(c&&(c.mx||0)>mv) mv=c.mx||0; }); bestPer[t]=mv; });
 const cards = groups.map(g => {
  const rows = terms.map(t => {
   const c = g.cells[t];
   if(!c) return `<tr><th>${t}개월</th><td class="cempty">·</td></tr>`;
   const hi = (c.mx===bestPer[t]) ? ' class="hi"' : '';
   return `<tr><th>${t}개월</th><td${hi}><span class="b">${c.base==null?'-':c.base}</span> `+
     `<span class="m">최고 ${c.mx==null?'-':c.mx}</span></td></tr>`;
  }).join('');
  const on = isOnline(g.joinway) ? '<span class="onbadge">비대면</span>' : '';
  return `<div class="ccard"><div class="cc-h">${esc(g.bank)}${on}`+
   `<button class="x" data-rm="${esc(g.key)}" title="빼기">✕</button></div>`+
   `<div class="cc-p">${esc(g.product)}${g.rsv?` <span class="tag">${esc(g.rsv)}</span>`:''}</div>`+
   `<table class="cc-t">${rows}</table>`+
   `<div class="cc-s">${esc(g.spcl||'-')}</div></div>`;
 }).join('');
 return `<div class="sheet-h"><b>나란히 비교 <small>${groups.length}개 · 칠해진 칸=기간별 최고</small></b>`+
   `<button class="x" data-close>✕</button></div><div class="ccards">${cards}</div>`;
}
function wizardHTML(){
 const termsAvail = [...new Set((APP[state.product]||[]).filter(r=>isNum(r.term_months))
   .map(r=>+r.term_months))].sort((a,b)=>a-b);
 const topts = termsAvail.map(t => `<option value="${t}"${String(state.term)===String(t)?' selected':''}>${t}개월</option>`).join('');
 const isDep = state.product==='deposit';
 return `<div class="sheet-h"><b>✨ 내 조건으로 찾기</b><button class="x" data-close>✕</button></div>
 <form id="wizForm" class="wiz">
  <label>상품<select name="product">
   <option value="deposit"${isDep?' selected':''}>예금 (목돈 예치)</option>
   <option value="saving"${!isDep?' selected':''}>적금 (매월 납입)</option></select></label>
  <label>기간<select name="term"><option value="전체">상관없음</option>${topts}</select></label>
  <label>가입방법<select name="online">
   <option value="0"${!state.online?' selected':''}>상관없음</option>
   <option value="1"${state.online?' selected':''}>비대면(앱·인터넷)만</option></select></label>
  <label>${isDep?'예치금액(원)':'월 납입액(원)'}
   <input name="amount" type="number" min="0" step="10000" inputmode="numeric"
    placeholder="예: 1000000" value="${state.amount||''}"></label>
  <div class="wiz-btns"><button type="button" class="btn-ghost" data-close>취소</button>
   <button type="submit" class="btn-primary">추천 받기</button></div>
  <p class="wiz-note">※ 금액을 넣으면 예상이자(세전·단리 근사치)를 함께 보여줍니다.
   기간을 고르면 해당 기간 기준으로 계산합니다.</p>
 </form>`;
}

function pivot(rows){
 const terms = [...new Set(rows.filter(r => isNum(r.term_months))
   .map(r => +r.term_months))].sort((a,b) => a-b);
 const groups = new Map();
 for(const r of rows){
  if(!isNum(r.term_months)) continue;
  const key = r.bank+'¦'+r.product+'¦'+(r.reserve_type||'');
  let g = groups.get(key);
  if(!g){ g={key, bank:r.bank, product:r.product, rsv:r.reserve_type||'',
    joinway:r.join_way||'', cells:{}, spcl:''}; groups.set(key,g); }
  if(!g.joinway && r.join_way) g.joinway = r.join_way;
  const t = +r.term_months;
  const base = parseFloat(r.base_rate), mx = parseFloat(r.max_rate);
  const cell = {base:isNaN(base)?null:base, mx:isNaN(mx)?null:mx};
  const prev = g.cells[t];
  if(!prev || (cell.mx||0) > (prev.mx||0)) g.cells[t] = cell;
  const sp = (r.special||'').trim();
  if(sp.length > g.spcl.length) g.spcl = sp;
 }
 const arr = [...groups.values()].sort((a,b) => bestMax(b)-bestMax(a));
 return {terms, arr};
}

function render(){
 document.getElementById('meta').textContent =
  '공시기준 '+APP.dcls+' · 조회시각 '+APP.now+' · 출처: 금융감독원 금융상품통합비교공시';
 renderHero();

 // 세그먼트(탭)
 document.querySelectorAll('#seg button').forEach(b => {
  const on = b.dataset.p === state.product;
  b.classList.toggle('on', on);
  b.setAttribute('role','tab'); b.setAttribute('aria-selected', on);
  b.onclick = () => { state.product = b.dataset.p; state.term = '전체'; state.compare = []; render(); };
 });
 // 마법사 열기
 document.getElementById('wizOpen').onclick = () => { state.modal = 'wizard'; renderOverlay(); };
 // 정렬 / 검색
 const sortEl = document.getElementById('sort');
 sortEl.value = state.sort;
 sortEl.onchange = () => { state.sort = sortEl.value; render(); };
 const qEl = document.getElementById('q');
 if(document.activeElement !== qEl) qEl.value = state.q;
 qEl.oninput = () => { state.q = qEl.value; render(); };

 // 은행 칩 (다중 선택 — 빈 선택 = 전체)
 const chipEl = document.getElementById('chips');
 const allOn = state.banks.size === 0;
 chipEl.innerHTML =
  `<button class="chip${allOn?' on':''}" data-b="__ALL__" aria-pressed="${allOn}">전체</button>` +
  APP.banks.map(b => {
   const on = state.banks.has(b);
   return `<button class="chip${on?' on':''}" data-b="${esc(b)}" aria-pressed="${on}">${esc(b)}</button>`;
  }).join('');
 chipEl.querySelectorAll('button').forEach(btn => btn.onclick = () => {
  const b = btn.dataset.b;
  if(b === '__ALL__') state.banks.clear();
  else state.banks.has(b) ? state.banks.delete(b) : state.banks.add(b);
  render();
 });

 const productRows = APP[state.product] || [];

 // 기간 선택(드롭다운)
 const termsAvail = [...new Set(productRows.filter(r => isNum(r.term_months))
   .map(r => +r.term_months))].sort((a,b) => a-b);
 const termSel = document.getElementById('term-sel');
 termSel.innerHTML = `<option value="전체">전체 기간</option>` +
   termsAvail.map(t => `<option value="${t}">${t}개월</option>`).join('');
 termSel.value = String(state.term);
 termSel.onchange = () => { state.term = termSel.value; render(); };

 // 필터 + 피벗
 let rows = productRows;
 if(state.banks.size) rows = rows.filter(r => state.banks.has(r.bank));
 const {terms, arr} = pivot(rows);
 const focus = state.term !== '전체' ? +state.term : null;
 const dispTerms = focus ? terms.filter(t => t === focus) : terms;

 // 필터: 비대면 → 검색 → 기간 보유
 let items = arr;
 if(state.online) items = items.filter(g => isOnline(g.joinway));
 const q = state.q.trim().toLowerCase();
 if(q) items = items.filter(g => (g.product+' '+g.bank+' '+g.rsv).toLowerCase().includes(q));
 if(focus) items = items.filter(g => g.cells[focus]);

 // 정렬
 const metric = g => focus
   ? (g.cells[focus] ? (state.sort==='base'?g.cells[focus].base:g.cells[focus].mx)||0 : 0)
   : (state.sort==='base' ? Math.max(0,...Object.values(g.cells).map(c=>c.base||0)) : bestMax(g));
 items = (state.sort === 'name')
   ? items.slice().sort((a,b) => a.product.localeCompare(b.product,'ko'))
   : items.slice().sort((a,b) => metric(b) - metric(a));

 // BEST(현재 목록 최고우대 1위)
 let bestG = null, mv = -1;
 for(const g of items){
  const v = focus ? (g.cells[focus]?g.cells[focus].mx||0:0) : bestMax(g);
  if(v > mv){ mv = v; bestG = g; }
 }

 const view = document.getElementById('view');
 const pname = state.product === 'deposit' ? '정기예금' : '적금';
 const title = state.banks.size === 0 ? '전체 은행'
   : APP.banks.filter(b => state.banks.has(b)).join(', ');
 const focusLbl = focus ? ` · ${focus}개월` : '';
 const onLbl = state.online ? ' · 비대면' : '';

 if(!items.length){
  view.innerHTML = `<h2>${esc(title)} · ${pname}${focusLbl}${onLbl}</h2>`+
   `<p class="empty">해당 조건의 상품이 없습니다. 필터를 줄여보세요.</p>`;
  renderTray(); renderOverlay(); return;
 }
 const showBank = state.banks.size !== 1;
 const ths = dispTerms.map(t => `<th class="num">${t}개월</th>`).join('');
 let trs = '', prevBank = null;
 for(const g of items){
  const sep = (showBank && prevBank && g.bank !== prevBank) ? ' rowsep' : '';
  prevBank = g.bank;
  const tag = g.rsv ? ` <span class="tag">${esc(g.rsv)}</span>` : '';
  const badge = g === bestG ? ` <span class="badge">BEST</span>` : '';
  const inCmp = state.compare.includes(g.key);
  const addBtn = `<button class="add${inCmp?' on':''}" data-k="${esc(g.key)}" aria-pressed="${inCmp}">${inCmp?'담음 ✓':'＋ 담기'}</button>`;
  let estLine = '';
  if(state.amount > 0 && focus){
   const c = g.cells[focus]; const e = c ? estInterest(state.product, c.base, focus, state.amount) : null;
   if(e != null) estLine = `<span class="est">예상이자 ${won(e)} <small>(세전·기본금리)</small></span>`;
  }
  let cells = '';
  for(const t of dispTerms){
   const c = g.cells[t];
   if(!c){ cells += `<td class="num cempty" data-label="${t}개월">·</td>`; continue; }
   cells += `<td class="num" data-label="${t}개월">`+
    `<span class="b">${c.base==null?'-':c.base}</span>`+
    `<span class="m">최고 ${c.mx==null?'-':c.mx}</span></td>`;
  }
  const bankCell = showBank ? `<td class="bank" data-label="은행">${esc(g.bank)}</td>` : '';
  trs += `<tr class="${sep.trim()}">${bankCell}`+
   `<td class="prod" data-label="상품">${esc(g.product)}${tag}${badge}${addBtn}${estLine}</td>`+
   `${cells}<td class="spcl" data-label="우대조건">${esc(g.spcl||'-')}</td></tr>`;
 }
 const bankTh = showBank ? '<th>은행</th>' : '';
 view.innerHTML = `<h2>${esc(title)} · ${pname}${focusLbl}${onLbl} <small>· ${items.length}개 상품</small></h2>`+
  `<div class="wrap"><table><thead><tr>${bankTh}<th>상품명</th>${ths}`+
  `<th>우대조건</th></tr></thead><tbody>${trs}</tbody></table></div>`;
 view.querySelectorAll('.add').forEach(b => b.onclick = () => toggleCompare(b.dataset.k));
 renderTray(); renderOverlay();
}
render();
</script>
</body></html>'''


def _font_face_css():
    """로컬 Pretendard woff2 를 base64로 임베드한 @font-face <style> 반환.
    파일이 없으면 None (CDN 폴백)."""
    import base64
    fdir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "assets", "fonts")
    weights = {400: "Regular", 600: "SemiBold", 700: "Bold"}
    faces = []
    for w, name in weights.items():
        fp = os.path.join(fdir, f"Pretendard-{name}.woff2")
        if not os.path.exists(fp):
            return None
        with open(fp, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        faces.append(
            "@font-face{font-family:'Pretendard';font-style:normal;"
            f"font-weight:{w};font-display:swap;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
    return "<style>" + "".join(faces) + "</style>"


def write_html(out, path):
    """은행 칩 다중선택 + 예금/적금 전환 인터랙티브 HTML 리포트 생성.
    디자인: Microsoft Fluent 2 토큰 / 폰트: Pretendard(로컬 임베드) / 렌더링: 클라이언트 JS."""
    import datetime
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    dcls = next((r["dcls_month"] for rows in out.values() for r in rows), "-")

    banks_order = ["국민은행", "우리은행", "농협은행", "하나은행",
                   "카카오뱅크", "기업은행", "수협은행"]
    payload = {
        "deposit": out.get("정기예금", []),
        "saving": out.get("적금", []),
        "banks": banks_order,
        "dcls": dcls,
        "now": now,
    }
    # </script> 깨짐 방지
    data_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    fontcss = _font_face_css() or (
        '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/'
        'pretendard@v1.3.9/dist/web/static/pretendard.min.css">')
    html = HTML_TEMPLATE.replace("__FONTCSS__", fontcss).replace("__DATA__", data_json)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", choices=["deposit", "saving", "both"],
                    default="both", help="조회 상품 (기본: both)")
    ap.add_argument("--banks", help="쉼표구분 은행명 (기본: 7개 은행 전체)")
    ap.add_argument("--term", help="저축기간(개월) 필터, 예: 12")
    ap.add_argument("--json", action="store_true", help="JSON 출력")
    ap.add_argument("--html", nargs="?", const="auto", metavar="PATH",
                    help="HTML 리포트 생성 후 브라우저로 열기 (경로 생략 가능)")
    ap.add_argument("--auth", help="FSS 인증키 (없으면 FSS_API_KEY 환경변수)")
    args = ap.parse_args()

    auth = args.auth or os.environ.get("FSS_API_KEY")
    if not auth:
        sys.exit("[오류] 인증키가 없습니다. FSS_API_KEY 환경변수를 설정하거나 "
                 "--auth 로 전달하세요. 발급: "
                 "https://finlife.fss.or.kr/finlife/api/apiList.do")

    if args.banks:
        wanted = [b.strip() for b in args.banks.split(",") if b.strip()]
        bank_keywords = {}
        for w in wanted:
            # 사용자가 준 이름이 기본맵에 있으면 그 키워드, 없으면 입력값 자체로 부분일치
            key = next((d for d in DEFAULT_BANKS if w in d or d in w), None)
            bank_keywords[key or w] = DEFAULT_BANKS.get(key, w)
    else:
        bank_keywords = DEFAULT_BANKS

    # HTML은 칩 전환을 위해 항상 예금+적금 모두 필요
    products = (["deposit", "saving"] if (args.product == "both" or args.html)
                else [args.product])

    out = {}
    for p in products:
        service, label = PRODUCTS[p]
        rows = collect(service, auth, bank_keywords, args.term)
        out[label] = rows
        if not args.json and not args.html:
            print_table(label, rows)

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))

    if args.html:
        import datetime
        import subprocess
        path = args.html
        if path == "auto":
            path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                f"금리표_{datetime.date.today():%Y%m%d}.html")
        write_html(out, path)
        print(f"[HTML 생성] {path}")
        try:
            subprocess.run(["open", path], check=False)
        except Exception:
            pass


if __name__ == "__main__":
    main()
