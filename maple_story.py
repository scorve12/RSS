import urllib.request
import urllib.parse
import json
import time
import re
from html.parser import HTMLParser
from datetime import datetime
import os
import sys
import signal
import atexit

class NoticeParser(HTMLParser):
    """HTML 파서 - 공지사항 목록 추출"""
    def __init__(self):
        super().__init__()
        self.in_notice_row = False
        self.in_title = False
        self.in_date = False
        self.current_notice = {}
        self.notices = []
        self.current_data = []
        
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        
        # 공지사항 행 시작
        if tag == 'tr' and attrs_dict.get('class') == 'notice':
            self.in_notice_row = True
            self.current_notice = {}
            
        # 제목 링크
        if self.in_notice_row and tag == 'a' and 'href' in attrs_dict:
            if '/News/Notice/Article' in attrs_dict['href']:
                self.in_title = True
                # URL에서 게시글 ID 추출
                match = re.search(r'Oid=(\d+)', attrs_dict['href'])
                if match:
                    self.current_notice['id'] = match.group(1)
                    self.current_notice['url'] = f"https://maplestory.nexon.com{attrs_dict['href']}"
                    
        # 날짜 셀
        if self.in_notice_row and tag == 'td' and attrs_dict.get('class') == 'date':
            self.in_date = True
            
    def handle_data(self, data):
        if self.in_title:
            self.current_data.append(data.strip())
        elif self.in_date:
            self.current_notice['date'] = data.strip()
            
    def handle_endtag(self, tag):
        if tag == 'a' and self.in_title:
            self.in_title = False
            self.current_notice['title'] = ''.join(self.current_data).strip()
            self.current_data = []
            
        if tag == 'td' and self.in_date:
            self.in_date = False
            
        if tag == 'tr' and self.in_notice_row:
            self.in_notice_row = False
            if 'id' in self.current_notice:
                self.notices.append(self.current_notice)

def send_server_status(webhook_url, status="started"):
    """서버 상태 알림 전송"""
    if status == "started":
        title = "🟢 메이플스토리 알림봇 시작"
        description = "공지사항 모니터링을 시작합니다."
        color = 5763719  # 녹색
    else:
        title = "🔴 메이플스토리 알림봇 종료"
        description = "공지사항 모니터링을 종료합니다."
        color = 15548997  # 빨간색
    
    embed = {
        "title": title,
        "description": description,
        "color": color,
        "fields": [
            {
                "name": "서버 시간",
                "value": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "inline": True
            },
            {
                "name": "체크 간격",
                "value": f"{os.environ.get('CHECK_INTERVAL', '300')}초",
                "inline": True
            }
        ],
        "footer": {
            "text": "메이플스토리 공지사항 알림봇"
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    data = {
        "embeds": [embed]
    }
    
    data_json = json.dumps(data).encode('utf-8')
    
    request = urllib.request.Request(
        webhook_url,
        data=data_json,
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(request) as response:
            if response.status == 204:
                print(f"서버 {status} 알림 전송 성공")
                return True
    except Exception as e:
        print(f"서버 상태 알림 전송 실패: {e}")
        return False

def get_notices():
    """메이플스토리 공지사항 가져오기"""
    url = "https://maplestory.nexon.com/News/Notice"
    
    # User-Agent 헤더 설정
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    request = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(request) as response:
            html = response.read().decode('utf-8')
            
        parser = NoticeParser()
        parser.feed(html)
        
        return parser.notices
        
    except Exception as e:
        print(f"공지사항 가져오기 실패: {e}")
        return []

def send_discord_webhook(webhook_url, notice):
    """디스코드 웹훅으로 알림 전송"""
    embed = {
        "title": notice['title'],
        "url": notice['url'],
        "color": 5814783,  # 파란색
        "fields": [
            {
                "name": "작성일",
                "value": notice['date'],
                "inline": True
            }
        ],
        "footer": {
            "text": "메이플스토리 공지사항"
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    data = {
        "embeds": [embed]
    }
    
    data_json = json.dumps(data).encode('utf-8')
    
    request = urllib.request.Request(
        webhook_url,
        data=data_json,
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(request) as response:
            if response.status == 204:
                print(f"알림 전송 성공: {notice['title']}")
                return True
    except Exception as e:
        print(f"알림 전송 실패: {e}")
        return False

def load_sent_notices(filename='sent_notices.json'):
    """이미 전송한 공지사항 ID 불러오기"""
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_sent_notices(sent_ids, filename='sent_notices.json'):
    """전송한 공지사항 ID 저장"""
    with open(filename, 'w') as f:
        json.dump(list(sent_ids), f)

# 전역 변수로 웹훅 URL 저장
WEBHOOK_URL = None

def cleanup():
    """프로그램 종료 시 실행될 정리 함수"""
    global WEBHOOK_URL
    if WEBHOOK_URL:
        print("\n프로그램 종료 중...")
        send_server_status(WEBHOOK_URL, "stopped")

def signal_handler(sig, frame):
    """시그널 핸들러 (Ctrl+C 등)"""
    cleanup()
    sys.exit(0)

def main():
    global WEBHOOK_URL
    
    # 환경 변수에서 설정 읽기
    WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')
    CHECK_INTERVAL = int(os.environ.get('CHECK_INTERVAL', '300'))
    
    # 웹훅 URL 확인
    if not WEBHOOK_URL:
        print("=" * 60)
        print("❌ 오류: DISCORD_WEBHOOK_URL 환경 변수가 설정되지 않았습니다!")
        print("=" * 60)
        sys.exit(1)
    
    # 종료 핸들러 등록
    atexit.register(cleanup)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 서버 시작 알림
    send_server_status(WEBHOOK_URL, "started")
    
    # 이미 전송한 공지사항 ID 불러오기
    sent_notices = load_sent_notices()
    
    print("=" * 50)
    print("🍄 메이플스토리 공지사항 모니터링 시작 🍄")
    print("=" * 50)
    print(f"체크 간격: {CHECK_INTERVAL}초 ({CHECK_INTERVAL//60}분)")
    print("중지하려면 Ctrl+C를 누르세요\n")
    
    # 처음 실행 시 현재 공지사항은 건너뛰기
    first_run = True
    
    try:
        while True:
            try:
                # 공지사항 가져오기
                notices = get_notices()
                
                if first_run:
                    # 처음 실행 시 현재 공지사항을 모두 "읽음" 처리
                    for notice in notices:
                        sent_notices.add(notice['id'])
                    save_sent_notices(sent_notices)
                    first_run = False
                    print("✅ 초기화 완료. 이제부터 새 공지사항을 감지합니다.\n")
                else:
                    # 새로운 공지사항 확인
                    new_notices = []
                    for notice in notices:
                        if notice['id'] not in sent_notices:
                            new_notices.append(notice)
                    
                    # 새 공지사항이 있으면 디스코드로 전송
                    if new_notices:
                        print(f"\n🆕 새로운 공지사항 {len(new_notices)}개 발견!")
                        
                        for notice in new_notices:
                            if send_discord_webhook(WEBHOOK_URL, notice):
                                sent_notices.add(notice['id'])
                                time.sleep(1)  # 연속 요청 방지
                        
                        # 전송한 공지사항 ID 저장
                        save_sent_notices(sent_notices)
                    else:
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 새로운 공지사항 없음", end='\r')
                
            except Exception as e:
                print(f"\n오류 발생: {e}")
                print("잠시 후 다시 시도합니다...")
            
            # 다음 체크까지 대기
            time.sleep(CHECK_INTERVAL)
            
    except KeyboardInterrupt:
        # Ctrl+C로 종료 시
        pass

if __name__ == "__main__":
    main()