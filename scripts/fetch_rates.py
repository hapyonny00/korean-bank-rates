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
                         [--term 12] [--json] [--auth KEY]

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


def _fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def write_html(out, path):
    """기간별 비교(피벗) HTML 리포트 생성. 우대조건은 표 안의 열로 표시."""
    import datetime
    import html as _html
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    dcls = next((r["dcls_month"] for rows in out.values() for r in rows), "-")

    def section(label, rows):
        if not rows:
            return f"<h2>{label}</h2><p class='empty'>조회된 상품 없음</p>"

        # 기간 컬럼 수집 (1,3,6,12,24,36 ... 숫자순)
        terms = sorted({int(r["term_months"]) for r in rows
                        if str(r.get("term_months", "")).isdigit()})

        # 행 그룹화: (은행, 상품, 적립유형) -> {기간: (기본, 최고)} + 우대조건
        groups = {}
        spcls = {}
        for r in rows:
            key = (r["bank"], r["product"], r["reserve_type"] or "")
            tm = r["term_months"]
            if not str(tm).isdigit():
                continue
            g = groups.setdefault(key, {})
            base, mx = _fnum(r["base_rate"]), _fnum(r["max_rate"])
            prev = g.get(int(tm))
            if not prev or (mx or 0) > (prev[1] or 0):
                g[int(tm)] = (base, mx)
            # 우대조건: 가장 긴(=가장 자세한) 설명을 대표로 사용
            sp = (r.get("special") or "").strip()
            if len(sp) > len(spcls.get(key, "")):
                spcls[key] = sp

        # 행 정렬: 상품 최고금리 내림차순
        def best(item):
            return max((c[1] or 0) for c in item[1].values())
        ordered = sorted(groups.items(), key=best, reverse=True)

        ths = "".join(f"<th class='num'>{t}개월</th>" for t in terms)
        trs = []
        bank_seen = None
        for (bank, prod, rsv), g in ordered:
            sep = " rowsep" if bank_seen and bank != bank_seen else ""
            bank_seen = bank
            tag = f" <span class='tag'>{rsv}</span>" if rsv else ""
            cells = []
            for t in terms:
                c = g.get(t)
                if not c:
                    cells.append(f"<td class='num cempty' data-label='{t}개월'>·</td>")
                    continue
                base, mx = c
                cells.append(
                    f"<td class='num' data-label='{t}개월'>"
                    f"<b>{mx if mx is not None else '-'}</b>"
                    f"<span class='base'>{base if base is not None else '-'}</span></td>")
            spcl = _html.escape(spcls.get((bank, prod, rsv), "") or "-")
            trs.append(
                f"<tr class='{sep.strip()}'><td class='bank' data-label='은행'>{bank}</td>"
                f"<td class='prod' data-label='상품'>{prod}{tag}</td>{''.join(cells)}"
                f"<td class='spcl' data-label='우대조건'>{spcl}</td></tr>")

        return (f"<h2>{label} <small>· {len(ordered)}개 상품 · 셀=최고우대"
                f"<span class='base'>기본</span></small></h2>"
                "<div class='wrap'><table><thead><tr>"
                f"<th>은행</th><th>상품명</th>{ths}<th>우대조건</th>"
                "</tr></thead><tbody>" + "".join(trs) + "</tbody></table></div>")

    body = "".join(section(lbl, rows) for lbl, rows in out.items())
    html = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>은행 예·적금 금리</title>
<style>
 :root{{color-scheme:light}}
 body{{font-family:-apple-system,'Apple SD Gothic Neo',sans-serif;margin:0;
  padding:24px;background:#fff;color:#1a1a1a}}
 h1{{font-size:22px;margin:0 0 4px}}
 h2{{font-size:16px;margin:32px 0 6px}}
 h2 small{{font-weight:400;color:#888;font-size:12px}}
 .meta{{color:#666;font-size:13px;margin:0}}
 .wrap{{overflow-x:auto;border:1px solid #ececef;border-radius:10px}}
 table{{border-collapse:separate;border-spacing:0;width:100%;font-size:13px}}
 th,td{{padding:7px 10px;text-align:left;border-bottom:1px solid #f0f0f2;
  vertical-align:top}}
 thead th{{background:#fafafb;position:sticky;top:0;z-index:2;color:#555;
  font-weight:600;border-bottom:2px solid #e7e7ea}}
 .num{{text-align:center;white-space:nowrap}}
 td.num b{{font-size:14px;color:#0a5}}
 td.num.empty{{color:#ccc}}
 .base{{display:block;font-size:10px;color:#9a9a9a;font-weight:400;margin-top:1px}}
 .bank{{font-weight:700;white-space:nowrap;color:#2a2a2a}}
 .prod{{color:#333;min-width:180px}}
 .spcl{{color:#666;font-size:12px;line-height:1.45;min-width:280px;
  max-width:420px;white-space:normal}}
 .tag{{font-size:10px;color:#0a5;border:1px solid #bfe6d2;border-radius:4px;
  padding:0 4px;margin-left:4px;vertical-align:middle}}
 tr.rowsep td{{border-top:2px solid #e7e7ea}}
 tbody tr:hover td{{background:#f6f9f7}}
 .empty{{color:#999}}
 .legend{{font-size:12px;color:#888;margin-top:10px}}
 .legend b{{color:#0a5}}

 /* ===== 반응형: 좁은 화면(모바일)에서는 상품별 카드로 ===== */
 @media (max-width:720px){{
  body{{padding:14px}}
  h1{{font-size:18px}}
  .wrap{{border:none;overflow:visible}}
  table,thead,tbody,tr,td{{display:block;width:auto}}
  thead{{display:none}}
  tr{{border:1px solid #e7e7ea;border-radius:12px;margin:0 0 12px;
   padding:10px 12px;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
  tr.rowsep td{{border-top:none}}
  td{{border:none;padding:3px 0;text-align:left;white-space:normal}}
  td.bank{{font-size:15px;font-weight:800;padding-top:0}}
  td.prod{{color:#666;min-width:0;margin-bottom:6px;
   border-bottom:1px dashed #eee;padding-bottom:6px}}
  /* 기간 금리: 라벨 + 값 한 줄 */
  td.num{{display:flex;justify-content:space-between;align-items:baseline;
   text-align:left;border-bottom:1px solid #f4f4f5;padding:5px 0}}
  td.num::before{{content:attr(data-label);color:#999;font-size:12px;
   font-weight:600}}
  td.num b{{font-size:15px}}
  .base{{display:inline;margin:0 0 0 6px;font-size:11px}}
  td.num.cempty{{display:none}}              /* 미판매 기간은 카드에서 숨김 */
  td.spcl{{margin-top:8px;min-width:0;max-width:none;background:#fafafb;
   border-radius:8px;padding:8px 10px}}
  td.spcl::before{{content:'우대조건';display:block;color:#999;
   font-size:11px;font-weight:600;margin-bottom:3px}}
 }}
</style></head><body>
<h1>🏦 한국 은행 예·적금 금리 — 기간별 비교</h1>
<p class="meta">공시기준 {dcls} · 조회시각 {now} ·
 출처: 금융감독원 금융상품통합비교공시</p>
{body}
<p class="legend">셀 큰 숫자=<b>최고우대금리(%)</b>, 작은 숫자=기본금리(%) ·
 같은 상품의 기간별 금리를 가로로 비교하세요 · 빈칸(·)은 해당 기간 미판매 ·
 맨 오른쪽 열에서 우대조건 확인</p>
</body></html>"""
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
                    help="HTML 표 리포트 생성 후 브라우저로 열기 (경로 생략 가능)")
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

    products = (["deposit", "saving"] if args.product == "both"
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
