from ultralytics import YOLO
import os # 경로 처리를 위해 os 모듈 추가 (만약 없다면)

# 1. YOLOv8n 모델을 로드합니다.
#    처음 실행 시, 필요한 모델 파일('yolov8n.pt')이 자동으로 다운로드됩니다.
model = YOLO('yolov8n.pt')

# 2. 모델을 OpenCV에서 가장 안정적으로 로드하는 Opset 12로 변환합니다.
#    이것이 이전에 발생했던 -5:Bad argument 오류를 해결하는 핵심입니다.
model.export(format='onnx', opset=11, imgsz=640)

print("\n모델 변환 완료!")
print("이제 'yolov8n.onnx' 파일을 프로젝트에 사용할 수 있습니다.")