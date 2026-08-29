#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LabelO API Client
==================
LabelO 솔루션의 REST API를 외부에서 호출하기 위한 Python 클라이언트.

사용법:
    1. 모듈로 임포트:
        from labelo_api_client import LabeloAPIClient
        client = LabeloAPIClient("http://localhost:8080")
        client.login("user@example.com", "password")
        projects = client.list_projects()

    2. 대화형 CLI:
        python labelo_api_client.py
        python labelo_api_client.py --url http://localhost:8080
"""

import argparse
import getpass
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.parse
import zipfile
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from urllib.parse import unquote, urljoin, urlparse

try:
    import requests
except ImportError:
    print("Error: 'requests' 라이브러리가 필요합니다.")
    print("설치: pip install requests")
    sys.exit(1)


# ─────────────────────────────────────────────
#  ANSI Color Helpers (CLI 출력용)
# ─────────────────────────────────────────────
class Color:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def cprint(text: str, color: str = Color.RESET):
    """컬러 텍스트 출력"""
    print(f"{color}{text}{Color.RESET}")


def print_table(headers: List[str], rows: List[List[str]], col_widths: Optional[List[int]] = None):
    """간단한 테이블 출력"""
    if not col_widths:
        col_widths = []
        for i, h in enumerate(headers):
            max_w = len(str(h))
            for row in rows:
                if i < len(row):
                    max_w = max(max_w, len(str(row[i])))
            col_widths.append(min(max_w + 2, 50))

    # 헤더
    header_line = ""
    for i, h in enumerate(headers):
        header_line += str(h).ljust(col_widths[i])
    cprint(header_line, Color.BOLD + Color.CYAN)
    cprint("─" * sum(col_widths), Color.DIM)

    # 행
    for row in rows:
        line = ""
        for i, cell in enumerate(row):
            if i < len(col_widths):
                line += str(cell).ljust(col_widths[i])
        print(line)


# ─────────────────────────────────────────────
#  LabelO API Client 클래스
# ─────────────────────────────────────────────
class LabeloAPIClient:
    """
    LabelO REST API 클라이언트

    Django 세션 로그인을 통해 API Token을 획득하고,
    이후 모든 API 호출에 Token 인증을 사용합니다.
    """

    def __init__(self, base_url: str = "http://localhost:8080"):
        """
        Args:
            base_url: LabelO 서버 URL (예: http://localhost:8080)
        """
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.token: Optional[str] = None
        self.user_info: Optional[Dict] = None

    # ──── 인증 관련 ────

    def login(self, email: str, password: str) -> str:
        """
        이메일과 비밀번호로 LabelO에 로그인하고 API 토큰을 획득합니다.

        Args:
            email: 사용자 이메일 주소
            password: 비밀번호

        Returns:
            API 토큰 문자열

        Raises:
            ConnectionError: 서버 연결 실패
            PermissionError: 로그인 실패 (잘못된 이메일/비밀번호)
        """
        # 1단계: 로그인 페이지에서 CSRF 토큰 획득
        login_url = f"{self.base_url}/user/login/"
        try:
            resp = self.session.get(login_url)
            resp.raise_for_status()
        except requests.ConnectionError:
            raise ConnectionError(f"LabelO 서버에 연결할 수 없습니다: {self.base_url}")
        except requests.HTTPError as e:
            raise ConnectionError(f"로그인 페이지 접근 실패: {e}")

        csrf_token = self.session.cookies.get("csrftoken")
        if not csrf_token:
            # 쿠키에 없으면 미들웨어 설정 확인, 일부 Django 설정에서는 다른 이름일 수 있음
            for cookie in self.session.cookies:
                if "csrf" in cookie.name.lower():
                    csrf_token = cookie.value
                    break

        # 2단계: 세션 로그인
        login_data = {
            "email": email,
            "password": password,
        }
        headers = {
            "Referer": login_url,
        }
        if csrf_token:
            headers["X-CSRFToken"] = csrf_token
            login_data["csrfmiddlewaretoken"] = csrf_token

        resp = self.session.post(login_url, data=login_data, headers=headers, allow_redirects=False)

        # 로그인 성공 시 302 리다이렉트
        if resp.status_code not in (200, 302):
            raise PermissionError(f"로그인 실패 (HTTP {resp.status_code})")

        # 로그인 실패 시 다시 로그인 페이지로 돌아옴 (200 + 에러 메시지)
        if resp.status_code == 200 and "/user/login/" in resp.url:
            raise PermissionError("로그인 실패: 이메일 또는 비밀번호가 올바르지 않습니다.")

        # 3단계: API 토큰 조회
        token_url = f"{self.base_url}/api/current-user/token"
        token_resp = self.session.get(token_url)

        if token_resp.status_code != 200:
            raise PermissionError(f"토큰 조회 실패 (HTTP {token_resp.status_code})")

        data = token_resp.json()
        self.token = data.get("token")

        if not self.token:
            raise PermissionError("토큰을 가져올 수 없습니다.")

        return self.token

    def login_with_token(self, token: str):
        """
        이미 발급받은 API 토큰으로 직접 인증합니다.

        Args:
            token: LabelO API 토큰
        """
        self.token = token

    def _auth_headers(self) -> Dict[str, str]:
        """인증 헤더 생성"""
        if not self.token:
            raise RuntimeError("먼저 login() 또는 login_with_token()을 호출하세요.")
        return {"Authorization": f"Token {self.token}"}

    def _api_get(self, path: str, params: Optional[Dict] = None) -> Any:
        """GET 요청"""
        url = f"{self.base_url}{path}"
        resp = requests.get(url, headers=self._auth_headers(), params=params)
        resp.raise_for_status()
        return resp.json()

    def _api_post(self, path: str, data: Optional[Dict] = None) -> Any:
        """POST 요청"""
        url = f"{self.base_url}{path}"
        resp = requests.post(url, headers=self._auth_headers(), json=data)
        resp.raise_for_status()
        return resp.json()

    def _api_patch(self, path: str, data: Optional[Dict] = None) -> Any:
        """PATCH 요청"""
        url = f"{self.base_url}{path}"
        resp = requests.patch(url, headers=self._auth_headers(), json=data)
        resp.raise_for_status()
        return resp.json()

    def _api_delete(self, path: str, data: Optional[Dict] = None) -> Any:
        """DELETE 요청"""
        url = f"{self.base_url}{path}"
        resp = requests.delete(url, headers=self._auth_headers(), json=data)
        if resp.status_code == 204:
            return {"message": "삭제 완료"}
        resp.raise_for_status()
        return resp.json()

    # ──── 사용자 관련 ────

    def get_whoami(self) -> Dict:
        """현재 로그인된 사용자 정보를 반환합니다."""
        data = self._api_get("/api/current-user/whoami")
        self.user_info = data
        return data

    def list_users(self) -> List[Dict]:
        """조직 내 전체 사용자 목록을 조회합니다."""
        return self._api_get("/api/users/")

    def update_user(self, user_id: int, **kwargs) -> Dict:
        """
        사용자 정보를 수정합니다 (username, first_name, last_name 등).

        Args:
            user_id: 사용자 ID
            **kwargs: 수정할 필드
        """
        return self._api_patch(f"/api/users/{user_id}/", data=kwargs)

    def get_organization(self, organization_id: Optional[int] = None) -> Dict:
        """
        조직 상세 정보를 조회합니다. organization_id가 지정되지 않으면 현재 사용자의 활성 조직 정보를 조회합니다.

        Args:
            organization_id: 조직 ID (선택 사항)

        Returns:
            조직 정보 딕셔너리 (id, title 등 포함)
        """
        if organization_id is None:
            whoami = self.get_whoami()
            organization_id = whoami.get("active_organization")
        if not organization_id:
            raise ValueError("활성 조직 정보가 없습니다.")
        return self._api_get(f"/api/organizations/{organization_id}")

    def get_invite_token(self) -> Dict:
        """현재 조직의 초대 링크 및 토큰을 조회합니다."""
        return self._api_get("/api/invite")

    def update_organization_member_role(self, organization_id: int, user_id: int, role: str) -> Dict:
        """
        조직 내 사용자의 역할을 변경합니다.

        Args:
            organization_id: 조직 ID
            user_id: 사용자 ID
            role: 역할 (annotater, reviewer, manager, administrator)
        """
        return self._api_patch(
            f"/api/organizations/{organization_id}/memberships/update/{user_id}",
            data={"group": role},
        )

    def remove_organization_member(self, organization_id: int, user_id: int) -> Dict:
        """
        조직에서 사용자를 제거합니다 (소프트 삭제).

        Args:
            organization_id: 조직 ID
            user_id: 사용자 ID
        """
        return self._api_delete(f"/api/organizations/{organization_id}/memberships/{user_id}/")

    def delete_user(self, user_id: int, organization_id: Optional[int] = None) -> Dict:
        """
        사용자를 제거합니다. 조직 ID가 주어지면 조직 멤버십을 해제하고, 그렇지 않으면 사용자 계정 삭제를 시도합니다.

        Args:
            user_id: 사용자 ID
            organization_id: 조직 ID (선택 사항)
        """
        if organization_id:
            try:
                return self.remove_organization_member(organization_id, user_id)
            except Exception:
                pass
        return self._api_delete(f"/api/users/{user_id}/")

    # ──── 프로젝트 관련 ────

    def list_projects(self, page: int = 1, page_size: int = 100) -> Dict:
        """
        프로젝트 목록을 조회합니다.

        Args:
            page: 페이지 번호
            page_size: 페이지당 항목 수

        Returns:
            프로젝트 목록 (results, count 포함)
        """
        return self._api_get("/api/projects/", params={"page": page, "page_size": page_size})

    def get_project(self, project_id: int) -> Dict:
        """
        특정 프로젝트의 상세 정보를 조회합니다.

        Args:
            project_id: 프로젝트 ID
        """
        return self._api_get(f"/api/projects/{project_id}/")

    def create_project(self, title: str, description: Optional[str] = "") -> Dict:
        """
        새 프로젝트를 생성합니다.

        Args:
            title: 프로젝트 이름
            description: 프로젝트 설명 (선택 사항)

        Returns:
            생성된 프로젝트 정보 딕셔너리 (id, title, created_at 등)
        """
        data = {"title": title}
        if description:
            data["description"] = description
        return self._api_post("/api/projects/", data=data)

    def import_tasks(
        self,
        project_id: int,
        tasks: Optional[Union[List[Dict], Dict]] = None,
        file_path: Optional[str] = None,
        on_progress: Optional[Callable[[int, int, str, str], None]] = None,
    ) -> Dict:
        """
        프로젝트에 라벨링할 데이터(태스크)를 가져옵니다 (Import).
        폴더 경로를 지정하면 내부의 파일들을 압축하지 않고 원본 그대로 개별 업로드합니다.

        Args:
            project_id: 프로젝트 ID
            tasks: 가져올 태스크 데이터 목록 또는 딕셔너리 (JSON)
            file_path: 업로드할 파일 또는 폴더 경로 (JSON, CSV, 이미지, 텍스트 등)
            on_progress: 다중 파일 업로드 시 진행률 콜백 함수 (current, total, filename, status)

        Returns:
            가져오기 결과 딕셔너리 (task_count, annotation_count, duration, data_columns 등)
        """
        url = f"{self.base_url}/api/projects/{project_id}/import"
        if file_path:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"파일 또는 폴더를 찾을 수 없습니다: {file_path}")

            # 1. 디렉토리(폴더)인 경우: 압축하지 않고 내부의 파일들을 개별 원본 그대로 업로드
            if os.path.isdir(file_path):
                all_files = []
                for root, _, filenames in os.walk(file_path):
                    for fname in sorted(filenames):
                        # 숨김 파일 및 시스템 파일 제외
                        if fname.startswith(".") or fname.lower() in ["thumbs.db", "desktop.ini"]:
                            continue
                        all_files.append(os.path.join(root, fname))

                if not all_files:
                    raise ValueError(f"폴더에 업로드 가능한 파일이 없습니다: {file_path}")

                total_files = len(all_files)
                total_task_count = 0
                total_annotation_count = 0
                all_data_columns = set()
                start_time = time.time()

                for idx, full_path in enumerate(all_files, 1):
                    fname = os.path.basename(full_path)
                    try:
                        with open(full_path, "rb") as f:
                            files = {"file": (fname, f)}
                            resp = requests.post(url, headers=self._auth_headers(), files=files)
                            if not resp.ok:
                                try:
                                    err_json = resp.json()
                                    err_msg = err_json.get("detail", err_json.get("error", resp.text))
                                except Exception:
                                    err_msg = resp.text
                                if on_progress:
                                    on_progress(idx, total_files, fname, "error")
                                raise requests.HTTPError(f"HTTP {resp.status_code}: {err_msg}", response=resp)

                            res_json = resp.json()
                            total_task_count += res_json.get("task_count", 0)
                            total_annotation_count += res_json.get("annotation_count", 0)
                            for col in res_json.get("data_columns", []):
                                all_data_columns.add(col)

                            if on_progress:
                                on_progress(idx, total_files, fname, "success")
                    except Exception as e:
                        if on_progress:
                            on_progress(idx, total_files, fname, "error")
                        raise

                duration = time.time() - start_time
                return {
                    "task_count": total_task_count,
                    "annotation_count": total_annotation_count,
                    "duration": duration,
                    "data_columns": list(all_data_columns),
                    "file_count": total_files,
                }

            # 2. 단일 파일인 경우
            else:
                filename = os.path.basename(file_path)
                with open(file_path, "rb") as f:
                    files = {"file": (filename, f)}
                    resp = requests.post(url, headers=self._auth_headers(), files=files)
                    if not resp.ok:
                        try:
                            err_json = resp.json()
                            err_msg = err_json.get("detail", err_json.get("error", resp.text))
                        except Exception:
                            err_msg = resp.text
                        raise requests.HTTPError(f"HTTP {resp.status_code}: {err_msg}", response=resp)
                    return resp.json()

        elif tasks is not None:
            return self._api_post(f"/api/projects/{project_id}/import", data=tasks)
        else:
            raise ValueError("tasks 데이터 또는 file_path 중 하나를 지정해야 합니다.")

    # ──── 프로젝트 멤버(라벨러) 관리 ────

    def get_project_members(self, project_id: int) -> List[Dict]:
        """
        프로젝트의 현재 멤버(라벨러) 목록을 조회합니다.

        Args:
            project_id: 프로젝트 ID

        Returns:
            프로젝트 멤버 목록
        """
        return self._api_get(f"/api/projects/{project_id}/members/")

    def get_available_users(self, project_id: int) -> List[Dict]:
        """
        프로젝트에 아직 등록되지 않은 추가 가능한 사용자 목록을 조회합니다.

        Args:
            project_id: 프로젝트 ID

        Returns:
            추가 가능한 사용자 목록
        """
        return self._api_get(f"/api/projects/{project_id}/get-users/")

    def add_labeler(self, project_id: int, user_id: int) -> Dict:
        """
        사용자를 프로젝트의 라벨러(멤버)로 등록합니다.

        Args:
            project_id: 프로젝트 ID
            user_id: 등록할 사용자 ID

        Returns:
            등록된 멤버 정보
        """
        return self._api_post(f"/api/projects/{project_id}/members/", data={"user": user_id})

    def remove_labeler(self, project_id: int, user_id: int) -> Dict:
        """
        프로젝트에서 라벨러(멤버)를 제거합니다.

        Args:
            project_id: 프로젝트 ID
            user_id: 제거할 사용자 ID

        Returns:
            삭제 결과
        """
        return self._api_delete(f"/api/projects/{project_id}/members/", data={"user": user_id})

    def add_labelers_bulk(self, project_id: int, user_ids: List[int]) -> List[Dict]:
        """
        여러 사용자를 한번에 프로젝트의 라벨러로 등록합니다.

        Args:
            project_id: 프로젝트 ID
            user_ids: 등록할 사용자 ID 목록

        Returns:
            등록 결과 목록
        """
        results = []
        for uid in user_ids:
            try:
                result = self.add_labeler(project_id, uid)
                results.append({"user_id": uid, "status": "success", "data": result})
            except requests.HTTPError as e:
                results.append({"user_id": uid, "status": "error", "error": str(e)})
        return results

    # ──── 사용자 등록(회원가입) ────

    def register_user(self, email: str, password: str, username: str, organization_name: str) -> Dict:
        """
        새로운 사용자를 등록(회원가입)합니다.
        로그인 없이 사용할 수 있습니다.

        Args:
            email: 사용자 이메일 주소
            password: 비밀번호 (8~64자)
            username: 사용자 이름
            organization_name: 조직 이름

        Returns:
            등록 결과 정보 딕셔너리

        Raises:
            ConnectionError: 서버 연결 실패
            ValueError: 유효성 검사 실패 (이메일 중복, 비밀번호 조건 불일치 등)
        """
        signup_url = f"{self.base_url}/user/signup/"

        # 1단계: 회원가입 페이지에서 CSRF 토큰 획득
        session = requests.Session()
        try:
            resp = session.get(signup_url)
            resp.raise_for_status()
        except requests.ConnectionError:
            raise ConnectionError(f"LabelO 서버에 연결할 수 없습니다: {self.base_url}")
        except requests.HTTPError as e:
            raise ConnectionError(f"회원가입 페이지 접근 실패: {e}")

        csrf_token = session.cookies.get("csrftoken")
        if not csrf_token:
            for cookie in session.cookies:
                if "csrf" in cookie.name.lower():
                    csrf_token = cookie.value
                    break

        # 2단계: 회원가입 요청
        signup_data = {
            "email": email,
            "password": password,
            "re_password": password,
            "name": username,
            "organization_name": organization_name,
        }
        headers = {
            "Referer": signup_url,
        }
        if csrf_token:
            headers["X-CSRFToken"] = csrf_token
            signup_data["csrfmiddlewaretoken"] = csrf_token

        resp = session.post(signup_url, data=signup_data, headers=headers, allow_redirects=False)

        # 성공 시 302 리다이렉트, 실패 시 200 + 에러 메시지
        if resp.status_code == 302:
            return {
                "status": "success",
                "message": "사용자 등록이 완료되었습니다.",
                "email": email,
                "username": username,
                "organization": organization_name,
            }
        elif resp.status_code == 200:
            # 폼 에러 메시지 추출 시도
            error_msg = "등록에 실패했습니다."
            if "already exists" in resp.text.lower():
                error_msg = "이미 존재하는 이메일입니다."
            elif "password" in resp.text.lower() and ("8" in resp.text or "length" in resp.text.lower()):
                error_msg = "비밀번호는 8~64자 사이여야 합니다."
            elif "don" in resp.text.lower() and "match" in resp.text.lower():
                error_msg = "비밀번호가 일치하지 않습니다."
            raise ValueError(error_msg)
        else:
            raise ValueError(f"회원가입 실패 (HTTP {resp.status_code})")

    def invite_user(self, email: str, password: str, username: str, role: str = "annotater") -> Dict:
        """
        새로운 사용자를 생성하고 현재 로그인된 사용자의 조직에 추가하며 역할을 부여합니다.
        비밀번호가 설정된 상태로 등록되므로 즉시 로그인이 가능합니다.

        처리 순서:
        1. 현재 조직 정보 및 초대 링크/토큰 조회 (GET /api/invite, GET /api/current-user/whoami)
        2. 초대 링크(/user/invite/?token={token})를 통해 새 사용자를 현재 조직의 활성 멤버로 등록
           - 별도의 독립 조직이 아닌 현재 로그인된 사용자의 조직 소속(status='active')으로 생성됨
        3. 생성된 사용자의 ID 조회 (GET /api/users/)
        4. 조직 내 역할(annotater, reviewer, manager, administrator) 부여
           (PATCH /api/organizations/{org_id}/memberships/update/{user_id})
        5. 사용자 이름(username) 설정 (PATCH /api/users/{user_id}/)

        Args:
            email: 사용자 이메일 주소
            password: 비밀번호 (8~64자)
            username: 사용자 이름
            role: 역할 (annotater, reviewer, manager, administrator)

        Returns:
            등록 결과 정보 딕셔너리

        Raises:
            RuntimeError: 로그인되지 않은 상태
            ConnectionError: 서버 연결 실패
            ValueError: 유효성 검사 실패
        """
        if not self.token:
            raise RuntimeError("먼저 login() 또는 login_with_token()을 호출하세요.")

        if not email or "@" not in email:
            raise ValueError("유효한 이메일 주소를 입력하세요.")
        if len(password) < 8 or len(password) > 64:
            raise ValueError("비밀번호는 8~64자 사이여야 합니다.")

        # 1. 현재 조직 정보 및 초대 토큰 조회
        whoami = self.get_whoami()
        active_org_id = whoami.get("active_organization")
        org_title = ""
        if active_org_id:
            try:
                org_info = self.get_organization(active_org_id)
                org_title = org_info.get("title", "")
            except Exception:
                pass

        try:
            invite_info = self._api_get("/api/invite")
            invite_url_path = invite_info.get("invite_url", "")
            token = invite_info.get("token", "")
        except Exception as e:
            raise ConnectionError(f"조직 초대 정보를 가져올 수 없습니다: {e}")

        # 초대 URL 구성
        if invite_url_path.startswith("http"):
            full_invite_url = invite_url_path
        else:
            full_invite_url = f"{self.base_url.rstrip('/')}/{invite_url_path.lstrip('/')}"

        # 2. 초대 링크를 통해 새 사용자를 현재 조직 멤버로 직접 가입
        session = requests.Session()
        try:
            get_resp = session.get(full_invite_url)
        except requests.RequestException as e:
            raise ConnectionError(f"서버에 연결할 수 없습니다: {e}")

        # CSRF 토큰 추출
        csrf_token = session.cookies.get("csrftoken")
        if not csrf_token:
            import re
            m = re.search(r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)["\']', get_resp.text)
            if m:
                csrf_token = m.group(1)

        signup_data = {
            "email": email,
            "password": password,
        }
        if csrf_token:
            signup_data["csrfmiddlewaretoken"] = csrf_token

        headers = {
            "Referer": full_invite_url,
        }
        if csrf_token:
            headers["X-CSRFToken"] = csrf_token

        try:
            resp = session.post(full_invite_url, data=signup_data, headers=headers, allow_redirects=False)
        except requests.RequestException as e:
            raise ConnectionError(f"회원가입 요청 실패: {e}")

        user_already_exists = False
        if resp.status_code == 302:
            # 성공 (리다이렉트)
            pass
        elif resp.status_code == 200:
            resp_text = resp.text.lower()
            if "already exists" in resp_text:
                user_already_exists = True
            elif "password" in resp_text and ("8" in resp_text or "length" in resp_text):
                raise ValueError("비밀번호는 8~64자 사이여야 합니다.")
            elif "invalid token" in resp_text:
                raise ValueError("초대 토큰이 유효하지 않습니다.")
            else:
                raise ValueError("사용자 등록에 실패했습니다.")
        else:
            raise ValueError(f"사용자 등록 실패 (HTTP {resp.status_code})")

        # 3. 사용자 ID 찾기
        users = self.list_users()
        user_obj = next((u for u in users if u.get("email", "").lower() == email.lower()), None)
        user_id = user_obj.get("id") if user_obj else None

        # 만약 이미 존재하던 사용자라면 조직에 멤버십을 생성/동기화하기 위해 send-mail 호출
        if user_already_exists:
            try:
                self._api_post("/api/invite/send-mail", {"email": email, "role": role})
            except Exception:
                pass
            users = self.list_users()
            user_obj = next((u for u in users if u.get("email", "").lower() == email.lower()), None)
            user_id = user_obj.get("id") if user_obj else None

        # 4. 조직 내 역할(role) 부여 및 활성화
        if user_id and active_org_id and role:
            try:
                self.update_organization_member_role(active_org_id, user_id, role)
            except Exception:
                pass

        # 5. 사용자 이름(username / first_name) 업데이트
        if user_id and username:
            try:
                self.update_user(user_id, username=username, first_name=username)
            except Exception:
                pass

        org_name_str = org_title or (f"ID: {active_org_id}" if active_org_id else "")
        return {
            "status": "success",
            "message": f"사용자가 등록되고 조직 '{org_name_str}'에 추가되었으며 역할이 부여되었습니다.",
            "id": user_id,
            "email": email,
            "username": username,
            "role": role,
            "organization_id": active_org_id,
            "organization_name": org_title,
        }

    # ──── 파일 다운로드 헬퍼 ────

    def _api_get_file(self, path: str, params: Optional[Dict] = None) -> requests.Response:
        """파일 바이너리를 다운로드하기 위한 GET 요청 (스트리밍)"""
        url = f"{self.base_url}{path}"
        resp = requests.get(url, headers=self._auth_headers(), params=params, stream=True)
        resp.raise_for_status()
        return resp

    # ──── 프로젝트 진행상황 모니터링 ────

    def get_project_summary(self, project_id: int) -> Dict:
        """
        프로젝트의 요약 정보(라벨 통계 등)를 조회합니다.

        Args:
            project_id: 프로젝트 ID

        Returns:
            프로젝트 요약 정보 (created_labels, created_annotations 등)
        """
        return self._api_get(f"/api/projects/{project_id}/summary/")

    def get_project_tasks(self, project_id: int, page: int = 1, page_size: int = 100) -> Dict:
        """
        프로젝트의 태스크 목록을 조회합니다.

        Args:
            project_id: 프로젝트 ID
            page: 페이지 번호
            page_size: 페이지당 항목 수

        Returns:
            태스크 목록 (results, count 등 포함)
        """
        return self._api_get(
            f"/api/projects/{project_id}/tasks/",
            params={"page": page, "page_size": page_size},
        )

    def get_project_progress(self, project_id: int) -> Dict:
        """
        프로젝트의 작업 진행상황을 종합적으로 조회합니다.
        프로젝트 상세 정보와 요약 정보를 결합하여 반환합니다.

        Args:
            project_id: 프로젝트 ID

        Returns:
            진행상황 정보 딕셔너리:
            - title: 프로젝트 제목
            - task_number: 전체 태스크 수
            - finished_task_number: 완료된 태스크 수
            - total_annotations_number: 전체 어노테이션 수
            - total_predictions_number: 전체 예측 수
            - num_tasks_with_annotations: 어노테이션이 있는 태스크 수
            - progress_percent: 진행률 (%)
            - summary: 프로젝트 요약 정보
        """
        project = self.get_project(project_id)
        summary = self.get_project_summary(project_id)

        task_number = project.get("task_number", 0) or 0
        finished = project.get("finished_task_number", 0) or 0
        num_with_annotations = project.get("num_tasks_with_annotations", 0) or 0
        total_annotations = project.get("total_annotations_number", 0) or 0
        total_predictions = project.get("total_predictions_number", 0) or 0

        progress_percent = (finished / task_number * 100) if task_number > 0 else 0.0

        return {
            "project_id": project_id,
            "title": project.get("title", ""),
            "task_number": task_number,
            "finished_task_number": finished,
            "num_tasks_with_annotations": num_with_annotations,
            "total_annotations_number": total_annotations,
            "total_predictions_number": total_predictions,
            "progress_percent": round(progress_percent, 1),
            "created_at": project.get("created_at", ""),
            "summary": summary,
        }

    # ──── 전체 사용자별 프로젝트 통계 ────

    def get_all_projects_stats(self) -> Dict:
        """
        전체 사용자 ID를 기준으로 프로젝트 수, 라벨링 완료 프로젝트 수,
        라벨링 중인 프로젝트 수를 통합 집계하여 반환합니다.

        프로젝트 상태 판정 기준:
        - 라벨링 완료: finished_task_number == task_number (task_number > 0)
        - 라벨링 중: num_tasks_with_annotations > 0 이고 아직 완료되지 않은 경우
        - 미시작: num_tasks_with_annotations == 0

        Returns:
            통계 딕셔너리:
            - total_projects: 전체 프로젝트 수
            - completed_projects: 라벨링 완료 프로젝트 수
            - in_progress_projects: 라벨링 중인 프로젝트 수
            - not_started_projects: 미시작 프로젝트 수
            - total_tasks: 전체 태스크 수 합계
            - total_finished_tasks: 완료된 태스크 수 합계
            - total_annotations: 전체 어노테이션 수 합계
            - overall_progress_percent: 전체 진행률 (%)
            - per_user: 사용자별 통계 딕셔너리 {user_id: {...}}
            - projects: 프로젝트별 상세 정보 리스트
        """
        # 모든 프로젝트를 페이징으로 조회
        all_projects = []
        page = 1
        while True:
            data = self.list_projects(page=page, page_size=100)
            projects = data.get("results", data) if isinstance(data, dict) else data
            if not projects:
                break
            all_projects.extend(projects)
            total_count = data.get("count", 0) if isinstance(data, dict) else len(projects)
            if len(all_projects) >= total_count:
                break
            page += 1

        # 전체 사용자 목록 조회
        users = self.list_users()
        user_map = {}
        for u in users:
            uid = u.get("id")
            name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
            user_map[uid] = {
                "user_id": uid,
                "email": u.get("email", ""),
                "name": name if name else u.get("email", ""),
                "role": u.get("active_org_role", "N/A"),
                "total_projects": 0,
                "completed_projects": 0,
                "in_progress_projects": 0,
                "not_started_projects": 0,
            }

        # 전체 통계 초기화
        total_projects = len(all_projects)
        completed_projects = 0
        in_progress_projects = 0
        not_started_projects = 0
        total_tasks = 0
        total_finished_tasks = 0
        total_annotations = 0

        project_details = []

        for p in all_projects:
            pid = p.get("id")
            task_num = p.get("task_number", 0) or 0
            finished_num = p.get("finished_task_number", 0) or 0
            num_with_ann = p.get("num_tasks_with_annotations", 0) or 0
            ann_count = p.get("total_annotations_number", 0) or 0
            members = p.get("members", [])

            total_tasks += task_num
            total_finished_tasks += finished_num
            total_annotations += ann_count

            # 프로젝트 상태 판정
            if task_num > 0 and finished_num >= task_num:
                status = "completed"
                completed_projects += 1
            elif num_with_ann > 0:
                status = "in_progress"
                in_progress_projects += 1
            else:
                status = "not_started"
                not_started_projects += 1

            progress_pct = (finished_num / task_num * 100) if task_num > 0 else 0.0

            # 멤버별 통계 갱신
            member_ids = []
            if isinstance(members, list):
                for m in members:
                    if isinstance(m, dict):
                        mid = m.get("id")
                    else:
                        mid = m
                    if mid is not None:
                        member_ids.append(mid)
                        if mid in user_map:
                            user_map[mid]["total_projects"] += 1
                            if status == "completed":
                                user_map[mid]["completed_projects"] += 1
                            elif status == "in_progress":
                                user_map[mid]["in_progress_projects"] += 1
                            else:
                                user_map[mid]["not_started_projects"] += 1

            # created_by도 멤버로 간주
            created_by = p.get("created_by", {})
            if isinstance(created_by, dict):
                creator_id = created_by.get("id")
            else:
                creator_id = created_by
            if creator_id and creator_id not in member_ids:
                if creator_id in user_map:
                    user_map[creator_id]["total_projects"] += 1
                    if status == "completed":
                        user_map[creator_id]["completed_projects"] += 1
                    elif status == "in_progress":
                        user_map[creator_id]["in_progress_projects"] += 1
                    else:
                        user_map[creator_id]["not_started_projects"] += 1

            project_details.append({
                "id": pid,
                "title": p.get("title", ""),
                "task_number": task_num,
                "finished_task_number": finished_num,
                "num_tasks_with_annotations": num_with_ann,
                "total_annotations_number": ann_count,
                "progress_percent": round(progress_pct, 1),
                "status": status,
                "member_count": len(member_ids),
            })

        overall_progress = (total_finished_tasks / total_tasks * 100) if total_tasks > 0 else 0.0

        return {
            "total_projects": total_projects,
            "completed_projects": completed_projects,
            "in_progress_projects": in_progress_projects,
            "not_started_projects": not_started_projects,
            "total_tasks": total_tasks,
            "total_finished_tasks": total_finished_tasks,
            "total_annotations": total_annotations,
            "overall_progress_percent": round(overall_progress, 1),
            "per_user": user_map,
            "projects": project_details,
        }

    # ──── 프로젝트 데이터 다운로드 ────

    @staticmethod
    def _is_media_url(val: Any) -> bool:
        """값이 이미지 또는 미디어 파일의 URL/경로인지 확인합니다."""
        if not isinstance(val, str):
            return False
        val_clean = val.strip()
        if not val_clean or val_clean.startswith("data:"):
            return False
        if val_clean.startswith(("/data/upload/", "/data/local-files/", "/storage-data/", "/data/")):
            return True
        if val_clean.startswith(("http://", "https://")):
            return True
        path = val_clean.split("?")[0].split("#")[0]
        ext = os.path.splitext(path)[1].lower()
        media_extensions = {
            ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif", ".svg", ".ico",
            ".mp3", ".wav", ".ogg", ".m4a", ".flac",
            ".mp4", ".avi", ".mov", ".webm", ".mkv",
            ".pdf", ".txt", ".pcd", ".bin"
        }
        return ext in media_extensions

    @classmethod
    def _extract_media_urls_from_data(cls, data: Any) -> set:
        """JSON 데이터(태스크 리스트 또는 딕셔너리)에서 모든 이미지/미디어 URL을 재귀적으로 추출합니다."""
        media_urls = set()

        def _scan(obj):
            if isinstance(obj, str):
                if cls._is_media_url(obj):
                    media_urls.add(obj)
            elif isinstance(obj, dict):
                for v in obj.values():
                    _scan(v)
            elif isinstance(obj, list):
                for item in obj:
                    _scan(item)

        _scan(data)
        return media_urls

    def _download_images_to_dir(
        self,
        media_urls: set,
        images_dir: str,
        progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
    ) -> int:
        """
        주어진 media_urls 목록의 모든 이미지를 images_dir에 다운로드합니다.

        Returns:
            성공적으로 다운로드된 이미지 수
        """
        os.makedirs(images_dir, exist_ok=True)
        used_filenames = set()
        total_images = len(media_urls)
        downloaded_count = 0

        for idx, raw_url in enumerate(sorted(media_urls), 1):
            parsed = urllib.parse.urlparse(raw_url)
            path = urllib.parse.unquote(parsed.path)
            fname = os.path.basename(path)
            if not fname:
                fname = f"image_{idx}.jpg"

            base, ext = os.path.splitext(fname)
            candidate_name = fname
            counter = 1
            while candidate_name in used_filenames:
                candidate_name = f"{base}_{counter}{ext}"
                counter += 1
            fname = candidate_name
            used_filenames.add(fname)

            if raw_url.startswith(("http://", "https://")):
                download_url = raw_url
            elif raw_url.startswith("/"):
                download_url = f"{self.base_url}{raw_url}"
            else:
                download_url = f"{self.base_url}/{raw_url}"

            target_img_path = os.path.join(images_dir, fname)
            status_msg = "success"
            try:
                headers = self._auth_headers() if (self.base_url in download_url or download_url.startswith("/")) else {}
                img_resp = requests.get(download_url, headers=headers, stream=True, timeout=30)
                if img_resp.status_code == 200:
                    with open(target_img_path, "wb") as img_f:
                        for chunk in img_resp.iter_content(chunk_size=8192):
                            img_f.write(chunk)
                    downloaded_count += 1
                else:
                    status_msg = f"failed (HTTP {img_resp.status_code})"
            except Exception as e:
                status_msg = f"failed ({e})"

            if progress_callback:
                progress_callback(idx, total_images, fname, status_msg)

        return downloaded_count

    def download_project_tasks(
        self,
        project_id: int,
        output_dir: str = ".",
        download_all: bool = True,
        export_type: str = "JSON",
        include_images: bool = True,
        progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
    ) -> str:
        """
        프로젝트의 태스크 데이터를 파일로 다운로드합니다.
        include_images=True인 경우, 태스크에 포함된 이미지/미디어 파일까지 모두 다운로드하여
        JSON과 함께 ZIP 파일로 압축하여 저장합니다.

        Args:
            project_id: 프로젝트 ID
            output_dir: 저장할 디렉토리 경로 (기본: 현재 디렉토리)
            download_all: True이면 모든 태스크, False이면 어노테이션된 태스크만
            export_type: 내보내기 형식 (기본: JSON)
            include_images: True이면 이미지 파일도 함께 다운로드하여 ZIP으로 압축 (기본: True)
            progress_callback: 다운로드 진행률 콜백 함수 (current, total, filename, status)

        Returns:
            저장된 파일(ZIP 또는 원본 파일)의 전체 경로
        """
        params = {
            "exportType": export_type,
            "download_all_tasks": str(download_all).lower(),
        }

        os.makedirs(output_dir, exist_ok=True)

        resp = self._api_get_file(f"/api/projects/{project_id}/export", params=params)

        # JSON 포맷이 아니거나 이미지 다운로드가 비활성화된 경우 기존 방식 처리
        if not export_type.upper().startswith("JSON") or not include_images:
            content_disp = resp.headers.get("Content-Disposition", "")
            filename = None
            if "filename=" in content_disp:
                filename = content_disp.split("filename=")[-1].strip('"').strip("'")
            if not filename:
                ext = "json" if export_type.upper().startswith("JSON") else export_type.lower()
                filename = resp.headers.get("filename", f"project-{project_id}-tasks.{ext}")

            filepath = os.path.join(output_dir, filename)
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return os.path.abspath(filepath)

        # JSON 데이터 파싱
        try:
            tasks_data = resp.json()
        except Exception:
            # JSON 파싱 실패 시 원본 바이너리 저장
            content_disp = resp.headers.get("Content-Disposition", "")
            filename = content_disp.split("filename=")[-1].strip('"').strip("'") if "filename=" in content_disp else f"project-{project_id}-tasks.json"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return os.path.abspath(filepath)

        # 미디어 URL 수집
        media_urls = self._extract_media_urls_from_data(tasks_data)

        # 임시 디렉토리 생성 및 파일 수집
        with tempfile.TemporaryDirectory() as tmp_dir:
            # 1. JSON 파일 저장
            prefix = "tasks" if download_all else "labeled-tasks"
            json_filename = f"project-{project_id}-{prefix}.json"
            json_path = os.path.join(tmp_dir, json_filename)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(tasks_data, f, ensure_ascii=False, indent=2)

            # 2. 이미지 다운로드
            images_dir = os.path.join(tmp_dir, "images")
            self._download_images_to_dir(media_urls, images_dir, progress_callback=progress_callback)

            # 3. ZIP 파일 압축
            zip_filename = f"project-{project_id}-{prefix}.zip"
            zip_filepath = os.path.join(output_dir, zip_filename)

            with zipfile.ZipFile(zip_filepath, "w", zipfile.ZIP_DEFLATED) as zf:
                # JSON 파일 아카이브에 추가
                zf.write(json_path, arcname=json_filename)
                # images 폴더 아카이브에 추가
                for root, _, files in os.walk(images_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, tmp_dir)
                        zf.write(file_path, arcname=rel_path)

            return os.path.abspath(zip_filepath)

    # ──── 라벨링 데이터 Export ────

    def get_export_formats(self, project_id: int) -> List[Dict]:
        """
        프로젝트에서 사용 가능한 Export 포맷 목록을 조회합니다.

        Args:
            project_id: 프로젝트 ID

        Returns:
            사용 가능한 포맷 목록 (name, title, disabled 등)
        """
        return self._api_get(f"/api/projects/{project_id}/export/formats")

    def create_export_snapshot(
        self,
        project_id: int,
        title: Optional[str] = None,
        task_filter_options: Optional[Dict] = None,
        annotation_filter_options: Optional[Dict] = None,
        serialization_options: Optional[Dict] = None,
    ) -> Dict:
        """
        Export 스냅샷을 생성합니다. 백그라운드에서 Export 파일이 생성됩니다.

        Args:
            project_id: 프로젝트 ID
            title: Export 제목 (선택)
            task_filter_options: 태스크 필터 옵션 (선택)
            annotation_filter_options: 어노테이션 필터 옵션 (선택)
            serialization_options: 직렬화 옵션 (선택)

        Returns:
            생성된 Export 정보 (id, status, title 등)
        """
        data = {}
        if title:
            data["title"] = title
        if task_filter_options:
            data["task_filter_options"] = task_filter_options
        if annotation_filter_options:
            data["annotation_filter_options"] = annotation_filter_options
        if serialization_options:
            data["serialization_options"] = serialization_options

        return self._api_post(f"/api/projects/{project_id}/exports/", data=data)

    def list_export_snapshots(self, project_id: int) -> List[Dict]:
        """
        프로젝트의 Export 스냅샷 목록을 조회합니다.

        Args:
            project_id: 프로젝트 ID

        Returns:
            Export 스냅샷 목록
        """
        return self._api_get(f"/api/projects/{project_id}/exports/")

    def get_export_snapshot(self, project_id: int, export_pk: int) -> Dict:
        """
        특정 Export 스냅샷의 상세 정보를 조회합니다.

        Args:
            project_id: 프로젝트 ID
            export_pk: Export 스냅샷 ID

        Returns:
            Export 스냅샷 상세 정보
        """
        return self._api_get(f"/api/projects/{project_id}/exports/{export_pk}")

    def download_export_snapshot(
        self,
        project_id: int,
        export_pk: int,
        export_type: Optional[str] = None,
        output_dir: str = ".",
        include_images: bool = True,
        progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
    ) -> str:
        """
        Export 스냅샷 파일을 다운로드합니다.
        include_images=True인 경우, 라벨링 데이터에 포함된 이미지 파일까지 다운로드하여
        ZIP 파일로 압축하여 저장합니다.

        Args:
            project_id: 프로젝트 ID
            export_pk: Export 스냅샷 ID
            export_type: 변환할 포맷 (선택, None이면 원본 JSON)
            output_dir: 저장할 디렉토리 경로 (기본: 현재 디렉토리)
            include_images: True이면 이미지 파일도 함께 다운로드하여 ZIP으로 압축 (기본: True)
            progress_callback: 다운로드 진행률 콜백 함수

        Returns:
            저장된 파일의 전체 경로
        """
        params = {}
        if export_type:
            params["exportType"] = export_type

        resp = self._api_get_file(
            f"/api/projects/{project_id}/exports/{export_pk}/download",
            params=params,
        )

        # 파일명 추출
        content_disp = resp.headers.get("Content-Disposition", "")
        filename = None
        if "filename=" in content_disp:
            filename = content_disp.split("filename=")[-1].strip('"').strip("'")
        if not filename:
            ext = export_type.lower() if export_type else "json"
            filename = resp.headers.get("filename", f"project-{project_id}-export-{export_pk}.{ext}")

        os.makedirs(output_dir, exist_ok=True)

        if not include_images:
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return os.path.abspath(filepath)

        # 이미지 포함 ZIP 패키징
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_download_path = os.path.join(tmp_dir, filename)
            with open(temp_download_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            # 다운로드된 파일이 ZIP인지 JSON/기타 파일인지 확인
            extract_dir = os.path.join(tmp_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)

            if zipfile.is_zipfile(temp_download_path):
                with zipfile.ZipFile(temp_download_path, "r") as zf:
                    zf.extractall(extract_dir)
            else:
                shutil.copy(temp_download_path, os.path.join(extract_dir, filename))

            # JSON/데이터 파일에서 미디어 URL 수집
            media_urls = set()
            for root, _, files in os.walk(extract_dir):
                for f in files:
                    if f.endswith(".json"):
                        fpath = os.path.join(root, f)
                        try:
                            with open(fpath, "r", encoding="utf-8") as jf:
                                jdata = json.load(jf)
                                media_urls.update(self._extract_media_urls_from_data(jdata))
                        except Exception:
                            pass

            # 이미지 다운로드
            images_dir = os.path.join(extract_dir, "images")
            self._download_images_to_dir(media_urls, images_dir, progress_callback=progress_callback)

            # 최종 ZIP 압축
            base_name, _ = os.path.splitext(filename)
            zip_filename = f"{base_name}.zip" if not filename.endswith(".zip") else filename
            zip_filepath = os.path.join(output_dir, zip_filename)

            with zipfile.ZipFile(zip_filepath, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(extract_dir):
                    for file in files:
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, extract_dir)
                        zf.write(full_path, arcname=rel_path)

            return os.path.abspath(zip_filepath)

    def export_and_download(
        self,
        project_id: int,
        export_type: str = "JSON",
        output_dir: str = ".",
        poll_interval: int = 2,
        max_wait: int = 300,
        task_filter_options: Optional[Dict] = None,
        annotation_filter_options: Optional[Dict] = None,
        serialization_options: Optional[Dict] = None,
        include_images: bool = True,
        progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
    ) -> str:
        """
        Export 스냅샷을 생성하고, 완료될 때까지 대기한 후 파일을 다운로드합니다.
        대규모 프로젝트에 적합한 비동기 Export 방식입니다.

        Args:
            project_id: 프로젝트 ID
            export_type: 내보내기 형식 (기본: JSON)
            output_dir: 저장할 디렉토리 경로 (기본: 현재 디렉토리)
            poll_interval: 상태 확인 간격 (초, 기본: 2)
            max_wait: 최대 대기 시간 (초, 기본: 300)
            task_filter_options: 태스크 필터 옵션 (선택)
            annotation_filter_options: 어노테이션 필터 옵션 (선택)
            serialization_options: 직렬화 옵션 (선택)
            include_images: True이면 이미지 파일도 함께 다운로드하여 ZIP으로 압축 (기본: True)
            progress_callback: 다운로드 진행률 콜백 함수

        Returns:
            저장된 파일의 전체 경로

        Raises:
            TimeoutError: 최대 대기 시간 초과
            RuntimeError: Export 실패
        """
        # 1. Export 스냅샷 생성
        snapshot = self.create_export_snapshot(
            project_id,
            task_filter_options=task_filter_options,
            annotation_filter_options=annotation_filter_options,
            serialization_options=serialization_options,
        )
        export_pk = snapshot["id"]

        # 2. 완료될 때까지 폴링
        elapsed = 0
        while elapsed < max_wait:
            snapshot = self.get_export_snapshot(project_id, export_pk)
            status = snapshot.get("status", "")

            if status == "completed":
                break
            elif status == "failed":
                raise RuntimeError(
                    f"Export 실패 (Export ID: {export_pk})"
                )

            time.sleep(poll_interval)
            elapsed += poll_interval

        if snapshot.get("status") != "completed":
            raise TimeoutError(
                f"Export가 {max_wait}초 내에 완료되지 않았습니다 (Export ID: {export_pk}, 상태: {snapshot.get('status')})"
            )

        # 3. 다운로드
        return self.download_export_snapshot(
            project_id,
            export_pk,
            export_type=export_type,
            output_dir=output_dir,
            include_images=include_images,
            progress_callback=progress_callback,
        )


# ─────────────────────────────────────────────
#  대화형 CLI 인터페이스
# ─────────────────────────────────────────────
class LabeloCLI:
    """LabelO API를 대화형으로 사용할 수 있는 CLI 인터페이스"""

    def __init__(self, base_url: str):
        self.client = LabeloAPIClient(base_url)

    def run(self):
        """메인 실행 루프"""
        self._print_banner()

        # 로그인
        if not self._do_login():
            return

        # 메인 메뉴 루프
        self._menu_loop()

    def _menu_loop(self):
        """메뉴 루프"""
        while True:
            self._print_menu()
            choice = input(f"\n{Color.YELLOW}선택> {Color.RESET}").strip()

            if choice == "1":
                self._show_my_info()
            elif choice == "2":
                self._show_projects()
            elif choice == "3":
                self._create_project_interactive()
            elif choice == "4":
                self._show_project_members()
            elif choice == "5":
                self._add_labeler_interactive()
            elif choice == "6":
                self._remove_labeler_interactive()
            elif choice == "7":
                self._show_users()
            elif choice == "8":
                self._show_available_users()
            elif choice == "9":
                self._bulk_add_labelers()
            elif choice == "10":
                self._register_user_interactive()
            elif choice == "11":
                self._remove_user_interactive()
            elif choice == "12":
                self._show_project_progress()
            elif choice == "13":
                self._import_data_interactive()
            elif choice == "14":
                self._download_project_data()
            elif choice == "15":
                self._export_labeled_data()
            elif choice == "0" or choice.lower() == "q":
                cprint("\n프로그램을 종료합니다. 감사합니다!", Color.CYAN)
                break
            else:
                cprint("잘못된 선택입니다. 다시 입력해주세요.", Color.RED)

    def _print_banner(self):
        banner = r"""
╔══════════════════════════════════════════════════╗
║                                                  ║
║      🏷️  LabelO API Client  🏷️                  ║
║                                                  ║
║   외부 API를 통한 라벨러 관리 프로그램            ║
║                                                  ║
╚══════════════════════════════════════════════════╝
        """
        cprint(banner, Color.CYAN + Color.BOLD)
        cprint(f"  서버: {self.client.base_url}", Color.DIM)
        print()

    def _print_menu(self):
        print()
        cprint("═" * 50, Color.BLUE)
        cprint("  📋 메인 메뉴", Color.BOLD + Color.BLUE)
        cprint("═" * 50, Color.BLUE)
        menu_items = [
            ("1", "내 정보 보기"),
            ("2", "프로젝트 목록 조회"),
            ("3", "📁 새 프로젝트 등록"),
            ("4", "프로젝트 멤버(라벨러) 조회"),
            ("5", "프로젝트에 라벨러 추가"),
            ("6", "프로젝트에서 라벨러 제거"),
            ("7", "전체 사용자 목록"),
            ("8", "프로젝트에 추가 가능한 사용자 조회"),
            ("9", "여러 라벨러 일괄 추가"),
            ("10", "새 사용자 등록 (현재 조직에 초대)"),
            ("11", "🗑️  사용자 제거 (조직에서 제거)"),
            ("12", "📊 프로젝트 작업 진행상황 모니터링"),
            ("13", "📥 프로젝트 데이터 Import (가져오기)"),
            ("14", "💾 프로젝트 데이터 다운로드 (백업)"),
            ("15", "📤 프로젝트 라벨링 데이터 Export"),
            ("0", "종료"),
        ]
        for num, label in menu_items:
            if num == "0":
                cprint(f"  {Color.RED}[{num}]{Color.RESET} {label}", "")
            else:
                print(f"  {Color.GREEN}[{num}]{Color.RESET} {label}")

    def _do_login(self) -> bool:
        """로그인 처리"""
        cprint("─── 로그인 ───", Color.BOLD)
        email = input(f"  {Color.CYAN}이메일: {Color.RESET}").strip()
        password = getpass.getpass(f"  {Color.CYAN}비밀번호: {Color.RESET}")

        try:
            token = self.client.login(email, password)
            cprint(f"\n  ✅ 로그인 성공!", Color.GREEN + Color.BOLD)
            cprint(f"  🔑 API Token: {token[:8]}...{token[-4:]}", Color.DIM)

            # 사용자 정보도 바로 가져오기
            user = self.client.get_whoami()
            name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
            if not name:
                name = user.get("email", "Unknown")
            cprint(f"  👤 안녕하세요, {name}님!", Color.GREEN)
            return True

        except ConnectionError as e:
            cprint(f"\n  ❌ 연결 오류: {e}", Color.RED)
            return False
        except PermissionError as e:
            cprint(f"\n  ❌ 인증 오류: {e}", Color.RED)
            return False
        except Exception as e:
            cprint(f"\n  ❌ 오류: {e}", Color.RED)
            return False

    def _show_my_info(self):
        """내 정보 출력"""
        try:
            user = self.client.get_whoami()
            active_org_id = user.get("active_organization")
            org_title = ""
            if active_org_id:
                try:
                    org_info = self.client.get_organization(active_org_id)
                    org_title = org_info.get("title", "")
                except Exception:
                    pass
            org_display = f"{org_title} (ID: {active_org_id})" if (org_title and active_org_id) else (org_title or str(active_org_id))

            print()
            cprint("─── 👤 내 정보 ───", Color.BOLD)
            info_items = [
                ("ID", user.get("id")),
                ("이메일", user.get("email")),
                ("이름", f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()),
                ("사용자명", user.get("username")),
                ("조직 ID", active_org_id if active_org_id is not None else "-"),
                ("소속 조직", org_display),
                ("조직 역할", user.get("active_org_role", "N/A")),
                ("조직 상태", user.get("active_org_status", "N/A")),
            ]
            for label, value in info_items:
                print(f"  {Color.CYAN}{label:10}{Color.RESET}: {value}")
        except Exception as e:
            cprint(f"  ❌ 오류: {e}", Color.RED)

    def _show_projects(self):
        """프로젝트 목록 출력"""
        try:
            data = self.client.list_projects()
            projects = data.get("results", data) if isinstance(data, dict) else data
            print()
            cprint(f"─── 📁 프로젝트 목록 (총 {data.get('count', len(projects))}개) ───", Color.BOLD)

            if not projects:
                cprint("  프로젝트가 없습니다.", Color.DIM)
                return

            headers = ["ID", "제목", "태스크 수", "생성일"]
            rows = []
            for p in projects:
                created = str(p.get("created_at", ""))[:10]
                rows.append([
                    str(p.get("id", "")),
                    str(p.get("title", ""))[:35],
                    str(p.get("task_number", 0)),
                    created,
                ])
            print()
            print_table(headers, rows, [8, 38, 12, 12])
        except Exception as e:
            cprint(f"  ❌ 오류: {e}", Color.RED)

    def _create_project_interactive(self):
        """새 프로젝트 등록 (대화형)"""
        # 현재 활성 조직 정보 조회
        active_org_id = None
        org_title = ""
        try:
            whoami = self.client.get_whoami()
            active_org_id = whoami.get("active_organization")
            if active_org_id:
                try:
                    org_info = self.client.get_organization(active_org_id)
                    org_title = org_info.get("title", "")
                except Exception:
                    pass
        except Exception:
            pass

        org_display = f"{org_title} (ID: {active_org_id})" if (org_title and active_org_id) else (org_title or str(active_org_id or "기본 조직"))

        print()
        cprint("─── 📁 새 프로젝트 등록 ───", Color.BOLD)
        cprint("  프로젝트 이름만 입력하여 프로젝트를 빠르게 등록합니다.", Color.DIM)
        cprint("  라벨링 인터페이스, 태스크 가져오기 등 상세 설정은 웹(브라우저)에서 설정할 수 있습니다.", Color.DIM)
        print()
        cprint(f"  🏢 대상 조직: {Color.CYAN}{org_display}{Color.RESET}", Color.BOLD)
        print()

        title = input(f"  {Color.CYAN}프로젝트 명: {Color.RESET}").strip()
        if not title:
            cprint("  ❌ 프로젝트 이름을 입력하세요.", Color.RED)
            return

        description = input(f"  {Color.CYAN}프로젝트 설명 (선택 사항): {Color.RESET}").strip()

        print()
        cprint("  ─── 입력 확인 ───", Color.BOLD)
        print(f"  소속 조직    : {org_display}")
        print(f"  프로젝트 명  : {title}")
        if description:
            print(f"  프로젝트 설명: {description}")
        print()
        confirm = input(f"  {Color.YELLOW}위 정보로 프로젝트를 생성하시겠습니까? (Y/n): {Color.RESET}").strip().lower()
        if confirm == "n":
            cprint("  취소되었습니다.", Color.DIM)
            return

        try:
            result = self.client.create_project(title, description=description)
            project_id = result.get("id")
            settings_url = f"{self.client.base_url}/projects/{project_id}/settings"

            print()
            cprint(f"  ✅ 프로젝트 등록 완료!", Color.GREEN + Color.BOLD)
            cprint(f"  📁 프로젝트 ID  : {project_id}", Color.GREEN)
            cprint(f"  🏷️  프로젝트 명  : {result.get('title', title)}", Color.GREEN)
            cprint(f"  🏢 소속 조직    : {org_display}", Color.GREEN)
            print()
            cprint(f"  🌐 웹 설정 바로가기: {Color.CYAN}{settings_url}{Color.RESET}", Color.BOLD)
            cprint(f"  💡 브라우저에서 위 URL로 접속하여 라벨링 인터페이스(Labeling Interface) 및 데이터를 설정하세요.", Color.DIM)
        except requests.HTTPError as e:
            if e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg = error_data.get("detail", error_data.get("error", str(e)))
                except Exception:
                    error_msg = str(e)
                cprint(f"  ❌ 프로젝트 생성 실패 (HTTP {e.response.status_code}): {error_msg}", Color.RED)
            else:
                cprint(f"  ❌ 프로젝트 생성 실패: {e}", Color.RED)
        except Exception as e:
            cprint(f"  ❌ 프로젝트 생성 실패: {e}", Color.RED)

    def _show_project_members(self):
        """프로젝트 멤버 조회"""
        project_id = input(f"  {Color.CYAN}프로젝트 ID: {Color.RESET}").strip()
        if not project_id.isdigit():
            cprint("  ❌ 유효한 프로젝트 ID를 입력하세요.", Color.RED)
            return

        try:
            members = self.client.get_project_members(int(project_id))
            print()
            cprint(f"─── 👥 프로젝트 #{project_id} 멤버 (총 {len(members)}명) ───", Color.BOLD)

            if not members:
                cprint("  멤버가 없습니다.", Color.DIM)
                return

            headers = ["사용자ID", "이메일", "이름", "조직ID", "역할", "상태"]
            rows = []
            for m in members:
                user = m.get("user", {})
                name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
                role = user.get("active_org_role", "N/A")
                org_id = str(user.get("active_organization", "") or "-")
                enabled = "활성" if m.get("enabled", True) else "비활성"
                rows.append([
                    str(user.get("id", "")),
                    str(user.get("email", "")),
                    name if name else "-",
                    org_id,
                    role,
                    enabled,
                ])
            print()
            print_table(headers, rows, [10, 30, 16, 10, 12, 10])
        except Exception as e:
            cprint(f"  ❌ 오류: {e}", Color.RED)

    def _show_users(self):
        """전체 사용자 목록 출력"""
        try:
            users = self.client.list_users()
            print()
            cprint(f"─── 👥 전체 사용자 목록 (총 {len(users)}명) ───", Color.BOLD)

            if not users:
                cprint("  사용자가 없습니다.", Color.DIM)
                return

            headers = ["ID", "이메일", "이름", "조직ID", "역할"]
            rows = []
            for u in users:
                name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
                role = u.get("active_org_role", "N/A")
                org_id = str(u.get("active_organization", "") or "-")
                rows.append([
                    str(u.get("id", "")),
                    str(u.get("email", "")),
                    name if name else "-",
                    org_id,
                    role,
                ])
            print()
            print_table(headers, rows, [8, 32, 18, 10, 12])
        except Exception as e:
            cprint(f"  ❌ 오류: {e}", Color.RED)

    def _show_available_users(self):
        """프로젝트에 추가 가능한 사용자 조회"""
        project_id = input(f"  {Color.CYAN}프로젝트 ID: {Color.RESET}").strip()
        if not project_id.isdigit():
            cprint("  ❌ 유효한 프로젝트 ID를 입력하세요.", Color.RED)
            return

        try:
            users = self.client.get_available_users(int(project_id))
            print()
            cprint(f"─── 👤 프로젝트 #{project_id}에 추가 가능한 사용자 (총 {len(users)}명) ───", Color.BOLD)

            if not users:
                cprint("  추가 가능한 사용자가 없습니다. (모든 사용자가 이미 멤버입니다)", Color.DIM)
                return

            headers = ["ID", "이메일", "이름", "조직ID", "역할"]
            rows = []
            for u in users:
                name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
                role = u.get("active_org_role", "N/A")
                org_id = str(u.get("active_organization", "") or "-")
                rows.append([
                    str(u.get("id", "")),
                    str(u.get("email", "")),
                    name if name else "-",
                    org_id,
                    role,
                ])
            print()
            print_table(headers, rows, [8, 32, 18, 10, 12])
        except Exception as e:
            cprint(f"  ❌ 오류: {e}", Color.RED)

    def _resolve_user_id(self, user_input: str, user_list: list) -> Optional[int]:
        """
        사용자 입력(ID 또는 이메일)을 실제 사용자 ID로 변환합니다.

        Args:
            user_input: 사용자가 입력한 값 (숫자 ID 또는 이메일)
            user_list: 사용자 정보 딕셔너리 목록 (user 키가 있는 멤버 또는 직접 사용자)

        Returns:
            사용자 ID (int) 또는 None
        """
        # 숫자면 그대로 사용자 ID로 시도
        if user_input.isdigit():
            input_id = int(user_input)
            # user_list에서 해당 ID가 실제로 존재하는지 확인
            for item in user_list:
                user = item.get("user", item)  # 멤버 목록이면 user 키, 사용자 목록이면 직접
                if user.get("id") == input_id:
                    return input_id
            # 목록에 없어도 일단 반환 (서버에서 검증)
            return input_id

        # 이메일 또는 이메일 일부로 검색
        matched = []
        for item in user_list:
            user = item.get("user", item)
            email = user.get("email", "")
            if email == user_input or email.lower() == user_input.lower():
                # 정확히 일치
                return user.get("id")
            if user_input.lower() in email.lower():
                matched.append(user)

        if len(matched) == 1:
            return matched[0].get("id")
        elif len(matched) > 1:
            cprint(f"  ⚠️  '{user_input}'에 해당하는 사용자가 여러 명입니다:", Color.YELLOW)
            for u in matched:
                print(f"      ID: {u.get('id')}  이메일: {u.get('email')}")
            return None
        else:
            cprint(f"  ❌ '{user_input}'에 해당하는 사용자를 찾을 수 없습니다.", Color.RED)
            return None

    def _add_labeler_interactive(self):
        """라벨러 추가 (대화형)"""
        project_id = input(f"  {Color.CYAN}프로젝트 ID: {Color.RESET}").strip()
        if not project_id.isdigit():
            cprint("  ❌ 유효한 프로젝트 ID를 입력하세요.", Color.RED)
            return

        pid = int(project_id)

        # 추가 가능한 사용자 목록을 먼저 보여줌
        try:
            available = self.client.get_available_users(pid)
            print()
            cprint(f"─── 추가 가능한 사용자 목록 ───", Color.BOLD)
            if not available:
                cprint("  추가 가능한 사용자가 없습니다. (모든 사용자가 이미 멤버입니다)", Color.DIM)
                return
            headers = ["ID", "이메일", "이름", "조직ID", "역할"]
            rows = []
            for u in available:
                name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
                role = u.get("active_org_role", "N/A")
                org_id = str(u.get("active_organization", "") or "-")
                rows.append([str(u.get("id", "")), str(u.get("email", "")), name if name else "-", org_id, role])
            print()
            print_table(headers, rows, [8, 32, 18, 10, 12])
        except Exception as e:
            cprint(f"  ⚠️  사용자 목록 조회 실패: {e}", Color.YELLOW)
            available = []

        print()
        user_input = input(f"  {Color.CYAN}추가할 사용자 (ID 또는 이메일): {Color.RESET}").strip()
        if not user_input:
            cprint("  ❌ 사용자를 입력하세요.", Color.RED)
            return

        user_id = self._resolve_user_id(user_input, available)
        if user_id is None:
            return

        try:
            result = self.client.add_labeler(pid, user_id)
            user_info = result.get("user", {})
            email = user_info.get("email", f"User #{user_id}")
            cprint(f"\n  ✅ 사용자 '{email}'(ID: {user_id})를 프로젝트 #{project_id}에 라벨러로 등록했습니다.", Color.GREEN)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 400:
                cprint(f"  ⚠️  이미 등록된 멤버이거나 등록할 수 없습니다.", Color.YELLOW)
            else:
                cprint(f"  ❌ 오류: {e}", Color.RED)
        except Exception as e:
            cprint(f"  ❌ 오류: {e}", Color.RED)

    def _remove_labeler_interactive(self):
        """라벨러 제거 (대화형)"""
        project_id = input(f"  {Color.CYAN}프로젝트 ID: {Color.RESET}").strip()
        if not project_id.isdigit():
            cprint("  ❌ 유효한 프로젝트 ID를 입력하세요.", Color.RED)
            return

        pid = int(project_id)

        # 현재 멤버 목록을 먼저 보여줌
        try:
            members = self.client.get_project_members(pid)
            print()
            cprint(f"─── 현재 프로젝트 #{project_id} 멤버 ───", Color.BOLD)
            if not members:
                cprint("  멤버가 없습니다.", Color.DIM)
                return
            headers = ["사용자ID", "이메일", "이름", "상태"]
            rows = []
            for m in members:
                user = m.get("user", {})
                name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
                enabled = "활성" if m.get("enabled", True) else "비활성"
                rows.append([
                    str(user.get("id", "")),
                    str(user.get("email", "")),
                    name if name else "-",
                    enabled,
                ])
            print()
            print_table(headers, rows, [10, 30, 18, 10])
        except Exception as e:
            cprint(f"  ⚠️  멤버 목록 조회 실패: {e}", Color.YELLOW)
            members = []

        print()
        user_input = input(f"  {Color.CYAN}제거할 사용자 (ID 또는 이메일): {Color.RESET}").strip()
        if not user_input:
            cprint("  ❌ 사용자를 입력하세요.", Color.RED)
            return

        user_id = self._resolve_user_id(user_input, members)
        if user_id is None:
            return

        # 제거 대상 정보 표시
        target_email = user_input
        for m in members:
            user = m.get("user", {})
            if user.get("id") == user_id:
                target_email = user.get("email", user_input)
                break

        cprint(f"\n  대상: {target_email} (ID: {user_id})", Color.YELLOW)
        confirm = input(f"  {Color.YELLOW}정말 제거하시겠습니까? (y/N): {Color.RESET}").strip().lower()
        if confirm != "y":
            cprint("  취소되었습니다.", Color.DIM)
            return

        try:
            self.client.remove_labeler(pid, user_id)
            cprint(f"\n  ✅ 사용자 '{target_email}'(ID: {user_id})를 프로젝트 #{project_id}에서 제거했습니다.", Color.GREEN)
        except requests.HTTPError as e:
            if e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg = error_data.get("error", "")
                except Exception:
                    error_msg = ""

                if e.response.status_code == 404:
                    if "created" in error_msg.lower():
                        cprint(f"  ⚠️  프로젝트 생성자는 제거할 수 없습니다.", Color.YELLOW)
                    else:
                        cprint(f"  ⚠️  해당 멤버를 찾을 수 없습니다. (서버 응답: {error_msg})", Color.YELLOW)
                else:
                    cprint(f"  ❌ 오류 (HTTP {e.response.status_code}): {error_msg or e}", Color.RED)
            else:
                cprint(f"  ❌ 오류: {e}", Color.RED)
        except Exception as e:
            cprint(f"  ❌ 오류: {e}", Color.RED)

    def _bulk_add_labelers(self):
        """여러 라벨러 일괄 추가"""
        project_id = input(f"  {Color.CYAN}프로젝트 ID: {Color.RESET}").strip()
        if not project_id.isdigit():
            cprint("  ❌ 유효한 프로젝트 ID를 입력하세요.", Color.RED)
            return

        user_ids_str = input(f"  {Color.CYAN}사용자 ID들 (쉼표로 구분): {Color.RESET}").strip()
        try:
            user_ids = [int(x.strip()) for x in user_ids_str.split(",") if x.strip()]
        except ValueError:
            cprint("  ❌ 사용자 ID는 숫자여야 합니다.", Color.RED)
            return

        if not user_ids:
            cprint("  ❌ 최소 1명 이상의 사용자 ID를 입력하세요.", Color.RED)
            return

        cprint(f"\n  프로젝트 #{project_id}에 {len(user_ids)}명을 등록합니다...", Color.CYAN)
        results = self.client.add_labelers_bulk(int(project_id), user_ids)

        success_count = 0
        fail_count = 0
        for r in results:
            if r["status"] == "success":
                user_data = r.get("data", {}).get("user", {})
                email = user_data.get("email", f"ID:{r['user_id']}")
                org_id = str(user_data.get("active_organization", "") or "-")
                cprint(f"  ✅ {email} (ID: {r['user_id']}, 조직ID: {org_id}) - 등록 성공", Color.GREEN)
                success_count += 1
            else:
                cprint(f"  ❌ 사용자 ID {r['user_id']} - 실패: {r['error']}", Color.RED)
                fail_count += 1

        print()
        cprint(f"  결과: 성공 {success_count}명 / 실패 {fail_count}명", Color.BOLD)

    def _register_user_interactive(self):
        """새 사용자 등록 - 현재 조직에 추가 (대화형)"""
        # 현재 로그인된 사용자의 조직 정보 조회
        active_org_id = None
        org_title = ""
        try:
            whoami = self.client.get_whoami()
            active_org_id = whoami.get("active_organization")
            if active_org_id:
                org_info = self.client.get_organization(active_org_id)
                org_title = org_info.get("title", "")
        except Exception:
            pass

        org_display = f"{org_title} (ID: {active_org_id})" if (org_title and active_org_id) else (org_title or str(active_org_id or "기본 조직"))

        print()
        cprint(f"─── 📝 새 사용자 등록 (소속 조직: {org_title or org_display}) ───", Color.BOLD)
        cprint(f"  새 사용자 계정을 생성하고 현재 조직({org_display})에 추가합니다.", Color.DIM)
        cprint("  비밀번호가 설정되므로 즉시 로그인 가능합니다.", Color.DIM)
        print()
        cprint(f"  🏢 대상 조직: {Color.CYAN}{org_display}{Color.RESET}", Color.BOLD)
        print()

        email = input(f"  {Color.CYAN}이메일: {Color.RESET}").strip()
        if not email or "@" not in email:
            cprint("  ❌ 유효한 이메일 주소를 입력하세요.", Color.RED)
            return

        password = getpass.getpass(f"  {Color.CYAN}비밀번호 (8자 이상): {Color.RESET}")
        if len(password) < 8:
            cprint("  ❌ 비밀번호는 8자 이상이어야 합니다.", Color.RED)
            return

        password_confirm = getpass.getpass(f"  {Color.CYAN}비밀번호 확인: {Color.RESET}")
        if password != password_confirm:
            cprint("  ❌ 비밀번호가 일치하지 않습니다.", Color.RED)
            return

        username = input(f"  {Color.CYAN}사용자 이름: {Color.RESET}").strip()
        if not username:
            cprint("  ❌ 사용자 이름을 입력하세요.", Color.RED)
            return

        # 역할 선택
        print()
        cprint("  역할 선택:", Color.BOLD)
        role_options = [
            ("1", "annotater", "Annotater (라벨링 작업자)"),
            ("2", "reviewer", "Reviewer (검수자)"),
            ("3", "manager", "Manager (관리자)"),
            ("4", "administrator", "Administrator (운영자)"),
        ]
        for num, _, desc in role_options:
            print(f"    {Color.GREEN}[{num}]{Color.RESET} {desc}")

        role_choice = input(f"  {Color.CYAN}역할 선택 (기본: 1): {Color.RESET}").strip()
        if not role_choice:
            role_choice = "1"

        role_map = {"1": "annotater", "2": "reviewer", "3": "manager", "4": "administrator"}
        role = role_map.get(role_choice)
        if not role:
            cprint("  ❌ 잘못된 역할 선택입니다.", Color.RED)
            return

        role_name = next(desc for num, _, desc in role_options if num == role_choice)

        # 입력 확인
        print()
        cprint("  ─── 입력 확인 ───", Color.BOLD)
        print(f"  소속 조직    : {org_display}")
        print(f"  이메일       : {email}")
        print(f"  사용자 이름  : {username}")
        print(f"  역할         : {role_name}")
        print()
        confirm = input(f"  {Color.YELLOW}위 정보로 등록하시겠습니까? (y/N): {Color.RESET}").strip().lower()
        if confirm != "y":
            cprint("  취소되었습니다.", Color.DIM)
            return

        try:
            result = self.client.invite_user(email, password, username, role)
            print()
            cprint(f"  ✅ 사용자 등록 완료!", Color.GREEN + Color.BOLD)
            cprint(f"  🏢 소속 조직: {org_display}", Color.GREEN)
            cprint(f"  📧 이메일: {result.get('email')}", Color.GREEN)
            cprint(f"  👤 이름: {result.get('username')}", Color.GREEN)
            cprint(f"  👔 역할: {role_name}", Color.GREEN)
            msg = result.get('message', '')
            if msg:
                cprint(f"  💬 {msg}", Color.DIM)
        except ConnectionError as e:
            cprint(f"  ❌ 연결 오류: {e}", Color.RED)
        except ValueError as e:
            cprint(f"  ❌ 등록 실패: {e}", Color.RED)
        except requests.HTTPError as e:
            if e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg = error_data.get('error', str(e))
                except Exception:
                    error_msg = str(e)
                cprint(f"  ❌ 오류: {error_msg}", Color.RED)
            else:
                cprint(f"  ❌ 오류: {e}", Color.RED)
        except Exception as e:
            cprint(f"  ❌ 오류: {e}", Color.RED)

    def _remove_user_interactive(self):
        """사용자 제거 (조직에서 제거 / 삭제) (대화형)"""
        # 현재 사용자 및 조직 정보 조회
        my_id = None
        active_org_id = None
        try:
            whoami = self.client.get_whoami()
            my_id = whoami.get("id")
            active_org_id = whoami.get("active_organization")
        except Exception:
            pass

        # 사용자 목록 표시
        try:
            users = self.client.list_users()
            print()
            cprint(f"─── 👥 사용자 목록 (총 {len(users)}명) ───", Color.BOLD)
            if not users:
                cprint("  사용자가 없습니다.", Color.DIM)
                return

            headers = ["ID", "이메일", "이름", "조직ID", "역할"]
            rows = []
            for u in users:
                name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
                role = u.get("active_org_role", "N/A")
                org_id = str(u.get("active_organization", "") or "-")
                rows.append([
                    str(u.get("id", "")),
                    str(u.get("email", "")),
                    name if name else "-",
                    org_id,
                    role,
                ])
            print()
            print_table(headers, rows, [8, 32, 18, 10, 12])
        except Exception as e:
            cprint(f"  ⚠️  사용자 목록 조회 실패: {e}", Color.YELLOW)
            users = []

        print()
        user_input = input(f"  {Color.CYAN}제거할 사용자 (ID 또는 이메일): {Color.RESET}").strip()
        if not user_input:
            cprint("  ❌ 사용자를 입력하세요.", Color.RED)
            return

        user_id = self._resolve_user_id(user_input, users)
        if user_id is None:
            return

        if my_id and user_id == my_id:
            cprint("  ⚠️  현재 로그인된 자기 자신은 제거할 수 없습니다.", Color.YELLOW)
            return

        # 제거 대상 정보 찾기
        target_email = user_input
        target_name = ""
        target_role = ""
        target_org = ""
        for u in users:
            if u.get("id") == user_id:
                target_email = u.get("email", user_input)
                target_name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
                target_role = u.get("active_org_role", "N/A")
                target_org = str(u.get("active_organization", "") or "-")
                break

        print()
        cprint(f"  ─── 🗑️  제거 대상 확인 ───", Color.BOLD)
        print(f"  사용자 ID : {user_id}")
        print(f"  이메일    : {target_email}")
        if target_name:
            print(f"  이름      : {target_name}")
        print(f"  조직 ID   : {target_org or active_org_id or '-'}")
        print(f"  역할      : {target_role or '-'}")
        print()
        cprint(f"  ⚠️  해당 사용자를 조직에서 제거(삭제)합니다.", Color.YELLOW)
        confirm = input(f"  {Color.YELLOW}정말 제거하시겠습니까? (y/N): {Color.RESET}").strip().lower()
        if confirm != "y":
            cprint("  취소되었습니다.", Color.DIM)
            return

        try:
            self.client.delete_user(user_id, active_org_id)
            print()
            cprint(f"  ✅ 사용자 '{target_email}' (ID: {user_id})를 성공적으로 제거했습니다.", Color.GREEN + Color.BOLD)
        except requests.HTTPError as e:
            if e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg = error_data.get("detail", error_data.get("error", str(e)))
                except Exception:
                    error_msg = str(e)
                cprint(f"  ❌ 오류 (HTTP {e.response.status_code}): {error_msg}", Color.RED)
            else:
                cprint(f"  ❌ 오류: {e}", Color.RED)
        except Exception as e:
            cprint(f"  ❌ 오류: {e}", Color.RED)

    def _show_project_progress(self):
        """프로젝트 작업 진행상황 모니터링"""
        # 먼저 프로젝트 목록을 보여줌
        try:
            data = self.client.list_projects()
            projects = data.get("results", data) if isinstance(data, dict) else data
            if projects:
                print()
                cprint("─── 📁 프로젝트 목록 ───", Color.BOLD)
                headers = ["ID", "제목", "태스크 수"]
                rows = []
                for p in projects:
                    rows.append([
                        str(p.get("id", "")),
                        str(p.get("title", ""))[:35],
                        str(p.get("task_number", 0)),
                    ])
                print()
                print_table(headers, rows, [8, 38, 12])
        except Exception:
            pass

        print()
        project_id = input(f"  {Color.CYAN}프로젝트 ID: {Color.RESET}").strip()
        if not project_id.isdigit():
            cprint("  ❌ 유효한 프로젝트 ID를 입력하세요.", Color.RED)
            return

        try:
            progress = self.client.get_project_progress(int(project_id))
            print()
            cprint(f"─── 📊 프로젝트 #{project_id} 작업 진행상황 ───", Color.BOLD)
            print()
            cprint(f"  📁 프로젝트: {progress['title']}", Color.CYAN)
            cprint(f"  📅 생성일: {str(progress.get('created_at', ''))[:10]}", Color.DIM)
            print()

            # 진행률 바 생성
            pct = progress["progress_percent"]
            bar_len = 30
            filled = int(bar_len * pct / 100)
            bar = "█" * filled + "░" * (bar_len - filled)

            if pct >= 100:
                bar_color = Color.GREEN
            elif pct >= 50:
                bar_color = Color.YELLOW
            else:
                bar_color = Color.CYAN

            cprint(f"  진행률:  [{bar}] {pct}%", bar_color + Color.BOLD)
            print()

            info_items = [
                ("전체 태스크", progress["task_number"]),
                ("완료 태스크", progress["finished_task_number"]),
                ("어노테이션 있는 태스크", progress["num_tasks_with_annotations"]),
                ("전체 어노테이션 수", progress["total_annotations_number"]),
                ("전체 예측 수", progress["total_predictions_number"]),
            ]
            for label, value in info_items:
                print(f"  {Color.CYAN}{label:22}{Color.RESET}: {value}")

            # 요약 정보 (라벨 통계)
            summary = progress.get("summary", {})
            created_labels = summary.get("created_labels", {})
            if created_labels:
                print()
                cprint("  ─── 라벨 통계 ───", Color.BOLD)
                for label_type, labels in created_labels.items():
                    if isinstance(labels, dict):
                        for label_name, count in labels.items():
                            print(f"    {Color.GREEN}{label_name}{Color.RESET}: {count}")
                    else:
                        print(f"    {Color.GREEN}{label_type}{Color.RESET}: {labels}")

        except Exception as e:
            cprint(f"  ❌ 오류: {e}", Color.RED)

    def _import_data_interactive(self):
        """프로젝트 데이터 Import (가져오기, 대화형)"""
        # 먼저 프로젝트 목록 표시
        try:
            data = self.client.list_projects()
            projects = data.get("results", data) if isinstance(data, dict) else data
            if projects:
                print()
                cprint("─── 📁 프로젝트 목록 ───", Color.BOLD)
                headers = ["ID", "제목", "태스크 수"]
                rows = []
                for p in projects:
                    rows.append([
                        str(p.get("id", "")),
                        str(p.get("title", ""))[:35],
                        str(p.get("task_number", 0)),
                    ])
                print()
                print_table(headers, rows, [8, 38, 12])
        except Exception:
            pass

        print()
        cprint("─── 📥 프로젝트 데이터 Import (가져오기) ───", Color.BOLD)
        cprint("  JSON, CSV, TSV, TXT, ZIP, 이미지 등의 데이터를 프로젝트에 등록합니다.", Color.DIM)
        print()

        project_id = input(f"  {Color.CYAN}프로젝트 ID: {Color.RESET}").strip()
        if not project_id.isdigit():
            cprint("  ❌ 유효한 프로젝트 ID를 입력하세요.", Color.RED)
            return

        pid = int(project_id)

        # 프로젝트 정보 확인
        proj_title = f"#{pid}"
        try:
            proj_info = self.client.get_project(pid)
            proj_title = proj_info.get("title", proj_title)
        except Exception:
            pass

        print()
        file_input = input(f"  {Color.CYAN}업로드할 파일 또는 폴더 경로 (예: ./data.json 또는 D:\\images): {Color.RESET}").strip()
        if not file_input:
            cprint("  ❌ 경로를 입력해주세요.", Color.RED)
            return

        # 따옴표 제거
        file_path = file_input.strip("\"'")
        if not os.path.exists(file_path):
            cprint(f"  ❌ 경로를 찾을 수 없습니다: {file_path}", Color.RED)
            return

        is_dir = os.path.isdir(file_path)
        if is_dir:
            file_count = sum(len(files) for _, _, files in os.walk(file_path))
            item_name = os.path.basename(os.path.normpath(file_path)) or "폴더"
            type_display = f"📁 폴더 (포함된 파일 {file_count:,}개, 압축 없이 원본 개별 업로드)"
        else:
            file_size = os.path.getsize(file_path)
            file_size_str = f"{file_size / (1024 * 1024):.2f} MB" if file_size >= 1024 * 1024 else f"{file_size / 1024:.1f} KB"
            item_name = os.path.basename(file_path)
            type_display = f"📄 파일 ({file_size_str})"

        print()
        cprint("  ─── Import 확인 ───", Color.BOLD)
        print(f"  대상 프로젝트: #{pid} ({proj_title})")
        print(f"  대상 이름    : {item_name}")
        print(f"  데이터 형식  : {type_display}")
        print(f"  전체 경로    : {file_path}")
        print()

        confirm = input(f"  {Color.YELLOW}위 데이터를 프로젝트에 Import하시겠습니까? (Y/n): {Color.RESET}").strip().lower()
        if confirm == "n":
            cprint("  취소되었습니다.", Color.DIM)
            return

        def on_progress(current, total, filename, status):
            pct = int(current / total * 100) if total > 0 else 100
            bar_len = 25
            filled = int(bar_len * current / total) if total > 0 else bar_len
            bar = "█" * filled + "░" * (bar_len - filled)
            status_icon = "✅" if status == "success" else "❌"
            fname_display = filename if len(filename) <= 25 else filename[:22] + "..."
            print(f"\r  📤 파일 업로드: [{bar}] {pct}% ({current}/{total}) {status_icon} {fname_display:<25}", end="", flush=True)

        if not is_dir:
            cprint("\n  ⏳ 데이터를 업로드하고 태스크를 생성 중입니다...", Color.CYAN)
        else:
            print()

        try:
            result = self.client.import_tasks(pid, file_path=file_path, on_progress=on_progress if is_dir else None)
            if is_dir:
                print()  # 줄바꿈

            task_count = result.get("task_count", 0)
            annotation_count = result.get("annotation_count", 0)
            duration = result.get("duration", 0)
            data_cols = result.get("data_columns", [])
            cols_str = ", ".join(data_cols) if data_cols else "없음"

            print()
            cprint("  ✅ 데이터 Import 완료!", Color.GREEN + Color.BOLD)
            cprint(f"  📁 프로젝트     : #{pid} ({proj_title})", Color.GREEN)
            if is_dir:
                cprint(f"  📂 업로드된 파일: {result.get('file_count', file_count):,}개", Color.GREEN)
            cprint(f"  📊 생성된 태스크: {task_count:,}개", Color.GREEN)
            if annotation_count > 0:
                cprint(f"  🏷️  어노테이션  : {annotation_count:,}개", Color.GREEN)
            if duration:
                cprint(f"  ⏱️  소요 시간   : {duration:.2f}초", Color.DIM)
            cprint(f"  📋 감지된 컬럼  : {cols_str}", Color.DIM)
            print()
            cprint(f"  🌐 프로젝트 바로가기: {Color.CYAN}{self.client.base_url}/projects/{pid}/data{Color.RESET}", Color.BOLD)
        except requests.HTTPError as e:
            if e.response is not None:
                try:
                    err_data = e.response.json()
                    err_msg = err_data.get("detail", err_data.get("error", str(e)))
                except Exception:
                    err_msg = str(e)
                cprint(f"  ❌ Import 실패 (HTTP {e.response.status_code}): {err_msg}", Color.RED)
            else:
                cprint(f"  ❌ Import 실패: {e}", Color.RED)
        except Exception as e:
            cprint(f"  ❌ Import 실패: {e}", Color.RED)

    def _download_project_data(self):
        """프로젝트 데이터 다운로드"""
        # 먼저 프로젝트 목록을 보여줌
        try:
            data = self.client.list_projects()
            projects = data.get("results", data) if isinstance(data, dict) else data
            if projects:
                print()
                cprint("─── 📁 프로젝트 목록 ───", Color.BOLD)
                headers = ["ID", "제목", "태스크 수"]
                rows = []
                for p in projects:
                    rows.append([
                        str(p.get("id", "")),
                        str(p.get("title", ""))[:35],
                        str(p.get("task_number", 0)),
                    ])
                print()
                print_table(headers, rows, [8, 38, 12])
        except Exception:
            pass

        print()
        cprint("─── 📥 프로젝트 데이터 다운로드 ───", Color.BOLD)
        project_id = input(f"  {Color.CYAN}프로젝트 ID: {Color.RESET}").strip()
        if not project_id.isdigit():
            cprint("  ❌ 유효한 프로젝트 ID를 입력하세요.", Color.RED)
            return

        pid = int(project_id)

        # 다운로드 옵션
        print()
        cprint("  다운로드 옵션:", Color.BOLD)
        print(f"    {Color.GREEN}[1]{Color.RESET} 모든 태스크 다운로드 (기본)")
        print(f"    {Color.GREEN}[2]{Color.RESET} 어노테이션된 태스크만 다운로드")
        option = input(f"  {Color.CYAN}선택 (기본: 1): {Color.RESET}").strip()
        download_all = option != "2"

        # 저장 경로
        output_dir = input(f"  {Color.CYAN}저장 경로 (기본: 현재 폴더): {Color.RESET}").strip()
        if not output_dir:
            output_dir = "."

        def on_progress(current, total, filename, status):
            pct = int(current / total * 100) if total > 0 else 100
            bar_len = 25
            filled = int(bar_len * current / total) if total > 0 else bar_len
            bar = "█" * filled + "░" * (bar_len - filled)
            status_icon = "✅" if status == "success" else "⚠️"
            fname_display = filename if len(filename) <= 25 else filename[:22] + "..."
            print(f"\r  📥 이미지 다운로드: [{bar}] {pct}% ({current}/{total}) {status_icon} {fname_display:<25}", end="", flush=True)

        try:
            cprint(f"\n  ⏳ 프로젝트 #{project_id} 데이터 및 이미지를 다운로드하여 압축합니다...", Color.CYAN)
            filepath = self.client.download_project_tasks(
                pid,
                output_dir=output_dir,
                download_all=download_all,
                include_images=True,
                progress_callback=on_progress,
            )
            print()  # 줄바꿈

            file_size = os.path.getsize(filepath)
            size_str = f"{file_size:,} bytes"
            if file_size > 1024 * 1024:
                size_str = f"{file_size / (1024 * 1024):.1f} MB"
            elif file_size > 1024:
                size_str = f"{file_size / 1024:.1f} KB"

            print()
            cprint(f"  ✅ 다운로드 및 압축 완료!", Color.GREEN + Color.BOLD)
            cprint(f"  📄 파일: {filepath}", Color.GREEN)
            cprint(f"  📦 크기: {size_str}", Color.GREEN)
            cprint(f"  📁 구성: JSON 태스크 데이터 + images/ 폴더 (이미지 포함)", Color.CYAN)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                cprint(f"  ⚠️  프로젝트를 찾을 수 없습니다.", Color.YELLOW)
            else:
                cprint(f"  ❌ 다운로드 실패: {e}", Color.RED)
        except Exception as e:
            cprint(f"  ❌ 오류: {e}", Color.RED)

    def _export_labeled_data(self):
        """프로젝트 라벨링 데이터 Export"""
        # 먼저 프로젝트 목록을 보여줌
        try:
            data = self.client.list_projects()
            projects = data.get("results", data) if isinstance(data, dict) else data
            if projects:
                print()
                cprint("─── 📁 프로젝트 목록 ───", Color.BOLD)
                headers = ["ID", "제목", "태스크 수"]
                rows = []
                for p in projects:
                    rows.append([
                        str(p.get("id", "")),
                        str(p.get("title", ""))[:35],
                        str(p.get("task_number", 0)),
                    ])
                print()
                print_table(headers, rows, [8, 38, 12])
        except Exception:
            pass

        print()
        cprint("─── 📤 프로젝트 라벨링 데이터 Export ───", Color.BOLD)
        project_id = input(f"  {Color.CYAN}프로젝트 ID: {Color.RESET}").strip()
        if not project_id.isdigit():
            cprint("  ❌ 유효한 프로젝트 ID를 입력하세요.", Color.RED)
            return

        pid = int(project_id)

        # Export 포맷 조회
        try:
            formats = self.client.get_export_formats(pid)
            available_formats = [f for f in formats if not f.get("disabled", False)]

            if available_formats:
                print()
                cprint("  사용 가능한 Export 포맷:", Color.BOLD)
                for i, fmt in enumerate(available_formats, 1):
                    name = fmt.get("name", "?")
                    title = fmt.get("title", "")
                    print(f"    {Color.GREEN}[{i}]{Color.RESET} {name} - {title}")

                fmt_choice = input(f"\n  {Color.CYAN}포맷 선택 (기본: 1=JSON): {Color.RESET}").strip()
                if not fmt_choice:
                    fmt_choice = "1"

                try:
                    fmt_idx = int(fmt_choice) - 1
                    if 0 <= fmt_idx < len(available_formats):
                        export_type = available_formats[fmt_idx]["name"]
                    else:
                        export_type = "JSON"
                except ValueError:
                    export_type = "JSON"
            else:
                export_type = "JSON"
        except Exception:
            cprint("  ⚠️  포맷 조회 실패. 기본 JSON으로 진행합니다.", Color.YELLOW)
            export_type = "JSON"

        # Export 방식 선택
        print()
        cprint("  Export 방식:", Color.BOLD)
        print(f"    {Color.GREEN}[1]{Color.RESET} Easy Export (직접 다운로드, 소규모 프로젝트용)")
        print(f"    {Color.GREEN}[2]{Color.RESET} Export 스냅샷 (백그라운드 처리, 대규모 프로젝트용)")
        method = input(f"  {Color.CYAN}선택 (기본: 1): {Color.RESET}").strip()

        # 저장 경로
        output_dir = input(f"  {Color.CYAN}저장 경로 (기본: 현재 폴더): {Color.RESET}").strip()
        if not output_dir:
            output_dir = "."

        def on_progress(current, total, filename, status):
            pct = int(current / total * 100) if total > 0 else 100
            bar_len = 25
            filled = int(bar_len * current / total) if total > 0 else bar_len
            bar = "█" * filled + "░" * (bar_len - filled)
            status_icon = "✅" if status == "success" else "⚠️"
            fname_display = filename if len(filename) <= 25 else filename[:22] + "..."
            print(f"\r  📥 이미지 다운로드: [{bar}] {pct}% ({current}/{total}) {status_icon} {fname_display:<25}", end="", flush=True)

        try:
            if method == "2":
                # 비동기 Export 스냅샷 방식
                cprint(f"\n  ⏳ Export 스냅샷을 생성하고 이미지 포함 압축 다운로드합니다 (포맷: {export_type})...", Color.CYAN)
                filepath = self.client.export_and_download(
                    pid,
                    export_type=export_type,
                    output_dir=output_dir,
                    include_images=True,
                    progress_callback=on_progress,
                )
            else:
                # Easy Export 방식
                cprint(f"\n  ⏳ 라벨링 데이터 및 이미지를 다운로드하여 압축합니다 (포맷: {export_type})...", Color.CYAN)
                filepath = self.client.download_project_tasks(
                    pid,
                    output_dir=output_dir,
                    download_all=False,
                    export_type=export_type,
                    include_images=True,
                    progress_callback=on_progress,
                )
            print()  # 줄바꿈

            file_size = os.path.getsize(filepath)
            size_str = f"{file_size:,} bytes"
            if file_size > 1024 * 1024:
                size_str = f"{file_size / (1024 * 1024):.1f} MB"
            elif file_size > 1024:
                size_str = f"{file_size / 1024:.1f} KB"

            print()
            cprint(f"  ✅ Export 완료!", Color.GREEN + Color.BOLD)
            cprint(f"  📄 파일: {filepath}", Color.GREEN)
            cprint(f"  📦 크기: {size_str}", Color.GREEN)
            cprint(f"  📋 포맷: {export_type}", Color.GREEN)
            cprint(f"  📁 구성: 라벨링 데이터 + images/ 폴더 (이미지 포함)", Color.CYAN)
        except TimeoutError as e:
            cprint(f"  ⏰ 시간 초과: {e}", Color.YELLOW)
        except RuntimeError as e:
            cprint(f"  ❌ Export 실패: {e}", Color.RED)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                cprint(f"  ⚠️  프로젝트를 찾을 수 없습니다.", Color.YELLOW)
            else:
                cprint(f"  ❌ Export 실패: {e}", Color.RED)
        except Exception as e:
            cprint(f"  ❌ 오류: {e}", Color.RED)


# ─────────────────────────────────────────────
#  메인 실행
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="LabelO API Client - 외부에서 API로 라벨러를 관리하는 프로그램",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # 대화형 모드 실행
  python labelo_api_client.py

  # 서버 URL 지정
  python labelo_api_client.py --url http://my-labelo-server:8080

  # 토큰으로 직접 인증
  python labelo_api_client.py --url http://localhost:8080 --token abc123
        """,
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8080",
        help="LabelO 서버 URL (기본값: http://localhost:8080)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="API 토큰 (지정 시 로그인 과정 생략)",
    )
    args = parser.parse_args()

    cli = LabeloCLI(args.url)

    if args.token:
        cli.client.login_with_token(args.token)
        cli._print_banner()
        cprint(f"  🔑 토큰으로 인증됨", Color.GREEN)
        try:
            user = cli.client.get_whoami()
            name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
            if not name:
                name = user.get("email", "Unknown")
            cprint(f"  👤 안녕하세요, {name}님!", Color.GREEN)
        except Exception:
            cprint("  ⚠️  토큰으로 사용자 정보를 확인할 수 없습니다.", Color.YELLOW)

        cli._menu_loop()
    else:
        cli.run()


if __name__ == "__main__":
    main()
