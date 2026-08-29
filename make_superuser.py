"""
Labelo 시스템 최고 관리자(Superuser) 생성 및 승격 스크립트

사용법:
  python make_superuser.py 2026@asan.com
  python make_superuser.py admin@example.com --create --password "Password123!"
"""
import os
import sys
import argparse

# Windows 콘솔 utf-8 인코딩 설정
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Django 설정 로드
labelo_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "labelo", "labelo")
if labelo_dir not in sys.path:
    sys.path.insert(0, labelo_dir)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.labelo")

try:
    import django
    django.setup()
except ImportError:
    print("❌ Django 환경을 로드할 수 없습니다. Labelo 서버 가상환경이 활성화되어 있는지 확인하세요.")
    sys.exit(1)

from users.models import User
from organizations.models import Organization, OrganizationMember
from django.contrib.auth.models import Group


def main():
    parser = argparse.ArgumentParser(description="Labelo 최고 관리자(Superuser) 생성/승격 도구")
    parser.add_argument("email", help="최고 관리자로 설정할 이메일")
    parser.add_argument("--create", action="store_true", help="계정이 없으면 새로 생성")
    parser.add_argument("--password", help="신규 생성 시 비밀번호 (미지정 시 자동 요청)")
    parser.add_argument("--username", help="사용자 이름 (기본값: 이메일 ID)")

    args = parser.parse_args()
    email = args.email.strip()

    try:
        user = User.objects.get(email=email)
        user.is_superuser = True
        user.is_staff = True
        user.is_active = True
        user.save()

        # owner 그룹 설정
        g, _ = Group.objects.get_or_create(name="owner")
        user.groups.set([g])

        print(f"\n✅ 기존 사용자 '{email}'(ID: {user.id}) 계정이 최고 관리자(Superuser)로 승격되었습니다!")

    except User.DoesNotExist:
        if not args.create:
            print(f"\n❌ 사용자 '{email}'를 찾을 수 없습니다.")
            print(f"   새로 생성하려면 '--create' 옵션을 추가하세요:")
            print(f"   python make_superuser.py {email} --create")
            sys.exit(1)

        password = args.password
        if not password:
            import getpass
            password = getpass.getpass("비밀번호 (8자 이상): ")
            if len(password) < 8:
                print("❌ 비밀번호는 8자 이상이어야 합니다.")
                sys.exit(1)

        username = args.username or email.split("@")[0]

        # 기본 조직 찾기
        org = Organization.objects.first()

        user = User.objects.create_user(
            email=email,
            password=password,
            username=username,
            is_superuser=True,
            is_staff=True,
            is_active=True,
            active_organization=org,
        )

        if org:
            org_member, _ = OrganizationMember.objects.get_or_create(
                user=user,
                organization=org,
                defaults={"role": "owner", "status": "active"},
            )
            org_member.role = "owner"
            org_member.status = "active"
            org_member.save()

        for g_name in ["administrator", "owner"]:
            g, _ = Group.objects.get_or_create(name=g_name)
            user.groups.add(g)

        print(f"\n✅ 최고 관리자(Superuser) 계정 '{email}'(ID: {user.id})이 성공적으로 생성되었습니다!")


if __name__ == "__main__":
    main()
