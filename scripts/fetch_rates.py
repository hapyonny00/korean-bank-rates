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

<div class="controls">
 <div class="seg" id="seg">
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
 <div class="chips" id="chips"></div>
</div>

<div id="view"></div>

<p class="legend">큰 숫자=<b>기본금리(%)</b>, 작은 숫자=최고우대금리(%) ·
 은행 칩으로 골라보고 예금/적금을 전환하세요 · 빈칸(·)은 해당 기간 미판매 ·
 맨 오른쪽 열에서 우대조건 확인</p>

<script>
const APP = __DATA__;
const state = {product:'deposit', banks:new Set()};  // 빈 Set = 전체
const esc = s => String(s==null?'':s).replace(/[&<>"]/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const isNum = v => /^\d+$/.test(String(v));
const bestMax = g => Math.max(0, ...Object.values(g.cells).map(c => c.mx||0));

function pivot(rows){
 const terms = [...new Set(rows.filter(r => isNum(r.term_months))
   .map(r => +r.term_months))].sort((a,b) => a-b);
 const groups = new Map();
 for(const r of rows){
  if(!isNum(r.term_months)) continue;
  const key = r.bank+'¦'+r.product+'¦'+(r.reserve_type||'');
  let g = groups.get(key);
  if(!g){ g={bank:r.bank, product:r.product, rsv:r.reserve_type||'', cells:{}, spcl:''};
   groups.set(key,g); }
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
 // 세그먼트
 document.querySelectorAll('#seg button').forEach(b => {
  b.classList.toggle('on', b.dataset.p === state.product);
  b.onclick = () => { state.product = b.dataset.p; render(); };
 });
 // 은행 칩 (다중 선택 — 빈 선택 = 전체)
 const chipEl = document.getElementById('chips');
 const allOn = state.banks.size === 0;
 chipEl.innerHTML =
  `<button class="chip${allOn?' on':''}" data-b="__ALL__">전체</button>` +
  APP.banks.map(b =>
   `<button class="chip${state.banks.has(b)?' on':''}" data-b="${esc(b)}">${esc(b)}</button>`
  ).join('');
 chipEl.querySelectorAll('button').forEach(btn => btn.onclick = () => {
  const b = btn.dataset.b;
  if(b === '__ALL__') state.banks.clear();
  else state.banks.has(b) ? state.banks.delete(b) : state.banks.add(b);
  render();
 });

 // 데이터 필터 + 피벗
 let rows = APP[state.product] || [];
 if(state.banks.size) rows = rows.filter(r => state.banks.has(r.bank));
 const {terms, arr} = pivot(rows);
 const view = document.getElementById('view');
 const pname = state.product === 'deposit' ? '정기예금' : '적금';
 const title = state.banks.size === 0 ? '전체 은행'
   : APP.banks.filter(b => state.banks.has(b)).join(', ');

 if(!arr.length){
  view.innerHTML = `<h2>${esc(title)} · ${pname}</h2>`+
   `<p class="empty">해당 조건의 상품이 없습니다.</p>`;
  return;
 }
 const showBank = state.banks.size !== 1;
 const ths = terms.map(t => `<th class="num">${t}개월</th>`).join('');
 let trs = '', prevBank = null;
 for(const g of arr){
  const sep = (showBank && prevBank && g.bank !== prevBank) ? ' rowsep' : '';
  prevBank = g.bank;
  const tag = g.rsv ? ` <span class="tag">${esc(g.rsv)}</span>` : '';
  let cells = '';
  for(const t of terms){
   const c = g.cells[t];
   if(!c){ cells += `<td class="num cempty" data-label="${t}개월">·</td>`; continue; }
   cells += `<td class="num" data-label="${t}개월">`+
    `<span class="b">${c.base==null?'-':c.base}</span>`+
    `<span class="m">최고 ${c.mx==null?'-':c.mx}</span></td>`;
  }
  const bankCell = showBank ? `<td class="bank" data-label="은행">${esc(g.bank)}</td>` : '';
  trs += `<tr class="${sep.trim()}">${bankCell}`+
   `<td class="prod" data-label="상품">${esc(g.product)}${tag}</td>`+
   `${cells}<td class="spcl" data-label="우대조건">${esc(g.spcl||'-')}</td></tr>`;
 }
 const bankTh = showBank ? '<th>은행</th>' : '';
 view.innerHTML = `<h2>${esc(title)} · ${pname} <small>· ${arr.length}개 상품</small></h2>`+
  `<div class="wrap"><table><thead><tr>${bankTh}<th>상품명</th>${ths}`+
  `<th>우대조건</th></tr></thead><tbody>${trs}</tbody></table></div>`;
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
