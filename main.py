import cv2
import json
import firebase_admin
from firebase_admin import credentials, db
import atexit
import numpy as np
import datetime
import time

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
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_KEY)
        firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_URL})
    
    status_ref = db.reference('system_status')
    status_ref.update({'connection': 'online', 'last_boot': str(datetime.datetime.now())})

    def on_exit():
        print("프로그램 종료 -> Offline 전환")
        status_ref.update({'connection': 'offline'})

    atexit.register(on_exit)
    print(">> Firebase 연결 성공")

except Exception as e:
    print(f">> Firebase 오류 (무시 가능): {e}")


# --- 3. 전역 변수 ---
drawing = False          
start_point = (-1, -1)   
rois = []                
frame = None
seat_statuses = {}       
seat_counters = {}       
ghost_timers = {}        
fps_update_counter = 0   


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
        for i in range(len(rois)):
            sid = f'seat{i+1}'
            seat_statuses[sid] = 'Vacant'
            seat_counters[sid] = 0
            ghost_timers[sid] = None 
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


# --- 6. 메인 루프 ---
load_rois()
cap = cv2.VideoCapture(0)
cv2.namedWindow('Live Cam')
cv2.setMouseCallback('Live Cam', draw_rectangle) 

print("\n--- 시스템 시작 (Test Mode) ---")
print(f"감지 대상: {TARGET_CLASSES}")
print(f"유령좌석 기준: {GHOST_TIME_THRESHOLD_SECONDS}초 (테스트용)")
print(f"색상설정 -> 사람: 파랑, 물건: 주황")
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

    if status_changed:
        seat_statuses = current_loop_statuses.copy()
        try:
            firebase_seat_data = {}
            for s_id, s_stat in seat_statuses.items():
                firebase_seat_data[s_id] = {
                    'status': s_stat,
                    'last_updated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            db.reference('seats').update(firebase_seat_data)
        except Exception as e:
            print(f"DB 업데이트 실패: {e}")

    # UI 그리기
    fps = 1 / (time.time() - start_frame_time)
    fps_update_counter += 1
    if fps_update_counter >= 30:
        try: db.reference('system_status').update({'fps': float(f"{fps:.1f}"), 'inference_ms': float(f"{inference_time:.1f}")})
        except: pass
        fps_update_counter = 0

    for i, roi in enumerate(rois):
        seat_id = f'seat{i+1}'
        status = seat_statuses.get(seat_id, 'Vacant')
        
        if status == "Occupied": color = COLOR_OCCUPIED
        elif status == "Ghost": color = COLOR_GHOST
        else: color = COLOR_VACANT 

        cv2.rectangle(frame, tuple(roi[0]), tuple(roi[1]), color, 2)
        
        cv2.rectangle(frame, (roi[0][0], roi[0][1] - 40), (roi[0][0] + 100, roi[0][1]), (0,0,0), -1)
        cv2.putText(frame, f"Seat {i+1}", (roi[0][0], roi[0][1] - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
        cv2.putText(frame, f"[{status}]", (roi[0][0], roi[0][1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        if ghost_timers.get(seat_id) is not None:
            elapsed = datetime.datetime.now() - ghost_timers[seat_id]
            mins, secs = divmod(elapsed.total_seconds(), 60)
            time_str = f"Wait: {int(mins):02d}:{int(secs):02d}"
            t_color = (0, 0, 255) if status == 'Ghost' else (255, 255, 255)
            
            cv2.rectangle(frame, (roi[0][0], roi[1][1]), (roi[0][0] + 110, roi[1][1] + 25), (0,0,0), -1)
            cv2.putText(frame, time_str, (roi[0][0] + 5, roi[1][1] + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, t_color, 1)

    cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.imshow('Live Cam', frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'): break
    elif key == ord('s'):
        with open('seats_config.json', 'w') as f: json.dump(rois, f)
        print(">> 설정 저장 완료")
    elif key == ord('c'):
        rois = []
        db.reference('seats').set({})
        print(">> 초기화 완료")

cap.release()
cv2.destroyAllWindows()