import cv2
import json
import firebase_admin
from firebase_admin import credentials, db
import atexit
import numpy as np
import datetime
import time
import random
import threading

# 하드웨어 센서 지원 (선택사항)
try:
    import Adafruit_DHT
    import RPi.GPIO as GPIO
    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False
    print(">> 하드웨어 센서 미사용 (시뮬레이션 모드)")

# 마이크 소음 센서 지원
try:
    import sounddevice as sd
    MIC_AVAILABLE = True
except ImportError:
    MIC_AVAILABLE = False
    print(">> 마이크 센서 미사용 (sounddevice 라이브러리 필요: pip install sounddevice)")

# --- 1. 설정 및 상수 정의 ---
try:
    from config import *
except ImportError:
    SERVICE_ACCOUNT_KEY = 'serviceAccountKey.json'
    FIREBASE_URL = 'https://YOUR_PROJECT_ID.firebaseio.com/'
    MODEL_PATH = 'yolov8n.onnx' 
    CLASSES_FILE = 'coco.names'
    CONFIRM_FRAMES = 5

# 인식 민감도 설정 (물건은 낮게 설정하여 민감하게 반응)
CONFIDENCE_PERSON = 0.60 
CONFIDENCE_ITEM = 0.25   

if 'ITEM_CLASSES' not in globals():
    ITEM_CLASSES = ["backpack", "handbag", "suitcase", "book", "laptop", "cell phone", "tablet", "mouse", "keyboard"]

if 'TARGET_CLASSES' not in globals():
    TARGET_CLASSES = ["person"] + ITEM_CLASSES

# [수정 1] 유령 좌석 테스트를 위해 '초' 단위로 변경 (10초)
GHOST_TIME_THRESHOLD_SECONDS = 10 

# [수정 2] 색상 정의 (BGR 형식)
COLOR_PERSON_BB = (255, 0, 0)    # 파란색 (사람 박스)
COLOR_ITEM_BB = (0, 165, 255)    # 주황색 (물건 박스)

COLOR_OCCUPIED = (0, 0, 255)     # 빨강 (좌석: 사용중)
COLOR_VACANT = (0, 255, 0)       # 초록 (좌석: 공석)
COLOR_GHOST = (0, 165, 255)      # 주황 (좌석: 유령) - 물건 색과 맞춤


# --- 2. Firebase 초기화 ---
firebase_available = False
try:
    if not firebase_admin._apps:
        # 서비스 계정 키 파일 존재 확인
        import os
        if not os.path.exists(SERVICE_ACCOUNT_KEY):
            print(f">> 경고: Firebase 키 파일을 찾을 수 없습니다: {SERVICE_ACCOUNT_KEY}")
            print(">> Firebase 기능 없이 실행됩니다.")
        else:
            cred = credentials.Certificate(SERVICE_ACCOUNT_KEY)
            firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_URL})
            firebase_available = True
    
    if firebase_available:
        status_ref = db.reference('system_status')
        try:
            status_ref.update({'connection': 'online', 'last_boot': str(datetime.datetime.now())})
            
            def on_exit():
                if firebase_available:
                    try:
                        print("프로그램 종료 -> Offline 전환")
                        status_ref.update({'connection': 'offline'})
                    except:
                        pass

            atexit.register(on_exit)
            print(">> Firebase 연결 성공")
        except Exception as e:
            print(f">> Firebase 상태 업데이트 실패: {e}")
            print(">> Firebase 키 파일이 올바른지 확인하세요.")
            firebase_available = False
            print(">> Firebase 미사용 모드로 실행됩니다.")
    else:
        print(">> Firebase 미사용 모드로 실행됩니다.")

except Exception as e:
    print(f">> Firebase 초기화 오류: {e}")
    print(f">> 오류 유형: {type(e).__name__}")
    if "Invalid JWT Signature" in str(e) or "invalid_grant" in str(e):
        print(">> Firebase 서비스 계정 키 파일이 잘못되었거나 만료되었습니다.")
        print(">> Firebase 콘솔에서 새로운 키 파일을 다운로드하세요.")
        print(f">> 현재 키 파일 경로: {SERVICE_ACCOUNT_KEY}")
    firebase_available = False


# --- 3. 전역 변수 ---
drawing = False          
start_point = (-1, -1)   
rois = []                
frame = None
seat_statuses = {}       
seat_counters = {}       
ghost_timers = {}        
fps_update_counter = 0

# 온도/습도/소음 관련 전역 변수
seat_temperatures = {}   # 좌석별 현재 온도
seat_humidities = {}     # 좌석별 현재 습도
seat_previous_temps = {}  # 좌석별 이전 온도 (온도 변화 방향 판단용)
# 소음은 통합으로 관리 (좌석별이 아님)
global_decibel = 45.0    # 전역 소음 레벨 (초기값)
global_sound_status = "조용함"  # 전역 소음 상태
sensor_update_counter = 0  # 센서 데이터 업데이트 카운터
SENSOR_UPDATE_INTERVAL = 10  # 10프레임마다 센서 데이터 업데이트 (더 자주 업데이트)
firebase_update_counter = 0  # Firebase 업데이트 카운터
FIREBASE_UPDATE_INTERVAL = 15  # 15프레임마다 Firebase 업데이트 (자동 업데이트)
SOUND_THRESHOLD = 60.0   # 소음 기준값 (60dB)
CALIBRATION_OFFSET = 100.0  # 마이크 감도 보정값

# 하드웨어 센서 설정 (Raspberry Pi에서 사용 시)
# 좌석별 GPIO 핀 매핑 (필요시 수정)
SEAT_SENSOR_PINS = {
    'seat1': 4,   # 좌석 1번의 DHT11 센서 GPIO 핀
    'seat2': 5,
    'seat3': 6,
    'seat4': 13,
    'seat5': 19,
    'seat6': 26,
    'seat7': 12,
    'seat8': 16,
    'seat9': 20,
    'seat10': 21,
}

# 하드웨어 센서 사용 여부 설정
USE_HARDWARE_SENSORS = False  # True로 변경하면 실제 센서 사용
USE_MIC_SENSOR = True  # True로 변경하면 실제 마이크로 소음 측정

# 날짜 기반 환경 설정
def get_season_from_date():
    """현재 날짜를 기반으로 여름/겨울 판단"""
    current_month = datetime.datetime.now().month
    # 6, 7, 8월: 여름, 12, 1, 2월: 겨울, 나머지: 봄/가을 (기본값 여름)
    if current_month in [12, 1, 2]:
        return "winter"  # 겨울
    elif current_month in [6, 7, 8]:
        return "summer"  # 여름
    else:
        # 봄/가을은 현재 날짜 기준으로 판단 (3-5월: 봄->여름, 9-11월: 가을->겨울)
        if current_month in [3, 4, 5]:
            return "summer"  # 봄이지만 여름으로 간주
        else:
            return "winter"  # 가을이지만 겨울로 간주

def get_environment_for_seat(seat_number, season):
    """좌석 번호와 계절에 따라 환경 설정"""
    if season == "summer":
        # 여름 환경: 고온 고습
        return {
            "temp_range": (28.0, 36.0),
            "hum_range": (70.0, 85.0),
            "decibel_range": (45.0, 75.0),
            "initial_temp": round(random.uniform(30.0, 34.0), 1),
            "environment": "여름 환경"
        }
    else:  # winter
        # 겨울 환경: 저온 저습
        return {
            "temp_range": (-2.0, 10.0),
            "hum_range": (30.0, 50.0),
            "decibel_range": (30.0, 55.0),
            "initial_temp": round(random.uniform(0.0, 5.0), 1),
            "environment": "겨울 환경"
        }   


# --- 4. AI 모델 로드 ---
try:
    net = cv2.dnn.readNet(MODEL_PATH)
    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
    net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
    print(f">> AI 모델 로드 완료: {MODEL_PATH}")
    
    with open(CLASSES_FILE, "r") as f:
        classes = [line.strip() for line in f.readlines()]
    
    TARGET_CLASS_IDS = [classes.index(name) for name in TARGET_CLASSES if name in classes]

except Exception as e:
    print(f"모델 로드 오류: {e}")
    exit()


# --- 5. 함수 정의 ---

def draw_rectangle(event, x, y, flags, param):
    """마우스로 좌석 그리기"""
    global start_point, drawing, rois, frame
    if event == cv2.EVENT_LBUTTONDOWN:
        drawing = True
        start_point = (x, y)
    elif event == cv2.EVENT_MOUSEMOVE:
        if drawing and frame is not None:
            temp_frame = frame.copy()
            for roi in rois:
                cv2.rectangle(temp_frame, tuple(roi[0]), tuple(roi[1]), COLOR_VACANT, 2)
            cv2.rectangle(temp_frame, start_point, (x, y), (0, 200, 0), 2)
            cv2.imshow('Live Cam', temp_frame)
    elif event == cv2.EVENT_LBUTTONUP:
        drawing = False
        end_point = (x, y)
        norm_start = (min(start_point[0], end_point[0]), min(start_point[1], end_point[1]))
        norm_end = (max(start_point[0], end_point[0]), max(start_point[1], end_point[1]))
        if (norm_end[0] - norm_start[0] > 10) and (norm_end[1] - norm_start[1] > 10):
            rois.append([norm_start, norm_end])
            print(f"좌석 추가됨: {norm_start} ~ {norm_end}")

def load_rois():
    global rois, seat_statuses, seat_counters, ghost_timers
    try:
        with open('seats_config.json', 'r') as f:
            loaded = json.load(f)
            rois = [[tuple(pt1), tuple(pt2)] for pt1, pt2 in loaded]
        print(f">> 좌석 {len(rois)}개 로드됨")
        
        # 날짜 기반 환경 정보
        season = get_season_from_date()
        season_kr = "여름" if season == "summer" else "겨울"
        print(f">> 현재 계절: {season_kr} (날짜 기반 자동 설정)")
        
        # 좌석 위치 정보를 Firebase에 저장
        seat_positions = {}
        for i in range(len(rois)):
            sid = f'seat{i+1}'
            seat_statuses[sid] = 'Vacant'
            seat_counters[sid] = 0
            ghost_timers[sid] = None
            initialize_seat_sensors(sid)  # 센서 데이터 초기화
            
            # 좌석 위치 정보 저장
            roi = rois[i]
            env_config = get_environment_for_seat(i+1, season)
            seat_positions[sid] = {
                'position': {
                    'x1': int(roi[0][0]),
                    'y1': int(roi[0][1]),
                    'x2': int(roi[1][0]),
                    'y2': int(roi[1][1])
                },
                'environment': env_config["environment"],
                'season': season,
                'season_kr': season_kr
            }
        
        # Firebase에 좌석 위치 정보 저장
        if firebase_available:
            try:
                db.reference('seat_positions').set(seat_positions)
                print(f">> 좌석 위치 정보 Firebase에 저장 완료")
            except Exception as e:
                print(f">> 좌석 위치 정보 저장 실패: {e}")
        else:
            print(f">> 좌석 위치 정보 로컬 저장 완료 (Firebase 미사용)")
            
    except FileNotFoundError:
        rois = []
        print(">> 설정 파일 없음. 마우스로 좌석을 그려주세요!")

def apply_ghost_logic(seat_id, is_person_present, are_items_present):
    global ghost_timers, seat_statuses
    current_time = datetime.datetime.now()
    
    if is_person_present:
        ghost_timers[seat_id] = None
        return 'Occupied'
    else:
        if are_items_present:
            # 사람은 없고 물건만 있는 경우 -> 유령 좌석 타이머 시작
            if ghost_timers[seat_id] is None:
                ghost_timers[seat_id] = current_time 
            
            elapsed = current_time - ghost_timers[seat_id]
            # [수정] 10초(Seconds) 기준으로 판단
            if elapsed.total_seconds() > GHOST_TIME_THRESHOLD_SECONDS:
                return 'Ghost' 
            else:
                return 'Occupied' 
        else:
            ghost_timers[seat_id] = None
            return 'Vacant'

# --- 온도/습도/소음 관련 함수 ---
def discomfort_index(temp, hum):
    """
    쾌적 지수(Discomfort Index) 계산
    DI = 0.81 × 온도 + 0.01 × 습도 × (0.99 × 온도 - 14.3) + 46.3
    """
    return 0.81 * temp + 0.01 * hum * (0.99 * temp - 14.3) + 46.3

def get_status(DI, temp, hum=None, decibel=None):
    """
    쾌적 지수와 온도, 습도, 소음에 따른 상태 반환
    """
    is_noisy = decibel is not None and decibel >= SOUND_THRESHOLD
    
    if temp <= 5.0:
        return "매우 추움" + (" (소음)" if is_noisy else "")
    elif temp <= 15.0:
        return "약간 추움" + (" (소음)" if is_noisy else "")
    elif DI >= 75:
        return "매우 더움" + (" (소음)" if is_noisy else "")
    elif DI < 68:
        if hum is not None and hum <= 30:
            return "쾌적 (건조함)" + (" (소음)" if is_noisy else "")
        else:
            return "쾌적" + (" (소음)" if is_noisy else "")
    else:
        return "다소 덥고 습함" + (" (소음)" if is_noisy else "")

def get_sound_status(decibel, threshold=60.0):
    """소음 레벨에 따른 상태 반환"""
    if decibel >= threshold:
        return "소음"
    else:
        return "조용함"

def calculate_target_temp(current_temp, current_hum, target_DI):
    """
    목표 쾌적 지수를 달성하기 위한 목표 온도 계산
    
    DI = 0.81 × temp + 0.01 × hum × (0.99 × temp - 14.3) + 46.3
    역산하여 목표 온도 계산:
    temp = (target_DI + 0.143 × hum - 46.3) / (0.81 + 0.0099 × hum)
    """
    if current_hum == 0:
        return current_temp  # 습도가 0이면 계산 불가
    
    denominator = 0.81 + 0.0099 * current_hum
    
    if abs(denominator) < 0.001:  # 분모가 거의 0이면
        return current_temp
    
    target_temp = (target_DI + 0.143 * current_hum - 46.3) / denominator
    return target_temp

def auto_adjust_temperature(current_temp, current_hum, current_DI, target_DI, adjustment_rate=0.1):
    """
    현재 온도를 목표 쾌적 지수에 맞게 자동 조절 (천천히)
    
    Args:
        current_temp: 현재 온도
        current_hum: 현재 습도 (변하지 않는다고 가정)
        current_DI: 현재 쾌적 지수
        target_DI: 목표 쾌적 지수
        adjustment_rate: 조절 속도 (0~1, 작을수록 천천히 조절, 기본값 0.1)
    
    Returns:
        새로운 온도
    """
    # 목표 온도 계산
    target_temp = calculate_target_temp(current_temp, current_hum, target_DI)
    
    # 점진적으로 조절 (급격한 변화 방지, 천천히 조절)
    new_temp = current_temp + (target_temp - current_temp) * adjustment_rate
    
    return round(new_temp, 1)

def control_hvac(temp, target_temp=22.0, previous_temp=None, tolerance=0.3):
    """
    냉난방기 제어 로직 (온도 변화 방향 기반)
    - 목표 온도보다 낮고 온도가 올라가는 중이면 → 난방 켜기
    - 목표 온도보다 높고 온도가 내려가는 중이면 → 냉방 켜기
    - 목표 온도에 도달하면 → 둘 다 끄기
    
    Returns:
        (heater_on, cooler_on, control_action): (난방기 상태, 냉방기 상태, 제어 액션)
    """
    temp_diff = temp - target_temp
    
    # 온도 변화 방향 확인
    temp_rising = False
    temp_falling = False
    if previous_temp is not None:
        temp_change = temp - previous_temp
        if temp_change > 0.01:  # 온도가 올라가는 중
            temp_rising = True
        elif temp_change < -0.01:  # 온도가 내려가는 중
            temp_falling = True
    
    # 목표 온도보다 낮으면 → 난방 필요
    if temp_diff < -tolerance:
        # 온도가 올라가는 중이면 난방이 작동 중
        if temp_rising:
            return (True, False, "난방")
        else:
            # 온도가 올라가지 않으면 난방 켜기
            return (True, False, "난방")
    # 목표 온도보다 높으면 → 냉방 필요
    elif temp_diff > tolerance:
        # 온도가 내려가는 중이면 냉방이 작동 중
        if temp_falling:
            return (False, True, "냉방")
        else:
            # 온도가 내려가지 않으면 냉방 켜기
            return (False, True, "냉방")
    else:
        # 목표 온도 범위 내 → 둘 다 끄기
        return (False, False, "유지")

def get_real_decibel_from_mic():
    """실제 마이크에서 소리를 측정하여 dB로 변환하는 함수"""
    global CALIBRATION_OFFSET
    if not MIC_AVAILABLE or not USE_MIC_SENSOR:
        return None
    
    try:
        duration = 0.5  # 측정 시간 (초)
        fs = 44100      # 샘플링 레이트 (표준 음질)
        
        # 마이크로 소리 녹음
        indata = sd.rec(int(duration * fs), samplerate=fs, channels=1, blocking=True)
        
        # RMS (Root Mean Square) 계산: 소리의 평균 에너지 구하기
        rms = np.sqrt(np.mean(indata.flatten()**2))
        
        # RMS가 0이면(완전 무음) 로그 계산 에러가 나므로 아주 작은 값으로 처리
        if rms <= 0:
            return 0.0
        
        # 데시벨 변환 공식: 20 * log10(RMS)
        db_val = 20 * np.log10(rms)
        
        # 보정값 적용 및 소수점 1자리 반올림
        final_db = float(round(db_val + CALIBRATION_OFFSET, 1))
        
        return final_db
    
    except Exception as e:
        print(f"마이크 측정 오류: {e}")
        return None

class SoundSensorThread(threading.Thread):
    """마이크 소음 측정 스레드 (통합 소음 데이터)"""
    def __init__(self, interval=1):
        super().__init__()
        self.interval = interval
        self.running = True
        self.daemon = True
    
    def run(self):
        global global_decibel, global_sound_status
        print(">> 통합 소음 센서 시작 (마이크 측정)")
        while self.running:
            try:
                if USE_MIC_SENSOR and MIC_AVAILABLE:
                    # 실제 마이크에서 측정
                    current_db = get_real_decibel_from_mic()
                    if current_db is not None:
                        global_decibel = current_db
                        global_sound_status = get_sound_status(current_db, SOUND_THRESHOLD)
                else:
                    # 시뮬레이션 모드: 약간의 변동
                    current_db = global_decibel
                    global_decibel = round(max(30.0, min(70.0, current_db + random.uniform(-3.0, 3.0))), 1)
                    global_sound_status = get_sound_status(global_decibel, SOUND_THRESHOLD)
                
                # Firebase에 통합 소음 데이터 저장
                if firebase_available:
                    try:
                        db.reference('global_sound').set({
                            'decibel': float(global_decibel),
                            'status': str(global_sound_status),
                            'timestamp': int(time.time()),
                            'last_updated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        })
                    except Exception as e:
                        pass  # Firebase 오류는 무시
                
                time.sleep(self.interval)
            except Exception as e:
                print(f">> 소음 센서 오류: {e}")
                time.sleep(3)

def read_hardware_sensor(seat_id):
    """실제 하드웨어 센서에서 온도/습도 읽기"""
    if not HARDWARE_AVAILABLE or not USE_HARDWARE_SENSORS:
        return None, None
    
    if seat_id not in SEAT_SENSOR_PINS:
        return None, None
    
    sensor_pin = SEAT_SENSOR_PINS[seat_id]
    sensor = Adafruit_DHT.DHT11
    
    try:
        humidity, temperature = Adafruit_DHT.read_retry(sensor, sensor_pin, retries=3, delay_seconds=0.5)
        if humidity is not None and temperature is not None:
            return round(temperature, 1), round(humidity, 1)
    except Exception as e:
        print(f"⚠️  센서 읽기 오류 ({seat_id}, GPIO {sensor_pin}): {str(e)}")
    
    return None, None

def initialize_seat_sensors(seat_id):
    """좌석별 센서 데이터 초기화 (날짜 기반 환경 설정) - 소음은 통합 사용"""
    global seat_temperatures, seat_humidities
    
    if seat_id not in seat_temperatures:
        # 좌석 번호 추출
        seat_number = int(seat_id.replace('seat', ''))
        
        # 날짜 기반 계절 판단
        season = get_season_from_date()
        env_config = get_environment_for_seat(seat_number, season)
        
        # 하드웨어 센서에서 읽기 시도
        if USE_HARDWARE_SENSORS and HARDWARE_AVAILABLE:
            temp, hum = read_hardware_sensor(seat_id)
            if temp is not None and hum is not None:
                seat_temperatures[seat_id] = temp
                seat_humidities[seat_id] = hum
            else:
                # 센서 읽기 실패 시 환경에 맞는 기본값
                seat_temperatures[seat_id] = env_config["initial_temp"]
                seat_humidities[seat_id] = round(random.uniform(*env_config["hum_range"]), 1)
        else:
            # 시뮬레이션 모드: 날짜 기반 환경 설정
            seat_temperatures[seat_id] = env_config["initial_temp"]
            seat_humidities[seat_id] = round(random.uniform(*env_config["hum_range"]), 1)
        
        # 소음은 통합 데이터 사용 (좌석별로 저장하지 않음)

def update_seat_sensors(seat_id):
    """좌석별 센서 데이터 업데이트 (소음은 통합 데이터 사용) - 자동 온도 조절 포함"""
    global seat_temperatures, seat_humidities, seat_previous_temps
    
    if seat_id not in seat_temperatures:
        initialize_seat_sensors(seat_id)
        seat_previous_temps[seat_id] = seat_temperatures[seat_id]
    
    # 이전 온도 저장
    previous_temp = seat_previous_temps.get(seat_id, seat_temperatures.get(seat_id, 22.0))
    
    # 목표 쾌적 지수 설정
    TARGET_DI = 65.0
    ADJUSTMENT_RATE = 0.1  # 천천히 조절 (10%씩)
    
    # 하드웨어 센서에서 읽기 시도
    if USE_HARDWARE_SENSORS and HARDWARE_AVAILABLE:
        temp, hum = read_hardware_sensor(seat_id)
        if temp is not None and hum is not None:
            # 실제 센서 값 사용
            current_temp = temp
            current_hum = hum
            
            # 현재 쾌적 지수 계산
            current_DI = discomfort_index(current_temp, current_hum)
            
            # 목표 쾌적 지수에 맞게 온도 자동 조절
            new_temp = auto_adjust_temperature(current_temp, current_hum, current_DI, TARGET_DI, ADJUSTMENT_RATE)
            
            # 온도 범위 제한 (15-30도 범위)
            new_temp = max(15.0, min(30.0, new_temp))
            
            # 온도 업데이트
            seat_previous_temps[seat_id] = seat_temperatures.get(seat_id, current_temp)
            seat_temperatures[seat_id] = new_temp
            seat_humidities[seat_id] = current_hum
        # 센서 읽기 실패 시 기존 값 유지
    else:
        # 시뮬레이션 모드: 자동 온도 조절
        current_temp = seat_temperatures[seat_id]
        current_hum = seat_humidities[seat_id]
        
        # 현재 쾌적 지수 계산
        current_DI = discomfort_index(current_temp, current_hum)
        
        # 목표 쾌적 지수에 맞게 온도 자동 조절
        new_temp = auto_adjust_temperature(current_temp, current_hum, current_DI, TARGET_DI, ADJUSTMENT_RATE)
        
        # 온도 범위 제한 (15-30도 범위)
        new_temp = max(15.0, min(30.0, new_temp))
        
        # 온도 업데이트
        seat_previous_temps[seat_id] = current_temp
        seat_temperatures[seat_id] = new_temp
        
        # 습도: 약간의 변동 (±2%)
        seat_humidities[seat_id] = round(max(30.0, min(70.0, current_hum + random.uniform(-2.0, 2.0))), 1)
    
    # 소음은 통합 데이터 사용 (좌석별로 업데이트하지 않음)


# --- 6. 메인 루프 ---
load_rois()

# 통합 소음 센서 스레드 시작
sound_sensor_thread = None
if USE_MIC_SENSOR or True:  # 항상 소음 센서 스레드 실행 (마이크 없으면 시뮬레이션)
    sound_sensor_thread = SoundSensorThread(interval=1)
    sound_sensor_thread.start()

cap = cv2.VideoCapture(0)
cv2.namedWindow('Live Cam')
cv2.setMouseCallback('Live Cam', draw_rectangle) 

print("\n--- 시스템 시작 (Test Mode) ---")
print(f"감지 대상: {TARGET_CLASSES}")
print(f"유령좌석 기준: {GHOST_TIME_THRESHOLD_SECONDS}초 (테스트용)")
print(f"색상설정 -> 사람: 파랑, 물건: 주황")
season = get_season_from_date()
season_kr = "여름" if season == "summer" else "겨울"
print(f"환경 설정: {season_kr} (현재 날짜 기반 자동 설정)")
if USE_HARDWARE_SENSORS and HARDWARE_AVAILABLE:
    print(f"온도/습도 센서: 하드웨어 모드 (실제 센서 사용)")
else:
    print(f"온도/습도 센서: 시뮬레이션 모드 (날짜 기반 환경 데이터 생성)")

if USE_MIC_SENSOR and MIC_AVAILABLE:
    print(f"소음 센서: 마이크 모드 (실제 마이크로 측정, 통합 데이터)")
else:
    print(f"소음 센서: 시뮬레이션 모드 (통합 데이터)")
print("---------------------------------------")

while True:
    start_frame_time = time.time()
    ret, frame = cap.read()
    if not ret: break

    frame_height, frame_width, _ = frame.shape
    
    # YOLOv8 표준 입력 (640x640)
    blob = cv2.dnn.blobFromImage(frame, 1/255.0, (640, 640), swapRB=True, crop=False)
    net.setInput(blob)
    
    inference_start = time.time()
    outputs = net.forward()
    inference_time = (time.time() - inference_start) * 1000

    outputs = np.transpose(outputs, (0, 2, 1)) 
    rows = outputs[0].shape[0] 

    boxes = []
    scores = []
    class_ids = []

    x_factor = frame_width / 640
    y_factor = frame_height / 640

    for i in range(rows):
        classes_scores = outputs[0][i][4:]
        minScore, maxScore, minClassLoc, (x_idx, maxClassIndex) = cv2.minMaxLoc(classes_scores)

        current_class_name = classes[maxClassIndex]
        
        # 민감도 설정
        threshold = CONFIDENCE_ITEM 
        if current_class_name == 'person':
            threshold = CONFIDENCE_PERSON

        if maxScore >= threshold:
            if maxClassIndex in TARGET_CLASS_IDS:
                x, y, w, h = outputs[0][i][0], outputs[0][i][1], outputs[0][i][2], outputs[0][i][3]
                
                left = int((x - w / 2) * x_factor)
                top = int((y - h / 2) * y_factor)
                width = int(w * x_factor)
                height = int(h * y_factor)
                
                boxes.append([left, top, width, height])
                scores.append(float(maxScore))
                class_ids.append(maxClassIndex)

    indices = cv2.dnn.NMSBoxes(boxes, scores, CONFIDENCE_ITEM, 0.45)

    detected_person_seats = set()
    detected_item_seats = set()

    if len(indices) > 0:
        for i in indices.flatten():
            class_id = class_ids[i]
            box = boxes[i]
            left, top, w, h = box
            
            center_x = left + w // 2
            center_y = top + h // 2
            class_name = classes[class_id]

            is_person = (class_name == 'person')
            is_item = (class_name in ITEM_CLASSES)

            # [수정] 박스 색상 적용 (사람:파랑, 물건:주황)
            color_bb = COLOR_PERSON_BB if is_person else COLOR_ITEM_BB
            
            cv2.rectangle(frame, (left, top), (left + w, top + h), color_bb, 2)
            cv2.putText(frame, f"{class_name} {scores[i]:.2f}", (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_bb, 2)

            for j, roi in enumerate(rois):
                seat_id = f'seat{j+1}'
                roi_start, roi_end = tuple(roi[0]), tuple(roi[1])
                
                if (roi_start[0] <= center_x <= roi_end[0]) and (roi_start[1] <= center_y <= roi_end[1]):
                    if is_person:
                        detected_person_seats.add(seat_id)
                    elif is_item:
                        detected_item_seats.add(seat_id)
                    break 

    # 상태 업데이트
    current_loop_statuses = seat_statuses.copy()
    status_changed = False 

    for i, roi in enumerate(rois):
        seat_id = f'seat{i+1}'
        if seat_id not in seat_statuses:
            seat_statuses[seat_id] = 'Vacant'
            seat_counters[seat_id] = 0
            ghost_timers[seat_id] = None
            initialize_seat_sensors(seat_id)  # 센서 데이터 초기화

        is_p = seat_id in detected_person_seats
        is_i = seat_id in detected_item_seats
        
        target_status = apply_ghost_logic(seat_id, is_p, is_i)
        
        counter = seat_counters.get(seat_id, 0)
        if target_status == 'Occupied':
            counter = min(counter + 1, CONFIRM_FRAMES)
        elif target_status in ('Vacant', 'Ghost'):
            counter = max(counter - 1, -CONFIRM_FRAMES)
        
        seat_counters[seat_id] = counter
        final_status = seat_statuses[seat_id]

        if counter >= CONFIRM_FRAMES: final_status = 'Occupied'
        elif counter <= -CONFIRM_FRAMES: final_status = target_status 
        
        if current_loop_statuses.get(seat_id) != final_status:
            print(f"상태 변경: {seat_id} -> {final_status}")
            status_changed = True
            current_loop_statuses[seat_id] = final_status

    # 센서 데이터 업데이트 (주기적으로)
    sensor_update_counter += 1
    if sensor_update_counter >= SENSOR_UPDATE_INTERVAL:
        for i, roi in enumerate(rois):
            seat_id = f'seat{i+1}'
            update_seat_sensors(seat_id)
        sensor_update_counter = 0

    # Firebase 업데이트 카운터 증가
    firebase_update_counter += 1
    
    # Firebase 업데이트 (상태 변경 시 또는 주기적으로 자동 업데이트)
    should_update_firebase = status_changed or firebase_update_counter >= FIREBASE_UPDATE_INTERVAL
    
    if should_update_firebase:
        if firebase_update_counter >= FIREBASE_UPDATE_INTERVAL:
            firebase_update_counter = 0  # 카운터 리셋
        seat_statuses = current_loop_statuses.copy()
        try:
            firebase_seat_data = {}
            # 실제 설정한 좌석(rois)만 Firebase에 업데이트
            for i, roi in enumerate(rois):
                s_id = f'seat{i+1}'
                if s_id not in seat_statuses:
                    continue
                s_stat = seat_statuses[s_id]
                # 센서 데이터 가져오기 (소음은 통합 데이터 사용)
                temp = seat_temperatures.get(s_id, 22.0)
                hum = seat_humidities.get(s_id, 50.0)
                decibel = global_decibel  # 통합 소음 데이터 사용
                
                # 쾌적 지수 계산
                DI = discomfort_index(temp, hum)
                
                # 상태 문자열 생성 (소음은 통합 데이터 사용)
                comfort_status = get_status(DI, temp, hum, decibel)
                sound_status = global_sound_status  # 통합 소음 상태 사용
                
                # 점유 상태를 영어로 변환 (기존 코드와 호환)
                occupancy_status = s_stat.lower()  # 'Occupied' -> 'occupied'
                occupancy_status_kr = {
                    'Occupied': '점유',
                    'Vacant': '공석',
                    'Ghost': '유령'
                }.get(s_stat, s_stat)
                
                # 좌석 번호 추출
                seat_number = int(s_id.replace('seat', ''))
                season = get_season_from_date()
                env_config = get_environment_for_seat(seat_number, season)
                
                # 목표 쾌적 지수 설정 (쾌적한 환경)
                TARGET_DI = 65.0
                
                # 목표 온도 계산
                target_temp = calculate_target_temp(temp, hum, TARGET_DI)
                
                # 이전 온도 가져오기 (온도 변화 방향 판단용)
                previous_temp = seat_previous_temps.get(s_id, temp)
                
                # 냉난방기 제어 (온도 변화 방향 기반)
                heater_on, cooler_on, control_action = control_hvac(temp, target_temp, previous_temp, tolerance=0.3)
                
                firebase_seat_data[s_id] = {
                    'status': s_stat,  # 기존 호환성 유지
                    'last_updated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    # 온도/습도/소음 데이터 추가
                    'temp': float(temp),
                    'hum': float(hum),
                    'DI': float(round(DI, 1)),
                    'decibel': float(decibel),
                    'comfort_status': str(comfort_status),
                    'sound_status': str(sound_status),
                    'occupancy_status': str(occupancy_status),
                    'occupancy_status_kr': str(occupancy_status_kr),
                    # 환경 정보 추가
                    'environment': env_config["environment"],
                    'season': season,
                    'season_kr': "여름" if season == "summer" else "겨울",
                    # 난방/냉방 제어 정보 추가
                    'heater_on': bool(heater_on),
                    'cooler_on': bool(cooler_on),
                    'target_temp': float(round(target_temp, 1)),
                    'target_DI': float(TARGET_DI),
                    'control_action': str(control_action),
                    'timestamp': int(time.time())
                }
            
            if firebase_available:
                # 실제 설정한 좌석만 업데이트하고, 나머지는 삭제
                seats_ref = db.reference('seats')
                seats_ref.update(firebase_seat_data)
                
                # Firebase에 있는 모든 좌석을 확인하고, 실제 설정하지 않은 좌석은 삭제
                try:
                    all_seats = seats_ref.get()
                    if all_seats:
                        for seat_id in list(all_seats.keys()):
                            # seat1, seat2, ... 형식인지 확인
                            if seat_id.startswith('seat'):
                                seat_num = int(seat_id.replace('seat', ''))
                                # 실제 설정한 좌석 수보다 많으면 삭제
                                if seat_num > len(rois):
                                    seats_ref.child(seat_id).delete()
                                    print(f">> 불필요한 좌석 삭제: {seat_id}")
                except Exception as e:
                    pass  # 삭제 실패는 무시
        except Exception as e:
            print(f"DB 업데이트 실패: {e}")
            if "Invalid JWT Signature" in str(e) or "invalid_grant" in str(e):
                print(">> Firebase 키 파일을 확인하세요.")
                firebase_available = False

    # UI 그리기
    fps = 1 / (time.time() - start_frame_time)
    fps_update_counter += 1
    if fps_update_counter >= 30:
        if firebase_available:
            try: 
                # 시스템 상태 주기적으로 업데이트 (온라인 상태 유지)
                db.reference('system_status').update({
                    'connection': 'online',
                    'fps': float(f"{fps:.1f}"), 
                    'inference_ms': float(f"{inference_time:.1f}"),
                    'last_update': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
            except Exception as e:
                if "Invalid JWT Signature" in str(e) or "invalid_grant" in str(e):
                    print(">> Firebase 인증 오류 발생. 키 파일을 확인하세요.")
                    firebase_available = False
        fps_update_counter = 0

    for i, roi in enumerate(rois):
        seat_id = f'seat{i+1}'
        status = seat_statuses.get(seat_id, 'Vacant')
        
        if status == "Occupied": color = COLOR_OCCUPIED
        elif status == "Ghost": color = COLOR_GHOST
        else: color = COLOR_VACANT 

        cv2.rectangle(frame, tuple(roi[0]), tuple(roi[1]), color, 2)
        
        # 좌석 정보 표시 영역 확장
        info_height = 80 if ghost_timers.get(seat_id) is not None else 60
        cv2.rectangle(frame, (roi[0][0], roi[0][1] - info_height), (roi[0][0] + 150, roi[0][1]), (0,0,0), -1)
        cv2.putText(frame, f"Seat {i+1}", (roi[0][0], roi[0][1] - info_height + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
        cv2.putText(frame, f"[{status}]", (roi[0][0], roi[0][1] - info_height + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        
        # 온도/소음 정보 표시 (소음은 통합 데이터)
        if seat_id in seat_temperatures:
            temp = seat_temperatures[seat_id]
            decibel = global_decibel  # 통합 소음 데이터 사용
            temp_text = f"{temp}°C"
            sound_text = f"{decibel:.0f}dB"
            cv2.putText(frame, temp_text, (roi[0][0], roi[0][1] - info_height + 45), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1)
            sound_color = (0, 0, 255) if decibel >= SOUND_THRESHOLD else (255, 255, 255)
            cv2.putText(frame, sound_text, (roi[0][0], roi[0][1] - info_height + 60), cv2.FONT_HERSHEY_SIMPLEX, 0.4, sound_color, 1)

        if ghost_timers.get(seat_id) is not None:
            elapsed = datetime.datetime.now() - ghost_timers[seat_id]
            mins, secs = divmod(elapsed.total_seconds(), 60)
            time_str = f"Wait: {int(mins):02d}:{int(secs):02d}"
            t_color = (0, 0, 255) if status == 'Ghost' else (255, 255, 255)
            
            cv2.rectangle(frame, (roi[0][0], roi[1][1]), (roi[0][0] + 120, roi[1][1] + 25), (0,0,0), -1)
            cv2.putText(frame, time_str, (roi[0][0] + 5, roi[1][1] + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, t_color, 1)

    cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.imshow('Live Cam', frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'): 
        # 프로그램 종료 시 오프라인으로 전환
        if firebase_available:
            try:
                db.reference('system_status').update({'connection': 'offline'})
            except:
                pass
        if sound_sensor_thread:
            sound_sensor_thread.running = False
        break
    elif key == ord('s'):
        with open('seats_config.json', 'w') as f: json.dump(rois, f)
        print(">> 설정 저장 완료")
        # 좌석 위치 정보를 Firebase에 업데이트
        try:
            seat_positions = {}
            season = get_season_from_date()
            season_kr = "여름" if season == "summer" else "겨울"
            for i in range(len(rois)):
                sid = f'seat{i+1}'
                roi = rois[i]
                env_config = get_environment_for_seat(i+1, season)
                seat_positions[sid] = {
                    'position': {
                        'x1': int(roi[0][0]),
                        'y1': int(roi[0][1]),
                        'x2': int(roi[1][0]),
                        'y2': int(roi[1][1])
                    },
                    'environment': env_config["environment"],
                    'season': season,
                    'season_kr': season_kr
                }
            if firebase_available:
                try:
                    db.reference('seat_positions').set(seat_positions)
                    print(">> 좌석 위치 정보 Firebase 업데이트 완료")
                except Exception as e:
                    print(f">> 좌석 위치 정보 업데이트 실패: {e}")
            else:
                print(">> 좌석 위치 정보 로컬 저장 완료 (Firebase 미사용)")
        except Exception as e:
            print(f">> 좌석 위치 정보 저장 실패: {e}")
    elif key == ord('c'):
        rois = []
        # 모든 좌석 데이터 초기화
        seat_statuses.clear()
        seat_counters.clear()
        ghost_timers.clear()
        seat_temperatures.clear()
        seat_humidities.clear()
        # Firebase도 초기화 (에러 처리 추가)
        if firebase_available:
            try:
                db.reference('seats').set({})
                db.reference('seat_positions').set({})
                print(">> 초기화 완료 (Firebase 포함)")
            except Exception as e:
                print(f">> Firebase 초기화 실패: {e}")
                print(">> 로컬 데이터는 초기화되었습니다.")
        else:
            print(">> 초기화 완료 (로컬만)")

# 프로그램 종료 시 오프라인으로 전환
if firebase_available:
    try:
        db.reference('system_status').update({'connection': 'offline'})
    except:
        pass

if sound_sensor_thread:
    sound_sensor_thread.running = False

cap.release()
cv2.destroyAllWindows()