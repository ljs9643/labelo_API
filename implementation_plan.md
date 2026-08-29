# LabelO API 연동 및 라벨러/데이터 관리 시스템 종합 구현 계획 및 명세

본 문서는 **LabelO REST API 연동 클라이언트, 대화형 CLI 도구, 백엔드 멀티테넌시 버그 수정, 데이터 Import/Export/다운로드 시스템**의 최종 구현 계획 및 명세서입니다.

---

## 1. 구현 목표 및 핵심 구성요소

1. **외부 API 클라이언트 라이브러리 ([`labelo_api_client.py`](file:///d:/_Dev/labelo_API/labelo_api_client.py))**:
   - 세션 로그인 기반 API Token 자동 발급 및 지속 인증
   - 조직(Organization), 사용자(User), 프로젝트(Project), 멤버(Labeler), 태스크 데이터(Import/Export/Download) 통합 제어
2. **대화형 콘솔 인터페이스 (`LabeloCLI`)**:
   - 메뉴 1~15번을 통한 직관적인 콘솔 UI (컬러 출력, 테이블 포맷, 실시간 프로그레스 바)
3. **스크립트형 CLI 도구 ([`labelo_api_example.py`](file:///d:/_Dev/labelo_API/labelo_api_example.py))**:
   - 서브커맨드 기반 자동화 및 배치 처리 지원
4. **백엔드 소스코드 개선 및 무결성 확보**:
   - 조직 멤버십 동기화, 사용자 조회 쿼리 최적화, 프론트엔드 다중 그룹 호환성 수정

---

## 2. 세부 구현 내역

### 2.1 API 클라이언트 코어 (`LabeloAPIClient`)

#### 🔐 인증 및 사용자/조직 관리
- `login(email, password)`: 로그인 페이지에서 CSRF 토큰을 추출하고 세션 인증을 거쳐 API Token 획득
- `login_with_token(token)`: 발급된 토큰으로 직접 클라이언트 인증
- `get_whoami()`: 현재 로그인된 사용자의 ID, 이름, 이메일, 활성 조직(`active_organization`) 정보 조회
- `list_users()`: 현재 조직에 속한 사용자 목록 조회
- `update_user(user_id, **kwargs)`: 사용자 정보 및 소속 조직 수정
- `delete_user(user_id, organization_id=None)`: 사용자 계정 삭제 또는 조직 멤버십 해제
- `remove_organization_member(organization_id, user_id)`: 조직에서 멤버십 제거 (Soft Delete)
- `register_user(email, password, username, org_name)`: 독립 조직을 가진 신규 계정 가입
- `invite_user(email, password, username, role)`: 현재 관리자 조직에 사용자 가입/초대 및 소속 전환
- `update_organization_member_role(org_id, user_id, role)`: 조직 내 역할(annotater, reviewer, manager 등) 변경 및 `status='active'` 활성화

#### 📁 프로젝트 관리
- `list_projects(page, page_size)`: 프로젝트 목록 조회
- `get_project(project_id)`: 프로젝트 상세 정보 조회
- `create_project(title, description="")`: **프로젝트 이름만 입력하여 즉시 생성** (웹 인터페이스 설정 URL 안내)

#### 👥 프로젝트 멤버(라벨러) 관리
- `get_project_members(project_id)`: 프로젝트에 등록된 라벨러 목록 조회
- `get_available_users(project_id)`: 프로젝트에 아직 등록되지 않은 추가 가능 사용자 조회
- `add_labeler(project_id, user_id)`: 프로젝트에 라벨러 1명 등록
- `add_labelers_bulk(project_id, user_ids)`: 여러 사용자 ID를 한 번에 프로젝트 멤버로 일괄 등록
- `remove_labeler(project_id, user_id)`: 프로젝트에서 라벨러 제거

#### 📊 모니터링 및 데이터 처리
- `get_project_progress(project_id)`: 프로젝트 진행률, 태스크/어노테이션 통계, 라벨 타입별 카운트 조회
- `import_tasks(project_id, file_path, tasks, on_progress)`:
  - 개별 파일(JSON, CSV, TSV, TXT, ZIP 등) 업로드
  - **폴더 입력 시 압축 없이 폴더 내 원본 파일들을 개별 순차 업로드** (실시간 진행률 콜백 지원)
- `download_tasks(project_id, output_dir, download_all, include_images, on_progress)`:
  - 태스크 JSON 데이터 및 원본 이미지 다운로드 후 `project-{id}-tasks.zip` 백업 파일 생성
- `export_labels(project_id, export_format, output_dir, snapshot, include_images)`:
  - 지원 포맷(JSON, CSV, COCO, YOLO 등)으로 변환 후 로컬 저장

---

### 2.2 대화형 CLI 메뉴 구성 (`LabeloCLI`)

```text
══════════════════════════════════════════════════
  📋 메인 메뉴
══════════════════════════════════════════════════
  [1]  내 정보 보기 (조직 ID, 조직명, 역할 확인)
  [2]  프로젝트 목록 조회
  [3]  📁 새 프로젝트 등록 (프로젝트명 입력으로 즉시 생성)
  [4]  프로젝트 멤버(라벨러) 조회 (조직 ID 확인)
  [5]  프로젝트에 라벨러 추가
  [6]  프로젝트에서 라벨러 제거
  [7]  전체 사용자 목록 (조직 ID, 역할 확인)
  [8]  프로젝트에 추가 가능한 사용자 조회
  [9]  여러 라벨러 일괄 추가 (쉼표 구분 ID 입력)
  [10] 새 사용자 등록 (현재 조직에 초대 및 소속 변경)
  [11] 🗑️  사용자 제거 (조직에서 멤버십 제거)
  [12] 📊 프로젝트 작업 진행상황 모니터링
  [13] 📥 프로젝트 데이터 Import (개별 파일 및 폴더 내 비압축 개별 업로드)
  [14] 💾 프로젝트 데이터 다운로드 (백업 ZIP 생성)
  [15] 📤 프로젝트 라벨링 데이터 Export (포맷 변환 및 다운로드)
  [0]  종료
```

---

### 2.3 스크립트형 CLI 도구 (`labelo_api_example.py`)

| 서브커맨드 | 주요 인자 | 설명 |
| :--- | :--- | :--- |
| `whoami` | - | 현재 사용자 및 조직 정보 조회 |
| `list-projects` | - | 프로젝트 목록 조회 |
| `create-project` | `--title`, `--description` | 새 프로젝트 생성 |
| `list-users` | - | 조직 내 전체 사용자 조회 |
| `list-members` | `--project` | 프로젝트 멤버 조회 |
| `available-users`| `--project` | 추가 가능한 사용자 조회 |
| `add-labeler` | `--project`, `--user` | 라벨러 1명 추가 |
| `add-labelers` | `--project`, `--users 1,2,3` | 여러 라벨러 일괄 추가 |
| `remove-labeler`| `--project`, `--user` | 라벨러 제거 |
| `invite-user` | `--invite-email`, `--invite-password`, `--invite-username`, `--role` | 현재 조직에 사용자 등록 |
| `delete-user` | `--user` | 사용자 제거 (조직에서 제거) |
| `project-progress` | `--project` | 진행률 및 통계 모니터링 |
| `import-data` | `--project`, `--file` (또는 `--json-data`) | 데이터 파일/폴더 Import |
| `download-tasks`| `--project`, `--output-dir`, `--all`, `--no-images` | 데이터 백업 다운로드 |
| `export-labels` | `--project`, `--format`, `--output-dir`, `--snapshot` | 라벨 데이터 Export |

---

## 3. 백엔드 버그 수정 및 개선 사항

1. **조직 멤버십 및 소속 조직 동기화 ([`organizations/api.py`](file:///d:/_Dev/labelo_API/labelo/labelo/organizations/api.py#L393-L415))**:
   - 역할 변경 시 `status = 'active'`, `deleted_at = None`, `user.active_organization = org` 자동 반영
2. **프로젝트 추가 가능 사용자 쿼리 수정 ([`projects/api.py`](file:///d:/_Dev/labelo_API/labelo/labelo/projects/api.py#L868-L886))**:
   - 루프 내 exclude 덮어쓰기 버그를 제거하고 `OrganizationMember` 필터를 통해 active 멤버를 정확하게 조회
3. **매니저 그룹 권한 추가 ([`core/permissions.py`](file:///d:/_Dev/labelo_API/labelo/labelo/core/permissions.py#L145-L151))**:
   - `manager` 그룹에 조직 멤버 권한 부여
4. **프론트엔드 그룹 렌더링 수정 ([`templates/base.html`](file:///d:/_Dev/labelo_API/labelo/labelo/templates/base.html#L98))**:
   - 다중 그룹 시 발생하던 JavaScript SyntaxError 방지를 위해 문자열 래핑 포맷 적용

---

## 4. API 엔드포인트 맵

| 기능 | HTTP | 엔드포인트 | 설명 |
| :--- | :--- | :--- | :--- |
| **인증** | GET/POST | `/user/login/` | 세션 로그인 및 CSRF/Token 처리 |
| **사용자 정보** | GET | `/api/current-user/whoami` | 내 정보 조회 |
| **사용자 목록** | GET | `/api/users/` | 조직 사용자 목록 조회 |
| **사용자 수정/삭제** | PATCH/DELETE | `/api/users/{id}/` | 사용자 수정 / 삭제 |
| **조직 멤버 역할** | PATCH | `/api/organizations/{org_id}/members/{user_id}` | 역할 변경 및 멤버십 활성화 |
| **프로젝트 목록/생성**| GET/POST | `/api/projects/` | 프로젝트 목록 조회 및 새 프로젝트 생성 |
| **프로젝트 상세** | GET/PATCH/DELETE| `/api/projects/{id}/` | 프로젝트 상세 / 수정 / 삭제 |
| **프로젝트 멤버** | GET/POST/DELETE | `/api/projects/{id}/members/` | 멤버 목록 / 추가 / 삭제 |
| **추가 가능 사용자**| GET | `/api/projects/{id}/users/` | 추가 가능한 사용자 목록 |
| **데이터 Import** | POST | `/api/projects/{id}/import` | 파일 및 태스크 Import |
| **데이터 Export** | GET | `/api/projects/{id}/export?exportType=JSON` | 라벨링 데이터 직접 다운로드 |
| **Export 스냅샷** | POST/GET | `/api/projects/{id}/exports/` | 스냅샷 생성 및 목록 조회 |
| **스냅샷 다운로드** | GET | `/api/projects/{id}/exports/{export_pk}/download` | 스냅샷 파일 다운로드 |

---

## 5. 검증 및 테스트 결과 (Verification)

* **로그인 및 인증**: 세션 로그인 및 API Token 발급/인증 정상 작동 확인
* **프로젝트 생성**: 메뉴 3번을 통한 프로젝트 명 입력 및 즉시 생성, 웹 설정 링크 연동 확인
* **라벨러 관리**: 프로젝트 멤버 조회, 추가 가능 사용자 조회(조직 ID 표시), 일괄 추가, 라벨러 제거 정상 작동 확인
* **사용자 등록/제거**: 신규 초대 등록 시 조직 소속 자동 전환 및 멤버 제거 정상 작동 확인
* **비압축 데이터 Import**: 메뉴 13번을 통해 `./images` 폴더 내 12개 이미지 파일을 원본 그대로 개별 업로드 및 22개 태스크 생성 확인 (소요시간 29.58초)
* **데이터 다운로드 및 Export**: JSON 태스크 데이터 및 원본 이미지 수집 ZIP 백업 파일 정상 생성 확인

---
*문서 작성일: 2026-08-24*  
*작성자: Antigravity AI Assistant*
