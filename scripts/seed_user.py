from __future__ import annotations

import argparse

from sqlmodel import Session, SQLModel, select

from app.core.security import get_password_hash
from app.db.session import engine
from app.models import User


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed a dev user for login")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument(
        "--role",
        default="admin",
        choices=["admin", "editor", "viewer"],
        help="Role to assign (default: admin)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="If user exists, delete and recreate",
    )
    args = parser.parse_args()

    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        existing = session.exec(select(User).where(User.email == args.email)).first()
        if existing is not None:
            if not args.reset:
                print("User already exists:")
                print(f"  id={existing.id}")
                print(f"  email={existing.email}")
                return 0

            session.delete(existing)
            session.commit()

        user = User(
            email=args.email,
            name=args.name,
            password_hash=get_password_hash(args.password),
            role=args.role,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        print("Created user:")
        print(f"  id={user.id}")
        print(f"  email={user.email}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
