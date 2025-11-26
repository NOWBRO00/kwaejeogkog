import cv2
import json
import firebase_admin
from firebase_admin import credentials, db
import atexit
import numpy as np
import datetime
import time

# config.py에서 모든 설정값 로드
from config import * # --- Firebase 초기화 ---
try:
    # 이미 앱이 초기화되어 있는지 확인
    if not firebase_admin._apps:
        cred = credentials.Certificate(SERVICE_ACCOUNT_KEY)
        firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_URL})
    
    # 프로그램 시작 시 시스템 상태 'online'으로 설정
    status_ref = db.reference('system_status')
    status_ref.update({
        'connection': 'online',
        'last_boot': str(datetime.datetime.now())
    })

    def on_exit():
        """프로그램 종료 시 실행되어 시스템 상태를 'offline'으로 변경합니다."""
        print("프로그램을 종료하며 상태를 'offline'으로 변경합니다.")
        status_ref.update({'connection': 'offline'})

    atexit.register(on_exit)
    print("Firebase 연결 성공")

except Exception as e:
    print(f"Firebase 연결 오류: {e}")
    # exit() # 실제 환경에서는 주석 해제 권장


# --- 전역 변수 설정 ---
drawing = False          # ROI 그리기 상태
start_point = (-1, -1)   # ROI 시작 좌표
rois = []                # 저장된 ROI 영역 리스트
frame = None
seat_statuses = {}       # 현재 좌석 상태 (메모리 상의 상태)
seat_counters = {}       # 상태 변경 지연을 위한 카운터
ghost_timers = {}        # 유령 좌석 타이머
fps_update_counter = 0   # FPS Firebase 전송 주기 관리용

# --- AI 모델 및 클래스 이름 로드 ---
try:
    net = cv2.dnn.readNet(MODEL_PATH)
    
    # [수정됨] 오류 방지를 위해 무조건 CPU 모드로 설정
    print("CPU 모드로 AI 모델을 설정합니다.")
    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
    net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
    
    print("AI 모델(YOLO)을 성공적으로 불러왔습니다.")
    
    with open(CLASSES_FILE, "r") as f:
        classes = [line.strip() for line in f.readlines()]
    
    TARGET_CLASS_IDS = [classes.index(name) for name in TARGET_CLASSES if name in classes]
    print(f"탐지 대상: {TARGET_CLASSES}")

except Exception as e:
    print(f"모델 로드 중 치명적 오류 발생: {e}")
    exit()


# --- 함수 정의 ---

def draw_rectangle(event, x, y, flags, param):
    """마우스로 좌석 영역(ROI)을 그리는 콜백 함수"""
    global start_point, drawing, rois, frame

    if event == cv2.EVENT_LBUTTONDOWN:
        drawing = True
        start_point = (x, y)
    elif event == cv2.EVENT_MOUSEMOVE:
        if drawing and frame is not None:
            temp_frame = frame.copy()
            # 기존 ROI 그리기
            for idx, roi in enumerate(rois):
                cv2.rectangle(temp_frame, tuple(roi[0]), tuple(roi[1]), COLOR_VACANT, 2)
            # 현재 그리고 있는 사각형 표시
            cv2.rectangle(temp_frame, start_point, (x, y), (0, 200, 0), 2)
            cv2.imshow('Live Cam', temp_frame)
    elif event == cv2.EVENT_LBUTTONUP:
        drawing = False
        end_point = (x, y)
        # 좌표 정규화 (왼쪽 상단, 오른쪽 하단 순서로 맞춤)
        x1, y1 = start_point
        x2, y2 = end_point
        norm_start_point = (min(x1, x2), min(y1, y2))
        norm_end_point = (max(x1, x2), max(y1, y2))
        
        # 너무 작은 영역은 무시
        if (norm_end_point[0] - norm_start_point[0] > 10) and (norm_end_point[1] - norm_start_point[1] > 10):
            rois.append([norm_start_point, norm_end_point])
            print(f"좌석 영역 추가됨: {norm_start_point} ~ {norm_end_point}")


def load_rois():
    """저장된 ROI 설정 파일을 불러옵니다."""
    global rois, seat_statuses, seat_counters, ghost_timers
    try:
        with open(CONFIG_FILE, 'r') as f:
            loaded = json.load(f)
            rois = [[tuple(pt1), tuple(pt2)] for pt1, pt2 in loaded]
        print(f"저장된 좌석 영역 {len(rois)}개를 불러왔습니다.")
        
        # 변수 초기화
        for i in range(len(rois)):
            seat_id = f'seat{i+1}'
            seat_statuses[seat_id] = 'Vacant'
            seat_counters[seat_id] = 0
            ghost_timers[seat_id] = None
            
    except FileNotFoundError:
        rois = []
        print("설정 파일이 없습니다. 새로운 좌석 영역을 지정해주세요.")


def apply_ghost_logic(seat_id, is_person_present, are_items_present):
    """사람과 물건 유무에 따른 좌석 상태(Occupied, Ghost, Vacant) 판별 로직"""
    global ghost_timers, seat_statuses

    current_time = datetime.datetime.now()
    current_status = seat_statuses.get(seat_id, 'Vacant')

    if is_person_present:
        # 사람이 있으면 무조건 점유 상태 & 타이머 리셋
        ghost_timers[seat_id] = None
        return 'Occupied'
    else:
        if are_items_present:
            # 사람은 없고 물건만 있는 경우
            if ghost_timers[seat_id] is None:
                ghost_timers[seat_id] = current_time
            
            time_elapsed = current_time - ghost_timers[seat_id]
            
            # 설정된 시간(분)을 초과했는지 확인
            if time_elapsed.total_seconds() > GHOST_TIME_THRESHOLD_MINUTES * 60:
                return 'Ghost'
            else:
                # 아직 시간이 안 지났으면 기존 상태 유지
                if current_status == 'Occupied':
                    return 'Occupied' 
                return current_status 
        else:
            # 사람도 없고 물건도 없음
            ghost_timers[seat_id] = None
            return 'Vacant'


# --- 메인 프로그램 시작 ---
load_rois()
cap = cv2.VideoCapture(0) # 웹캠 인덱스 (필요시 변경)
cv2.namedWindow('Live Cam')
cv2.setMouseCallback('Live Cam', draw_rectangle)

print("\n--- 스마트 도서관 좌석 관리 시스템 (AI Ver.) ---")
print(f"유령 좌석 임계 시간: {GHOST_TIME_THRESHOLD_MINUTES}분")
print("1. 마우스 드래그: 좌석 영역 지정")
print("S: 저장 | C: 초기화 | Q: 종료")
print("-------------------------------------------------")

while True:
    start_frame_time = time.time()
    ret, frame = cap.read()
    if not ret:
        print("웹캠 신호를 받을 수 없습니다.")
        break

    # --- 1. AI 입력 전처리 및 추론 ---
    [height, width, _] = frame.shape
    length = max((height, width))
    image = np.zeros((length, length, 3), np.uint8)
    image[0:height, 0:width] = frame
    scale = length / 640

    inference_start = time.time()
    blob = cv2.dnn.blobFromImage(image, scalefactor=1 / 255, size=(640, 640), swapRB=True)
    net.setInput(blob)
    
    # [오류 발생 지점 수정됨] Backend가 CPU로 설정되어 안전함
    outputs = net.forward()
    
    inference_end = time.time()
    inference_time = (inference_end - inference_start) * 1000  # ms 단위

    # --- 2. AI 출력 해석 (NMS 적용) ---
    outputs = np.array([cv2.transpose(outputs[0])])
    rows = outputs.shape[1]
    boxes, scores, class_ids = [], [], []

    for i in range(rows):
        classes_scores = outputs[0][i][4:]
        (minScore, maxScore, minClassLoc, (x, maxClassIndex)) = cv2.minMaxLoc(classes_scores)
        if maxScore >= CONFIDENCE_THRESHOLD and maxClassIndex in TARGET_CLASS_IDS:
            scores.append(maxScore)
            class_ids.append(maxClassIndex)
            box = [
                outputs[0][i][0] - (0.5 * outputs[0][i][2]),
                outputs[0][i][1] - (0.5 * outputs[0][i][3]),
                outputs[0][i][2],
                outputs[0][i][3]
            ]
            boxes.append(box)

    indices = cv2.dnn.NMSBoxes(boxes, scores, CONFIDENCE_THRESHOLD, 0.45)

    # --- 3. 감지된 객체와 좌석 매칭 ---
    detected_person_seats = set()
    detected_item_seats = set()

    if len(indices) > 0:
        for i in indices.flatten():
            class_id = class_ids[i]
            left, top, w, h = [int(val * scale) for val in boxes[i]]
            center_x = left + w // 2
            center_y = top + h // 2
            class_name = classes[class_id]

            is_person = (class_name == 'person')
            
            # 화면에 바운딩 박스 그리기
            color_bb = COLOR_PERSON_BB if is_person else COLOR_ITEM_BB
            cv2.rectangle(frame, (left, top), (left + w, top + h), color_bb, 2)
            cv2.putText(frame, class_name, (left, top - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_bb, 2)

            # 좌석 ROI 안에 중심점이 있는지 확인
            for j, roi in enumerate(rois):
                seat_id = f'seat{j+1}'
                roi_start, roi_end = tuple(roi[0]), tuple(roi[1])
                if (roi_start[0] <= center_x <= roi_end[0]) and (roi_start[1] <= center_y <= roi_end[1]):
                    if is_person:
                        detected_person_seats.add(seat_id)
                    else:
                        detected_item_seats.add(seat_id)
                    break # 한 객체는 한 좌석에만 속함

    # --- 4. 좌석 상태 판별 및 Firebase 업데이트 ---
    current_loop_statuses = seat_statuses.copy()
    status_changed = False 

    for i, roi in enumerate(rois):
        seat_id = f'seat{i+1}'
        
        if seat_id not in seat_statuses:
            seat_statuses[seat_id] = 'Vacant'
            seat_counters[seat_id] = 0
            ghost_timers[seat_id] = None

        is_person = seat_id in detected_person_seats
        is_item = seat_id in detected_item_seats
        
        target_status = apply_ghost_logic(seat_id, is_person, is_item)

        counter = seat_counters.get(seat_id, 0)
        if target_status == 'Occupied':
            counter = min(counter + 1, CONFIRM_FRAMES)
        elif target_status in ('Vacant', 'Ghost'):
            counter = max(counter - 1, -CONFIRM_FRAMES)
        
        seat_counters[seat_id] = counter

        final_status = seat_statuses[seat_id]
        if counter >= CONFIRM_FRAMES:
            final_status = 'Occupied'
        elif counter <= -CONFIRM_FRAMES:
            final_status = target_status 
        
        if current_loop_statuses.get(seat_id) != final_status:
            print(f"상태 변경 감지: {seat_id} -> {final_status}")
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
            print(">> Firebase seats 업데이트 완료")
        except Exception as e:
            print(f"Firebase seats 업데이트 실패: {e}")

    # --- 5. 화면 표시 및 시스템 상태 전송 ---
    end_frame_time = time.time()
    fps = 1 / (end_frame_time - start_frame_time) if (end_frame_time - start_frame_time) > 0 else 0

    fps_update_counter += 1
    if fps_update_counter >= 30:
        try:
            sys_data = {
                'connection': 'online',
                'fps': float(f"{fps:.2f}"),
                'inference_ms': float(f"{inference_time:.2f}"),
                'last_update': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            db.reference('system_status').update(sys_data)
            fps_update_counter = 0
        except Exception as e:
            print(f"시스템 상태 전송 실패: {e}")
            fps_update_counter = 0

    # 화면 그리기
    for i, roi in enumerate(rois):
        seat_id = f'seat{i+1}'
        status = seat_statuses.get(seat_id, 'Vacant')
        
        if status == "Occupied":
            color = COLOR_OCCUPIED
        elif status == "Ghost":
            color = COLOR_GHOST
        else:
            color = COLOR_VACANT

        cv2.rectangle(frame, tuple(roi[0]), tuple(roi[1]), color, 2)
        
        label = f"seat {i+1}"
        cv2.putText(frame, label, (roi[0][0], roi[0][1] - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        status_label = f"[{status}]"
        cv2.putText(frame, status_label, (roi[0][0], roi[0][1] - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        if status == 'Ghost' and ghost_timers.get(seat_id):
            time_since_item = datetime.datetime.now() - ghost_timers[seat_id]
            minutes = int(time_since_item.total_seconds() // 60)
            seconds = int(time_since_item.total_seconds() % 60)
            time_str = f"Ghost: {minutes:02d}:{seconds:02d}"
            cv2.putText(frame, time_str, (roi[0][0], roi[0][1] + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

    cv2.putText(frame, f"FPS: {fps:.2f} | Inf: {inference_time:.1f}ms", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    
    cv2.imshow('Live Cam', frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord('s'):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(rois, f)
        print(f"설정 저장 완료: {CONFIG_FILE}")
    elif key == ord('c'):
        rois = []
        seat_statuses = {}
        seat_counters = {}
        db.reference('seats').set({})
        print("설정 초기화 완료")

cap.release()
cv2.destroyAllWindows()