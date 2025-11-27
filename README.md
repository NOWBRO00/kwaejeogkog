# kwaejeogkog
# 📚 AI 기반 스마트 도서관 좌석 관리 시스템 (Smart Seat Manager)

실시간 객체 인식(Object Detection) 기술을 활용하여 도서관의 좌석 점유 여부를 판단하고, 장시간 자리를 비우고 물건만 놔두는 '좌석 사유화(Ghost Seat)' 문제를 해결하기 위한 지능형 관리 시스템입니다.

---

## 🚀 프로젝트 개요 (Overview)

도서관이나 카페에서 사람이 없는데 가방이나 책만 덩그러니 놓여있어 앉지 못하는 경험, 다들 있으시죠?
이 프로젝트는 CCTV(웹캠) 영상을 분석하여 사람과 소지품을 구별하고, 일정 시간 이상 사람이 없이 물건만 놓여있는 좌석을 '유령 좌석(Ghost)'으로 분류하여 관리자에게 알립니다.

### 🎯 핵심 기능
1.  실시간 좌석 모니터링: 웹캠을 통해 좌석별 상태(공석/사용중)를 실시간으로 감지합니다.
2.  유령 좌석(사유화) 탐지: 사람이 자리를 비우고 물건만 남겨둔 시간을 측정하여, 설정된 시간(예: 10분)이 지나면 'Ghost' 상태로 전환합니다.
3.  정교한 객체 인식: YOLOv8 모델을 사용하여 사람(Person)과 소지품(Backpack, Laptop, Book 등)을 명확히 구분합니다.
4.  Firebase 연동: 감지된 데이터를 실시간으로 Firebase DB에 전송하여, 모바일 앱이나 웹에서 현황을 볼 수 있습니다.

---

## 🛠 사용 기술 및 라이브러리 (Tech Stack)

* **Language:** Python 3.x
* **Computer Vision:** OpenCV (`opencv-python`)
* **AI Model:** YOLOv8 Nano (`ONNX` 포맷)
* **Database:** Firebase Realtime Database (`firebase-admin`)
* **Dependencies:** `numpy`, `ultralytics`

---

## 🧠 핵심 로직 및 알고리즘 (Algorithm)

### 1. 경량화된 AI 모델 사용 (YOLOv8 + ONNX)
* **Why?** 기존 YOLO 모델은 무거워서 일반 노트북이나 라즈베리파이에서 돌리기 어렵습니다.
* **Solution:** 최신 **YOLOv8 Nano** 모델을 **ONNX(Open Neural Network Exchange)** 포맷으로 변환하여 사용했습니다. 이를 통해 PyTorch와 같은 무거운 의존성 없이 **OpenCV만으로 CPU 환경에서 고속 추론**이 가능합니다.

### 2. 문맥 편향(Contextual Bias) 해결을 위한 이중 임계값 적용
* **Problem:** AI는 보통 '사람이 들고 있는 가방'은 잘 찾지만, '의자에 혼자 있는 가방'은 확신을 못해 인식을 놓치는 경우가 많습니다.
* **Solution:** 인식 민감도(Confidence Threshold)를 객체별로 다르게 설정했습니다.
    * **사람(Person):** 오탐지를 줄이기 위해 기준을 **높게(0.60)** 설정.
    * **물건(Item):** 흐릿하게 찍혀도 유령 좌석을 잡아내기 위해 기준을 **낮게(0.25)** 설정.

### 3. 상태 머신(State Machine) 기반 좌석 판별
각 좌석은 다음 로직에 따라 상태가 변경됩니다.

1.  **Occupied (점유):** 좌석 영역(ROI) 내에 **사람**이 감지됨 (🔴 빨간색).
2.  **Wait (대기):** 사람은 없고 **물건**만 감지됨. 타이머 작동 시작.
3.  **Ghost (유령):** 대기 상태가 설정 시간(예: 5분)을 초과함 (🟠 주황색).
4.  **Vacant (공석):** 사람도 없고 물건도 없음 (🟢 초록색).

---

## 💻 설치 및 실행 방법 (Installation & Usage)

터미널(PowerShell 또는 CMD)에서 아래 순서대로 명령어를 입력하여 환경을 구성하고 실행합니다.

Coding partner
네, AI 기반 스마트 도서관 좌석 관리 시스템의 README.md 초안입니다.

이 문서는 프로젝트의 목적, 핵심 기술, 알고리즘 로직(유령 좌석 판별 등), 그리고 설치 및 실행 방법을 체계적으로 정리하여, 포트폴리오나 깃허브(GitHub) 메인 화면에 바로 사용할 수 있도록 작성했습니다.

README.md (복사하여 사용하세요)
Markdown
# 📚 AI 기반 스마트 도서관 좌석 관리 시스템 (Smart Seat Manager)

실시간 객체 인식(Object Detection) 기술을 활용하여 도서관의 **좌석 점유 여부**를 판단하고, 장시간 자리를 비우고 물건만 놔두는 **'좌석 사유화(Ghost Seat)'** 문제를 해결하기 위한 지능형 관리 시스템입니다.

---

## 🚀 프로젝트 개요 (Overview)

도서관이나 카페에서 사람이 없는데 가방이나 책만 덩그러니 놓여있어 앉지 못하는 경험, 다들 있으시죠?
이 프로젝트는 CCTV(웹캠) 영상을 분석하여 **사람**과 **소지품**을 구별하고, 일정 시간 이상 사람이 없이 물건만 놓여있는 좌석을 **'유령 좌석(Ghost)'**으로 분류하여 관리자에게 알립니다.

### 🎯 핵심 기능
1.  **실시간 좌석 모니터링:** 웹캠을 통해 좌석별 상태(공석/사용중)를 실시간으로 감지합니다.
2.  **유령 좌석(사유화) 탐지:** 사람이 자리를 비우고 물건만 남겨둔 시간을 측정하여, 설정된 시간(예: 10분)이 지나면 'Ghost' 상태로 전환합니다.
3.  **정교한 객체 인식:** YOLOv8 모델을 사용하여 사람(Person)과 소지품(Backpack, Laptop, Book 등)을 명확히 구분합니다.
4.  **Firebase 연동:** 감지된 데이터를 실시간으로 Firebase DB에 전송하여, 모바일 앱이나 웹에서 현황을 볼 수 있습니다.

---

## 🛠 사용 기술 및 라이브러리 (Tech Stack)

* **Language:** Python 3.x
* **Computer Vision:** OpenCV (`opencv-python`)
* **AI Model:** YOLOv8 Nano (`ONNX` 포맷)
* **Database:** Firebase Realtime Database (`firebase-admin`)
* **Dependencies:** `numpy`, `ultralytics`

---

## 🧠 핵심 로직 및 알고리즘 (Algorithm)

### 1. 경량화된 AI 모델 사용 (YOLOv8 + ONNX)
* **Why?** 기존 YOLO 모델은 무거워서 일반 노트북이나 라즈베리파이에서 돌리기 어렵습니다.
* **Solution:** 최신 **YOLOv8 Nano** 모델을 **ONNX(Open Neural Network Exchange)** 포맷으로 변환하여 사용했습니다. 이를 통해 PyTorch와 같은 무거운 의존성 없이 **OpenCV만으로 CPU 환경에서 고속 추론**이 가능합니다.

### 2. 문맥 편향(Contextual Bias) 해결을 위한 이중 임계값 적용
* **Problem:** AI는 보통 '사람이 들고 있는 가방'은 잘 찾지만, '의자에 혼자 있는 가방'은 확신을 못해 인식을 놓치는 경우가 많습니다.
* **Solution:** 인식 민감도(Confidence Threshold)를 객체별로 다르게 설정했습니다.
    * **사람(Person):** 오탐지를 줄이기 위해 기준을 **높게(0.60)** 설정.
    * **물건(Item):** 흐릿하게 찍혀도 유령 좌석을 잡아내기 위해 기준을 **낮게(0.25)** 설정.

### 3. 상태 머신(State Machine) 기반 좌석 판별
각 좌석은 다음 로직에 따라 상태가 변경됩니다.

1.  **Occupied (점유):** 좌석 영역(ROI) 내에 **사람**이 감지됨 (🔴 빨간색).
2.  **Wait (대기):** 사람은 없고 **물건**만 감지됨. 타이머 작동 시작.
3.  **Ghost (유령):** 대기 상태가 설정 시간(예: 5분)을 초과함 (🟠 주황색).
4.  **Vacant (공석):** 사람도 없고 물건도 없음 (🟢 초록색).

---

🎮 사용 가이드 (User Guide)
프로그램이 실행되면 웹캠 창(Live Cam)이 뜹니다.

좌석 생성: 마우스 왼쪽 버튼으로 드래그하여 좌석 영역(ROI)을 그립니다.

좌석 저장: 키보드 s를 누르면 현재 그려진 좌석 위치가 파일(seats_config.json)로 저장됩니다.

초기화: 키보드 c를 누르면 모든 좌석 설정이 초기화됩니다.

종료: 키보드 q를 누르면 프로그램이 종료되고 Firebase 연결이 해제됩니다.

---

📂 디렉토리 구조 (Directory Structure)
library/
│
├── main.py                # 메인 실행 파일 (AI 로직 및 UI 포함)
├── config.py              # (선택) 설정 파일
├── yolov8n.onnx           # AI 모델 파일
├── coco.names             # 클래스 이름 목록
├── serviceAccountKey.json # Firebase 인증 키
├── seats_config.json      # 저장된 좌석 좌표 파일 (자동 생성)
└── README.md              # 프로젝트 설명서

---

터미널 진행 단계
cd "C:\Users\junho\library”

pip install opencv-python numpy firebase-admin ultralytics

pip uninstall opencv-python numpy -y
pip install opencv-python

python -m venv venv
.\venv\Scripts\activate
pip install opencv-python firebase-admin ultralytics
python [main.py](http://main.py/)

python [main.py](http://main.py/)

---

⚠️ 주의사항
yolov8n.onnx, coco.names, serviceAccountKey.json 파일이 같은 폴더 내에 반드시 존재해야 합니다.

웹캠이 연결되어 있어야 작동합니다.
