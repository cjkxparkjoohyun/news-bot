import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

KEYWORDS = ["단체교섭", "노사관계", "택배노조", "화물연대", "노동위원회"]
TARGET_HOURS_KST = [8, 10, 12, 15, 17, 19, 23]
KST = timezone(timedelta(hours=9))

def clean_html(text):
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', '', text)
    clean = clean.replace('&quot;', '"').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    return clean.strip()

def send_telegram(text):
    if not TOKEN or not CHAT_ID:
        print("[오류] TELEGRAM_TOKEN 또는 CHAT_ID가 설정되지 않았습니다.")
        return False
    
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        'chat_id': CHAT_ID,
        'text': text,
        'disable_web_page_preview': 'true'
    }).encode('utf-8')
    
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"[성공] 텔레그램 발송 완료! (코드: {resp.status})")
            return True
    except Exception as e:
        print(f"[오류] 텔레그램 발송 실패: {e}")
        return False

def fetch_rss(keyword):
    encoded_kw = urllib.parse.quote(keyword)
    # 한국 뉴스 전용 RSS 엔진 적용 (네이버, 연합뉴스, 주요 언론사 포함)
    url = f"https://news.google.com/rss/search?q={encoded_kw}&hl=ko&gl=KR&ceid=KR:ko"
    articles = []
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            for item in root.findall('./channel/item'):
                title = clean_html(item.findtext('title') or "")
                link = (item.findtext('link') or "").strip()
                desc = clean_html(item.findtext('description') or "")
                
                if link:
                    articles.append({'title': title, 'link': link, 'desc': desc})
    except Exception as e:
        print(f"[{keyword}] RSS 수집 오류: {e}")
        
    return articles

def main():
    now_kst = datetime.now(KST)
    print(f"현재 KST 시각: {now_kst.strftime('%Y-%m-%d %H:%M:%S')}")

    articles_dict = {}

    for kw in KEYWORDS:
        kw_articles = fetch_rss(kw)
        for art in kw_articles:
            if art['link'] not in articles_dict:
                articles_dict[art['link']] = art

    articles = list(articles_dict.values())
    print(f"수집된 전체 기사 수: {len(articles)}개")

    header_time = now_kst.strftime("%Y-%m-%d %H:%M")

    # 수집된 기사가 0개일 경우, 지정해주신 대로 텔레그램 브리핑 발송
    if not articles:
        print("[알림] 수집된 뉴스가 없어 안내 메시지를 발송합니다.")
        send_telegram(f"[주요 뉴스 브리핑 - {header_time}]\n\n현재 조건에 맞는 최신 뉴스가 없습니다.")
        return

    # 중요도 점수 산정 (포함된 키워드 가짓수 카운트)
    for art in articles:
        full_text = art['title'] + " " + art['desc']
        score = sum(1 for kw in KEYWORDS if kw in full_text)
        art['score'] = score

    # 정렬: 가짓수 높은 순 정렬
    articles.sort(key=lambda x: x['score'], reverse=True)
    top_20 = articles[:20]

    # 메시지 구성 (이모티콘 사용 금지)
    message = f"[주요 뉴스 브리핑 - {header_time}]\n\n"
    max_len = 3900

    sent_count = 0
    for i, art in enumerate(top_20, 1):
        item_text = f"{i}. {art['title']}\n링크: {art['link']}\n\n"
        if len(message) + len(item_text) > max_len:
            break
        message += item_text
        sent_count += 1

    if sent_count > 0:
        send_telegram(message)

if __name__ == "__main__":
    main()
