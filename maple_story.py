import urllib.request
import urllib.parse
import json
import time
import re
from html.parser import HTMLParser
from datetime import datetime
import os
import sys

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

def load_dotenv(filename='.env'):
    """간단한 .env 파일 로더 (표준 라이브러리만 사용)"""
    if not os.path.exists(filename):
        return False
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # 따옴표 제거
                    value = value.strip()
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    os.environ[key.strip()] = value
        return True
    except Exception as e:
        print(f".env 파일 읽기 오류: {e}")
        return False

def create_env_template():
    """샘플 .env 파일 생성"""
    template = """# 메이플스토리 공지사항 알림봇 설정
# 디스코드 웹훅 URL (필수)
DISCORD_WEBHOOK_URL=여기에_웹훅_URL_입력

# 체크 간격 (초) - 기본값: 300초 (5분)
CHECK_INTERVAL=300

# 처음 실행 시 기존 공지사항 무시 - true/false (기본값: true)
SKIP_INITIAL=true
"""
    
    with open('.env.example', 'w', encoding='utf-8') as f:
        f.write(template)
    
    print(".env.example 파일을 생성했습니다.")
    print(".env.example을 .env로 복사하고 설정을 수정해주세요.")

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

def main():
    # .env 파일 로드
    env_loaded = load_dotenv()
    
    # 환경 변수에서 설정 읽기
    WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')
    CHECK_INTERVAL = int(os.environ.get('CHECK_INTERVAL', '300'))
    SKIP_INITIAL = os.environ.get('SKIP_INITIAL', 'true').lower() == 'true'
    
    # 웹훅 URL 확인
    if not WEBHOOK_URL or WEBHOOK_URL == '여기에_웹훅_URL_입력':
        print("=" * 60)
        print("❌ 오류: 디스코드 웹훅 URL이 설정되지 않았습니다!")
        print("=" * 60)
        
        if not env_loaded:
            print("\n.env 파일이 없습니다.")
            create_env_template()
            print("\n설정 방법:")
            print("1. .env.example을 .env로 복사")
            print("2. .env 파일을 열어서 DISCORD_WEBHOOK_URL 설정")
            print("3. 프로그램 다시 실행")
        else:
            print("\n.env 파일에서 DISCORD_WEBHOOK_URL을 설정해주세요.")
            
        print("=" * 60)
        sys.exit(1)
    
    # 이미 전송한 공지사항 ID 불러오기
    sent_notices = load_sent_notices()
    
    print("=" * 50)
    print("🍄 메이플스토리 공지사항 모니터링 시작 🍄")
    print("=" * 50)
    print(f"체크 간격: {CHECK_INTERVAL}초 ({CHECK_INTERVAL//60}분)")
    print(f"초기 공지사항 건너뛰기: {SKIP_INITIAL}")
    print("중지하려면 Ctrl+C를 누르세요\n")
    
    # 처음 실행 시 현재 공지사항 처리
    first_run = True
    
    while True:
        try:
            # 공지사항 가져오기
            notices = get_notices()
            
            if first_run and SKIP_INITIAL:
                # 처음 실행 시 현재 공지사항을 모두 "읽음" 처리
                for notice in notices:
                    sent_notices.add(notice['id'])
                save_sent_notices(sent_notices)
                first_run = False
                print("✅ 초기화 완료. 이제부터 새 공지사항을 감지합니다.\n")
            else:
                first_run = False
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
            
        except KeyboardInterrupt:
            print("\n\n프로그램을 종료합니다...")
            break
        except Exception as e:
            print(f"\n오류 발생: {e}")
            print("잠시 후 다시 시도합니다...")
        
        # 다음 체크까지 대기
        try:
            time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            print("\n\n프로그램을 종료합니다...")
            break

if __name__ == "__main__":
    main()