import os 
# config.py (쾌적콕! - AI Vision Module Configuration)

# BASE_DIR 정의: 현재 파일(config.py)이 위치한 디렉토리의 절대 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) 

# --- Firebase 및 시스템 설정 ---
FIREBASE_URL = 'https://smart-library-seat-default-rtdb.firebaseio.com/'
SERVICE_ACCOUNT_KEY = os.path.join(BASE_DIR, 'serviceAccountKey.json')  
CONFIG_FILE = os.path.join(BASE_DIR, 'config_file.json')               

# --- AI 모델 및 클래스 설정 ---
MODEL_PATH = os.path.join(BASE_DIR, 'yolov8n.onnx')                    
CLASSES_FILE = os.path.join(BASE_DIR, 'classes.txt')
CONFIDENCE_THRESHOLD = 0.5  # AI 탐지 신뢰도 임계값 (0.25에서 0.5로 상향 권장)
TARGET_CLASSES = ['person', 'backpack', 'laptop', 'handbag', 'book'] # 탐지 대상 클래스

# --- 좌석 상태 관리 및 안정화 설정 (Soft Real-Time) ---
CONFIRM_FRAMES = 10              # 상태 변경을 확정하기 위해 필요한 연속 프레임 수
GHOST_TIME_THRESHOLD_MINUTES = 5 # 유령 좌석 판별 임계 시간 (분 단위)

# --- 시각화 설정 ---
# 색상 (BGR 포맷)
COLOR_VACANT = (0, 255, 0)      # Green
COLOR_OCCUPIED = (0, 0, 255)    # Red
COLOR_GHOST = (0, 165, 255)     # Orange
COLOR_PERSON_BB = (255, 0, 0)   # Blue
COLOR_ITEM_BB = (0, 165, 255)   # Orange