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
    # ── 국내 전문지 직접 RSS (GitHub Actions에서 안정적으로 작동) ──────────────
    {'url': 'https://rss.etnews.com/Section901.xml',          # 전자신문 IT
     'region': 'domestic', 'country': 'domestic'},
    {'url': 'https://rss.etnews.com/Section902.xml',          # 전자신문 통신방송
     'region': 'domestic', 'country': 'domestic'},
    {'url': 'https://www.sisajournal-e.com/rss/allArticle.xml', # 시사저널e
     'region': 'domestic', 'country': 'domestic'},
    {'url': 'https://digitaltoday.co.kr/rss/allArticle.xml',  # 디지털투데이
     'region': 'domestic', 'country': 'domestic'},
    # ── 해외 — 통신 전문지 직접 RSS (CI에서 안정적) ─────────────────────────────
    {'url': 'https://www.fiercewireless.com/rss/xml',  # 미국 통신 전문지
     'region': 'overseas', 'country': 'us'},
    {'url': 'https://www.rcrwireless.com/feed',        # 미국 통신 전문지
     'region': 'overseas', 'country': 'us'},
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
    # 한국어
    '요금', '요금제', '이용약관', '결합', '리텐션', '안면인증', '최적요금제', '번들',
    '방통위', '과기정통부', '알뜰폰', 'MVNO', '해지', '약정',
    # 영어
    'plan', 'pricing', 'tariff', 'retention', 'bundle', 'facial recognition',
    'churn', 'subscriber', 'ARPU', 'contract', 'terms of service',
]

VALID_TAGS = ['요금제', '최적요금제', '리텐션', '결합상품', '이용약관', '안면인증', '규제·정책']

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
  "summary_ko": "한국어 요약 2~3문장. 핵심 수치와 우리 업무(요금/리텐션/결합/약관/인증)에 주는 시사점 포함.",
  "tags": ["태그1"],
  "carrier": "통신사명 또는 빈문자열",
  "importance": 3
}}

규칙:
- relevant: 요금·요금제·이용약관·리텐션·결합상품·안면인증·통신규제 관련이면 true
- tags: 다음 중만 사용 → {tags_str}
- carrier: 다음 중만 사용 → {carriers}
- importance: 1~5 정수. 우리 팀 업무 직결도 기준 (5=즉시 대응 필요, 3=참고, 1=관련 낮음)"""

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
            entries = feed.entries[:10]  # 소스당 최대 10개
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


if __name__ == '__main__':
    collect()
    bill_summary_collect()


# ── 법안 요약 수집 ─────────────────────────────────────────────────────────────

BILL_API_BASE = 'https://open.assembly.go.kr/portal/openapi/nzmimeepazxkubdpn'
BILL_TOPIC_KW = ['이동통신', '통신요금', '요금제', '번호이동', '데이터요금', 'MVNO', '알뜰폰', '로밍']
BILL_SUMMARY_FILE = 'data/bill_summaries.json'


def is_bill_relevant(name: str) -> bool:
    n = name.lower()
    return any(kw.lower() in n for kw in BILL_TOPIC_KW)


def fetch_bills(api_key: str) -> list:
    import urllib.request, urllib.parse
    params = urllib.parse.urlencode({'KEY': api_key, 'Type': 'json', 'pIndex': 1, 'pSize': 100, 'AGE': 22, 'BILL_NAME': '전기통신사업법'})
    url = f'{BILL_API_BASE}?{params}'
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read().decode('utf-8'))
        svc_key = [k for k in data if k != 'RESULT'][0]
        rows = None
        for item in data[svc_key]:
            if 'row' in item:
                rows = item['row']
                break
        return rows or []
    except Exception as e:
        print(f'  ⚠️  법안 API 오류: {e}')
        return []


def summarize_bill(bill: dict) -> str | None:
    name = bill.get('BILL_NAME', '')
    proposer = bill.get('RST_PROPOSER') or bill.get('PROPOSER', '')
    committee = bill.get('CURR_COMMITTEE', '')
    propose_dt = bill.get('PROPOSE_DT', '')

    prompt = f"""다음 국회 전기통신사업법 개정안의 제안이유와 주요내용을 통신업계 실무자 관점에서 2문장으로 간결하게 요약해줘. 요약문만 출력해.

법안명: {name}
대표발의자: {proposer}
발의일: {propose_dt}
소관위: {committee}"""

    try:
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=180,
            messages=[{'role': 'user', 'content': prompt}]
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f'  ⚠️  요약 오류: {e}')
        return None


def bill_summary_collect():
    api_key = os.environ.get('ASSEMBLY_API_KEY', '')
    if not api_key:
        print('\n⏭  ASSEMBLY_API_KEY 없음 — 법안 요약 건너뜀')
        return

    print(f'\n📋 법안 요약 수집 시작')

    # 기존 요약 로드
    existing: dict = {}
    if os.path.exists(BILL_SUMMARY_FILE):
        try:
            with open(BILL_SUMMARY_FILE, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        except Exception:
            existing = {}

    rows = fetch_bills(api_key)
    print(f'  → {len(rows)}건 수신')

    updated = 0
    for b in rows:
        bill_id = b.get('BILL_ID', '')
        if not bill_id:
            continue
        # 공포 완료 제외
        if b.get('PROM_DT'):
            continue
        # 토픽 필터
        if not is_bill_relevant(b.get('BILL_NAME', '')):
            continue
        # 2025년 이전 제외
        propose_dt = b.get('PROPOSE_DT', '').replace('-', '')
        activity_dates = [b.get('CURR_COMMITTEE_DT', ''), b.get('COMMITTEE_DT', ''), b.get('LAW_PROC_DT', ''), b.get('PROC_DT', '')]
        recent_activity = any(d.replace('-', '') >= '20250101' for d in activity_dates if d)
        recent_propose = propose_dt >= '20250101' if propose_dt else False
        if not recent_propose and not recent_activity:
            continue
        # 이미 요약 있으면 건너뜀
        if bill_id in existing:
            continue

        print(f'  ✅ 요약 생성: {b["BILL_NAME"][:40]}')
        summary = summarize_bill(b)
        if summary:
            existing[bill_id] = {
                'summary': summary,
                'bill_name': b.get('BILL_NAME', ''),
                'updated': TODAY,
            }
            updated += 1
        time.sleep(0.5)

    if updated > 0:
        with open(BILL_SUMMARY_FILE, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        print(f'✅ bill_summaries.json 저장 완료 ({updated}건 추가, 총 {len(existing)}건)')
    else:
        print(f'  변경 없음 (총 {len(existing)}건)')
