"""Run `python -m app.db.check` to verify the configured PostgreSQL connection."""

import asyncio
import sys

from sqlalchemy.exc import SQLAlchemyError

from app.db.session import check_database, close_database


async def main() -> int:
    try:
        await check_database()
        print("PostgreSQL connection successful.")
        return 0
    except (SQLAlchemyError, OSError):
        print("PostgreSQL connection failed. Check DATABASE_URL and the database service.")
        return 1
    finally:
        await close_database()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
