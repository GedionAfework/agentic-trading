from __future__ import annotations

import argparse
import asyncio
import os

from private_trading_core.config import get_settings
from private_trading_core.logging import configure_logging, get_logger

from private_trading_db.services.auth import create_user, get_user_by_email
from private_trading_db.session import dispose_engine, get_session_factory

logger = get_logger(__name__)


async def seed_owner(
    email: str,
    password: str,
    display_name: str = "Owner",
) -> None:
    factory = get_session_factory()
    async with factory() as session:
        existing = await get_user_by_email(session, email)
        if existing is not None:
            logger.info("owner_exists email=%s", email)
            return
        await create_user(
            session,
            email=email,
            password=password,
            display_name=display_name,
            roles=["owner", "admin"],
        )
        await session.commit()
        logger.info("owner_created email=%s", email)


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="Seed the owner account")
    parser.add_argument(
        "--email",
        default=os.getenv("OWNER_EMAIL", "owner@example.com"),
    )
    parser.add_argument(
        "--password",
        default=os.getenv("OWNER_PASSWORD", "changeme-owner"),
    )
    parser.add_argument("--display-name", default="Owner")
    args = parser.parse_args()

    settings = get_settings()
    logger.info("seeding database=%s", settings.database_url.split("@")[-1])

    async def _run() -> None:
        try:
            await seed_owner(args.email, args.password, args.display_name)
        finally:
            await dispose_engine()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
