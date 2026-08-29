# LabelO API Client & Management Tool

LabelO 웹 시스템 외부에서 독립적인 Python 클라이언트 및 CLI를 통해 **조직, 사용자(라벨러/검수자/관리자), 프로젝트, 데이터(태스크 Import, Export, 백업 다운로드)**를 완벽하게 제어하기 위한 프로젝트입니다.

## 📌 주요 기능

### 1. 사용자 및 조직 관리
* **조직 기반 사용자 초대 및 등록**: 신규 사용자 등록 및 기존 타 조직 계정 초대, 조직 자동 전환
* **라벨러 및 검수자 관리**: 프로젝트별 멤버 추가/제거, 여러 라벨러 일괄 추가, 조직 내 사용자 조회 및 멤버십 삭제

### 2. 프로젝트 관리
* **프로젝트 생성**: CLI에서 프로젝트 명만 입력하여 즉시 생성 및 라벨링 환경 설정 지원
* **모니터링**: 프로젝트 작업 진행률 및 라벨 통계 실시간 조회

### 3. 데이터 Import & Export
* **데이터 Import (가져오기)**: `.json`, `.csv`, `.tsv`, `.txt`, `.zip`, 이미지/오디오 파일 업로드 지원
  * **폴더 업로드**: 폴더(디렉토리) 경로 입력 시 압축하지 않고 내부의 파일들을 원본 그대로 개별 순차 업로드
* **데이터 Export 및 백업**: `JSON`, `CSV`, `TSV`, `COCO`, `YOLO`, `VOC` 등 다양한 포맷 변환 및 다운로드 지원
  * 이미지와 JSON 데이터를 포함한 완벽한 오프라인 백업 압축 파일(`zip`) 다운로드 기능 포함

## 🚀 사용 방법

이 프로젝트는 두 가지 방식의 CLI 인터페이스를 제공합니다.

### 1. 대화형 CLI 인터페이스
터미널에서 `labelo_api_client.py`를 실행하면 대화형 메뉴 시스템을 통해 모든 기능을 이용할 수 있습니다.
```bash
python labelo_api_client.py
```
*(실행 후 이메일 및 비밀번호 또는 API Token으로 로그인)*

### 2. 커맨드라인 스크립트 도구
CI/CD 파이프라인이나 배치 자동화 작업에 활용하기 위한 커맨드 명령어 방식입니다. `labelo_api_example.py`를 사용합니다.

```bash
# 1. 새 프로젝트 생성
python labelo_api_example.py --email admin@test.com --password 1234 create-project --title "새프로젝트"

# 2. 데이터 Import (파일 또는 폴더)
python labelo_api_example.py --email admin@test.com --password 1234 import-data --project 22 --file "./images"

# 3. 여러 라벨러 일괄 추가
python labelo_api_example.py --email admin@test.com --password 1234 add-labelers --project 22 --users 4,5,10

# 4. 프로젝트 데이터 백업 다운로드
python labelo_api_example.py --email admin@test.com --password 1234 download-tasks --project 22 --output-dir ./backup

# 5. 라벨링 데이터 Export
python labelo_api_example.py --email admin@test.com --password 1234 export-labels --project 22 --format JSON
```

## 📂 프로젝트 구조

* `labelo_api_client.py`: 메인 API 클라이언트 라이브러리 및 대화형 CLI (15가지 메뉴 지원)
* `labelo_api_example.py`: 서브커맨드 기반 자동화 파이프라인 CLI 스크립트
* `make_superuser.py`: 관리자 계정 생성 유틸리티 
* `PROJECT_HISTORY.md`: 전체 프로젝트 개발 이력 및 백엔드 기능 개선 사항을 담은 히스토리 문서
