"""Create (or reset) the initial admin account.

Usage (from the backend/ directory):
    python ../scripts/create_admin.py --username admin --password 'StrongPass123'
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.security import hash_password  # noqa: E402
from app.db.session import async_session_factory, init_db  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.repositories.user import UserRepository  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", required=True)
    parser.add_argument("--full-name", default="Administrator")
    parser.add_argument("--reset", action="store_true",
                        help="reset password/role/is_active if the user already exists")
    args = parser.parse_args()

    if len(args.password) < 8:
        raise SystemExit("password must be at least 8 characters")

    await init_db()
    async with async_session_factory() as db:
        repo = UserRepository(db)
        user = await repo.get_by_username(args.username)
        if user is None:
            user = User(
                username=args.username,
                full_name=args.full_name,
                role=UserRole.admin,
                hashed_password=hash_password(args.password),
            )
            repo.add(user)
            print(f"created admin user '{args.username}'")
        elif args.reset:
            user.hashed_password = hash_password(args.password)
            user.role = UserRole.admin
            user.is_active = True
            print(f"reset password for admin user '{args.username}'")
        else:
            # never silently reset an existing account on a re-run
            print(f"ALREADY_EXISTS: user '{args.username}' left untouched "
                  "(pass --reset to reset the password)")
            return
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
