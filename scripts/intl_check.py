#!/usr/bin/env python3
"""
Telecom Watch — 국제비교 소스 자동 검증
매주 월요일 실행: 각 국제 비교 보고서(OECD·ITU·총무성 등)의 신판 발표 여부를
Claude 웹 검색으로 확인하고, 새 발표가 있으면 intl.json 갱신 + 팀용 요약 보고서 생성.

수동 실행: INTL_CHECK=1 python scripts/intl_check.py
"""
import os, json, time
from datetime import datetime, timezone, timedelta

import anthropic

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime('%Y-%m-%d')
INTL_FILE = 'data/intl.json'
REPORTS_FILE = 'data/intl_reports.json'
MAX_REPORTS = 30   # 보고서 최대 보관 수

client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])


def check_source(item: dict) -> dict | None:
    """웹 검색으로 해당 소스의 신판 발표 여부 확인. 새 발표 시 dict 반환."""
    prompt = f"""당신은 한국 이동통신사(SKT) 서비스제도팀의 리서치 어시스턴트입니다.
아래 국제 통신요금/시장 비교 보고서의 최신 발표 현황을 웹 검색으로 확인해주세요.

[확인 대상]
- 발행기관: {item.get('org','')}
- 보고서명: {item.get('name','')}
- 발표 주기: {item.get('cycle','')}
- 현재 기록된 최신판: {item.get('latest','')}

[할 일]
1. 웹 검색으로 이 보고서의 가장 최근 발표(판/연도)를 확인
2. 현재 기록된 최신판보다 새로운 발표가 있는지 판단
3. 새 발표가 있으면 한국 관련 핵심 결과를 파악

[응답 형식 — 아래 JSON만 출력, 다른 텍스트 금지]
{{
  "new_edition": true 또는 false,
  "latest": "확인된 최신판 표기 (예: 2026년판 (2026.5 공표))",
  "result": "한국 관련 핵심 결과 1~2문장 (새 발표 없으면 빈 문자열)",
  "team_report": "팀 보고용 요약 3~4문장: 무엇이 발표됐고, 한국 순위/평가가 어떻게 나왔고, 대응 관점에서 뭘 봐야 하는지 (새 발표 없으면 빈 문자열)",
  "source_url": "확인에 사용한 대표 출처 URL (없으면 빈 문자열)"
}}

확실하지 않으면 new_edition은 false로 판단하세요. 추측으로 새 발표를 만들어내지 마세요."""

    try:
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=1024,
            tools=[{
                'type': 'web_search_20250305',
                'name': 'web_search',
                'max_uses': 2,
            }],
            messages=[{'role': 'user', 'content': prompt}],
        )
        # 최종 텍스트 블록에서 JSON 추출
        text = ''
        for block in msg.content:
            if block.type == 'text':
                text += block.text
        text = text.strip()
        if '```' in text:
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        start = text.find('{')
        end = text.rfind('}')
        if start < 0 or end < 0:
            return None
        data = json.loads(text[start:end + 1])
        return data
    except Exception as e:
        print(f'  ⚠️  검증 오류 ({item.get("id","")}): {e}')
        return None


def intl_check():
    if not os.path.exists(INTL_FILE):
        print('⏭  intl.json 없음 — 건너뜀')
        return

    with open(INTL_FILE, 'r', encoding='utf-8') as f:
        intl = json.load(f)
    items = intl.get('items', [])

    reports = []
    if os.path.exists(REPORTS_FILE):
        try:
            with open(REPORTS_FILE, 'r', encoding='utf-8') as f:
                reports = json.load(f)
        except Exception:
            reports = []

    print(f'🌐 국제비교 소스 자동 검증 시작 ({len(items)}개 소스)')
    updated = 0
    checked = 0
    skipped = 0
    from datetime import date
    today_d = datetime.now(KST).date()
    for item in items:
        # 최근 5일 내 검증한 소스는 스킵 (수동 재실행 시 중복 비용 방지)
        v = item.get('verified', '')
        try:
            if v and (today_d - date.fromisoformat(v)).days < 5:
                skipped += 1
                continue
        except Exception:
            pass
        print(f'  🔍 {item.get("name","")[:50]}')
        res = check_source(item)
        time.sleep(1)
        if res is not None:
            item['verified'] = TODAY   # 검증 수행일 스탬프 (신판 여부 무관)
            checked += 1
        if not res or not res.get('new_edition'):
            continue

        new_latest = res.get('latest', '')
        if not new_latest or new_latest == item.get('latest'):
            continue

        print(f'  🆕 신판 확인: {new_latest}')
        item['latest'] = new_latest
        if res.get('result'):
            item['result'] = res['result']
        updated += 1

        if res.get('team_report'):
            reports.insert(0, {
                'date': TODAY,
                'source_id': item.get('id', ''),
                'org': item.get('org', ''),
                'name': item.get('name', ''),
                'latest': new_latest,
                'report': res['team_report'],
                'url': res.get('source_url', '') or item.get('url', ''),
            })

    if checked > 0:
        intl['updated'] = TODAY
        with open(INTL_FILE, 'w', encoding='utf-8') as f:
            json.dump(intl, f, ensure_ascii=False, indent=2)
    if updated > 0:
        with open(REPORTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(reports[:MAX_REPORTS], f, ensure_ascii=False, indent=2)
        print(f'✅ 신판 {updated}건 반영 + 팀 보고서 생성 (검증 {checked}건)')
    else:
        print(f'  신판 없음 — 검증 {checked}건 확인일 갱신 (최근 검증 스킵 {skipped}건)')


if __name__ == '__main__':
    # 매주 월요일 또는 INTL_CHECK=1 수동 실행 시에만 동작 (비용 관리)
    is_monday = datetime.now(KST).weekday() == 0
    forced = os.environ.get('INTL_CHECK') == '1'
    if is_monday or forced:
        intl_check()
    else:
        print('⏭  월요일 아님 — 국제비교 검증 건너뜀 (INTL_CHECK=1 로 강제 실행 가능)')
