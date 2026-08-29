# 🏷️ LabelO API 연동 및 라벨러/데이터 관리 시스템 개발 이력

본 문서는 **LabelO API 클라이언트 개발 및 백엔드 기능 개선, 라벨러 관리, 데이터 Import/Export/다운로드 시스템 구축**에 관한 전체 작업 이력과 기능 명세를 정리한 기록 문서입니다.

---

## 📌 목차
1. [프로젝트 개요](#1-프로젝트-개요)
2. [전체 작업 이력 타임라인](#2-전체-작업-이력-타임라인)
3. [주요 기능 및 아키텍처](#3-주요-기능-및-아키텍처)
   - [3.1 Labelo API Client (labelo_api_client.py)](#31-labelo-api-client-labelo_api_clientpy)
   - [3.2 대화형 CLI 메뉴 구성 (메뉴 1~15)](#32-대화형-cli-메뉴-구성-메뉴-115)
   - [3.3 스크립트형 CLI 도구 (labelo_api_example.py)](#33-스크립트형-cli-도구-labelo_api_examplepy)
4. [백엔드 버그 수정 및 시스템 개선 내역](#4-백엔드-버그-수정-및-시스템-개선-내역)
5. [데이터 Import & Export 명세](#5-데이터-import--export-명세)
6. [파일 및 디렉토리 구조](#6-파일-및-디렉토리-구조)

---

## 1. 프로젝트 개요

* **프로젝트명**: LabelO API Client & Management Tool
* **목표**:
  * LabelO 웹 시스템 외부에서 독립적인 Python 클라이언트 및 CLI를 통해 **조직, 사용자(라벨러/검수자/관리자), 프로젝트, 데이터(태스크 Import, Export, 백업 다운로드)**를 완벽하게 제어
  * 백엔드 멀티테넌시(조직 기반) 정책과 역할 기반 접근 제어(RBAC) 호환성 확보
  * 직관적인 대화형 콘솔(CLI) 및 자동화 스크립트 지원

---

## 2. 전체 작업 이력 타임라인

### Phase 1: API 클라이언트 및 라벨러 관리 기본 기능 구축
* **LabelO REST API 클라이언트 개발** (`LabeloAPIClient`):
  * Django 세션 로그인 및 Token 인증 체계 연동 (`/user/login/`, CSRF 토큰 핸들링, `Token <key>` 인증)
  * 사용자 정보 조회 (`get_whoami`), 조직 내 전체 사용자 조회 (`list_users`)
  * 프로젝트 목록 (`list_projects`), 프로젝트 상세 (`get_project`)
  * 프로젝트 멤버 조회 (`get_project_members`), 멤버 추가/제거 (`add_labeler`, `remove_labeler`)
  * 미참여 사용자 조회 (`get_available_users`), 여러 라벨러 일괄 추가 (`add_labelers_bulk`)

### Phase 2: 데이터 다운로드 및 Export 기능 추가
* **프로젝트 데이터 백업 다운로드** (`download_tasks`):
  * 전체 태스크 / 어노테이션 완료 태스크 JSON 데이터 저장
  * 원본 이미지 파일 자동 감지 및 로컬 폴더/ZIP 압축 다운로드 (`download_task_images`)
  * 실시간 진행률 프로그레스 바 구현
* **라벨링 데이터 Export 기능** (`export_labels`):
  * 지원 포맷(JSON, CSV, COCO, YOLO, VOC, TSV 등) 자동 감지
  * 즉시 변환 다운로드 및 대규모 프로젝트용 스냅샷(Snapshot) 변환 지원

### Phase 3: 조직 멀티테넌시 및 사용자 등록/제거 기능 고도화
* **조직 기반 사용자 초대/등록 기능** (`invite_user`):
  * 신규 사용자 등록 시 현재 관리자의 활성 조직명 자동 기재
  * 기존 타 조직 계정 초대 시 **현재 조직으로 소속(`active_organization`) 자동 전환 및 멤버십 활성화(`status='active'`)**
* **조직 ID 및 조직명 표시 전면 반영**:
  * 내 정보, 프로젝트 멤버, 전체 사용자, 추가 가능 사용자, 일괄 추가, 사용자 등록 화면에 `조직 ID` 및 `조직명` 컬럼 반영
* **사용자 제거 기능 구현** (`delete_user`, `remove_organization_member`):
  * 조직 멤버십 해제(Soft Delete) 및 계정 삭제 연동
  * 대화형 UI에서 본인 삭제 방지 및 안전 확인 프롬프트 추가

### Phase 4: 웹 프론트엔드 렌더링 호환성 및 다중 그룹 오류 해결
* **웹 화면 백지(White Screen) 오류 해결**:
  * 다중 그룹(`administrator`, `owner` 등)을 보유한 사용자의 웹 로그인 시 `base.html`의 템플릿 태그가 JavaScript SyntaxError를 유발하던 문제를 안전한 문자열 포맷으로 수정

### Phase 5: 프로젝트 등록 및 비압축 데이터 Import 기능 완성
* **새 프로젝트 등록 기능** (`create_project`):
  * CLI에서 프로젝트 명만 입력하여 즉시 생성
  * 생성 완료 후 라벨링 인터페이스 설정을 위한 웹 바로가기 링크 안내
* **프로젝트 데이터 Import 기능** (`import_tasks`):
  * JSON, CSV, TSV, TXT, ZIP 등 개별 파일 업로드 지원
  * **폴더(디렉토리) 입력 시 압축하지 않고 폴더 내 원본 파일들을 개별 순차 업로드**하도록 개선
  * 실시간 파일 업로드 진행률 프로그레스 바 적용
  * API 토큰 속성 참조 버그(`_auth_headers()`) 및 타입 임포트(`Union`) 정비

---

## 3. 주요 기능 및 아키텍처

### 3.1 Labelo API Client ([`labelo_api_client.py`](file:///d:/_Dev/labelo_API/labelo_api_client.py))

`LabeloAPIClient` 클래스는 모든 REST API 통신을 전담하는 코어 라이브러리입니다.

| 카테고리 | 메서드명 | 설명 |
| :--- | :--- | :--- |
| **인증** | `login(email, password)` | 세션 로그인 후 API Token 자동 발급 |
| | `login_with_token(token)` | 기존 API Token으로 직접 인증 |
| **사용자** | `get_whoami()` | 현재 로그인된 사용자 및 활성 조직 정보 조회 |
| | `list_users()` | 조직 내 전체 사용자 목록 조회 |
| | `update_user(user_id, ...)` | 사용자 정보/소속 조직 수정 |
| | `delete_user(user_id, org_id)` | 사용자 제거 (조직 멤버십 해제) |
| | `remove_organization_member(org_id, user_id)` | 특정 조직에서 사용자 멤버십 제거 |
| **프로젝트** | `list_projects(page, page_size)` | 프로젝트 목록 조회 |
| | `get_project(project_id)` | 프로젝트 상세 정보 조회 |
| | `create_project(title, description)` | 새 프로젝트 생성 |
| **멤버 관리** | `get_project_members(project_id)` | 프로젝트에 등록된 라벨러 목록 조회 |
| | `get_available_users(project_id)` | 프로젝트에 추가 가능한 후보 사용자 조회 |
| | `add_labeler(project_id, user_id)` | 프로젝트에 라벨러 1명 추가 |
| | `add_labelers_bulk(project_id, user_ids)` | 여러 라벨러 일괄 추가 |
| | `remove_labeler(project_id, user_id)` | 프로젝트에서 라벨러 제거 |
| **등록/초대** | `register_user(email, password, ...)` | 신규 회원가입 (독립 조직 생성) |
| | `invite_user(email, password, ...)` | 현재 관리자 조직에 사용자 등록/초대 |
| | `update_organization_member_role(org_id, user_id, role)` | 조직 내 역할(annotater, reviewer, manager 등) 변경 |
| **모니터링** | `get_project_progress(project_id)` | 프로젝트 진행률 및 라벨 통계 조회 |
| **데이터 처리** | `import_tasks(project_id, file_path, on_progress)` | 데이터/폴더 파일 개별 순차 Import |
| | `download_tasks(project_id, ...)` | 태스크 데이터 JSON 및 이미지 ZIP 다운로드 |
| | `export_labels(project_id, export_format, ...)` | 라벨링 결과 포맷별 Export & 다운로드 |

---

### 3.2 대화형 CLI 메뉴 구성 (메뉴 1~15)

`python labelo_api_client.py` 실행 시 제공되는 대화형 메뉴 시스템입니다:

```text
══════════════════════════════════════════════════
  📋 메인 메뉴
══════════════════════════════════════════════════
  [1]  내 정보 보기 (조직 ID, 조직명, 역할 확인)
  [2]  프로젝트 목록 조회
  [3]  📁 새 프로젝트 등록 (프로젝트명 입력으로 즉시 생성)
  [4]  프로젝트 멤버(라벨러) 조회
  [5]  프로젝트에 라벨러 추가
  [6]  프로젝트에서 라벨러 제거
  [7]  전체 사용자 목록 (조직 ID, 역할 확인)
  [8]  프로젝트에 추가 가능한 사용자 조회
  [9]  여러 라벨러 일괄 추가 (쉼표로 여러 ID 입력)
  [10] 새 사용자 등록 (현재 조직에 초대 및 소속 변경)
  [11] 🗑️  사용자 제거 (조직에서 멤버십 제거)
  [12] 📊 프로젝트 작업 진행상황 모니터링
  [13] 📥 프로젝트 데이터 Import (개별 파일 및 폴더 내 비압축 개별 업로드)
  [14] 💾 프로젝트 데이터 다운로드 (백업 ZIP 생성)
  [15] 📤 프로젝트 라벨링 데이터 Export (포맷 변환 및 다운로드)
  [0]  종료
```

---

### 3.3 스크립트형 CLI 도구 ([`labelo_api_example.py`](file:///d:/_Dev/labelo_API/labelo_api_example.py))

CI/CD 파이프라인이나 배치 작업에 사용할 수 있는 커맨드라인 인터페이스입니다:

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

---

## 4. 백엔드 버그 수정 및 시스템 개선 내역

LabelO 백엔드 소스코드의 결함을 분석하고 다음과 같이 수정했습니다:

1. **초대된 사용자의 프로젝트 등록 불가 버그 해결**:
   - **문제**: 초대로 가입한 사용자의 `OrganizationMember.status`가 `invited`로 남아있고 `active_organization`이 일치하지 않아 프로젝트 추가 대상(`GetUsersAPI`)에서 누락됨.
   - **수정 파일**: [`labelo/labelo/organizations/api.py`](file:///d:/_Dev/labelo_API/labelo/labelo/organizations/api.py#L393-L415) (`OrganizationMemberUpdate`)
   - **반영**: 역할 업데이트 시 `org_member.status = 'active'`, `org_member.deleted_at = None`, `user.active_organization = org` 자동 동기화.

2. **프로젝트 추가 가능 사용자 조회 쿼리 최적화**:
   - **문제**: `GetUsersAPI.get_queryset` 내부 for 루프에서 `users.exclude(...)`를 매번 재할당하여 쿼리가 덮어써지던 버그.
   - **수정 파일**: [`labelo/labelo/projects/api.py`](file:///d:/_Dev/labelo_API/labelo/labelo/projects/api.py#L868-L886)
   - **반영**: `OrganizationMember` 필터를 기반으로 active 멤버를 한 번에 정확하게 조회하도록 수정.

3. **매니저(Manager) 그룹 권한 보강**:
   - **수정 파일**: [`labelo/labelo/core/permissions.py`](file:///d:/_Dev/labelo_API/labelo/labelo/core/permissions.py#L145-L151)
   - **반영**: `manager` 그룹에 조직 멤버 조회/추가/변경 권한 부여.

4. **웹 브라우저 백지 화면(SyntaxError) 수정**:
   - **문제**: 다중 그룹을 가진 사용자가 웹 로그인 시 `base.html`의 템플릿 태그가 `group: "administrator", "owner",` 형태로 출력되어 JS 문법 에러 발생.
   - **수정 파일**: [`labelo/labelo/templates/base.html`](file:///d:/_Dev/labelo_API/labelo/labelo/templates/base.html#L98)
   - **반영**: 그룹 목록을 안전한 단일 문자열 포맷으로 감싸서 렌더링되도록 수정.

---

## 5. 데이터 Import & Export 명세

### 📥 Data Import (가져오기)
* **단일 파일**: `.json`, `.csv`, `.tsv`, `.txt`, `.zip`, 이미지/오디오 파일 지원
* **폴더(디렉토리)**: 폴더 경로 입력 시 **압축하지 않고 내부의 파일들을 원본 그대로 개별 순차 업로드** (실시간 프로그레스 바 지원)
* **엔드포인트**: `POST /api/projects/{project_id}/import`

### 📤 Data Export & Backup (내보내기 & 백업)
* **지원 포맷**: `JSON`, `JSON_MIN`, `CSV`, `TSV`, `COCO`, `YOLO`, `VOC`, `BRUSH_TO_NUMPY` 등
* **이미지 포함 백업**: 태스크 데이터 JSON과 원본 이미지 파일들을 수집하여 `project-{id}-tasks.zip` 형태의 완벽한 오프라인 백업 압축 파일 생성
* **엔드포인트**: `GET /api/projects/{project_id}/export`, `POST /api/projects/{project_id}/exports`

---

## 6. 파일 및 디렉토리 구조

```text
d:\_Dev\labelo_API\
├── labelo_api_client.py     # 메인 API 클라이언트 라이브러리 및 대화형 CLI (메뉴 1~15)
├── labelo_api_example.py    # 서브커맨드 기반 자동화 CLI 스크립트
├── PROJECT_HISTORY.md       # 📋 전체 프로젝트 개발 이력 및 명세서 (본 파일)
│
└── labelo\                  # LabelO 백엔드 소스코드
    ├── labelo\
    │   ├── core\            # 권한 및 기본 설정
    │   ├── organizations\   # 조직 및 멤버십 관리 API
    │   ├── projects\        # 프로젝트 및 태스크 API
    │   ├── data_import\     # 데이터 가져오기 API
    │   └── templates\       # HTML 및 React 렌더링 템플릿
    └── web\                 # React 기반 웹 프론트엔드
```

---
*문서 작성일: 2026-08-24*  
*작성자: Antigravity AI Assistant*
