# Task List

## API 클라이언트 (labelo_api_client.py)
- [x] `_api_get_file()` 메서드 추가 (바이너리 파일 다운로드용)
- [x] `get_project_summary()` 메서드 추가
- [x] `get_project_tasks()` 메서드 추가
- [x] `get_project_progress()` 메서드 추가
- [x] `download_project_tasks()` 메서드 추가
- [x] `get_export_formats()` 메서드 추가
- [x] `create_export_snapshot()` 메서드 추가
- [x] `list_export_snapshots()` 메서드 추가
- [x] `get_export_snapshot()` 메서드 추가
- [x] `download_export_snapshot()` 메서드 추가
- [x] `export_and_download()` 메서드 추가 (스냅샷 생성→폴링→다운로드 일괄)
- [x] CLI 메뉴에 3개 항목 추가 (10, 11, 12)
- [x] CLI 핸들러 3개 구현
- [x] 11번 프로젝트 데이터 다운로드 시 이미지 파일 다운로드 및 ZIP 압축 기능 추가
- [x] 12번 프로젝트 라벨링 데이터 Export 시 이미지 파일 다운로드 및 ZIP 압축 기능 추가 (Easy Export 및 스냅샷 방식 모두 지원)

## 예제 스크립트 (labelo_api_example.py)
- [x] `cmd_project_progress()` 구현
- [x] `cmd_download_tasks()` 구현 (이미지 포함 ZIP 압축 및 --no-images 옵션)
- [x] `cmd_export_labels()` 구현 (이미지 포함 ZIP 압축 및 --no-images 옵션)
- [x] 서브커맨드 등록

## 검증
- [x] Python 구문 검사 통과
- [x] CLI help 출력 확인
- [x] 이미지 URL 판별 및 압축 다운로드 로직 검증
