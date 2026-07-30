import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

# 깃허브 Secrets에서 토큰/ID 가져오기
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
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        'chat_id': CHAT_ID,
        'text': text,
        'disable_web_page_preview': 'true'
    }).encode('utf-8')
    req = urllib.request.Request(url, data=data)
    try:
        urllib.request.urlopen(req)
        print("텔레그램 발송 성공")
    except Exception as e:
        print(f"텔레그램 발송 실패: {e}")

def main():
    now_kst = datetime.now(KST)
    
    # 1. 평일 검사 (월=0 ~ 금=4, 토=5, 일=6)
    if now_kst.weekday() > 4:
        print("주말이므로 실행을 스킵합니다.")
        return

    current_hour = now_kst.hour
    if current_hour not in TARGET_HOURS_KST:
        print(f"현재 시각({current_hour}시)은 설정된 발송 시간이 아닙니다.")
        return

    # 2. 직전 발송 시간대와의 간격 계산
    if current_hour == 8:
        hours_back = 9   # 전일 23시 ~ 금일 08시
    elif current_hour == 15:
        hours_back = 3   # 12시 ~ 15시
    elif current_hour == 23:
        hours_back = 4   # 19시 ~ 23시
    else:
        hours_back = 2   # 8->10, 10->12, 15->17, 17->19

    # 안전 범위를 위해 약간의 여유(10분) 포함
    time_threshold = now_kst - timedelta(hours=hours_back, minutes=10)

    articles_dict = {}

    # 3. 네이버 뉴스 RSS 수집
    for kw in KEYWORDS:
        encoded_kw = urllib.parse.quote(kw)
        url = f"https://newssearch.naver.com/search.naver?where=rss&query={encoded_kw}"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                xml_data = response.read()
                root = ET.fromstring(xml_data)
                
                for item in root.findall('./channel/item'):
                    title = clean_html(item.findtext('title') or "")
                    link = (item.findtext('link') or "").strip()
                    desc = clean_html(item.findtext('description') or "")
                    
                    if not link or link in articles_dict:
                        continue

                    articles_dict[link] = {
                        'title': title,
                        'link': link,
                        'desc': desc
                    }
        except Exception as e:
            print(f"[{kw}] 수집 중 오류: {e}")

    articles = list(articles_dict.values())
    if not articles:
        print("수집된 뉴스가 없습니다.")
        return

    # 4. 중요도 점수 산정 (포함된 키워드 가짓수 카운트)
    for art in articles:
        full_text = art['title'] + " " + art['desc']
        score = sum(1 for kw in KEYWORDS if kw in full_text)
        art['score'] = score

    # 5. 정렬: 가짓수 높은 순 정렬
    articles.sort(key=lambda x: x['score'], reverse=True)
    
    # 상위 20개 추출
    top_20 = articles[:20]

    # 6. 메시지 구성 (이모티콘 금지, 글자수 초과시 자르기)
    header_time = now_kst.strftime("%Y-%m-%d %H:%M")
    message = f"[주요 뉴스 브리핑 - {header_time}]\n\n"
    max_len = 3900  # 텔레그램 안전 글자수 제한

    sent_count = 0
    for i, art in enumerate(top_20, 1):
        item_text = f"{i}. {art['title']}\n링크: {art['link']}\n\n"
        if len(message) + len(item_text) > max_len:
            break  # 용량 초과 시 분할하지 않고 초과분은 기사 버림
        message += item_text
        sent_count += 1

    if sent_count > 0:
        send_telegram(message)

if __name__ == "__main__":
    main()
