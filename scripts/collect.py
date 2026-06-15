#!/usr/bin/env python3
"""
Telecom Watch — Daily News Collection Agent
매일 오전 8시(KST) 자동 실행: 국내/해외 통신산업 동향 수집 및 Claude AI 처리
"""
import os, json, hashlib, time
from datetime import datetime, timezone, timedelta
import feedparser
import anthropic

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime('%Y-%m-%d')
DATA_FILE = 'data/articles.json'

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

# ── 수집 소스 ──────────────────────────────────────────────────────────────────
FEEDS = [
    # 국내 — Google 뉴스 RSS (키워드 기반)
    {'url': 'https://news.google.com/rss/search?q=통신+요금제+SKT+KT+LGU플러스&hl=ko&gl=KR&ceid=KR:ko',
     'region': 'domestic', 'country': 'domestic'},
    {'url': 'https://news.google.com/rss/search?q=이용약관+통신사+방통위+과기정통부&hl=ko&gl=KR&ceid=KR:ko',
     'region': 'domestic', 'country': 'domestic'},
    {'url': 'https://news.google.com/rss/search?q=통신+결합상품+리텐션+안면인증&hl=ko&gl=KR&ceid=KR:ko',
     'region': 'domestic', 'country': 'domestic'},
    {'url': 'https://news.google.com/rss/search?q=최적요금제+알뜰폰+MVNO&hl=ko&gl=KR&ceid=KR:ko',
     'region': 'domestic', 'country': 'domestic'},
    # 국내 — 전문지 RSS
    {'url': 'https://rss.etnews.com/Section901.xml',
     'region': 'domestic', 'country': 'domestic'},
    # 미국
    {'url': 'https://news.google.com/rss/search?q=ATT+Verizon+TMobile+pricing+plan+2025&hl=en-US&gl=US&ceid=US:en',
     'region': 'overseas', 'country': 'us'},
    {'url': 'https://news.google.com/rss/search?q=mobile+carrier+retention+bundle+terms&hl=en-US&gl=US&ceid=US:en',
     'region': 'overseas', 'country': 'us'},
    # 일본
    {'url': 'https://news.google.com/rss/search?q=NTT+Docomo+SoftBank+KDDI+料金&hl=ja&gl=JP&ceid=JP:ja',
     'region': 'overseas', 'country': 'jp'},
    # 유럽
    {'url': 'https://news.google.com/rss/search?q=Deutsche+Telekom+Vodafone+Orange+pricing+regulation&hl=en-GB&gl=GB&ceid=GB:en',
     'region': 'overseas', 'country': 'eu'},
    # 중국
    {'url': 'https://news.google.com/rss/search?q=China+Mobile+Unicom+Telecom+pricing+facial&hl=en-US&gl=US&ceid=US:en',
     'region': 'overseas', 'country': 'cn'},
]

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
