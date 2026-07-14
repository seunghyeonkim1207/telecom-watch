#!/usr/bin/env python3
"""
Telecom Watch — Daily News Collection Agent
매일 오전 8시(KST) 자동 실행: 국내/해외 통신산업 동향 수집 및 Claude AI 처리
"""
from __future__ import annotations
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

def fetch_article_text(url: str) -> str:
    """기사 페이지에서 본문 텍스트 추출 (요약 생성용 입력으로만 사용 — 저장·게시하지 않음)."""
    import requests as req, re
    if not url:
        return ''
    try:
        r = req.get(url, timeout=8, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'})
        if not r.ok:
            return ''
        html = r.text
        txt = re.sub(r'<script[\s\S]*?</script>', '', html, flags=re.IGNORECASE)
        txt = re.sub(r'<style[\s\S]*?</style>', '', txt, flags=re.IGNORECASE)
        # 본문 영역 우선 추출 (article 태그가 있으면)
        m = re.search(r'<article[\s\S]*?</article>', txt, flags=re.IGNORECASE)
        if m:
            txt = m.group(0)
        txt = re.sub(r'<[^>]+>', ' ', txt)
        txt = txt.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
        txt = re.sub(r'\s+', ' ', txt).strip()
        return txt[:4000]
    except Exception:
        return ''


def batch_relevance(items: list) -> list:
    """기사 여러 건의 관련성을 한 번의 호출로 판별 (비용 절감 — 본문 없이 제목+RSS요약만).
    items: [{'title':..., 'summary':...}] → 관련 있는 인덱스 리스트 반환."""
    lines = []
    for i, it in enumerate(items):
        lines.append(f"[{i}] {it['title']} — {it['summary'][:150]}")
    prompt = ("아래 뉴스 목록에서 한국 이동통신사(SKT·KT·LGU+·알뜰폰) 실무팀에 관련 있는 기사의 번호만 골라줘.\n"
        "관련 기준: 요금·요금제·약관·결합·리텐션 / 이통사 정책·서비스·실적 / 통신 규제·법률(방통위·과기정통부) / "
        "5G·네트워크 / 단말 유통 / 해외 이통사 벤치마킹 가치.\n"
        "단순 IT기기 리뷰, 통신과 무관한 기업 소식, 주가 단신은 제외.\n\n"
        + "\n".join(lines)
        + '\n\nJSON만 출력: {"relevant": [번호, 번호, ...]}')
    try:
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=200,
            messages=[{'role': 'user', 'content': prompt}]
        )
        text = msg.content[0].text.strip()
        if '```' in text:
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        data = json.loads(text.strip())
        return [i for i in data.get('relevant', []) if isinstance(i, int) and 0 <= i < len(items)]
    except Exception as ex:
        print(f'  ⚠️  배치 판별 오류: {ex} — 전체 통과 처리')
        return list(range(len(items)))


def process_with_claude(title: str, summary: str, country: str, body: str = '') -> dict | None:
    carriers = ', '.join(CARRIER_MAP.get(country, []))
    tags_str = ', '.join(VALID_TAGS)

    body_section = f'\n본문(발췌): {body[:1800]}' if body else ''
    prompt = f"""통신산업 뉴스 기사를 분석하고 아래 JSON 형식으로만 응답해. 다른 텍스트 없이 JSON만 출력.

제목: {title}
내용: {summary[:600]}{body_section}
국가코드: {country}

{{
  "relevant": true 또는 false,
  "title_ko": "한국어 제목. 원문이 한국어면 그대로. 영어/일어면 자연스러운 한국어로 번역.",
  "summary_ko": "한국어 요약 2~3문장. 핵심 수치와 통신업계 시사점 포함.",
  "summary_long": "한국어 상세 요약 5~7문장. 본문의 핵심 수치·일정·관계자 발언 요지·배경·통신업계 시사점을 포함해 기사를 안 읽어도 내용을 파악할 수 있게. 반드시 자신의 문장으로 재서술하고 본문 문장을 그대로 베끼지 마.",
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
            max_tokens=1200,
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

    # ── 1단계: 후보 수집 (키워드 필터 + 중복 제거 — API 호출 없음) ──
    candidates = []
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
                if not title or not is_relevant(title + ' ' + summary):
                    continue
                aid = article_id(title)
                if aid in existing_ids:
                    continue
                existing_ids.add(aid)   # 후보 간 중복도 방지
                candidates.append({
                    'id': aid, 'title': title, 'summary': summary, 'link': link,
                    'region': feed_info['region'], 'country': feed_info['country'],
                    'source_name': feed.feed.get('title', ''),
                })
        except Exception as e:
            print(f'  ❌ 피드 수집 오류: {e}')
            continue

    print(f'\n🧮 후보 {len(candidates)}건 — 배치 관련성 판별 시작 (비용 절감 2단계 구조)')

    # ── 2단계: 12건씩 묶어 관련성 판별 (제목+요약만, 저비용) ──
    relevant_items = []
    BATCH = 12
    for i in range(0, len(candidates), BATCH):
        chunk = candidates[i:i+BATCH]
        keep = batch_relevance(chunk)
        for idx in keep:
            relevant_items.append(chunk[idx])
        time.sleep(0.5)
    print(f'  → 관련 판정 {len(relevant_items)}건 / 후보 {len(candidates)}건')

    # ── 3단계: 관련 기사만 본문 크롤링 + 상세 처리 (하루 최대 60건 상한) ──
    MAX_DETAIL = 60
    for c in relevant_items[:MAX_DETAIL]:
        print(f'  ✅ 처리 중: {c["title"][:50]}')
        body = fetch_article_text(c['link'])
        result = process_with_claude(c['title'], c['summary'], c['country'], body)
        if not result or not result.get('relevant'):
            print(f'  ❌ 상세 검토에서 제외')
            continue
        new_articles.append({
            'id':          c['id'],
            'title':       result.get('title_ko', c['title']),
            'summary':     result.get('summary_ko', c['summary'][:300]),
            'summary_long': result.get('summary_long', ''),
            'tags':        [t for t in result.get('tags', []) if t in VALID_TAGS],
            'region':      c['region'],
            'country':     c['country'],
            'carrier':     result.get('carrier', ''),
            'importance':  int(result.get('importance', 3)),
            'date':        TODAY,
            'source_url':  c['link'],
            'source_name': c['source_name'],
        })
        time.sleep(0.6)  # API 레이트 리밋 방지

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
    return new_articles


# ── 법안 요약 수집 ─────────────────────────────────────────────────────────────

BILL_API_BASE = 'https://open.assembly.go.kr/portal/openapi/nzmimeepazxkubdpn'
BILL_SUMMARY_FILE = 'data/bill_summaries.json'
BILLS_FILE = 'data/bills.json'   # 제안이유 본문 포함 통신 법안 코퍼스
BILL_CHANGES_FILE = 'data/bill_changes.json'   # 법안 단계 변경 감지 기록
# 단계 변경 감지 대상 필드 (필드명, 표시 라벨)
BILL_STAGE_FIELDS = [
    ('CURR_COMMITTEE_DT', '소관위 회부'),
    ('COMMITTEE_DT', '위원회 의결'),
    ('LAW_PROC_DT', '법사위'),
    ('PROC_DT', '본회의 의결'),
    ('PROC_RESULT', '처리 결과'),
]
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


def summarize_from_text(raw_text: str) -> dict | None:
    """제안이유·주요내용 텍스트 → 요약 + SKT 사업 영향도(JSON)."""
    if not raw_text or len(raw_text) <= 100:
        return None
    prompt = f"""다음은 국회 법안 페이지의 제안이유·주요내용 텍스트입니다. 아래 JSON 형식으로만 응답해. 다른 텍스트 없이 JSON만 출력.

{{
  "summary": "통신업계 실무자 관점 2~3문장 요약 (안내 문구 금지)",
  "impact": "높음" 또는 "중간" 또는 "낮음",
  "impact_reason": "SKT 등 이동통신사 사업 관점에서 왜 그 영향도인지 한 문장",
  "topic": "법안의 핵심 주제 한 단어~두 단어 (예: 다크패턴 금지, 위약금 상한, 불법촬영물, 대포폰 근절, 알뜰폰, 생체정보, 보이스피싱, 플랫폼 규제 등 — 같은 취지 법안이면 같은 주제명이 나오도록 일반적인 표현 사용)"
}}

[영향도 기준]
- 높음: 요금·약관·결합·단말유통·번호이동 등 이동통신사 핵심 사업/수익에 직접 영향
- 중간: 부가통신·플랫폼·이용자보호 등 간접 영향 또는 일부 사업 영향
- 낮음: 통신과 약하게 연관되거나 사업 영향이 미미

[법안 텍스트]
{raw_text}"""
    try:
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=320,
            messages=[{'role': 'user', 'content': prompt}]
        )
        text = msg.content[0].text.strip()
        if '```' in text:
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        data = json.loads(text.strip())
        if not data.get('summary'):
            return None
        if data.get('impact') not in ('높음', '중간', '낮음'):
            data['impact'] = '중간'
        return data
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

    # 방어: API 실패로 0건이거나 기존 대비 절반 미만으로 급감하면
    # 빈/부실 데이터로 덮어쓰지 않고 기존 코퍼스를 유지한다.
    if not rows or (prev_by_id and len(rows) < len(prev_by_id) * 0.5):
        print(f'  ⚠️  수신 {len(rows)}건 < 기존 {len(prev_by_id)}건의 50% — 기존 코퍼스 유지, 저장 건너뜀')
        return

    corpus = []
    summaries = {}
    new_crawls = 0
    changes = []   # 이번 실행에서 감지된 단계 변경
    for b in rows:
        bill_id = b.get('BILL_ID', '')
        if not bill_id or b.get('PROM_DT'):   # 공포 완료 제외
            continue
        if not _is_recent_bill(b):
            continue

        prev = prev_by_id.get(bill_id)
        # 단계 변경 감지: 이전 코퍼스와 비교해 진행 단계·처리결과가 달라졌으면 기록
        if prev:
            for field, label in BILL_STAGE_FIELDS:
                old_v = prev.get(field) or ''
                new_v = b.get(field) or ''
                if new_v and new_v != old_v:
                    changes.append({
                        'bill_id': bill_id,
                        'bill_name': b.get('BILL_NAME', ''),
                        'field': field,
                        'label': label,
                        'old': old_v,
                        'new': new_v,
                        'detected': TODAY,
                    })
        reason = (prev or {}).get('REASON_TEXT', '')
        summary = (prev or {}).get('SUMMARY', '')
        impact = (prev or {}).get('IMPACT', '')
        impact_reason = (prev or {}).get('IMPACT_REASON', '')
        topic = (prev or {}).get('TOPIC', '')

        # 본문이 아직 없으면 크롤링
        if not reason:
            reason = fetch_bill_text(b) or ''
            if reason:
                new_crawls += 1
                time.sleep(0.4)
        # 요약·영향도·주제 중 비어 있는 게 있으면 생성/백필 (본문 있을 때)
        if reason and has_claude and (not summary or not impact or not topic):
            print(f'  ✅ 요약·영향도·주제 생성: {b.get("BILL_NAME","")[:40]}')
            res = summarize_from_text(reason)
            if res:
                summary = res.get('summary', '')
                impact = res.get('impact', '')
                impact_reason = res.get('impact_reason', '')
                topic = res.get('topic', '') or topic
            time.sleep(0.4)

        entry = dict(b)              # API 원본 필드 전부 패스스루
        entry['REASON_TEXT'] = reason
        entry['SUMMARY'] = summary
        entry['IMPACT'] = impact
        entry['IMPACT_REASON'] = impact_reason
        entry['TOPIC'] = topic
        corpus.append(entry)
        if summary:
            summaries[bill_id] = {
                'summary': summary,
                'impact': impact,
                'impact_reason': impact_reason,
                'bill_name': b.get('BILL_NAME', ''),
                'updated': (prev or {}).get('SUMMARY_UPDATED', TODAY),
            }

    os.makedirs('data', exist_ok=True)
    with open(BILLS_FILE, 'w', encoding='utf-8') as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)
    with open(BILL_SUMMARY_FILE, 'w', encoding='utf-8') as f:
        json.dump(summaries, f, ensure_ascii=False, indent=2)
    # 단계 변경 기록 저장 (기존 기록 앞에 추가, 최대 50건)
    if changes:
        old_changes = []
        if os.path.exists(BILL_CHANGES_FILE):
            try:
                with open(BILL_CHANGES_FILE, 'r', encoding='utf-8') as f:
                    old_changes = json.load(f)
            except Exception:
                old_changes = []
        with open(BILL_CHANGES_FILE, 'w', encoding='utf-8') as f:
            json.dump((changes + old_changes)[:50], f, ensure_ascii=False, indent=2)
        print(f'🔔 법안 단계 변경 {len(changes)}건 감지')
    print(f'✅ bills.json 저장 ({len(corpus)}건, 신규 크롤링 {new_crawls}건) / 요약 {len(summaries)}건')


# ── 규제 일정 자동 추출 ─────────────────────────────────────────────────────────

CALENDAR_FILE = 'data/calendar.json'
MAX_CAL_EVENTS = 80


def extract_calendar_events(new_articles: list):
    """오늘 수집 기사에서 미래의 규제·통신 일정을 추출해 calendar.json에 병합."""
    if not new_articles or not os.environ.get('ANTHROPIC_API_KEY', ''):
        return
    lines = [f"- {a.get('title','')} :: {a.get('summary','')[:150]}" for a in new_articles[:40]]
    prompt = (f"오늘 날짜는 {TODAY}입니다. 아래 통신산업 뉴스들에서 '앞으로 예정된 구체적 일정'만 추출해줘.\n"
        "대상: 제도/요금제 시행일, 신규가입 중단일, 공청회·간담회, 국회/방통위/과기정통부 일정, 의견수렴 마감일 등.\n"
        "이미 지난 일정, 날짜가 불명확한 것('조만간', '하반기 중')은 제외. 연도가 없으면 문맥상 가장 가까운 미래로 판단.\n\n"
        + "\n".join(lines)
        + '\n\nJSON만 출력: {"events": [{"date": "YYYY-MM-DD", "title": "일정 제목 (간결하게)", "org": "주체 기관/회사"}]}\n'
        "확실한 일정이 없으면 events는 빈 배열.")
    try:
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=800,
            messages=[{'role': 'user', 'content': prompt}]
        )
        text = msg.content[0].text.strip()
        if '```' in text:
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        events = json.loads(text.strip()).get('events', [])
    except Exception as ex:
        print(f'  ⚠️  일정 추출 오류: {ex}')
        return

    merge_calendar_events(events, '뉴스 자동추출')


def merge_calendar_events(events: list, source_label: str):
    """추출된 일정을 calendar.json에 중복 없이 병합 (미래 일정만)."""
    if not events:
        return
    cal = []
    if os.path.exists(CALENDAR_FILE):
        try:
            with open(CALENDAR_FILE, 'r', encoding='utf-8') as f:
                cal = json.load(f)
        except Exception:
            cal = []
    existing = {(e.get('date',''), e.get('title','')) for e in cal}
    added = 0
    for ev in events:
        d, t = ev.get('date',''), ev.get('title','')
        if not d or not t or d < TODAY:
            continue
        # 같은 날짜에 비슷한 제목이 이미 있으면 스킵 (앞 10자 비교)
        if (d, t) in existing or any(x[0]==d and x[1][:10]==t[:10] for x in existing):
            continue
        cal.append({'date': d, 'title': t, 'org': ev.get('org',''), 'country': '국내',
                    'imp': 'mid', 'source': 'auto'})
        existing.add((d, t))
        added += 1
    if added:
        cal.sort(key=lambda e: e.get('date',''))
        with open(CALENDAR_FILE, 'w', encoding='utf-8') as f:
            json.dump(cal[-MAX_CAL_EVENTS:], f, ensure_ascii=False, indent=2)
        print(f'📅 규제 일정 {added}건 자동 추가 ({source_label})')


# ── 오늘의 브리핑 (TOP 3) ──────────────────────────────────────────────────────

BRIEFING_FILE = 'data/briefing.json'


def generate_briefing(new_articles: list):
    """오늘 새로 수집된 기사 중 핵심 3건 + 종합 브리핑 한 문단 생성 → data/briefing.json."""
    if not os.environ.get('ANTHROPIC_API_KEY', ''):
        return
    if not new_articles:
        print('\n📰 오늘 새 기사 없음 — 브리핑 생략')
        return

    # 중요도 높은 순으로 후보 추림 (최대 15건)
    cand = sorted(new_articles, key=lambda a: a.get('importance', 3), reverse=True)[:15]
    lines = [f"[{i}] (중요도 {a.get('importance',3)}) {a.get('title','')} — {a.get('summary','')[:160]}"
             for i, a in enumerate(cand)]
    prompt = ("다음은 오늘 수집된 통신산업 뉴스 목록입니다. 통신사 실무자가 아침에 30초로 핵심을 파악하도록,\n"
              "가장 중요한 3건을 고르고 종합 브리핑을 작성해줘. 아래 JSON 형식으로만 응답:\n\n"
              '{\n  "summary": "오늘 동향 종합 2~3문장",\n'
              '  "picks": [{"index": 0, "why": "왜 중요한지 한 문장"}]\n}\n\n'
              "picks는 정확히 3개(기사가 3개 미만이면 그 수만큼). index는 아래 번호.\n\n"
              + "\n".join(lines))
    try:
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=600,
            messages=[{'role': 'user', 'content': prompt}]
        )
        text = msg.content[0].text.strip()
        if '```' in text:
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        data = json.loads(text.strip())
    except Exception as e:
        print(f'  ⚠️  브리핑 생성 오류: {e}')
        return

    picks = []
    for p in data.get('picks', [])[:3]:
        idx = p.get('index')
        if isinstance(idx, int) and 0 <= idx < len(cand):
            a = cand[idx]
            picks.append({'id': a['id'], 'title': a['title'], 'why': p.get('why', '')})
    out = {'date': TODAY, 'summary': data.get('summary', ''), 'picks': picks}
    with open(BRIEFING_FILE, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f'✅ briefing.json 저장 (핵심 {len(picks)}건)')


# ── 텔레그램 알림 ───────────────────────────────────────────────────────────────
# TELEGRAM_CHAT_ID 는 콤마로 여러 개 지정 가능 (개인 + 팀 그룹 동시 발송)
#   예: "123456789,-1001234567890"  (그룹/채널 ID는 음수)

def tg_chat_ids():
    raw = os.environ.get('TELEGRAM_CHAT_ID', '')
    return [c.strip() for c in raw.split(',') if c.strip()]


def tg_send(text: str) -> bool:
    """등록된 모든 채팅방으로 텍스트 메시지 발송."""
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    ids = tg_chat_ids()
    if not token or not ids:
        return False
    import requests as req
    ok = False
    for cid in ids:
        try:
            r = req.post(f'https://api.telegram.org/bot{token}/sendMessage', json={
                'chat_id': cid, 'text': text, 'parse_mode': 'Markdown',
                'disable_web_page_preview': True,
            }, timeout=15)
            ok = ok or r.ok
            if not r.ok:
                print(f'  ⚠️  텔레그램 발송 실패({cid}): {r.status_code} {r.text[:100]}')
        except Exception as ex:
            print(f'  ⚠️  텔레그램 오류({cid}): {ex}')
    return ok


def tg_send_document(filepath: str, caption: str = '') -> bool:
    """등록된 모든 채팅방으로 파일 첨부 발송 (워드 보고서 등)."""
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    ids = tg_chat_ids()
    if not token or not ids or not os.path.exists(filepath):
        return False
    import requests as req
    ok = False
    for cid in ids:
        try:
            with open(filepath, 'rb') as f:
                r = req.post(f'https://api.telegram.org/bot{token}/sendDocument',
                    data={'chat_id': cid, 'caption': caption[:1000]},
                    files={'document': (os.path.basename(filepath), f, 'application/msword')},
                    timeout=30)
            ok = ok or r.ok
            if not r.ok:
                print(f'  ⚠️  파일 발송 실패({cid}): {r.status_code} {r.text[:100]}')
        except Exception as ex:
            print(f'  ⚠️  파일 발송 오류({cid}): {ex}')
    return ok


def send_telegram_alert(new_articles: list):
    """중요도 5 기사 + 신규 발의 통신 법안을 텔레그램으로 발송.
    TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 시크릿이 없으면 조용히 건너뜀."""
    if not os.environ.get('TELEGRAM_BOT_TOKEN', '') or not tg_chat_ids():
        print('\n⏭  텔레그램 시크릿 없음 — 알림 생략')
        return

    urgent = [a for a in new_articles if a.get('importance', 3) >= 5]

    # 오늘 신규 발의된 통신 법안
    new_bills = []
    if os.path.exists(BILLS_FILE):
        try:
            with open(BILLS_FILE, 'r', encoding='utf-8') as f:
                for b in json.load(f):
                    if b.get('PROPOSE_DT', '').replace('-', '') == TODAY.replace('-', ''):
                        new_bills.append(b)
        except Exception:
            pass

    # 오늘 감지된 법안 단계 변경
    stage_changes = []
    if os.path.exists(BILL_CHANGES_FILE):
        try:
            with open(BILL_CHANGES_FILE, 'r', encoding='utf-8') as f:
                stage_changes = [c for c in json.load(f) if c.get('detected') == TODAY]
        except Exception:
            pass

    # 국제비교 소스 인용 보도 감지 (오늘 새 기사 중 소스 키워드 언급)
    intl_mentions = []
    try:
        with open('data/intl.json', 'r', encoding='utf-8') as f:
            intl_items = json.load(f).get('items', [])
        for a in new_articles:
            hay = (a.get('title', '') + ' ' + a.get('summary', '')).lower()
            for it in intl_items:
                # 짧고 흔한 키워드(ITU/OECD 단독)는 기관명이 제목에 있을 때만 매칭
                kws = [k for k in it.get('keywords', []) if len(k) >= 3]
                if any(k.lower() in hay for k in kws):
                    intl_mentions.append({'article': a, 'source': it.get('org', '')})
                    break
    except Exception:
        pass

    # 다가오는 규제 일정 (D-7 이내) — data/calendar.json 기준
    upcoming = []
    try:
        from datetime import date
        today_d = datetime.now(KST).date()
        with open('data/calendar.json', 'r', encoding='utf-8') as f:
            for ev in json.load(f):
                try:
                    ev_d = date.fromisoformat(ev.get('date', ''))
                except Exception:
                    continue
                diff = (ev_d - today_d).days
                if 0 <= diff <= 7:
                    upcoming.append((diff, ev))
        upcoming.sort(key=lambda x: x[0])
    except Exception:
        pass

    # ① 오늘의 브리핑 (있으면 항상 포함)
    briefing = None
    try:
        with open(BRIEFING_FILE, 'r', encoding='utf-8') as f:
            b = json.load(f)
        if b.get('date') == TODAY and b.get('summary'):
            briefing = b
    except Exception:
        pass

    if not urgent and not new_bills and not stage_changes and not intl_mentions and not upcoming and not briefing:
        print('\n📭 알릴 내용 없음 — 알림 생략')
        return

    parts = [f"📡 *텔레콤워치 일일 알림* ({TODAY})", ""]
    if briefing:
        parts.append("🌅 *오늘의 브리핑*")
        parts.append(briefing.get('summary', ''))
        for p in briefing.get('picks', [])[:3]:
            parts.append(f"▸ {p.get('title','')}")
            if p.get('why'):
                parts.append(f"   └ {p['why']}")
        parts.append("")
    if urgent:
        parts.append(f"🔴 *긴급 뉴스 {len(urgent)}건*")
        for a in urgent[:5]:
            parts.append(f"• {a.get('title','')}")
        parts.append("")
    if stage_changes:
        parts.append(f"⚖️ *법안 단계 변경 {len(stage_changes)}건*")
        for c in stage_changes[:5]:
            parts.append(f"• {c.get('bill_name','')[:40]} → {c.get('label','')} ({c.get('new','')})")
        parts.append("")
    if new_bills:
        parts.append(f"📋 *신규 발의 법안 {len(new_bills)}건*")
        for b in new_bills[:5]:
            parts.append(f"• {b.get('BILL_NAME','')}")
        parts.append("")
    if intl_mentions:
        parts.append(f"🌐 *국제비교 인용 보도 감지 {len(intl_mentions)}건*")
        for m in intl_mentions[:4]:
            parts.append(f"• [{m['source']}] {m['article'].get('title','')[:45]}")
        parts.append("")
    if upcoming:
        parts.append(f"📅 *다가오는 규제 일정*")
        for diff, ev in upcoming[:5]:
            dd = 'D-Day' if diff == 0 else f'D-{diff}'
            parts.append(f"• ({dd}) {ev.get('title','')}")
    message = "\n".join(parts)

    if tg_send(message):
        print(f'✅ 텔레그램 알림 발송 (브리핑 {1 if briefing else 0} / 긴급 {len(urgent)} / 변경 {len(stage_changes)} / 신규법안 {len(new_bills)} / 인용 {len(intl_mentions)} / 일정 {len(upcoming)})')


def send_weekly_report():
    """매주 금요일: 주간 요약 리포트를 텔레그램으로 발송."""
    if datetime.now(KST).weekday() != 4:   # 금요일만
        return
    if not os.environ.get('TELEGRAM_BOT_TOKEN', '') or not tg_chat_ids():
        return
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            arts = json.load(f).get('articles', [])
    except Exception:
        return
    from datetime import date, timedelta as td
    today_d = datetime.now(KST).date()
    monday = today_d - td(days=today_d.weekday())
    week = [a for a in arts if a.get('date', '') >= monday.isoformat()]
    dom = [a for a in week if a.get('region') == 'domestic']
    top5 = sorted(week, key=lambda a: a.get('importance', 3), reverse=True)[:5]

    changes = []
    try:
        with open(BILL_CHANGES_FILE, 'r', encoding='utf-8') as f:
            cutoff = (today_d - td(days=7)).isoformat()
            changes = [c for c in json.load(f) if c.get('detected', '') >= cutoff]
    except Exception:
        pass

    parts = [f"📊 *주간 리포트* ({monday.isoformat()} ~ {TODAY})", ""]
    parts.append(f"이번 주 수집: 총 {len(week)}건 (국내 {len(dom)} / 해외 {len(week)-len(dom)})")
    if top5:
        parts.append("")
        parts.append("*주요 기사 TOP 5*")
        for a in top5:
            parts.append(f"• {a.get('title','')[:50]}")
    if changes:
        parts.append("")
        parts.append(f"*법안 진행 변동 {len(changes)}건*")
        for c in changes[:5]:
            parts.append(f"• {c.get('bill_name','')[:35]} → {c.get('label','')}")
    parts.append("")
    parts.append("상세: https://telecom-watch-chi.vercel.app")
    if tg_send("\n".join(parts)):
        print('✅ 주간 리포트 발송 (금요일)')


if __name__ == '__main__':
    new_articles = collect() or []
    bill_corpus_collect()
    extract_calendar_events(new_articles)
    generate_briefing(new_articles)
    send_telegram_alert(new_articles)
    send_weekly_report()
