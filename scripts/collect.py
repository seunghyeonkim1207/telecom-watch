#!/usr/bin/env python3
"""
Telecom Watch — Daily News Collection Agent
매일 오전 8시(KST) 자동 실행: 국내/해외 통신산업 동향 수집 및 Claude AI 처리
"""
import os, json, hashlib, time
from datetime import datetime, timezone, timedelta
import feedparser
import anthropic

feedparser.USER_AGENT = 'TelecomWatch/1.0 (news aggregator; +https://telecom-watch-chi.vercel.app)'

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime('%Y-%m-%d')
DATA_FILE = 'data/articles.json'

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

# ── 수집 소스 ──────────────────────────────────────────────────────────────────
# Google 뉴스 RSS는 GitHub Actions IP를 차단 → 국내 전문지 직접 RSS 위주로 구성
FEEDS = [
    # ── 국내 전문지 ───────────────────────────────────────────────────────────
    {'url': 'https://rss.etnews.com/Section901.xml',           # 전자신문 IT
     'region': 'domestic', 'country': 'domestic'},
    {'url': 'https://rss.etnews.com/Section902.xml',           # 전자신문 통신방송
     'region': 'domestic', 'country': 'domestic'},
    {'url': 'https://rss.etnews.com/Section903.xml',           # 전자신문 과학기술
     'region': 'domestic', 'country': 'domestic'},
    {'url': 'https://www.sisajournal-e.com/rss/allArticle.xml', # 시사저널e
     'region': 'domestic', 'country': 'domestic'},
    {'url': 'https://digitaltoday.co.kr/rss/allArticle.xml',   # 디지털투데이
     'region': 'domestic', 'country': 'domestic'},
    {'url': 'https://www.itbiznews.com/rss/allArticle.xml',    # IT비즈뉴스
     'region': 'domestic', 'country': 'domestic'},
    {'url': 'https://www.yna.co.kr/rss/economy.xml',           # 연합뉴스 경제
     'region': 'domestic', 'country': 'domestic'},
    {'url': 'https://www.yna.co.kr/rss/industry.xml',          # 연합뉴스 산업
     'region': 'domestic', 'country': 'domestic'},
    # ── 해외 — 통신 전문지 ────────────────────────────────────────────────────
    {'url': 'https://www.fiercewireless.com/rss/xml',          # Fierce Wireless (미국)
     'region': 'overseas', 'country': 'us'},
    {'url': 'https://www.fiercetelecom.com/rss/xml',           # Fierce Telecom (미국)
     'region': 'overseas', 'country': 'us'},
    {'url': 'https://www.rcrwireless.com/feed',                # RCR Wireless (미국)
     'region': 'overseas', 'country': 'us'},
    {'url': 'https://www.lightreading.com/rss.xml',            # Light Reading (글로벌)
     'region': 'overseas', 'country': 'us'},
    {'url': 'https://www.gsma.com/newsroom/feed/',             # GSMA 공식 (글로벌)
     'region': 'overseas', 'country': 'us'},
    {'url': 'https://www.totaltele.com/rss/',                  # Total Telecom (글로벌)
     'region': 'overseas', 'country': 'us'},
    {'url': 'https://www.capacitymedia.com/rss/',              # Capacity Media (글로벌)
     'region': 'overseas', 'country': 'us'},
    # ── 해외 — 일반 IT·비즈니스 (통신 관련 기사 포함) ────────────────────────
    {'url': 'https://feeds.arstechnica.com/arstechnica/tech-policy', # Ars Technica 정책
     'region': 'overseas', 'country': 'us'},
    {'url': 'https://www.theverge.com/rss/index.xml',          # The Verge (미국)
     'region': 'overseas', 'country': 'us'},
    {'url': 'https://feeds.bloomberg.com/technology/news.rss', # Bloomberg Tech
     'region': 'overseas', 'country': 'us'},
    {'url': 'https://feeds.a.dj.com/rss/RSSWSJD.xml',         # WSJ Tech
     'region': 'overseas', 'country': 'us'},
    # ── 국내 — 종합·경제 일간지 (통신 관련 기사 포함) ────────────────────────────
    {'url': 'https://www.chosun.com/arc/outboundfeeds/rss/?outputType=xml',  # 조선일보
     'region': 'domestic', 'country': 'domestic'},
    {'url': 'https://www.mk.co.kr/rss/30000001/',              # 매일경제
     'region': 'domestic', 'country': 'domestic'},
    {'url': 'https://rss.donga.com/total.xml',                 # 동아일보
     'region': 'domestic', 'country': 'domestic'},
    {'url': 'https://www.khan.co.kr/rss/rssdata/total_news.xml', # 경향신문
     'region': 'domestic', 'country': 'domestic'},
    {'url': 'https://www.techm.kr/rss/allArticle.xml',         # 테크M
     'region': 'domestic', 'country': 'domestic'},
]

# Google 뉴스 RSS는 로컬 테스트 시 추가로 활용 (CI에서는 차단됨)
GOOGLE_NEWS_FEEDS = [
    {'url': 'https://news.google.com/rss/search?q=통신+요금제+SKT+KT+LGU플러스&hl=ko&gl=KR&ceid=KR:ko',
     'region': 'domestic', 'country': 'domestic'},
    {'url': 'https://news.google.com/rss/search?q=이용약관+통신사+방통위+과기정통부&hl=ko&gl=KR&ceid=KR:ko',
     'region': 'domestic', 'country': 'domestic'},
    {'url': 'https://news.google.com/rss/search?q=통신+결합상품+리텐션+안면인증&hl=ko&gl=KR&ceid=KR:ko',
     'region': 'domestic', 'country': 'domestic'},
    {'url': 'https://news.google.com/rss/search?q=ATT+Verizon+TMobile+pricing+plan&hl=en-US&gl=US&ceid=US:en',
     'region': 'overseas', 'country': 'us'},
    {'url': 'https://news.google.com/rss/search?q=NTT+Docomo+SoftBank+KDDI+料金&hl=ja&gl=JP&ceid=JP:ja',
     'region': 'overseas', 'country': 'jp'},
]

# CI 환경 감지: GitHub Actions에서 실행 중이면 Google 뉴스 피드 제외
import os as _os
if not _os.environ.get('GITHUB_ACTIONS'):
    FEEDS = FEEDS + GOOGLE_NEWS_FEEDS

RELEVANCE_KEYWORDS = [
    # 한국어 — 핵심 키워드
    '요금', '요금제', '이용약관', '결합', '리텐션', '안면인증', '최적요금제', '번들',
    '방통위', '과기정통부', '알뜰폰', 'MVNO', '해지', '약정',
    # 한국어 — 통신사·업계 일반
    'SKT', 'KT', 'LG U+', 'LGU+', '이동통신', '통신사', '통신요금', '5G', 'LTE',
    '번호이동', '단말기', '데이터', '무제한', '통신비', '가입자', 'MNO', '알뜰통신',
    # 한국어 — 요금·상품 정책
    '선택약정', '공시지원금', '완전자급제', '단통법', '멤버십', '혜택 축소',
    '약관 변경', '서비스 종료', '신규가입 중단', '개편', '고객 보호',
    # 한국어 — 규제·제도
    '전기통신사업법', '단말기유통법', '이용자 보호', '통신분쟁',
    # 한국어 — 시장·경쟁
    '점유율', '가입자 순증', '번호이동 순증',
    # 영어 — 핵심
    'plan', 'pricing', 'tariff', 'retention', 'bundle', 'facial recognition',
    'churn', 'subscriber', 'ARPU', 'contract', 'terms of service',
    # 영어 — 통신 업계
    'telecom', 'wireless', 'spectrum', 'roaming', 'unlimited',
    '5G rollout', 'network slicing', 'eSIM', 'fixed wireless', 'spectrum auction',
    'mobile network', 'carrier', 'operator', 'MVNO', 'MNO',
]

VALID_TAGS = ['요금제', '최적요금제', '리텐션', '결합상품', '이용약관', '안면인증', '규제·정책',
             '통신사동향', '서비스정책', '단말기·유통', '시장경쟁', '기술·네트워크']

CARRIER_MAP = {
    'domestic': ['SKT', 'KT', 'LG U+', '알뜰폰', '방통위', '과기정통부'],
    'us':       ['AT&T', 'Verizon', 'T-Mobile'],
    'jp':       ['NTT Docomo', 'SoftBank', 'KDDI'],
    'eu':       ['Deutsche Telekom', 'Vodafone', 'Orange', 'BT', 'Telecom Italia'],
    'cn':       ['China Mobile', 'China Unicom', 'China Telecom'],
}

# ── 유틸 함수 ──────────────────────────────────────────────────────────────────

def is_relevant(text: str) -> bool:
    lower = text.lower()
    return any(kw.lower() in lower for kw in RELEVANCE_KEYWORDS)

def article_id(title: str) -> str:
    return hashlib.md5(title.encode('utf-8')).hexdigest()[:12]

def load_existing() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'updated': TODAY, 'articles': []}

# ── Claude API 처리 ────────────────────────────────────────────────────────────

def process_with_claude(title: str, summary: str, country: str) -> dict | None:
    carriers = ', '.join(CARRIER_MAP.get(country, []))
    tags_str = ', '.join(VALID_TAGS)

    prompt = f"""통신산업 뉴스 기사를 분석하고 아래 JSON 형식으로만 응답해. 다른 텍스트 없이 JSON만 출력.

제목: {title}
내용: {summary[:600]}
국가코드: {country}

{{
  "relevant": true 또는 false,
  "title_ko": "한국어 제목. 원문이 한국어면 그대로. 영어/일어면 자연스러운 한국어로 번역.",
  "summary_ko": "한국어 요약 2~3문장. 핵심 수치와 통신업계 시사점 포함.",
  "tags": ["태그1"],
  "carrier": "통신사명 또는 빈문자열",
  "importance": 3
}}

규칙:
- relevant: 아래 중 하나라도 해당하면 true
  · 요금·요금제·이용약관·결합상품·리텐션·안면인증 관련
  · SKT·KT·LG U+·알뜰폰 등 이동통신사 정책·서비스·실적·전략 관련
  · 통신 규제·법률·정책(방통위·과기정통부·전기통신사업법 등) 관련
  · 5G·LTE·네트워크 투자·기술 동향 관련
  · 단말기 유통·공시지원금·자급제 관련
  · 해외 이통사 요금·정책·경쟁 동향으로 국내 벤치마킹 가치 있는 것
- tags: 다음 중만 사용 → {tags_str}
- carrier: 다음 중만 사용 → {carriers}
- importance: 1~5 정수 (5=즉시 대응 필요, 4=중요 참고, 3=일반 참고, 2=낮음, 1=매우 낮음)"""

    try:
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=700,
            messages=[{'role': 'user', 'content': prompt}]
        )
        text = msg.content[0].text.strip()
        # 코드블록 제거
        if '```' in text:
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        print(f'  ⚠️  Claude 처리 오류: {e}')
        return None

# ── 메인 수집 함수 ─────────────────────────────────────────────────────────────

def collect():
    print(f'\n🔍 Telecom Watch 수집 시작 — {TODAY}')
    existing = load_existing()
    existing_ids = {a['id'] for a in existing['articles']}
    new_articles = []

    for feed_info in FEEDS:
        print(f'\n📡 {feed_info["url"][:70]}...')
        try:
            feed = feedparser.parse(feed_info['url'])
            entries = feed.entries[:20]  # 소스당 최대 20개
            print(f'  → {len(entries)}건 수신')

            for entry in entries:
                title   = getattr(entry, 'title', '').strip()
                summary = getattr(entry, 'summary', getattr(entry, 'description', '')).strip()
                link    = getattr(entry, 'link', '')

                # 1차 관련성 필터
                if not title or not is_relevant(title + ' ' + summary):
                    continue

                # 중복 확인
                aid = article_id(title)
                if aid in existing_ids:
                    print(f'  ⏭  중복 건너뜀: {title[:40]}')
                    continue

                print(f'  ✅ 처리 중: {title[:50]}')

                # Claude AI 처리
                result = process_with_claude(title, summary, feed_info['country'])
                if not result or not result.get('relevant'):
                    print(f'  ❌ 관련 없음 — 제외')
                    continue

                new_articles.append({
                    'id':          aid,
                    'title':       result.get('title_ko', title),
                    'summary':     result.get('summary_ko', summary[:300]),
                    'tags':        [t for t in result.get('tags', []) if t in VALID_TAGS],
                    'region':      feed_info['region'],
                    'country':     feed_info['country'],
                    'carrier':     result.get('carrier', ''),
                    'importance':  int(result.get('importance', 3)),
                    'date':        TODAY,
                    'source_url':  link,
                    'source_name': feed.feed.get('title', ''),
                })
                existing_ids.add(aid)
                time.sleep(0.8)  # API 레이트 리밋 방지

        except Exception as e:
            print(f'  ❌ 피드 수집 오류: {e}')
            continue

    # ── 저장 ──────────────────────────────────────────────────────────────────
    print(f'\n💾 새 기사 {len(new_articles)}건 수집 완료')

    all_articles = new_articles + existing['articles']
    # 최신순 정렬, 최대 300건 유지
    all_articles = sorted(all_articles, key=lambda x: x['date'], reverse=True)[:300]

    os.makedirs('data', exist_ok=True)
    output = {
        'updated': datetime.now(KST).isoformat(),
        'articles': all_articles
    }
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f'✅ data/articles.json 저장 완료 (총 {len(all_articles)}건)')


# ── 법안 요약 수집 ─────────────────────────────────────────────────────────────

BILL_API_BASE = 'https://open.assembly.go.kr/portal/openapi/nzmimeepazxkubdpn'
BILL_SUMMARY_FILE = 'data/bill_summaries.json'
BILLS_FILE = 'data/bills.json'   # 제안이유 본문 포함 통신 법안 코퍼스
# 통신 관련 법안 풀을 구성하기 위한 의안명 검색어 (OPEN API는 의안명만 검색 가능).
# 이 풀 안에서 화면이 사용자 키워드를 의안명+제안이유에 매칭한다.
BILL_SEARCH_TERMS = ['전기통신사업법', '이동통신', '통신요금', '통신비', '알뜰폰',
                     '정보통신', '방송통신', '단말기', '전기통신', '부가통신']


def is_bill_relevant(name: str) -> bool:
    # fetch_bills 자체가 통신 관련 법안만 가져오므로 모두 통과
    return bool(name)


def fetch_bills(api_key: str) -> list:
    import requests as req
    all_rows = {}
    for term in BILL_SEARCH_TERMS:
        params = {'KEY': api_key, 'Type': 'json', 'pIndex': 1, 'pSize': 100, 'AGE': 22, 'BILL_NAME': term}
        try:
            r = req.get(BILL_API_BASE, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            svc_key = [k for k in data if k != 'RESULT'][0]
            for item in data[svc_key]:
                if 'row' in item:
                    for b in item['row']:
                        bid = b.get('BILL_ID', '')
                        if bid:
                            all_rows[bid] = b
                    break
        except Exception as e:
            print(f'  ⚠️  법안 API 오류 ({term}): {e}')
    return list(all_rows.values())


def _extract_reason(txt: str) -> str | None:
    """정제된 텍스트에서 제안이유 섹션부터 잘라 반환."""
    idx = txt.find('제안이유')
    if idx < 0:
        idx = txt.find('주요내용')
    if idx >= 0:
        return txt[idx:idx+2500]
    return None


def _fetch_via_billinfo(bill_id: str) -> str | None:
    """방법1: billDetail.do(쿠키+csrf) → billInfo.do POST 로 fragment 획득."""
    import requests as req, re
    detail_url = f'https://likms.assembly.go.kr/bill/billDetail.do?billId={bill_id}'
    info_url = 'https://likms.assembly.go.kr/bill/bi/bill/detail/billInfo.do'
    s = req.Session()
    s.headers.update({'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'ko-KR,ko;q=0.9'})
    html = s.get(detail_url, timeout=12).text
    params = {}
    for inp in re.findall(r'<input[^>]+type="hidden"[^>]*>', html):
        n = re.search(r'name="([^"]+)"', inp)
        v = re.search(r'value="([^"]*)"', inp)
        if n:
            params[n.group(1)] = v.group(1) if v else ''
    if not params.get('billId'):
        params['billId'] = bill_id
    frag = s.post(info_url, data=params, timeout=12, headers={
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': detail_url,
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    }).text
    txt = re.sub(r'<[^>]+>', ' ', frag)
    txt = txt.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    txt = re.sub(r'\s+', ' ', txt).strip()
    return _extract_reason(txt)


def _fetch_via_jina(bill_id: str) -> str | None:
    """방법2: r.jina.ai 리더로 JS 렌더링된 본문 마크다운 획득 (폴백)."""
    import requests as req, re
    target = f'https://likms.assembly.go.kr/bill/billDetail.do?billId={bill_id}'
    md = req.get('https://r.jina.ai/' + target, timeout=30,
                 headers={'User-Agent': 'Mozilla/5.0'}).text
    txt = re.sub(r'\s+', ' ', md).strip()
    return _extract_reason(txt)


def fetch_bill_text(bill: dict) -> str | None:
    """국회 의안정보시스템에서 제안이유·주요내용 텍스트 추출.

    billDetail.do 는 JS 렌더링이라 정적 HTML에 본문이 없음.
    방법1(billInfo.do POST) → 실패 시 방법2(jina 리더) 순으로 시도.
    """
    bill_id = bill.get('BILL_ID', '')
    if not bill_id:
        return None
    for method in (_fetch_via_billinfo, _fetch_via_jina):
        try:
            result = method(bill_id)
            if result and len(result) > 100:
                return result
        except Exception as e:
            print(f'  ⚠️  {method.__name__} 실패: {e}')
    return None


def summarize_from_text(raw_text: str) -> str | None:
    """크롤링된 제안이유·주요내용 텍스트를 2~3문장으로 요약."""
    if not raw_text or len(raw_text) <= 100:
        return None
    prompt = f"""다음은 국회 법안 페이지의 제안이유·주요내용 텍스트입니다. 통신업계 실무자 관점에서 2~3문장으로 간결하게 요약해줘. 요약문만 출력하고, 다른 안내 문구는 절대 넣지 마.

{raw_text}"""
    try:
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=220,
            messages=[{'role': 'user', 'content': prompt}]
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f'  ⚠️  요약 오류: {e}')
        return None


def _is_recent_bill(b: dict) -> bool:
    """2025년 이후 발의 또는 진행된 법안만 대상."""
    propose_dt = b.get('PROPOSE_DT', '').replace('-', '')
    activity_dates = [b.get('CURR_COMMITTEE_DT', ''), b.get('COMMITTEE_DT', ''),
                      b.get('LAW_PROC_DT', ''), b.get('PROC_DT', '')]
    recent_activity = any(d.replace('-', '') >= '20250101' for d in activity_dates if d)
    recent_propose = propose_dt >= '20250101' if propose_dt else False
    return recent_propose or recent_activity


def bill_corpus_collect():
    """통신 법안 풀을 구성하고 각 법안의 제안이유 본문 + 요약을 data/bills.json 에 저장.

    - 화면은 이 코퍼스를 받아 사용자 키워드를 의안명+제안이유에 매칭해 필터링한다.
    - 이미 본문·요약이 있는 법안은 재크롤링/재요약하지 않고 캐시 재사용한다.
    - data/bill_summaries.json 도 함께 갱신(기존 화면 호환).
    """
    assembly_key = os.environ.get('ASSEMBLY_API_KEY', '')
    if not assembly_key:
        print('\n⏭  ASSEMBLY_API_KEY 없음 — 법안 수집 건너뜀')
        return
    has_claude = bool(os.environ.get('ANTHROPIC_API_KEY', ''))

    print('\n📋 법안 코퍼스 수집 시작')

    # 기존 코퍼스 로드 (본문·요약 캐시 재사용)
    prev_by_id: dict = {}
    if os.path.exists(BILLS_FILE):
        try:
            with open(BILLS_FILE, 'r', encoding='utf-8') as f:
                for it in json.load(f):
                    if it.get('BILL_ID'):
                        prev_by_id[it['BILL_ID']] = it
        except Exception:
            prev_by_id = {}

    rows = fetch_bills(assembly_key)
    print(f'  → {len(rows)}건 수신 (검색어 {len(BILL_SEARCH_TERMS)}개)')

    corpus = []
    summaries = {}
    new_crawls = 0
    for b in rows:
        bill_id = b.get('BILL_ID', '')
        if not bill_id or b.get('PROM_DT'):   # 공포 완료 제외
            continue
        if not _is_recent_bill(b):
            continue

        prev = prev_by_id.get(bill_id)
        reason = (prev or {}).get('REASON_TEXT', '')
        summary = (prev or {}).get('SUMMARY', '')

        # 본문이 아직 없으면 크롤링 (+ 요약)
        if not reason:
            reason = fetch_bill_text(b) or ''
            if reason and has_claude:
                print(f'  ✅ 본문·요약 생성: {b.get("BILL_NAME","")[:40]}')
                summary = summarize_from_text(reason) or ''
                new_crawls += 1
                time.sleep(0.5)

        entry = dict(b)              # API 원본 필드 전부 패스스루
        entry['REASON_TEXT'] = reason
        entry['SUMMARY'] = summary
        corpus.append(entry)
        if summary:
            summaries[bill_id] = {
                'summary': summary,
                'bill_name': b.get('BILL_NAME', ''),
                'updated': (prev or {}).get('SUMMARY_UPDATED', TODAY),
            }

    os.makedirs('data', exist_ok=True)
    with open(BILLS_FILE, 'w', encoding='utf-8') as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)
    with open(BILL_SUMMARY_FILE, 'w', encoding='utf-8') as f:
        json.dump(summaries, f, ensure_ascii=False, indent=2)
    print(f'✅ bills.json 저장 ({len(corpus)}건, 신규 크롤링 {new_crawls}건) / 요약 {len(summaries)}건')


if __name__ == '__main__':
    collect()
    bill_corpus_collect()
