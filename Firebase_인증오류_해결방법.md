# Firebase 인증 오류 해결 방법

## 🔴 "Invalid JWT Signature" 오류 원인

이 오류는 다음과 같은 경우에 발생합니다:

1. **서비스 계정 키 파일이 만료됨**
2. **키 파일이 Firebase 콘솔에서 삭제됨**
3. **키 파일이 손상됨**
4. **키 파일이 다른 프로젝트의 것임**

## ✅ 해결 방법

### 1단계: Firebase 콘솔 접속
1. https://console.firebase.google.com 접속
2. 프로젝트 **"smart-library-seat"** 선택

### 2단계: 새로운 서비스 계정 키 다운로드
1. 좌측 상단 ⚙️ 아이콘 클릭 → **프로젝트 설정**
2. **서비스 계정** 탭 클릭
3. **새 비공개 키 생성** 버튼 클릭
4. 다운로드된 JSON 파일 확인

### 3단계: 키 파일 교체
1. 다운로드한 JSON 파일을 `serviceAccountKey.json`으로 이름 변경
2. 기존 파일을 백업 (선택사항)
3. `kwaejeogkog` 폴더에 저장 (기존 파일 덮어쓰기)

### 4단계: 프로그램 재실행
```bash
python main.py
```

## 🔍 현재 설정 확인

- **프로젝트 ID**: smart-library-seat
- **Database URL**: https://smart-library-seat-default-rtdb.firebaseio.com/
- **키 파일 경로**: kwaejeogkog/serviceAccountKey.json

## ⚠️ 참고사항

- 키 파일이 없거나 잘못되어도 프로그램은 실행됩니다
- 다만 Firebase 연동 기능만 작동하지 않습니다
- 카메라 기능은 정상적으로 작동합니다


