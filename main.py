import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
KST = timezone(timedelta(hours=9))

# 사내 대시보드 기반 복합 카테고리 및 키워드 세트 정의
KW_PARCEL = ["택배", "물류", "배송", "화물", "운송", "택배기사", "화물연대", "택배노조", "택배업계", "택배차량"]
KW_WAGE = ["임금", "통상임금", "수당", "급여", "처우", "성과급", "기본급", "임금인상", "임금체불"]
KW_SAFETY = ["안전", "산재", "안전사고", "사고", "과로사", "산업안전", "안전기준", "사망", "위험"]
KW_UNION = ["노동조합", "노조", "파업", "교섭", "단체교섭", "노조활동", "파업찬반", "쟁의행위", "노동위원회", "노사관계"]
KW_POLICY = ["정책", "제도", "법안", "개정", "정부", "규제", "고용부", "국토부", "대책", "법제화"]
KW_POLITICS = ["정치", "국회", "여당", "야당", "국회의원", "선거", "정당", "상임위", "입법"]

KEYWORDS = [
    "단체교섭", "노사관계", "택배노조", "화물연대", "노동위원회",
    "택배", "물류", "배송", "화물", "임금", "안전", "산재", "과로사", "노조", "파업", "국토부"
]

COMPANIES = {
    "CJ대한통운": ["CJ대한통운", "CJ"],
    "쿠팡": ["쿠팡", "쿠팡CLS", "쿠팡이츠", "CLS"],
    "롯데글로벌로지스": ["롯데글로벌로지스", "롯데택배", "롯데"],
    "한진": ["한진", "한진택배"],
    "로젠": ["로젠", "로젠택배"]
}

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

def categorize(text):
    if any(kw in text for kw in KW_PARCEL): return "택배/물류"
    if any(kw in text for kw in KW_WAGE): return "임금/처우"
    if any(kw in text for kw in KW_SAFETY): return "안전/산재"
    if any(kw in text for kw in KW_UNION): return "노조/쟁의"
    if any(kw in text for kw in KW_POLICY): return "정책/제도"
    if any(kw in text for kw in KW_POLITICS): return "정치동향"
    return "일반"

def detect_company(text):
    detected = []
    for cmp_name, keywords in COMPANIES.items():
        if any(kw in text for kw in keywords):
            detected.append(cmp_name)
    return ", ".join(detected) if detected else "일반"

def fetch_rss(keyword):
    encoded_kw = urllib.parse.quote(keyword)
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
                pub_date_str = item.findtext('pubDate') or ""
                
                pub_dt = None
                if pub_date_str:
                    try:
                        dt = parsedate_to_datetime(pub_date_str)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        pub_dt = dt.astimezone(KST)
                    except Exception:
                        pass
                
                if link and title:
                    full_text = title + " " + desc
                    cat = categorize(full_text)
                    company = detect_company(full_text)
                    
                    articles.append({
                        'title': title, 
                        'link': link, 
                        'desc': desc, 
                        'pub_dt': pub_dt,
                        'cat': cat,
                        'company': company
                    })
    except Exception as e:
        print(f"[{keyword}] RSS 수집 오류: {e}")
        
    return articles

def main():
    now_kst = datetime.now(KST)
    print(f"현재 KST 시각: {now_kst.strftime('%Y-%m-%d %H:%M:%S')}")

    # 현재 시각 기준 정확히 12시간 전
    time_threshold = now_kst - timedelta(hours=12)
    print(f"기사 필터링 기준 시각 (최근 12시간 이내): {time_threshold.strftime('%Y-%m-%d %H:%M:%S')}")

    articles_dict = {}

    for kw in KEYWORDS:
        kw_articles = fetch_rss(kw)
        for art in kw_articles:
            if art['link'] not in articles_dict:
                articles_dict[art['link']] = art

    all_articles = list(articles_dict.values())

    # [핵심 수정] 날짜 정보가 없거나, 12시간 이내 기사가 아니면 무조건 제외 (옛날 기사 유입 원천 차단)
    articles = []
    for art in all_articles:
        if art['pub_dt'] and art['pub_dt'] >= time_threshold:
            articles.append(art)
        else:
            print(f"[제외됨 - 기간 초과/날짜 오류] {art['title']} ({art['pub_dt']})")

    print(f"최근 12시간 내 엄격히 검증된 신규 기사 수: {len(articles)}개")

    header_time = now_kst.strftime("%Y-%m-%d %H:%M")

    if not articles:
        print("[알림] 수집된 신규 뉴스가 없어 안내 메시지를 발송합니다.")
        send_telegram(f"[주요 뉴스 브리핑 - {header_time}]\n\n현재 조건에 맞는 신규 뉴스가 없습니다.")
        return

    all_kws = KW_PARCEL + KW_WAGE + KW_SAFETY + KW_UNION + KW_POLICY
    for art in articles:
        full_text = art['title'] + " " + art['desc']
        score = sum(1 for kw in all_kws if kw in full_text)
        art['score'] = score

    articles.sort(key=lambda x: x['score'], reverse=True)
    top_20 = articles[:20]

    max_len = 3800
    messages = []
    current_msg = f"[주요 뉴스 브리핑 - {header_time}]\n\n"

    sent_count = 0
    for i, art in enumerate(top_20, 1):
        item_text = f"{i}. {art['title']}\n분류: {art['cat']} | 기업: {art['company']}\n링크: {art['link']}\n\n"
        
        if len(current_msg) + len(item_text) > max_len:
            messages.append(current_msg)
            current_msg = f"[주요 뉴스 브리핑 - {header_time} (이어서)]\n\n"
            
        current_msg += item_text
        sent_count += 1

    if current_msg.strip():
        messages.append(current_msg)

    for msg in messages:
        send_telegram(msg)
        
    print(f"총 {sent_count}건의 기사가 성공적으로 전송되었습니다.")

if __name__ == "__main__":
    main()
