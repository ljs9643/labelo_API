#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LabelO API 사용 예제 스크립트
==============================
labelo_api_client.py의 LabeloAPIClient를 활용한 자동화 예제.

커맨드라인에서 직접 실행하여 라벨러를 관리하고 데이터를 다운로드할 수 있습니다.

사용법:
    # 로그인 후 프로젝트 목록 조회
    python labelo_api_example.py --url http://localhost:8080 --email admin@test.com --password 1234 list-projects

    # 프로젝트 멤버 조회
    python labelo_api_example.py --url http://localhost:8080 --email admin@test.com --password 1234 list-members --project 1

    # 라벨러 추가
    python labelo_api_example.py --url http://localhost:8080 --email admin@test.com --password 1234 add-labeler --project 1 --user 5

    # 여러 라벨러 일괄 추가
    python labelo_api_example.py --url http://localhost:8080 --email admin@test.com --password 1234 add-labelers --project 1 --users 5,6,7

    # 라벨러 제거
    python labelo_api_example.py --url http://localhost:8080 --email admin@test.com --password 1234 remove-labeler --project 1 --user 5

    # 새 사용자 등록 (현재 조직에 추가) - 로그인 필요
    python labelo_api_example.py --url http://localhost:8080 --email admin@test.com --password 1234 invite-user --invite-email new@test.com --invite-password 12345678 --invite-username NewUser --role annotater

    # 새 사용자 등록 (독립 회원가입) - 로그인 없이 사용 가능
    python labelo_api_example.py --url http://localhost:8080 register-user --reg-email new@test.com --reg-password 12345678 --reg-username NewUser --reg-org MyOrg

    # 프로젝트 작업 진행상황 모니터링
    python labelo_api_example.py --url http://localhost:8080 --email admin@test.com --password 1234 project-progress --project 1

    # 프로젝트 데이터 다운로드 (현재 폴더에 저장)
    python labelo_api_example.py --url http://localhost:8080 --email admin@test.com --password 1234 download-tasks --project 1
    python labelo_api_example.py --url http://localhost:8080 --email admin@test.com --password 1234 download-tasks --project 1 --output-dir ./data --all

    # 라벨링 데이터 Export (JSON, CSV 등)
    python labelo_api_example.py --url http://localhost:8080 --email admin@test.com --password 1234 export-labels --project 1
    python labelo_api_example.py --url http://localhost:8080 --email admin@test.com --password 1234 export-labels --project 1 --format CSV --output-dir ./exports

    # 토큰으로 직접 인증
    python labelo_api_example.py --url http://localhost:8080 --token abc123def456 list-projects
"""

import argparse
import json
import os
import sys

# 같은 디렉토리의 클라이언트 모듈 임포트
try:
    from labelo_api_client import LabeloAPIClient, cprint, print_table, Color
except ImportError:
    print("Error: labelo_api_client.py 파일이 같은 디렉토리에 있어야 합니다.")
    sys.exit(1)


def create_client(args) -> LabeloAPIClient:
    """인자에서 클라이언트를 생성하고 인증합니다."""
    client = LabeloAPIClient(args.url)

    if args.token:
        client.login_with_token(args.token)
        cprint(f"✅ 토큰 인증 완료", Color.GREEN)
    elif args.email and args.password:
        try:
            token = client.login(args.email, args.password)
            cprint(f"✅ 로그인 성공 (Token: {token[:8]}...)", Color.GREEN)
        except Exception as e:
            cprint(f"❌ 로그인 실패: {e}", Color.RED)
            sys.exit(1)
    else:
        cprint("❌ --email/--password 또는 --token이 필요합니다.", Color.RED)
        sys.exit(1)

    return client


def cmd_whoami(args):
    """내 정보 조회"""
    client = create_client(args)
    user = client.get_whoami()
    print(json.dumps(user, indent=2, ensure_ascii=False))


def cmd_list_projects(args):
    """프로젝트 목록 조회"""
    client = create_client(args)
    data = client.list_projects()
    projects = data.get("results", data) if isinstance(data, dict) else data

    cprint(f"\n📁 프로젝트 목록 (총 {data.get('count', len(projects))}개)", Color.BOLD)
    headers = ["ID", "제목", "태스크 수", "생성일"]
    rows = []
    for p in projects:
        created = str(p.get("created_at", ""))[:10]
        rows.append([
            str(p.get("id", "")),
            str(p.get("title", ""))[:40],
            str(p.get("task_number", 0)),
            created,
        ])
    print()
    print_table(headers, rows, [8, 42, 12, 12])

    if args.json:
        print("\n--- JSON ---")
        print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_list_members(args):
    """프로젝트 멤버(라벨러) 조회"""
    client = create_client(args)
    members = client.get_project_members(args.project)

    cprint(f"\n👥 프로젝트 #{args.project} 멤버 (총 {len(members)}명)", Color.BOLD)
    headers = ["사용자ID", "이메일", "이름", "역할", "상태"]
    rows = []
    for m in members:
        user = m.get("user", {})
        name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
        role = user.get("active_org_role", "N/A")
        enabled = "활성" if m.get("enabled", True) else "비활성"
        rows.append([
            str(user.get("id", "")),
            str(user.get("email", "")),
            name if name else "-",
            role,
            enabled,
        ])
    print()
    print_table(headers, rows, [10, 30, 18, 12, 10])

    if args.json:
        print("\n--- JSON ---")
        print(json.dumps(members, indent=2, ensure_ascii=False))


def cmd_list_users(args):
    """전체 사용자 목록 조회"""
    client = create_client(args)
    users = client.list_users()

    cprint(f"\n👥 전체 사용자 목록 (총 {len(users)}명)", Color.BOLD)
    headers = ["ID", "이메일", "이름", "역할"]
    rows = []
    for u in users:
        name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
        role = u.get("active_org_role", "N/A")
        rows.append([
            str(u.get("id", "")),
            str(u.get("email", "")),
            name if name else "-",
            role,
        ])
    print()
    print_table(headers, rows, [8, 35, 20, 12])

    if args.json:
        print("\n--- JSON ---")
        print(json.dumps(users, indent=2, ensure_ascii=False))


def cmd_available_users(args):
    """프로젝트에 추가 가능한 사용자 조회"""
    client = create_client(args)
    users = client.get_available_users(args.project)

    cprint(f"\n👤 프로젝트 #{args.project}에 추가 가능한 사용자 (총 {len(users)}명)", Color.BOLD)
    headers = ["ID", "이메일", "이름", "역할"]
    rows = []
    for u in users:
        name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
        role = u.get("active_org_role", "N/A")
        rows.append([
            str(u.get("id", "")),
            str(u.get("email", "")),
            name if name else "-",
            role,
        ])
    print()
    print_table(headers, rows, [8, 35, 20, 12])


def cmd_add_labeler(args):
    """라벨러 추가"""
    client = create_client(args)
    try:
        result = client.add_labeler(args.project, args.user)
        user_info = result.get("user", {})
        email = user_info.get("email", f"User #{args.user}")
        cprint(f"\n✅ 사용자 '{email}'(ID: {args.user})를 프로젝트 #{args.project}에 라벨러로 등록했습니다.", Color.GREEN)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        cprint(f"\n❌ 라벨러 추가 실패: {e}", Color.RED)
        sys.exit(1)


def cmd_add_labelers(args):
    """여러 라벨러 일괄 추가"""
    client = create_client(args)
    try:
        user_ids = [int(x.strip()) for x in args.users.split(",") if x.strip()]
    except ValueError:
        cprint("❌ 사용자 ID는 쉼표로 구분된 숫자여야 합니다.", Color.RED)
        sys.exit(1)

    cprint(f"\n프로젝트 #{args.project}에 {len(user_ids)}명을 등록합니다...", Color.CYAN)
    results = client.add_labelers_bulk(args.project, user_ids)

    success_count = 0
    fail_count = 0
    for r in results:
        if r["status"] == "success":
            user_data = r.get("data", {}).get("user", {})
            email = user_data.get("email", f"ID:{r['user_id']}")
            cprint(f"  ✅ {email} (ID: {r['user_id']}) - 등록 성공", Color.GREEN)
            success_count += 1
        else:
            cprint(f"  ❌ 사용자 ID {r['user_id']} - 실패: {r['error']}", Color.RED)
            fail_count += 1

    print()
    cprint(f"결과: 성공 {success_count}명 / 실패 {fail_count}명", Color.BOLD)

    if args.json:
        print("\n--- JSON ---")
        print(json.dumps(results, indent=2, ensure_ascii=False))


def cmd_remove_labeler(args):
    """라벨러 제거"""
    client = create_client(args)
    try:
        result = client.remove_labeler(args.project, args.user)
        cprint(f"\n✅ 사용자(ID: {args.user})를 프로젝트 #{args.project}에서 제거했습니다.", Color.GREEN)
    except Exception as e:
        cprint(f"\n❌ 라벨러 제거 실패: {e}", Color.RED)
        sys.exit(1)


def cmd_register_user(args):
    """새 사용자 등록 (독립 회원가입)"""
    client = LabeloAPIClient(args.url)
    try:
        result = client.register_user(args.reg_email, args.reg_password, args.reg_username, args.reg_org)
        cprint(f"\n✅ 사용자 등록 완료!", Color.GREEN + Color.BOLD)
        cprint(f"  📧 이메일: {result.get('email')}", Color.GREEN)
        cprint(f"  👤 이름: {result.get('username')}", Color.GREEN)
        cprint(f"  🏢 조직: {result.get('organization')}", Color.GREEN)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
    except ConnectionError as e:
        cprint(f"\n❌ 연결 오류: {e}", Color.RED)
        sys.exit(1)
    except ValueError as e:
        cprint(f"\n❌ 등록 실패: {e}", Color.RED)
        sys.exit(1)
    except Exception as e:
        cprint(f"\n❌ 오류: {e}", Color.RED)
        sys.exit(1)


def cmd_invite_user(args):
    """현재 조직에 새 사용자 등록"""
    client = create_client(args)
    try:
        result = client.invite_user(args.invite_email, args.invite_password, args.invite_username, args.role)
        cprint(f"\n✅ 사용자 등록 완료!", Color.GREEN + Color.BOLD)
        org_name = result.get('organization_name') or result.get('organization_id')
        if org_name:
            cprint(f"  🏢 조직: {org_name}", Color.GREEN)
        cprint(f"  📧 이메일: {result.get('email')}", Color.GREEN)
        cprint(f"  👤 이름: {result.get('username')}", Color.GREEN)
        cprint(f"  👔 역할: {result.get('role')}", Color.GREEN)
        msg = result.get('message', '')
        if msg:
            cprint(f"  💬 {msg}", Color.DIM)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        cprint(f"\n❌ 등록 실패: {e}", Color.RED)
        sys.exit(1)


def cmd_delete_user(args):
    """사용자 제거 (조직에서 제거 / 삭제)"""
    client = create_client(args)
    try:
        whoami = client.get_whoami()
        active_org_id = whoami.get("active_organization")
        client.delete_user(args.user, active_org_id)
        cprint(f"\n✅ 사용자(ID: {args.user})를 성공적으로 제거했습니다.", Color.GREEN)
    except Exception as e:
        cprint(f"\n❌ 사용자 제거 실패: {e}", Color.RED)
        sys.exit(1)


def cmd_project_progress(args):
    """프로젝트 작업 진행상황 모니터링"""
    client = create_client(args)
    try:
        progress = client.get_project_progress(args.project)

        cprint(f"\n📊 프로젝트 #{args.project} 작업 진행상황", Color.BOLD)
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

        headers = ["항목", "값"]
        rows = [
            ["전체 태스크", str(progress["task_number"])],
            ["완료 태스크", str(progress["finished_task_number"])],
            ["어노테이션 있는 태스크", str(progress["num_tasks_with_annotations"])],
            ["전체 어노테이션 수", str(progress["total_annotations_number"])],
            ["전체 예측 수", str(progress["total_predictions_number"])],
            ["진행률", f"{pct}%"],
        ]
        print_table(headers, rows, [25, 15])

        # 라벨 통계
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

        if args.json:
            print("\n--- JSON ---")
            print(json.dumps(progress, indent=2, ensure_ascii=False))

    except Exception as e:
        cprint(f"\n❌ 진행상황 조회 실패: {e}", Color.RED)
        sys.exit(1)


def cmd_create_project(args):
    """새 프로젝트 생성"""
    client = create_client(args)
    try:
        project = client.create_project(args.title, description=args.description or "")
        pid = project.get("id")
        settings_url = f"{client.base_url}/projects/{pid}/settings"
        cprint(f"\n✅ 프로젝트가 성공적으로 생성되었습니다!", Color.GREEN + Color.BOLD)
        cprint(f"  📁 프로젝트 ID: {pid}", Color.GREEN)
        cprint(f"  🏷️  프로젝트 명: {project.get('title')}", Color.GREEN)
        cprint(f"  🌐 웹 설정 바로가기: {settings_url}", Color.CYAN)
        cprint(f"  💡 브라우저에서 위 URL로 접속하여 라벨링 인터페이스 및 데이터를 설정하세요.", Color.DIM)
        if args.json:
            print(json.dumps(project, indent=2, ensure_ascii=False))
    except Exception as e:
        cprint(f"\n❌ 프로젝트 생성 실패: {e}", Color.RED)
        sys.exit(1)


def cmd_import_data(args):
    """프로젝트 데이터 Import"""
    client = create_client(args)
    try:
        cprint(f"\n⏳ 프로젝트 #{args.project}에 데이터를 Import합니다...", Color.CYAN)
        if args.file:
            result = client.import_tasks(args.project, file_path=args.file)
        elif args.json_data:
            tasks_data = json.loads(args.json_data)
            result = client.import_tasks(args.project, tasks=tasks_data)
        else:
            cprint("❌ --file 또는 --json-data 중 하나를 지정해야 합니다.", Color.RED)
            sys.exit(1)

        task_count = result.get("task_count", 0)
        annotation_count = result.get("annotation_count", 0)
        duration = result.get("duration", 0)
        data_cols = result.get("data_columns", [])
        cols_str = ", ".join(data_cols) if data_cols else "없음"

        cprint(f"\n✅ 데이터 Import 완료!", Color.GREEN + Color.BOLD)
        cprint(f"  📁 프로젝트 ID  : #{args.project}", Color.GREEN)
        cprint(f"  📊 생성된 태스크: {task_count:,}개", Color.GREEN)
        if annotation_count > 0:
            cprint(f"  🏷️  어노테이션  : {annotation_count:,}개", Color.GREEN)
        if duration:
            cprint(f"  ⏱️  소요 시간   : {duration:.2f}초", Color.DIM)
        cprint(f"  📋 감지된 컬럼  : {cols_str}", Color.DIM)
        cprint(f"  🌐 프로젝트 바로가기: {client.base_url}/projects/{args.project}/data", Color.CYAN)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        cprint(f"\n❌ 데이터 Import 실패: {e}", Color.RED)
        sys.exit(1)


def cmd_download_tasks(args):
    """프로젝트 데이터 다운로드"""
    client = create_client(args)
    output_dir = args.output_dir or "."
    download_all = not args.annotated_only
    include_images = not args.no_images

    def on_progress(current, total, filename, status):
        pct = int(current / total * 100) if total > 0 else 100
        bar_len = 25
        filled = int(bar_len * current / total) if total > 0 else bar_len
        bar = "█" * filled + "░" * (bar_len - filled)
        status_icon = "✅" if status == "success" else "⚠️"
        fname_display = filename if len(filename) <= 25 else filename[:22] + "..."
        print(f"\r  📥 이미지 다운로드: [{bar}] {pct}% ({current}/{total}) {status_icon} {fname_display:<25}", end="", flush=True)

    try:
        cprint(f"\n⏳ 프로젝트 #{args.project} 데이터를 다운로드합니다...", Color.CYAN)
        if download_all:
            cprint("  (모든 태스크 포함)", Color.DIM)
        else:
            cprint("  (어노테이션된 태스크만)", Color.DIM)

        if include_images:
            cprint("  (이미지 파일 포함 압축 ZIP)", Color.DIM)

        filepath = client.download_project_tasks(
            args.project,
            output_dir=output_dir,
            download_all=download_all,
            include_images=include_images,
            progress_callback=on_progress if include_images else None,
        )
        if include_images:
            print()  # 줄바꿈

        file_size = os.path.getsize(filepath)
        size_str = f"{file_size:,} bytes"
        if file_size > 1024 * 1024:
            size_str = f"{file_size / (1024 * 1024):.1f} MB"
        elif file_size > 1024:
            size_str = f"{file_size / 1024:.1f} KB"

        cprint(f"\n✅ 다운로드 완료!", Color.GREEN + Color.BOLD)
        cprint(f"  📄 파일: {filepath}", Color.GREEN)
        cprint(f"  📦 크기: {size_str}", Color.GREEN)
        if include_images:
            cprint(f"  📁 구성: JSON 태스크 데이터 + images/ 폴더 (이미지 포함)", Color.CYAN)

    except Exception as e:
        cprint(f"\n❌ 다운로드 실패: {e}", Color.RED)
        sys.exit(1)


def cmd_export_labels(args):
    """라벨링 데이터 Export"""
    client = create_client(args)
    output_dir = args.output_dir or "."
    export_type = args.format or "JSON"
    include_images = not args.no_images

    def on_progress(current, total, filename, status):
        pct = int(current / total * 100) if total > 0 else 100
        bar_len = 25
        filled = int(bar_len * current / total) if total > 0 else bar_len
        bar = "█" * filled + "░" * (bar_len - filled)
        status_icon = "✅" if status == "success" else "⚠️"
        fname_display = filename if len(filename) <= 25 else filename[:22] + "..."
        print(f"\r  📥 이미지 다운로드: [{bar}] {pct}% ({current}/{total}) {status_icon} {fname_display:<25}", end="", flush=True)

    try:
        # 사용 가능한 포맷 확인
        if args.list_formats:
            formats = client.get_export_formats(args.project)
            cprint(f"\n📋 프로젝트 #{args.project}에서 사용 가능한 Export 포맷:", Color.BOLD)
            headers = ["포맷", "제목", "사용 가능"]
            rows = []
            for fmt in formats:
                disabled = fmt.get("disabled", False)
                status = "❌ 비활성" if disabled else "✅ 활성"
                rows.append([
                    fmt.get("name", "?"),
                    fmt.get("title", ""),
                    status,
                ])
            print()
            print_table(headers, rows, [15, 40, 12])
            return

        if args.snapshot:
            # Export 스냅샷 방식 (대규모 프로젝트용)
            cprint(f"\n⏳ Export 스냅샷을 생성합니다 (포맷: {export_type})...", Color.CYAN)
            if include_images:
                cprint("  (이미지 파일 포함 압축 ZIP)", Color.DIM)
            filepath = client.export_and_download(
                args.project,
                export_type=export_type,
                output_dir=output_dir,
                include_images=include_images,
                progress_callback=on_progress if include_images else None,
            )
        else:
            # Easy Export 방식
            cprint(f"\n⏳ 라벨링 데이터를 Export합니다 (포맷: {export_type})...", Color.CYAN)
            if include_images:
                cprint("  (이미지 파일 포함 압축 ZIP)", Color.DIM)
            filepath = client.download_project_tasks(
                args.project,
                output_dir=output_dir,
                download_all=False,
                export_type=export_type,
                include_images=include_images,
                progress_callback=on_progress if include_images else None,
            )

        if include_images:
            print()  # 줄바꿈

        file_size = os.path.getsize(filepath)
        size_str = f"{file_size:,} bytes"
        if file_size > 1024 * 1024:
            size_str = f"{file_size / (1024 * 1024):.1f} MB"
        elif file_size > 1024:
            size_str = f"{file_size / 1024:.1f} KB"

        cprint(f"\n✅ Export 완료!", Color.GREEN + Color.BOLD)
        cprint(f"  📄 파일: {filepath}", Color.GREEN)
        cprint(f"  📦 크기: {size_str}", Color.GREEN)
        cprint(f"  📋 포맷: {export_type}", Color.GREEN)
        if include_images:
            cprint(f"  📁 구성: 라벨링 데이터 + images/ 폴더 (이미지 포함)", Color.CYAN)

    except TimeoutError as e:
        cprint(f"\n⏰ 시간 초과: {e}", Color.YELLOW)
        sys.exit(1)
    except RuntimeError as e:
        cprint(f"\n❌ Export 실패: {e}", Color.RED)
        sys.exit(1)
    except Exception as e:
        cprint(f"\n❌ Export 실패: {e}", Color.RED)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="LabelO API 자동화 예제 스크립트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # 공통 인자
    parser.add_argument("--url", default="http://localhost:8080", help="LabelO 서버 URL")
    parser.add_argument("--email", help="로그인 이메일")
    parser.add_argument("--password", help="로그인 비밀번호")
    parser.add_argument("--token", help="API 토큰 (이메일/비밀번호 대신 사용)")
    parser.add_argument("--json", action="store_true", help="JSON 형식으로도 출력")

    # 서브 커맨드
    subparsers = parser.add_subparsers(dest="command", help="실행할 명령")

    # whoami
    subparsers.add_parser("whoami", help="내 정보 조회")

    # list-projects
    subparsers.add_parser("list-projects", help="프로젝트 목록 조회")

    # list-users
    subparsers.add_parser("list-users", help="전체 사용자 목록 조회")

    # list-members
    p_members = subparsers.add_parser("list-members", help="프로젝트 멤버 조회")
    p_members.add_argument("--project", type=int, required=True, help="프로젝트 ID")

    # available-users
    p_avail = subparsers.add_parser("available-users", help="프로젝트에 추가 가능한 사용자 조회")
    p_avail.add_argument("--project", type=int, required=True, help="프로젝트 ID")

    # add-labeler
    p_add = subparsers.add_parser("add-labeler", help="프로젝트에 라벨러 추가")
    p_add.add_argument("--project", type=int, required=True, help="프로젝트 ID")
    p_add.add_argument("--user", type=int, required=True, help="사용자 ID")

    # add-labelers (일괄)
    p_adds = subparsers.add_parser("add-labelers", help="프로젝트에 여러 라벨러 일괄 추가")
    p_adds.add_argument("--project", type=int, required=True, help="프로젝트 ID")
    p_adds.add_argument("--users", required=True, help="사용자 ID들 (쉼표 구분, 예: 1,2,3)")

    # remove-labeler
    p_rm = subparsers.add_parser("remove-labeler", help="프로젝트에서 라벨러 제거")
    p_rm.add_argument("--project", type=int, required=True, help="프로젝트 ID")
    p_rm.add_argument("--user", type=int, required=True, help="사용자 ID")

    # register-user (독립 회원가입)
    p_reg = subparsers.add_parser("register-user", help="새 사용자 등록 (독립 회원가입, 로그인 불필요)")
    p_reg.add_argument("--reg-email", required=True, help="등록할 사용자 이메일")
    p_reg.add_argument("--reg-password", required=True, help="비밀번호 (8자 이상)")
    p_reg.add_argument("--reg-username", required=True, help="사용자 이름")
    p_reg.add_argument("--reg-org", required=True, help="조직 이름")

    # invite-user (현재 조직에 사용자 등록, 로그인 필요)
    p_inv = subparsers.add_parser("invite-user", help="현재 조직에 새 사용자 등록 (로그인 필요)")
    p_inv.add_argument("--invite-email", required=True, help="등록할 사용자 이메일")
    p_inv.add_argument("--invite-password", required=True, help="비밀번호 (8자 이상)")
    p_inv.add_argument("--invite-username", required=True, help="사용자 이름")
    p_inv.add_argument("--role", default="annotater", choices=["annotater", "reviewer", "manager", "administrator"], help="역할 (기본: annotater)")

    # delete-user (사용자 제거)
    p_del_user = subparsers.add_parser("delete-user", help="사용자 제거 (조직에서 제거 / 삭제)")
    p_del_user.add_argument("--user", type=int, required=True, help="제거할 사용자 ID")

    # create-project (새 프로젝트 등록)
    p_create_p = subparsers.add_parser("create-project", help="새 프로젝트 생성 (프로젝트 명만 입력)")
    p_create_p.add_argument("--title", required=True, help="프로젝트 이름")
    p_create_p.add_argument("--description", default="", help="프로젝트 설명 (선택 사항)")

    # project-progress (프로젝트 진행상황 모니터링)
    p_progress = subparsers.add_parser("project-progress", help="프로젝트 작업 진행상황 모니터링")
    p_progress.add_argument("--project", type=int, required=True, help="프로젝트 ID")

    # import-data (데이터 Import)
    p_import = subparsers.add_parser("import-data", help="프로젝트 데이터 Import (JSON, CSV, ZIP 파일 등)")
    p_import.add_argument("--project", type=int, required=True, help="프로젝트 ID")
    p_import.add_argument("--file", help="업로드할 데이터 파일 경로 (JSON, CSV, TSV, TXT, ZIP 등)")
    p_import.add_argument("--json-data", help="직접 전달할 JSON 문자열 (예: '[{\"image\": \"...\"}]')")

    # download-tasks (프로젝트 데이터 다운로드)
    p_download = subparsers.add_parser("download-tasks", help="프로젝트 데이터 다운로드 (이미지 포함 ZIP 압축)")
    p_download.add_argument("--project", type=int, required=True, help="프로젝트 ID")
    p_download.add_argument("--output-dir", default=".", help="저장 경로 (기본: 현재 폴더)")
    p_download.add_argument("--all", action="store_true", default=True, help="모든 태스크 다운로드 (기본: True)")
    p_download.add_argument("--annotated-only", action="store_true", help="어노테이션된 태스크만 다운로드")
    p_download.add_argument("--no-images", action="store_true", help="이미지 다운로드 제외 (JSON만 저장)")

    # export-labels (라벨링 데이터 Export)
    p_export = subparsers.add_parser("export-labels", help="프로젝트 라벨링 데이터 Export & 다운로드 (이미지 포함 ZIP 압축)")
    p_export.add_argument("--project", type=int, required=True, help="프로젝트 ID")
    p_export.add_argument("--format", default="JSON", help="Export 포맷 (기본: JSON, 예: CSV, COCO, YOLO 등)")
    p_export.add_argument("--output-dir", default=".", help="저장 경로 (기본: 현재 폴더)")
    p_export.add_argument("--snapshot", action="store_true", help="Export 스냅샷 방식 사용 (대규모 프로젝트용)")
    p_export.add_argument("--list-formats", action="store_true", help="사용 가능한 Export 포맷 목록 조회")
    p_export.add_argument("--no-images", action="store_true", help="이미지 다운로드 제외 (라벨 데이터만 저장)")

    args = parser.parse_args()

    # register-user 커맨드는 사전 체크 skip
    if args.command == "register-user":
        cmd_register_user(args)
        return

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # 커맨드 라우팅
    commands = {
        "whoami": cmd_whoami,
        "list-projects": cmd_list_projects,
        "create-project": cmd_create_project,
        "list-users": cmd_list_users,
        "list-members": cmd_list_members,
        "available-users": cmd_available_users,
        "add-labeler": cmd_add_labeler,
        "add-labelers": cmd_add_labelers,
        "remove-labeler": cmd_remove_labeler,
        "register-user": cmd_register_user,
        "invite-user": cmd_invite_user,
        "delete-user": cmd_delete_user,
        "project-progress": cmd_project_progress,
        "import-data": cmd_import_data,
        "download-tasks": cmd_download_tasks,
        "export-labels": cmd_export_labels,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
