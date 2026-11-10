# 📚 쾌적콕 (kwaejeogkog) — AI 기반 스마트 도서관 좌석 관리 시스템

실시간 객체 인식(Object Detection) 기술을 활용하여 도서관의 **좌석 점유 여부**를 판단하고, 장시간 자리를 비우고 물건만 놔두는 **'좌석 사유화(Ghost Seat)'** 문제를 해결하기 위한 지능형 관리 시스템입니다.

---

## 🚀 프로젝트 개요 (Overview)

도서관이나 카페에서 사람이 없는데 가방이나 책만 덩그러니 놓여있어 앉지 못하는 경험, 다들 있으시죠?
이 프로젝트는 CCTV(웹캠) 영상을 분석하여 **사람**과 **소지품**을 구별하고, 일정 시간 이상 사람이 없이 물건만 놓여있는 좌석을 **'유령 좌석(Ghost)'**으로 분류하여 관리자에게 알립니다.

### 🎯 핵심 기능
1. **실시간 좌석 모니터링:** 웹캠을 통해 좌석별 상태(공석/사용중)를 실시간으로 감지합니다.
2. **유령 좌석(사유화) 탐지:** 사람이 자리를 비우고 물건만 남겨둔 시간을 측정하여, 설정된 시간이 지나면 'Ghost' 상태로 전환합니다.
3. **정교한 객체 인식:** YOLOv8 모델을 사용하여 사람(Person)과 소지품(Backpack, Laptop, Book 등)을 구분합니다.
4. **Firebase 연동:** 감지된 데이터를 실시간으로 Firebase Realtime Database에 전송하여, 웹 대시보드에서 현황을 볼 수 있습니다.
5. **온도/습도/소음 데이터 통합:** 좌석별 온도, 습도, 소음 레벨을 함께 기록하고 쾌적 지수를 계산합니다.

---

## 🛠 사용 기술 (Tech Stack)

* **Language:** Python 3.x, JavaScript (웹 대시보드)
* **Computer Vision:** OpenCV (`opencv-python`)
* **AI Model:** YOLOv8 Nano (`ONNX` 포맷)
* **Database:** Firebase Realtime Database (`firebase-admin`)
* **Dependencies:** `numpy`, `sounddevice` (마이크 소음 측정, 선택), `ultralytics` (모델 변환 시)

---

## 🧠 핵심 로직 (Algorithm)

### 1. 경량화된 AI 모델 사용 (YOLOv8 + ONNX)
* **Why?** 기존 YOLO 모델은 무거워서 일반 노트북이나 라즈베리파이에서 돌리기 어렵습니다.
* **Solution:** **YOLOv8 Nano** 모델을 **ONNX** 포맷으로 변환(`convert_model.py`)하여 사용했습니다. PyTorch 같은 무거운 의존성 없이 **OpenCV만으로 CPU 환경에서 추론**이 가능합니다.

### 2. 문맥 편향(Contextual Bias) 해결을 위한 객체별 임계값
* **Problem:** 모델은 '사람이 들고 있는 가방'은 잘 찾지만, '의자에 혼자 있는 가방'은 확신을 못해 놓치는 경우가 많습니다.
* **Solution:** 인식 민감도(Confidence Threshold)를 객체별로 다르게 설정했습니다.
  * **사람(Person):** 오탐지를 줄이기 위해 **높게(0.60)** 설정
  * **물건(Item):** 흐릿하게 찍혀도 유령 좌석을 잡아내기 위해 **낮게(0.25)** 설정

### 3. 상태 머신(State Machine) 기반 좌석 판별

| 상태 | 조건 | 표시 |
| --- | --- | --- |
| **Occupied (점유)** | 좌석 영역(ROI) 안에 사람이 감지됨 | 🔴 빨강 |
| **Wait (대기)** | 사람은 없고 물건만 감지됨, 타이머 시작 | — |
| **Ghost (유령)** | 대기 상태가 설정 시간을 초과함 | 🟠 주황 |
| **Vacant (공석)** | 사람도 물건도 없음 | 🟢 초록 |

---

## 📂 디렉토리 구조

```text
kwaejeogkog/
├── main.py                 # 메인 실행 파일 (AI 추론, 좌석 판별, UI)
├── config.py               # Firebase URL, 키 경로 등 설정
├── convert_model.py        # YOLOv8 → ONNX 변환 스크립트
├── yolov8n.onnx            # AI 모델 파일
├── classes.txt             # 클래스 이름 목록
├── seats_config.json       # 저장된 좌석 좌표 (실행 중 자동 생성)
├── index.html, script.js   # 웹 대시보드
└── serviceAccountKey.json  # Firebase 서비스 계정 키 (직접 발급, 저장소에 포함하지 않음)
```

---

## 💻 설치 및 실행 방법

### 1. 라이브러리 설치

프로젝트 폴더에서 실행합니다.

```bash
pip install opencv-python numpy firebase-admin

# 마이크로 소음을 측정하려면 (선택)
pip install sounddevice
```

### 2. Firebase 서비스 계정 키 준비

1. Firebase 콘솔 → 프로젝트 설정 → **서비스 계정** → **새 비공개 키 생성**
2. 다운로드한 JSON 파일을 `serviceAccountKey.json`으로 이름을 바꿔 프로젝트 폴더에 둡니다.
3. `config.py`의 `FIREBASE_URL`을 본인 프로젝트의 Realtime Database 주소로 바꿉니다.

> ⚠️ `serviceAccountKey.json`은 `.gitignore`에 포함되어 있습니다. 비밀키이므로 절대 커밋하지 마세요.

### 3. 웹 대시보드 실행 (터미널 1)

```bash
python -m http.server 8000
```

브라우저에서 `http://localhost:8000`에 접속합니다. 포트가 사용 중이면 다른 번호(3000, 5000 등)를 사용하세요.

### 4. 카메라 프로그램 실행 (터미널 2)

```bash
python main.py
```

---

## 🎮 사용 가이드

1. 웹캠 창이 열리면 마우스로 드래그해서 좌석 영역(ROI)을 그립니다. 여러 좌석을 추가할 수 있습니다.
2. 키보드 단축키
   - **`s`**: 현재 좌석 설정을 `seats_config.json`에 저장
   - **`c`**: 모든 좌석 설정 초기화
   - **`q`**: 프로그램 종료 (Firebase 연결 해제)
3. 화면 표시 정보
   - 각 좌석에 온도(°C)와 소음(dB) 레벨이 표시됩니다.
   - 소음이 60dB 이상이면 빨간색으로 표시됩니다.
   - 좌석 상태: 빨강(점유), 초록(공석), 주황(유령)

---

## 📊 Firebase에 기록되는 데이터

| 필드 | 설명 |
| --- | --- |
| `status`, `occupancy_status` | 좌석 점유 상태 |
| `temp` | 온도 |
| `hum` | 습도 |
| `decibel` | 소음 레벨 |
| `DI` | 쾌적 지수 (Discomfort Index) |
| `comfort_status` | 쾌적 상태 |

> 소음은 `sounddevice`가 설치되어 있으면 마이크로 실제 측정합니다. 온도·습도는 실제 센서 대신 프로그램에서 생성한 값으로, 데이터 흐름과 대시보드 표시를 검증하는 용도입니다.

---

## ⚠️ 요구사항

- 웹캠 연결
- Python 3.x
- `yolov8n.onnx`, `classes.txt`, `serviceAccountKey.json` 파일
