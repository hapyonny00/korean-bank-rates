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
            "join_deny": base.get("join_deny", ""),  # 1:제한없음 2:서민전용 3:일부제한
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
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='88'>&#127974;</text></svg>">
__FONTCSS__
<style>
 /* ===== Microsoft Fluent 2 디자인 토큰 / 폰트: Pretendard ===== */
 :root{
  color-scheme:light;
  --neutralFg1:#242424; --neutralFg2:#424242; --neutralFg3:#616161;
  --neutralBg1:#ffffff; --neutralBg2:#fafafa; --neutralBg3:#f5f5f5;
  --neutralStroke1:#d1d1d1; --neutralStroke2:#e5e7eb;
  /* 레퍼런스 팔레트: 연블루 배경 + 화이트 셸 + 블루 액센트 */
  --pageBg:#cddff8; --blue:#4285f4; --blueDeep:#3573dd;
  --blueSoft:#e6effc; --grayPill:#eef0f4; --ink:#101215;
  --brandFg:#3573dd; --brandFgHover:#2b62c4;
  --radiusMd:4px; --radiusLg:6px; --radiusXl:8px; --radiusPill:999px;
  --shadow2:0 1px 2px rgba(0,0,0,.14),0 0 2px rgba(0,0,0,.12);
  --fontBase:'Pretendard','Pretendard Variable',-apple-system,
   'Segoe UI Variable','Apple SD Gothic Neo','Malgun Gothic',system-ui,sans-serif;
 }
 *{box-sizing:border-box}
 body{font-family:var(--fontBase);margin:0;padding:34px 26px;
  background:var(--pageBg);color:var(--neutralFg1);
  font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased}
 /* ===== 화이트 셸 (레퍼런스의 큰 라운드 컨테이너) ===== */
 .widget{max-width:1200px;margin:0 auto;background:#fff;border-radius:40px;
  padding:26px 34px 22px;box-shadow:0 30px 70px rgba(60,90,140,.18)}
 /* ===== 탑바: 로고 + 중앙 필 내비 ===== */
 .whead{display:flex;align-items:center;gap:14px;padding:4px 2px 10px;
  flex-wrap:wrap}
 .brand{display:inline-flex;align-items:center;gap:9px;cursor:pointer;border:0;
  background:transparent;padding:4px 6px 4px 4px;border-radius:12px}
 .brand:hover{background:var(--grayPill)}
 .brand-ic{display:inline-flex;align-items:center;justify-content:center;
  width:30px;height:30px;border-radius:9px;background:var(--blue);color:#fff}
 .brand-ic svg{width:18px;height:18px}
 .brand-tx{font-family:'Poppins',var(--fontBase);font-weight:600;font-size:16px;
  letter-spacing:-.2px;color:var(--ink)}
 .mods{display:flex;gap:8px;margin:0 auto;overflow-x:auto;max-width:100%}
 .mods button{font:inherit;font-size:13.5px;font-weight:500;cursor:pointer;
  color:var(--neutralFg2);background:var(--grayPill);border:0;
  border-radius:var(--radiusPill);padding:9px 18px;white-space:nowrap;
  transition:background .12s}
 .mods button:hover{background:#e3e6ec}
 .mods button.on{background:var(--blue);color:#fff;font-weight:600}
 .whead .meta{text-align:right}
 /* ===== 홈 히어로 (중앙 정렬, 흰 배경 위 검은 헤드라인) ===== */
 .heroC{text-align:center;padding:56px 16px 22px;max-width:760px;margin:0 auto}
 .pillbadge{display:inline-flex;align-items:center;gap:7px;font-size:13px;
  font-weight:600;color:var(--blueDeep);background:var(--blueSoft);
  border-radius:var(--radiusPill);padding:7px 15px;margin-bottom:26px}
 .pillbadge svg{width:15px;height:15px}
 .heroC h1{font-size:clamp(38px,6vw,66px);font-weight:600;margin:0 0 18px;
  line-height:1.12;letter-spacing:-1.6px;color:var(--ink)}
 .herosub{margin:0 auto 26px;color:var(--neutralFg3);font-size:14.5px;
  max-width:400px}
 /* Get Started 자리의 LLM 입력창 */
 .askbar{display:flex;align-items:center;gap:8px;background:#fff;
  border:1px solid var(--neutralStroke2);
  border-radius:var(--radiusPill);padding:7px 7px 7px 18px;max-width:560px;
  margin:0 auto;box-shadow:0 10px 30px rgba(66,133,244,.16)}
 .askbar>svg{width:18px;height:18px;color:var(--neutralFg3);flex:none}
 .askbar input{flex:1;min-width:0;border:0;outline:none;font:inherit;font-size:15px;
  background:transparent;color:var(--neutralFg1)}
 .askbar input::placeholder{color:var(--neutralFg3)}
 .sendbtn{display:inline-flex;align-items:center;justify-content:center;gap:7px;
  flex:none;height:42px;border-radius:var(--radiusPill);border:0;cursor:pointer;
  color:#fff;font:inherit;font-size:14px;font-weight:600;padding:0 20px;
  background:linear-gradient(180deg,#5b97f7,var(--blue));
  box-shadow:0 6px 16px rgba(66,133,244,.35)}
 .sendbtn:hover{filter:brightness(1.05)}
 .sendbtn svg{width:16px;height:16px}
 .sugg{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px;justify-content:center}
 .sugg button{font:inherit;font-size:13px;cursor:pointer;
  color:var(--neutralFg2);background:var(--grayPill);border:0;
  border-radius:var(--radiusPill);padding:6px 14px}
 .sugg button:hover{background:#e3e6ec}
 /* 채팅 로그 (하단 화이트 그라데이션으로 자연스럽게 사라짐) */
 .chatlogwrap{position:relative;margin:18px auto 0;max-width:640px;text-align:left}
 .chatlog{display:flex;flex-direction:column;gap:10px;
  max-height:360px;overflow:auto;padding:4px 2px 28px}
 .chatfade{position:absolute;left:-24px;right:-24px;bottom:0;height:52px;
  background:linear-gradient(to bottom, rgba(255,255,255,0), #fff 88%);
  pointer-events:none;border-radius:0 0 14px 14px}
 .msg{max-width:85%;padding:10px 14px;border-radius:16px;font-size:14px;
  line-height:1.55;white-space:pre-line}
 .msg.user{align-self:flex-end;background:var(--blue);color:#fff;
  border-bottom-right-radius:6px}
 .msg.bot{align-self:flex-start;background:var(--grayPill);
  color:var(--neutralFg1);border-bottom-left-radius:6px}
 .msg.bot b{color:var(--blueDeep)}
 /* 리셋 버튼: 질문하기 옆 작은 아이콘 버튼 */
 .chatclear{display:inline-flex;align-items:center;justify-content:center;flex:none;
  width:38px;height:38px;border-radius:50%;border:0;cursor:pointer;
  color:var(--neutralFg3);background:transparent}
 .chatclear:hover{background:var(--grayPill);color:var(--neutralFg1)}
 .chatclear svg{width:17px;height:17px}
 /* ===== 모듈 카드 3장 (레퍼런스 하단 카드) ===== */
 .modrow{display:grid;grid-template-columns:1fr 1.55fr 1fr;gap:20px;
  margin:34px 4px 10px;align-items:stretch}
 .mcard{font:inherit;text-align:left;cursor:pointer;border-radius:24px;
  padding:20px 22px;min-height:230px;display:flex;flex-direction:column;
  transition:transform .15s,box-shadow .15s;position:relative}
 .mcard:hover{transform:translateY(-3px);box-shadow:0 16px 34px rgba(60,90,140,.16)}
 .mcard.light{background:#fff;border:1px solid var(--neutralStroke2);
  box-shadow:0 8px 24px rgba(60,90,140,.08)}
 .mcard.bluecard{background:linear-gradient(135deg,#8db9f8 0%,#5b97f7 55%,#3f7ff0 100%);
  border:0;color:#fff}
 .mc-k{font-size:13px;color:var(--neutralFg3);font-weight:500;margin-bottom:6px}
 .mc-v{font-size:34px;font-weight:700;letter-spacing:-1px;color:var(--ink)}
 .mc-s{font-size:13px;color:var(--neutralFg2);margin-top:4px}
 .mc-up{display:inline-block;font-size:12px;font-weight:600;color:var(--blueDeep);
  margin-top:4px}
 .mc-foot{margin-top:auto;border-top:1px solid var(--neutralBg3);padding-top:10px;
  font-size:12px;color:var(--neutralFg3);text-align:center}
 .mcard .pillbadge{margin-bottom:14px;background:rgba(255,255,255,.22);
  color:#fff;font-size:12.5px}
 .mc-title{font-size:clamp(22px,2.6vw,32px);font-weight:800;letter-spacing:-.8px;
  line-height:1.15;margin-bottom:auto}
 .mcard.bluecard p{font-size:13.5px;color:rgba(255,255,255,.88);line-height:1.6;
  margin:18px 0 0}
 .mc-spark{margin-top:8px}
 .mc-spark svg{display:block;width:100%;height:auto}
 /* 하단 스트립 */
 .shellfoot{display:flex;justify-content:space-between;align-items:center;
  padding:16px 6px 2px;color:var(--neutralFg3);font-size:12.5px}
 .page{margin-top:6px}
 /* ===== 카드 공통 / 추이 그래프 ===== */
 .card{border:1px solid var(--neutralStroke2);border-radius:18px;background:#fff;
  padding:16px 18px;margin:0 0 8px;box-shadow:var(--shadow2)}
 .card-h{display:flex;align-items:baseline;gap:10px;font-size:16px;margin-bottom:6px}
 .card-sub{font-size:12px;color:var(--neutralFg3)}
 #trend{overflow-x:auto}
 #trend svg{display:block;width:100%;height:auto}
 .trend-note{color:var(--neutralFg3);font-size:13px;padding:14px 2px}
 .ic-cal{width:16px;height:16px;flex:none}
 /* 모듈 섹션 헤더 + 컴팩트 날짜 칩 */
 .modhead{display:flex;align-items:center;justify-content:flex-start;gap:12px;
  flex-wrap:wrap;margin:34px 4px 14px}
 .datechip{display:inline-flex;align-items:center;gap:8px;cursor:pointer;font:inherit;
  background:#fff;border:1px solid var(--neutralStroke2);border-radius:var(--radiusPill);
  padding:8px 8px 8px 14px;box-shadow:0 4px 14px rgba(60,90,140,.08);
  transition:background .12s,box-shadow .12s}
 .datechip:hover{background:var(--grayPill);box-shadow:0 6px 18px rgba(60,90,140,.12)}
 .datechip .ic-cal{color:var(--blueDeep)}
 .datechip .dc-date{font-size:14px;font-weight:700;color:var(--ink);letter-spacing:-.2px}
 .datechip .dc-wd{font-size:12.5px;color:var(--neutralFg3);font-weight:600}
 .datechip.today .dc-date{color:var(--blueDeep)}
 .datechip .dc-chev{color:var(--neutralFg3);font-size:11px;
  background:var(--grayPill);border-radius:50%;width:22px;height:22px;
  display:inline-flex;align-items:center;justify-content:center}
 /* 달력 데이트피커 */
 .sheet.narrow{max-width:360px}
 .cal{margin:0 auto}
 .cal-h{display:flex;align-items:center;justify-content:space-between;margin:4px 0 14px}
 .cal-h b{font-size:17px;font-weight:800;letter-spacing:-.3px}
 .cal-nav{display:inline-flex;gap:6px}
 .cal-nav button{width:32px;height:32px;border-radius:50%;border:0;cursor:pointer;
  font-size:16px;line-height:1;color:var(--neutralFg2);background:var(--grayPill)}
 .cal-nav button:hover{background:#e3e6ec}
 .cal-dow,.cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:4px}
 .cal-dow{margin-bottom:6px}
 .cal-dow span{text-align:center;font-size:12px;font-weight:600;color:var(--neutralFg3)}
 .cal-dow span.we{color:#c05299}
 .cal-day{aspect-ratio:1;display:flex;align-items:center;justify-content:center;
  border:0;background:transparent;border-radius:50%;font:inherit;font-size:14px;
  color:var(--ink);cursor:pointer;position:relative;padding:0}
 .cal-day.empty{visibility:hidden;cursor:default}
 .cal-day.off{color:#c7ccd3;cursor:default}
 .cal-day.has{font-weight:600}
 .cal-day.has::after{content:'';position:absolute;bottom:5px;width:4px;height:4px;
  border-radius:50%;background:var(--blue)}
 .cal-day.has:hover:not(.sel){background:var(--blueSoft)}
 .cal-day.sel{background:var(--blue);color:#fff;font-weight:700}
 .cal-day.sel::after{background:#fff}
 .cal-cap{text-align:center;font-size:12px;color:var(--neutralFg3);margin:14px 0 2px}
 /* 추이 기간 선택 필드 */
 .tdates{display:inline-flex;align-items:center;gap:8px;font-size:13px;color:var(--neutralFg3)}
 .tdates .ic-cal{color:var(--neutralFg3);margin-right:-2px}
 .tdate{font:inherit;font-size:12.5px;cursor:pointer;border:1px solid var(--neutralStroke2);
  background:#fff;color:var(--ink);border-radius:var(--radiusPill);padding:6px 13px;font-weight:600}
 .tdate:hover{background:var(--grayPill)}
 .tdate.reset{color:var(--neutralFg3);font-weight:500}
 /* 추이 컨트롤 (은행별/상품별 비교) */
 .tctrl{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:2px 0 16px}
 .tsegwrap{display:inline-flex;background:var(--grayPill);border-radius:var(--radiusPill);
  padding:3px;gap:2px}
 .tseg{font:inherit;font-size:12.5px;font-weight:600;cursor:pointer;border:0;
  background:transparent;color:var(--neutralFg2);border-radius:var(--radiusPill);
  padding:6px 13px}
 .tseg.on{background:var(--blue);color:#fff}
 .tchips{display:flex;flex-wrap:wrap;gap:6px}
 .tchip{font:inherit;font-size:12.5px;cursor:pointer;border:1px solid var(--neutralStroke2);
  background:#fff;color:var(--neutralFg2);border-radius:var(--radiusPill);padding:5px 12px}
 .tchip.on{background:var(--ink);color:#fff;border-color:var(--ink)}
 .tlegend{display:flex;flex-wrap:wrap;gap:14px;margin-top:12px;font-size:12.5px;
  color:var(--neutralFg2)}
 .tlegend span{display:inline-flex;align-items:center;gap:6px}
 .tlegend i{width:11px;height:11px;border-radius:50%;display:inline-block}
 h2{font-size:20px;font-weight:700;margin:8px 0 10px;line-height:1.3}
 h2 small{font-weight:400;color:var(--neutralFg3);font-size:13px}
 .meta{color:#b0b5bd;font-size:13px;margin:0}

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
 .stickybar{position:sticky;top:0;z-index:5;background:#fff;
  padding:12px 0 14px;border-bottom:1px solid var(--neutralStroke2)}
 .toolbar{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-bottom:12px}
 .search{flex:1 1 220px;min-width:150px;font:inherit;font-size:14px;
  padding:9px 12px;border:1px solid var(--neutralStroke1);
  border-radius:var(--radiusMd);background:var(--neutralBg1);color:var(--neutralFg1)}
 .search::placeholder{color:var(--neutralFg3)}
 /* Fluent 2 드롭다운 (전체 기간 / 정렬) */
 .sort{font:inherit;font-size:14px;cursor:pointer;color:var(--neutralFg1);
  padding:9px 34px 9px 12px;border:1px solid var(--neutralStroke1);
  border-radius:var(--radiusMd);background-color:var(--neutralBg1);
  -webkit-appearance:none;appearance:none;background-repeat:no-repeat;
  background-position:right 10px center;background-size:16px;
  background-image:url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23616161' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'><path d='m6 9 6 6 6-6'/></svg>")}
 .sort:hover{border-color:var(--neutralFg3);background-color:var(--neutralBg2)}
 .sort:focus-visible{outline:2px solid var(--brandFg);outline-offset:1px;
  border-color:var(--brandFg)}
 .terms{margin-top:10px}
 .terms .chip{padding:5px 13px;font-size:13px}
 /* 포커스 접근성 (Fluent focus stroke) */
 :focus-visible{outline:2px solid var(--brandFg);outline-offset:2px;
  border-radius:var(--radiusMd)}
 /* BEST 배지 */
 .badge{display:inline-block;font-size:11px;font-weight:700;color:#fff;
  background:var(--brandFg);border-radius:var(--radiusPill);
  padding:1px 8px;margin-left:6px;vertical-align:middle;letter-spacing:.3px}
 @media (max-width:900px){.modrow{grid-template-columns:1fr}}

 /* 툴바 3단 정리 */
 .barrow{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
 .barrow.primary{justify-content:space-between;margin-bottom:12px}
 .barrow.refine{margin-top:12px}
 .btn-primary{display:inline-flex;align-items:center;gap:7px;font:inherit;font-size:14px;
  font-weight:600;cursor:pointer;color:#fff;background:var(--brandFg);
  border:1px solid var(--brandFg);border-radius:var(--radiusMd);padding:9px 16px}
 .btn-primary:hover{background:var(--brandFgHover);border-color:var(--brandFgHover)}
 .btn-primary svg{width:18px;height:18px;flex:none}
 /* 검색창 안 돋보기 아이콘 */
 .searchwrap{position:relative;display:flex;align-items:center;flex:1 1 240px;min-width:160px}
 .searchwrap svg{position:absolute;left:11px;width:17px;height:17px;
  color:var(--neutralFg3);pointer-events:none}
 .searchwrap .search{flex:1;width:100%;min-width:0;padding-left:34px}
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
 /* hidden 속성이 display:flex 를 이기도록(안 그러면 빈 오버레이가 안 닫힘) */
 .overlay[hidden]{display:none}
 .tray[hidden]{display:none}
 .sheet{background:var(--neutralBg1);border-radius:32px;width:100%;
  max-width:880px;box-shadow:0 20px 50px rgba(20,40,80,.28);padding:22px 24px}
 .sheet-h{display:flex;justify-content:space-between;align-items:center;
  margin-bottom:14px;font-size:17px}
 .sheet-h small{font-weight:400;color:var(--neutralFg3);font-size:12px}
 .x{font:inherit;font-size:16px;cursor:pointer;border:0;background:transparent;
  color:var(--neutralFg3);padding:4px 8px;border-radius:var(--radiusMd)}
 .x:hover{background:var(--neutralBg2)}
 /* 비교 카드 */
 .ccards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
 .ccard{border:1px solid var(--neutralStroke2);border-radius:18px;padding:14px}
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
 .wiz select{cursor:pointer;padding-right:34px;-webkit-appearance:none;appearance:none;
  background-repeat:no-repeat;background-position:right 10px center;background-size:16px;
  background-image:url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23616161' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'><path d='m6 9 6 6 6-6'/></svg>")}
 .wiz select:focus-visible,.wiz input:focus-visible{outline:2px solid var(--brandFg);
  outline-offset:1px;border-color:var(--brandFg)}
 .wiz-btns{grid-column:1/-1;display:flex;justify-content:flex-end;gap:8px;margin-top:4px}
 .wiz-note{grid-column:1/-1;font-size:12px;color:var(--neutralFg3);margin:2px 0 0}
 @media (max-width:560px){.wiz{grid-template-columns:1fr}}
 /* 하단 트레이 공간 */
 body{padding-bottom:88px}

 /* ===== 표 (다른 카드와 통일된 24px 라운드, 깔끔한 라인 스타일) ===== */
 .wrap{overflow-x:auto;border:1px solid var(--neutralStroke2);background:#fff;
  border-radius:24px;box-shadow:var(--shadow2)}
 table{border-collapse:separate;border-spacing:0;width:100%;font-size:15px}
 th,td{padding:14px 18px;text-align:left;
  border-bottom:1px solid var(--neutralBg3);vertical-align:top}
 thead th{background:transparent;position:sticky;top:0;z-index:2;
  color:var(--neutralFg3);font-weight:600;font-size:12.5px;letter-spacing:.2px;
  padding-top:16px;padding-bottom:12px;
  border-bottom:1px solid var(--neutralStroke2)}
 .num{text-align:center;white-space:nowrap}
 /* 기본금리 크게(강조), 최고우대 작게 */
 td.num .b{display:block;font-size:18px;color:var(--neutralFg1)}
 td.num .m{display:block;font-size:13px;color:var(--neutralFg3);margin-top:2px}
 td.num.cempty{color:var(--neutralStroke1)}
 .bank{font-weight:600;white-space:nowrap;color:var(--neutralFg1)}
 .prod{color:var(--ink);font-weight:700;min-width:180px}
 .spcl{color:var(--neutralFg3);font-size:13px;line-height:1.5;
  min-width:260px;max-width:420px;white-space:normal}
 .tag{font-size:12px;color:var(--neutralFg2);background:var(--neutralBg3);
  border:1px solid var(--neutralStroke2);border-radius:var(--radiusMd);
  padding:1px 6px;margin-left:6px;vertical-align:middle;font-weight:400}
 tr.rowsep td{border-top:1px solid var(--neutralStroke2)}
 tbody tr:last-child td{border-bottom:0}
 tbody tr:hover td{background:var(--neutralBg2)}
 .empty{color:var(--neutralFg3);padding:20px 2px}
 .legend{font-size:13px;color:var(--neutralFg3);margin-top:14px}
 .legend b{color:var(--neutralFg2);font-weight:600}

 /* ===== 반응형: 좁은 화면(모바일)에서는 상품별 카드로 ===== */
 @media (max-width:720px){
  body{padding:12px 8px}
  .widget{padding:16px 14px;border-radius:26px}
  .heroC{padding:28px 4px 16px}
  .heroC h1{letter-spacing:-1.2px}
  h2{font-size:18px}
  .whead .meta{display:none}
  .mods{margin:0;order:3;flex-basis:100%}
  .sendbtn{padding:0 14px}
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
<div class="widget">
<header class="whead">
 <button class="brand" id="brandhome" type="button" aria-label="첫 화면으로">
  <span class="brand-ic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
   stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
   <path d="M3 9.5 12 4l9 5.5"/><path d="M5 10v8M9.5 10v8M14.5 10v8M19 10v8"/>
   <path d="M3.5 21h17"/></svg></span>
  <span class="brand-tx">interest rate Agent</span>
 </button>
 <nav class="mods" id="mods" aria-label="페이지 이동">
  <button type="button" data-m="home" class="on">홈</button>
  <button type="button" data-m="dep">예금</button>
  <button type="button" data-m="sav">적금</button>
  <button type="button" data-m="trend">금리 추이</button>
  <button type="button" data-m="cmp">상품 비교</button>
  <button type="button" data-m="wiz">내 조건</button>
 </nav>
 <span class="meta" id="meta"></span>
</header>

<section id="homeview">
 <div class="heroC">
  <span class="pillbadge"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
   stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
   <path d="M3 9.5 12 4l9 5.5"/><path d="M5 10v8M9.5 10v8M14.5 10v8M19 10v8"/>
   <path d="M3.5 21h17"/></svg>금융감독원 공시로 확인해요</span>
  <h1>날짜별 예·적금,<br>편하게 찾아드릴게요</h1>
  <p class="herosub">7개 은행 예·적금 금리를 매일 아침 새로 가져와요.<br>
   궁금한 건 편하게 물어보세요.</p>
  <div class="askbar" role="search">
   <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"
    stroke-linecap="round" stroke-linejoin="round"><path d="m14 5 5 5L8 21H3v-5z"/>
    <path d="m12.5 6.5 5 5"/></svg>
   <input id="ask" type="text" placeholder="궁금한 걸 물어보세요 · 예) 12개월 예금 금리"
    aria-label="금리 질문" autocomplete="off">
   <button id="send" class="sendbtn" aria-label="질문 보내기">질문하기<svg
    viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
    stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/>
    <path d="m13 6 6 6-6 6"/></svg></button>
   <button id="chatclear" class="chatclear" type="button" hidden aria-label="대화 리셋"
    title="대화 리셋">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
     stroke-linecap="round" stroke-linejoin="round">
     <path d="M3.5 9.5a8.5 8.5 0 1 1 1.02 6.4"/><path d="M3.5 4v5.5H9"/></svg></button>
  </div>
  <div class="sugg" id="sugg"></div>
  <div class="chatlogwrap" id="chatlogwrap" hidden>
   <div id="chatlog" class="chatlog" aria-live="polite"></div>
   <div class="chatfade" aria-hidden="true"></div>
  </div>
 </div>
 <div class="modhead">
  <div id="datenav"></div>
 </div>
 <div class="modrow" id="modrow" aria-label="모듈 바로가기"></div>
 <div class="shellfoot"><span id="footstat"></span>
  <span class="hint">카드를 누르면 자세히 볼 수 있어요 →</span></div>
</section>

<section class="card page" id="trendcard" hidden>
 <div class="card-h"><b>날짜별 금리 추이</b>
  <span class="card-sub" id="trendsub"></span></div>
 <div class="tctrl" id="tctrl"></div>
 <div id="trend"></div>
</section>

<div id="ratespage" class="page" hidden>
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
  <button id="wizOpen" class="btn-primary" type="button"><svg viewBox="0 0 24 24"
   fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"
   stroke-linejoin="round"><circle cx="12" cy="7.5" r="3.5"/>
   <path d="M4.5 19.5a7.5 7.5 0 0 1 15 0"/></svg>내 조건으로 찾기</button>
 </div>
 <div class="chips" id="chips" role="group" aria-label="은행 선택"></div>
 <div class="barrow refine">
  <span class="searchwrap"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
   stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/>
   <path d="m20 20-3.2-3.2"/></svg>
   <input id="q" class="search" type="search" placeholder="상품·은행 검색"
    aria-label="상품 검색" autocomplete="off"></span>
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
<p class="legend">※ 여기 금리는 세전 연이율이에요. 우대금리는 조건을 채우면 받을 수 있어요.
 상품마다 단리·복리와 과세 조건이 다를 수 있으니, 가입 전에 각 은행 약관을 확인해요.</p>
</div><!-- /#ratespage -->
</div><!-- /.widget -->

<div id="tray" class="tray" hidden></div>
<div id="overlay" class="overlay" hidden><div class="sheet" id="sheet"></div></div>

<script>
const APP = __DATA__;
const state = {view:'home', product:'deposit', banks:new Set(), term:'전체',
  q:'', sort:'max', compare:[], modal:null, online:false, amount:0,
  ratetype:'', joindeny:'', rsvtype:'', minrate:0,
  viewDate:null, trendProduct:'deposit', trendMetric:'max', trendBanks:new Set(),
  pickerMonth:null, pickerTarget:'view', trendFrom:null, trendTo:null};
const esc = s => String(s==null?'':s).replace(/[&<>"]/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const isNum = v => /^\d+$/.test(String(v));
const bestMax = g => Math.max(0, ...Object.values(g.cells).map(c => c.mx||0));
const ICON_DEP = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="2.5" y="6.5" width="19" height="11" rx="2"/><circle cx="12" cy="12" r="2.4"/></svg>';
const ICON_SAV = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="6.5" rx="6.5" ry="2.6"/><path d="M5.5 6.5v5c0 1.4 2.9 2.6 6.5 2.6s6.5-1.2 6.5-2.6v-5"/><path d="M5.5 11.5v5c0 1.4 2.9 2.6 6.5 2.6s6.5-1.2 6.5-2.6v-5"/></svg>';
// Uicons(Flaticon) 스타일 캘린더 라인 아이콘
const ICON_CAL = '<svg class="ic-cal" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="16" rx="4.5"/><path d="M3 9.5h18M8 3v3.4M16 3v3.4"/></svg>';

function heroBest(list){
 let best = null;
 for(const r of list){
  const mx = parseFloat(r.max_rate); if(isNaN(mx)) continue;
  if(!best || mx > best.mx) best = {mx, base:parseFloat(r.base_rate), bank:r.bank,
    product:r.product, term:r.term_months, rsv:r.reserve_type||''};
 }
 return best;
}
function miniSpark(){
 // 홈 우측 카드용 미니 추이(예금 전체 최고, 레퍼런스의 라인차트+툴팁)
 const hist = APP.history || {};
 const dates = Object.keys(hist).sort();
 const pts = dates.map(d => { const day = (hist[d]||{}).deposit || {};
  let m = 0; for(const b in day) m = Math.max(m, day[b].max||0); return m || null; });
 const vals = pts.filter(v => v != null);
 if(vals.length === 0) return {svg:'', last:null, delta:null};
 let mn = Math.min(...vals), mx = Math.max(...vals);
 if(mx-mn < 0.3){ const c=(mx+mn)/2; mn=c-0.2; mx=c+0.2; }
 const W=250,H=96,L=8,R=12,T=30,B=18;
 const X=i=>L+(W-L-R)*(dates.length===1?0.5:i/(dates.length-1));
 const Y=v=>T+(H-T-B)*(1-(v-mn)/(mx-mn));
 let d='';
 const P=pts.map((v,i)=>v==null?null:{x:X(i),y:Y(v)}).filter(Boolean);
 if(P.length>1){ d='M'+P[0].x+' '+P[0].y;
  for(let i=1;i<P.length;i++){ const a=P[i-1],b=P[i],cx=(a.x+b.x)/2;
   d+=' C'+cx+' '+a.y+' '+cx+' '+b.y+' '+b.x+' '+b.y; } }
 let s='<svg viewBox="0 0 '+W+' '+H+'" aria-hidden="true">';
 dates.forEach((dd,i)=>{ s+='<line x1="'+X(i)+'" y1="'+T+'" x2="'+X(i)+'" y2="'
  +(H-B)+'" stroke="#eef0f4"/>'; });
 if(d) s+='<path d="'+d+'" fill="none" stroke="#4285f4" stroke-width="2" stroke-linecap="round"/>';
 P.forEach(p=>{ s+='<circle cx="'+p.x+'" cy="'+p.y+'" r="3" fill="#fff" stroke="#4285f4" stroke-width="1.6"/>'; });
 const lp=P[P.length-1], lv=vals[vals.length-1];
 if(lp){ const txt=lv.toFixed(2)+'%', tw=txt.length*6.6+14;
  s+='<rect x="'+(lp.x-tw/2)+'" y="'+(lp.y-26)+'" width="'+tw+'" height="18" rx="9" fill="#101215"/>'
   +'<text x="'+lp.x+'" y="'+(lp.y-13)+'" text-anchor="middle" font-size="10" font-weight="700" fill="#fff">'+txt+'</text>'; }
 dates.forEach((dd,i)=>{ s+='<text x="'+X(i)+'" y="'+(H-4)+'" text-anchor="middle" font-size="9" fill="#9aa1ab">'
  +(+dd.slice(5,7))+'/'+(+dd.slice(8,10))+'</text>'; });
 s+='</svg>';
 const delta = vals.length>1 ? lv-vals[0] : null;
 return {svg:s, last:lv, delta};
}
function histDates(){ return Object.keys(APP.history||{}).sort(); }
function latestDate(){ const d = histDates(); return d[d.length-1] || null; }
function histVal(date, prod, bank, metric){
 const day = (APP.history[date]||{})[prod] || {};
 if(bank === '전체'){ let m = 0; for(const b in day) m = Math.max(m, (day[b]||{})[metric]||0);
  return m || null; }
 return day[bank] ? (day[bank][metric] || null) : null;
}
function histTop(date, prod, metric){
 const day = (APP.history[date]||{})[prod] || {}; let bb=null, bv=-1;
 for(const b in day){ const v = (day[b]||{})[metric]||0; if(v > bv){ bv = v; bb = b; } }
 return bb ? {bank:bb, rate:bv} : null;
}
function renderModules(){
 const vd = state.viewDate || latestDate();
 const isToday = !vd || vd === latestDate();
 const dl = isToday ? '오늘' : (vd ? (+vd.slice(5,7))+'/'+(+vd.slice(8,10)) : '오늘');
 let depV, depS, savV, savS, footTxt;
 if(isToday){
  const dep = heroBest(APP.deposit), sav = heroBest(APP.saving);
  depV = dep?dep.mx+'%':'-'; depS = dep?esc(dep.bank)+' · '+esc(dep.product)+' · '+dep.term+'개월':'';
  savV = sav?sav.mx+'%':'-'; savS = sav?esc(sav.bank)+' · '+esc(sav.product)+' · '+sav.term+'개월':'';
  footTxt = '기본금리 기준 예금 '+(dep&&!isNaN(dep.base)?dep.base:'-')+'% · 적금 '
    +(sav&&!isNaN(sav.base)?sav.base:'-')+'%';
 } else {
  const dt = histTop(vd,'deposit','max'), st = histTop(vd,'saving','max');
  const db = histTop(vd,'deposit','base'), sb = histTop(vd,'saving','base');
  depV = dt?dt.rate+'%':'-'; depS = dt?esc(dt.bank)+' 최고 (은행 기준)':'기록 없음';
  savV = st?st.rate+'%':'-'; savS = st?esc(st.bank)+' 최고 (은행 기준)':'기록 없음';
  footTxt = '기본금리 최고 예금 '+(db?db.rate:'-')+'% · 적금 '+(sb?sb.rate:'-')+'%';
 }
 const sp = miniSpark();
 const el = document.getElementById('modrow');
 el.innerHTML =
  `<button type="button" class="mcard light" data-m="dep">
    <div class="mc-k">${dl}의 최고 예금</div>
    <div class="mc-v">${depV}</div>
    <div class="mc-s">${depS}</div>
    <div class="mc-k" style="margin-top:14px">${dl}의 최고 적금</div>
    <div class="mc-v">${savV}</div>
    <div class="mc-s">${savS}</div>
    <div class="mc-foot">${footTxt}</div>
   </button>
   <button type="button" class="mcard bluecard" data-m="cmp">
    <span class="pillbadge">${ICON_DEP}상품 비교</span>
    <div class="mc-title">여러 상품을<br>나란히 비교해요</div>
    <p>7개 은행 ${(APP.deposit||[]).length+(APP.saving||[]).length}개 상품 중
     2~4개를 담으면 기간별 금리와 우대 조건을 한 번에 볼 수 있어요.
     내 조건에 맞는 상품만 골라볼 수도 있어요.</p>
   </button>
   <button type="button" class="mcard light" data-m="trend">
    <div class="mc-k">금리 추이 (예금 최고)</div>
    <div class="mc-v">${sp.last!=null?sp.last.toFixed(2)+'%':'-'}</div>
    ${sp.delta!=null?'<span class="mc-up">'+(sp.delta>=0?'▲':'▼')+' '
      +Math.abs(sp.delta).toFixed(2)+'%p</span>':''}
    <div class="mc-spark">${sp.svg}</div>
   </button>`;
 el.querySelectorAll('.mcard').forEach(c => c.onclick = () => showView(c.dataset.m));
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
 sheet.innerHTML = state.modal==='compare' ? compareHTML()
   : state.modal==='datepicker' ? calendarHTML() : wizardHTML();
 sheet.classList.toggle('narrow', state.modal==='datepicker');
 ov.onclick = e => { if(e.target===ov) closeOverlay(); };
 sheet.querySelectorAll('[data-cal]').forEach(b => b.onclick = () => {
  const [y,m] = state.pickerMonth.split('-').map(Number);
  const nd = new Date(y, m-1 + (b.dataset.cal==='next'?1:-1), 1);
  state.pickerMonth = nd.getFullYear()+'-'+String(nd.getMonth()+1).padStart(2,'0');
  renderOverlay();
 });
 sheet.querySelectorAll('[data-day]').forEach(b => b.onclick = () => pickDate(b.dataset.day));
 sheet.querySelectorAll('[data-close]').forEach(b => b.onclick = closeOverlay);
 sheet.querySelectorAll('[data-rm]').forEach(b => b.onclick = () => {
  const i = state.compare.indexOf(b.dataset.rm); if(i>=0) state.compare.splice(i,1);
  if(!state.compare.length){ closeOverlay(); render(); } else { renderOverlay(); render(); }
 });
 sheet.querySelectorAll('[data-reset]').forEach(b => b.onclick = () => {
  state.term='전체'; state.online=false; state.amount=0;
  state.ratetype=''; state.joindeny=''; state.rsvtype=''; state.minrate=0;
  renderOverlay();
 });
 const form = document.getElementById('wizForm');
 if(form) form.onsubmit = e => {
  e.preventDefault();
  const f = new FormData(form);
  state.product = f.get('product');
  state.term = f.get('term');
  state.online = f.get('online')==='1';
  state.amount = parseInt(f.get('amount'),10) || 0;
  state.ratetype = f.get('ratetype') || '';
  state.joindeny = f.get('joindeny') || '';
  state.rsvtype = f.get('rsvtype') || '';
  state.minrate = parseFloat(f.get('minrate')) || 0;
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
 return `<div class="sheet-h"><b><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" style="width:18px;height:18px;vertical-align:-3px;margin-right:5px"><circle cx="12" cy="7.5" r="3.5"/><path d="M4.5 19.5a7.5 7.5 0 0 1 15 0"/></svg>내 조건으로 찾기</b><button class="x" data-close>✕</button></div>
 <form id="wizForm" class="wiz">
  <label>상품<select name="product">
   <option value="deposit"${isDep?' selected':''}>예금 (목돈 예치)</option>
   <option value="saving"${!isDep?' selected':''}>적금 (매월 납입)</option></select></label>
  <label>기간<select name="term"><option value="전체">상관없음</option>${topts}</select></label>
  <label>가입방법<select name="online">
   <option value="0"${!state.online?' selected':''}>상관없음</option>
   <option value="1"${state.online?' selected':''}>비대면(앱·인터넷)만</option></select></label>
  <label>이자 방식<select name="ratetype">
   <option value="">상관없음</option>
   <option value="단리"${state.ratetype==='단리'?' selected':''}>단리</option>
   <option value="복리"${state.ratetype==='복리'?' selected':''}>복리</option></select></label>
  <label>가입 대상<select name="joindeny">
   <option value="">상관없음</option>
   <option value="1"${state.joindeny==='1'?' selected':''}>누구나 (제한 없음)</option></select></label>
  ${!isDep ? `<label>적립 방식<select name="rsvtype">
   <option value="">상관없음</option>
   <option value="자유적립식"${state.rsvtype==='자유적립식'?' selected':''}>자유적립식</option>
   <option value="정액적립식"${state.rsvtype==='정액적립식'?' selected':''}>정액적립식</option></select></label>` : ''}
  <label>최고우대 금리 하한(%)
   <input name="minrate" type="number" min="0" step="0.1" inputmode="decimal"
    placeholder="예: 3.0" value="${state.minrate||''}"></label>
  <label>${isDep?'예치금액(원)':'월 납입액(원)'}
   <input name="amount" type="number" min="0" step="10000" inputmode="numeric"
    placeholder="예: 1000000" value="${state.amount||''}"></label>
  <div class="wiz-btns"><button type="button" class="btn-ghost" data-reset>초기화</button>
   <button type="button" class="btn-ghost" data-close>닫기</button>
   <button type="submit" class="btn-primary">추천 받기</button></div>
  <p class="wiz-note">※ 금액을 넣으면 예상이자(세전·단리 근사치)를 함께 보여줍니다.
   기간을 고르면 해당 기간 기준으로 계산합니다.</p>
 </form>`;
}

// ===== 날짜별 금리 추이 그래프 =====
const LINE_COLORS = ['#0f6cbd','#7a5af8','#e8618c','#12a594','#e07b39','#5a6acf','#c05299'];
const WD = ['일','월','화','수','목','금','토'];
function renderDatenav(){
 const el = document.getElementById('datenav');
 const ds = histDates();
 if(!ds.length){ el.innerHTML = ''; return; }
 const vd = state.viewDate || latestDate();
 const dt = new Date(vd + 'T00:00:00');
 const isToday = vd === latestDate();
 el.innerHTML =
  '<button class="datechip'+(isToday?' today':'')+'" id="datebtn" aria-label="조회 날짜 선택">'
  + ICON_CAL
  + '<span class="dc-date">'+(dt.getMonth()+1)+'월 '+dt.getDate()+'일</span>'
  + '<span class="dc-wd">'+WD[dt.getDay()]+'요일'+(isToday?' · 오늘':'')+'</span>'
  + '<span class="dc-chev" aria-hidden="true">▾</span></button>';
 document.getElementById('datebtn').onclick = () => openCalendar('view');
}
// ===== 달력 데이트피커 =====
function openCalendar(target){
 state.pickerTarget = target;
 let base = target==='from' ? state.trendFrom
   : target==='to' ? state.trendTo : state.viewDate;
 base = base || latestDate() || new Date().toISOString().slice(0,10);
 state.pickerMonth = base.slice(0,7);
 state.modal = 'datepicker';
 renderOverlay();
}
function pickDate(d){
 const t = state.pickerTarget;
 if(t==='from'){ state.trendFrom = d; if(state.trendTo && d > state.trendTo) state.trendTo = d; }
 else if(t==='to'){ state.trendTo = d; if(state.trendFrom && d < state.trendFrom) state.trendFrom = d; }
 else { state.viewDate = d; }
 state.modal = null;
 render();
}
function calendarHTML(){
 const avail = new Set(histDates());
 const cur = state.viewDate || latestDate();
 const [y,m] = state.pickerMonth.split('-').map(Number);
 const first = new Date(y, m-1, 1);
 const startDow = (first.getDay()+6)%7;         // 월요일 시작
 const daysInMonth = new Date(y, m, 0).getDate();
 const pad = n => String(n).padStart(2,'0');
 const title = y+'년 '+m+'월';
 let cells = '';
 for(let i=0;i<startDow;i++) cells += '<span class="cal-day empty"></span>';
 for(let d=1; d<=daysInMonth; d++){
  const iso = y+'-'+pad(m)+'-'+pad(d);
  const has = avail.has(iso);
  const sel = (state.pickerTarget==='from'?state.trendFrom
    :state.pickerTarget==='to'?state.trendTo:cur) === iso;
  const cls = 'cal-day' + (has?' has':' off') + (sel?' sel':'');
  cells += '<button class="'+cls+'"'+(has?' data-day="'+iso+'"':' disabled')+'>'+d+'</button>';
 }
 const dow = ['월','화','수','목','금','토','일']
   .map((w,i)=>'<span'+(i>=5?' class="we"':'')+'>'+w+'</span>').join('');
 const cap = state.pickerTarget==='view' ? '금리를 확인할 날짜를 골라요 · 점(●) 있는 날에 데이터가 있어요'
   : (state.pickerTarget==='from' ? '추이 시작일을 골라요' : '추이 종료일을 골라요')
   + ' · 점(●) 있는 날에 데이터가 있어요';
 return '<div class="sheet-h"><b>날짜 선택</b><button class="x" data-close>✕</button></div>'
  + '<div class="cal"><div class="cal-h"><b>'+title+'</b><div class="cal-nav">'
  + '<button data-cal="prev" aria-label="이전 달">‹</button>'
  + '<button data-cal="next" aria-label="다음 달">›</button></div></div>'
  + '<div class="cal-dow">'+dow+'</div>'
  + '<div class="cal-grid">'+cells+'</div>'
  + '<p class="cal-cap">'+cap+'</p></div>';
}
function renderTrendControls(){
 const el = document.getElementById('tctrl');
 const seg = (arr, attr, cur) => '<div class="tsegwrap">' + arr.map(([v,l]) =>
   '<button class="tseg'+(String(cur)===String(v)?' on':'')+'" '+attr+'="'+v+'">'+l+'</button>'
  ).join('') + '</div>';
 const allOn = state.trendBanks.size === 0;
 const chips = '<div class="tchips"><button class="tchip'+(allOn?' on':'')
   +'" data-tb="__ALL__">전체 최고</button>'
   + APP.banks.map(b => '<button class="tchip'+(state.trendBanks.has(b)?' on':'')
     +'" data-tb="'+esc(b)+'">'+esc(b)+'</button>').join('') + '</div>';
 const drange = '<div class="tdates">'+ICON_CAL
   + '<button class="tdate" data-open="from">'+(state.trendFrom||'시작일')+'</button>'
   + '<span>~</span>'
   + '<button class="tdate" data-open="to">'+(state.trendTo||'종료일')+'</button>'
   + ((state.trendFrom||state.trendTo)?'<button class="tdate reset" data-open="reset">전체기간</button>':'')
   + '</div>';
 el.innerHTML =
   seg([['deposit','예금'],['saving','적금'],['both','예금+적금']],'data-tp',state.trendProduct)
   + seg([['max','최고우대'],['base','기본금리']],'data-tm',state.trendMetric)
   + drange + chips;
 el.querySelectorAll('[data-tp]').forEach(b => b.onclick = () => {
  state.trendProduct = b.dataset.tp; renderTrend(); });
 el.querySelectorAll('[data-tm]').forEach(b => b.onclick = () => {
  state.trendMetric = b.dataset.tm; renderTrend(); });
 el.querySelectorAll('[data-tb]').forEach(b => b.onclick = () => {
  const v = b.dataset.tb;
  if(v === '__ALL__') state.trendBanks.clear();
  else state.trendBanks.has(v) ? state.trendBanks.delete(v) : state.trendBanks.add(v);
  renderTrend(); });
 el.querySelectorAll('[data-open]').forEach(b => b.onclick = () => {
  const t = b.dataset.open;
  if(t === 'reset'){ state.trendFrom = null; state.trendTo = null; renderTrend(); }
  else openCalendar(t);
 });
}
function renderTrend(){
 renderTrendControls();
 const el = document.getElementById('trend'), sub = document.getElementById('trendsub');
 let dates = histDates();
 if(state.trendFrom) dates = dates.filter(d => d >= state.trendFrom);
 if(state.trendTo) dates = dates.filter(d => d <= state.trendTo);
 const prods = state.trendProduct==='both' ? ['deposit','saving'] : [state.trendProduct];
 const banks = state.trendBanks.size ? APP.banks.filter(b => state.trendBanks.has(b)) : ['전체'];
 const metric = state.trendMetric, mlbl = metric==='max' ? '최고우대' : '기본금리';
 const series = [];
 for(const bank of banks) for(const prod of prods){
  const pl = prod==='deposit' ? '예금' : '적금';
  series.push({ name:(bank==='전체'?'전체 최고':bank)+(prods.length>1?' '+pl:''),
   pts: dates.map(d => histVal(d, prod, bank, metric)) });
 }
 const pn = prods.length>1 ? '예금·적금 비교' : (prods[0]==='deposit'?'예금':'적금');
 sub.textContent = pn+' · '+mlbl+' · '
   +(banks[0]==='전체'?'7개 은행 중 최고':banks.join('·'))+' · '+dates.length+'일 기록';
 const vals = series.flatMap(s => s.pts).filter(v => v != null);
 if(!dates.length || !vals.length){
  el.innerHTML = '<p class="trend-note">아직 기록이 없어요. 매일 아침 7시 갱신 때마다 하루치가 쌓여요.</p>';
  return;
 }
 let mn = Math.min(...vals), mx = Math.max(...vals);
 if(mx - mn < 0.4){ const c = (mx+mn)/2; mn = c-0.25; mx = c+0.25; }
 const W=720, H=250, L=42, R=20, Tp=20, B=30, single = series.length===1;
 const X = i => L + (W-L-R) * (dates.length===1 ? 0.5 : i/(dates.length-1));
 const Y = v => Tp + (H-Tp-B) * (1-(v-mn)/(mx-mn));
 const fmtD = d => (+d.slice(5,7))+'/'+(+d.slice(8,10));
 function path(pts){
  const p = pts.map((v,i)=> v==null?null:{x:X(i),y:Y(v)}).filter(Boolean);
  if(p.length < 2) return {d:'', p};
  let d = 'M'+p[0].x.toFixed(1)+' '+p[0].y.toFixed(1);
  for(let i=1;i<p.length;i++){ const a=p[i-1], b=p[i], cx=((a.x+b.x)/2).toFixed(1);
   d += ' C'+cx+' '+a.y.toFixed(1)+' '+cx+' '+b.y.toFixed(1)+' '+b.x.toFixed(1)+' '+b.y.toFixed(1); }
  return {d, p};
 }
 let g = '<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="날짜별 '+pn+' '+mlbl+' 추이">';
 g += '<defs><linearGradient id="tg" x1="0" y1="0" x2="0" y2="1">'
   +'<stop offset="0" stop-color="'+LINE_COLORS[0]+'" stop-opacity=".22"/>'
   +'<stop offset="1" stop-color="'+LINE_COLORS[0]+'" stop-opacity="0"/></linearGradient></defs>';
 for(let i=0;i<3;i++){ const v = mn + (mx-mn)*i/2, y = Y(v);
  g += '<line x1="'+L+'" y1="'+y.toFixed(1)+'" x2="'+(W-R)+'" y2="'+y.toFixed(1)+'" stroke="#eceef1"/>'
   +'<text x="'+(L-6)+'" y="'+(y+4).toFixed(1)+'" text-anchor="end" font-size="10.5" fill="#8a8f98">'
   + v.toFixed(1)+'</text>'; }
 if(single){ const {d,p} = path(series[0].pts);
  if(d){ const yb = H-B;
   g += '<path d="'+d+' L'+p[p.length-1].x.toFixed(1)+' '+yb+' L'+p[0].x.toFixed(1)+' '+yb
     +' Z" fill="url(#tg)"/>'; } }
 series.forEach((s,si) => { const col = LINE_COLORS[si % LINE_COLORS.length];
  const {d,p} = path(s.pts);
  if(d) g += '<path d="'+d+'" fill="none" stroke="'+col+'" stroke-width="2.4" stroke-linecap="round"/>';
  p.forEach(pt => { g += '<circle cx="'+pt.x.toFixed(1)+'" cy="'+pt.y.toFixed(1)
    +'" r="3.2" fill="#fff" stroke="'+col+'" stroke-width="2"/>'; }); });
 // 각 시리즈 마지막 값 라벨
 series.forEach((s,si) => { const col = LINE_COLORS[si % LINE_COLORS.length];
  const idx = s.pts.map((v,i)=>v==null?null:i).filter(v=>v!=null);
  if(!idx.length) return;
  const li = idx[idx.length-1], lv = s.pts[li], lx = X(li), ly = Y(lv);
  const txt = lv.toFixed(2), tw = txt.length*7+14;
  g += '<rect x="'+(lx-tw/2).toFixed(1)+'" y="'+(ly-30).toFixed(1)+'" width="'+tw.toFixed(1)
    +'" height="19" rx="9.5" fill="'+col+'"/>'
    +'<text x="'+lx.toFixed(1)+'" y="'+(ly-16.5).toFixed(1)+'" text-anchor="middle" font-size="11"'
    +' font-weight="700" fill="#fff">'+txt+'</text>'; });
 const step = Math.max(1, Math.ceil(dates.length/8));
 dates.forEach((d,i) => { if(i%step===0 || i===dates.length-1)
  g += '<text x="'+X(i).toFixed(1)+'" y="'+(H-9)+'" text-anchor="middle" font-size="10.5" fill="#8a8f98">'
    + fmtD(d)+'</text>'; });
 g += '</svg>';
 if(!single) g += '<div class="tlegend">' + series.map((s,si) =>
   '<span><i style="background:'+LINE_COLORS[si%LINE_COLORS.length]+'"></i>'+esc(s.name)+'</span>'
  ).join('') + '</div>';
 if(dates.length === 1) g += '<p class="trend-note">오늘 첫 기록이에요 — 내일 아침 7시부터 선이 그려져요.</p>';
 el.innerHTML = g;
}

// ===== 금리 에이전트 채팅 (내장 데이터 기반 오프라인 응답) =====
const chatMsgs = [];
const SUGGS = ['12개월 예금 최고 금리는?','카카오뱅크 적금 알려줘',
  '100만원 12개월 이자 얼마?','국민 하나 예금 비교'];
function addMsg(cls, html){
 chatMsgs.push({cls, html});
 const log = document.getElementById('chatlog');
 document.getElementById('chatlogwrap').hidden = false;
 log.innerHTML = chatMsgs.map(m=>'<div class="msg '+m.cls+'">'+m.html+'</div>').join('');
 log.scrollTop = 1e9;
 document.getElementById('chatclear').hidden = false;
}
function clearChat(){
 chatMsgs.length = 0;
 document.getElementById('chatlog').innerHTML = '';
 document.getElementById('chatlogwrap').hidden = true;
 document.getElementById('chatclear').hidden = true;
}
function parseAmount(q){
 let m = q.match(/(\d+(?:\.\d+)?)\s*억/); if(m) return Math.round(+m[1]*1e8);
 m = q.match(/(\d+(?:\.\d+)?)\s*천\s*만/); if(m) return Math.round(+m[1]*1e7);
 m = q.match(/(\d+(?:\.\d+)?)\s*백\s*만/); if(m) return Math.round(+m[1]*1e6);
 m = q.match(/(\d[\d,]*)\s*만\s*원?/); if(m) return +m[1].replace(/,/g,'')*1e4;
 m = q.match(/(\d[\d,]{3,})\s*원/); if(m) return +m[1].replace(/,/g,'');
 return 0;
}
function agentAnswer(q){
 const prod = /적금/.test(q) ? 'saving' : (/예금/.test(q) ? 'deposit' : state.product);
 const pname = prod==='deposit' ? '예금' : '적금';
 const banks = APP.banks.filter(b => {
  const s = b.replace('은행','').replace('뱅크','');
  return q.indexOf(b)>=0 || (s && q.indexOf(s)>=0);
 });
 const tmM = q.match(/(\d+)\s*개월/);
 const tm = tmM ? +tmM[1] : 0;
 const amt = parseAmount(q);
 const wantBase = /기본/.test(q) && !/최고|우대/.test(q);
 const lbl = wantBase ? '기본금리' : '최고우대금리';
 let arr = allGroups(prod);
 if(banks.length) arr = arr.filter(g => banks.includes(g.bank));
 if(tm) arr = arr.filter(g => g.cells[tm]);
 const val = g => { if(tm){ const c=g.cells[tm]; return (wantBase?c.base:c.mx)||0; }
  return Math.max(0, ...Object.values(g.cells).map(c=>(wantBase?c.base:c.mx)||0)); };
 const bestTerm = g => { let bt=0,bv=-1; for(const t in g.cells){
   const v=(wantBase?g.cells[t].base:g.cells[t].mx)||0; if(v>bv){bv=v;bt=+t;} } return bt; };
 arr = arr.slice().sort((a,b)=>val(b)-val(a));
 if(!arr.length) return {html:'조건에 맞는 상품을 찾지 못했어요. 은행명·기간을 바꾸거나 "'
   +pname+'" 대신 다른 상품으로 물어보세요.'};
 let html;
 if(/비교/.test(q) && banks.length >= 2){
  html = '<b>'+banks.join(' vs ')+'</b> · '+pname+(tm?' '+tm+'개월':'')+' '+lbl+' 비교\n';
  banks.forEach(b => { const g = arr.find(x=>x.bank===b);
   if(!g){ html += '· '+b+': 해당 조건 상품 없음\n'; return; }
   const t = tm || bestTerm(g);
   html += '· '+b+' <b>'+val(g).toFixed(2)+'%</b> — '+esc(g.product)+' ('+t+'개월)\n'; });
 } else {
  const top = arr.slice(0, 3);
  html = (banks.length?banks.join('·')+' ':'')+(tm?tm+'개월 ':'')+pname+' '+lbl
    +' TOP'+top.length+'\n';
  top.forEach((g,i)=>{ const t = tm || bestTerm(g);
   const c = g.cells[t] || {};
   html += (i+1)+'. <b>'+val(g).toFixed(2)+'%</b> '+esc(g.bank)+' '+esc(g.product)
     +' ('+t+'개월, 기본 '+(c.base==null?'-':c.base)+'%)\n'; });
 }
 if(amt > 0){
  const g0 = arr[0], t0 = tm || bestTerm(g0), c0 = g0.cells[t0];
  const e = c0 ? estInterest(prod, c0.base, t0, amt) : null;
  if(e != null) html += '\n💰 1위 상품에 '+won(amt)
    +(prod==='saving'?'씩 매달':'을')+' '+t0+'개월 → 예상이자 <b>'+won(e)
    +'</b> (세전·기본금리 단리 근사)\n';
 }
 html += '\n아래 표에도 이 조건을 적용해뒀어요.';
 return {html, apply(){ state.product=prod;
   state.banks = new Set(banks); state.term = tm ? String(tm) : '전체';
   state.q=''; render(); }};
}
function sendMsg(){
 const inp = document.getElementById('ask');
 const q = (inp.value||'').trim();
 if(!q) return;
 addMsg('user', esc(q));
 inp.value = '';
 const a = agentAnswer(q);
 addMsg('bot', a.html);
 if(a.apply) a.apply();
}
// ===== 페이지 전환: 모듈 클릭 → 해당 내용 페이지 =====
function showView(m){
 if(m==='dep' || m==='sav'){
  state.product = m==='sav' ? 'saving' : 'deposit';
  state.term='전체'; state.compare=[];
 }
 state.view = m;
 render();
 if(m==='wiz'){ state.modal='wizard'; renderOverlay(); }
 if(m==='cmp' && state.compare.length){ state.modal='compare'; renderOverlay(); }
 try{ window.scrollTo({top:0, behavior:'smooth'}); }catch(e){}
}
function applyView(){
 const v = state.view || 'home';
 const home = document.getElementById('homeview');
 const rates = document.getElementById('ratespage');
 const trend = document.getElementById('trendcard');
 home.hidden = v !== 'home';
 trend.hidden = v !== 'trend';
 rates.hidden = !(v==='dep' || v==='sav' || v==='cmp' || v==='wiz');
 document.querySelectorAll('#mods button').forEach(b => {
  const m = b.dataset.m;
  b.classList.toggle('on', m === v ||
   (v==='dep' && m==='dep') || (v==='sav' && m==='sav'));
 });
}
function initChat(){
 const sug = document.getElementById('sugg');
 sug.innerHTML = SUGGS.map(s=>'<button type="button">'+esc(s)+'</button>').join('');
 sug.querySelectorAll('button').forEach(b => b.onclick = () => {
  document.getElementById('ask').value = b.textContent; sendMsg(); });
 document.getElementById('send').onclick = sendMsg;
 document.getElementById('chatclear').onclick = clearChat;
 document.getElementById('brandhome').onclick = () => showView('home');
 document.getElementById('ask').addEventListener('keydown', e => {
  if(e.key === 'Enter') sendMsg(); });
 // 탑바 모듈 내비 → 페이지 전환
 document.querySelectorAll('#mods button').forEach(b =>
  b.onclick = () => showView(b.dataset.m));
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
    joinway:r.join_way||'', ratetype:r.rate_type||'', joindeny:r.join_deny||'',
    cells:{}, spcl:''}; groups.set(key,g); }
  if(!g.joinway && r.join_way) g.joinway = r.join_way;
  if(!g.ratetype && r.rate_type) g.ratetype = r.rate_type;
  if(!g.joindeny && r.join_deny) g.joindeny = r.join_deny;
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
 document.getElementById('footstat').textContent =
  '7개 은행 · 상품 '+((APP.deposit||[]).length+(APP.saving||[]).length)
  +'개 · 매일 아침 7시에 새로 가져와요';
 renderModules(); renderDatenav();

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
 if(state.ratetype) items = items.filter(g => (g.ratetype||'').indexOf(state.ratetype) >= 0);
 if(state.joindeny) items = items.filter(g => String(g.joindeny) === state.joindeny);
 if(state.product==='saving' && state.rsvtype) items = items.filter(g => g.rsv === state.rsvtype);
 const q = state.q.trim().toLowerCase();
 if(q) items = items.filter(g => (g.product+' '+g.bank+' '+g.rsv).toLowerCase().includes(q));
 if(focus) items = items.filter(g => g.cells[focus]);
 if(state.minrate > 0) items = items.filter(g => {
  const v = focus ? (g.cells[focus]?g.cells[focus].mx||0:0) : bestMax(g);
  return v >= state.minrate;
 });

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
 const conds = [];
 if(state.online) conds.push('비대면');
 if(state.ratetype) conds.push(state.ratetype);
 if(state.joindeny === '1') conds.push('누구나');
 if(state.product==='saving' && state.rsvtype) conds.push(state.rsvtype);
 if(state.minrate > 0) conds.push(state.minrate+'%↑');
 const onLbl = conds.length ? ' · ' + conds.join(' · ') : '';

 if(!items.length){
  view.innerHTML = `<h2>${esc(title)} · ${pname}${focusLbl}${onLbl}</h2>`+
   `<p class="empty">조건에 맞는 상품이 없어요. 필터를 조금 줄여보세요.</p>`;
  renderTrend(); renderTray(); renderOverlay(); applyView(); return;
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
 renderTrend(); renderTray(); renderOverlay(); applyView();
}
initChat();
render();
</script>
</body></html>'''


def _fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _root_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _bank_best(rows):
    """은행별 대표 지표: 전 상품·기간 중 최고우대 최댓값과 기본금리 최댓값."""
    best = {}
    for r in rows:
        mx, base = _fnum(r.get("max_rate")), _fnum(r.get("base_rate"))
        b = best.setdefault(r["bank"], {"max": 0.0, "base": 0.0})
        if mx and mx > b["max"]:
            b["max"] = mx
        if base and base > b["base"]:
            b["base"] = base
    return best


def _seed_history_from_20260629(hist):
    """과거 생성본(금리표_20260629.html)에서 은행별 최고치를 파싱해 시드."""
    import re
    if "2026-06-29" in hist:
        return
    p = os.path.join(_root_dir(), "금리표_20260629.html")
    if not os.path.exists(p):
        return
    h = open(p, encoding="utf-8").read()
    day = {}
    for sec in re.split(r"<h2>", h)[1:]:
        label = ("deposit" if sec.startswith("정기예금")
                 else "saving" if sec.startswith("적금") else None)
        if not label:
            continue
        best = {}
        for tr in re.split(r"<tr", sec):
            mb = re.search(r"class=['\"]bank['\"][^>]*>([^<]+)<", tr)
            if not mb:
                continue
            bank = mb.group(1)
            for base, mx in re.findall(
                    r"class='num'>([\d.]+)%</td><td class='num max'>([\d.]+)%", tr):
                b = best.setdefault(bank, {"max": 0.0, "base": 0.0})
                b["max"] = max(b["max"], float(mx))
                b["base"] = max(b["base"], float(base))
        if best:
            day[label] = best
    if day:
        hist["2026-06-29"] = day


def update_history(out):
    """history.json에 오늘 스냅샷(은행별 최고우대/기본 최댓값) 누적. 반환: 전체 이력."""
    import datetime
    path = os.path.join(_root_dir(), "history.json")
    try:
        hist = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        hist = {}
    _seed_history_from_20260629(hist)
    today = datetime.date.today().isoformat()
    hist[today] = {
        "deposit": _bank_best(out.get("정기예금", [])),
        "saving": _bank_best(out.get("적금", [])),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=1)
    return hist


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
    # 브랜드용 Poppins SemiBold (있으면 임베드)
    pp = os.path.join(fdir, "Poppins-SemiBold.woff2")
    if os.path.exists(pp):
        with open(pp, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        faces.append(
            "@font-face{font-family:'Poppins';font-style:normal;font-weight:600;"
            f"font-display:swap;src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
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
        "history": update_history(out),
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
