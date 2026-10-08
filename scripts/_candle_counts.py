import asyncio

from private_trading_db.session import dispose_engine, get_session_factory
from sqlalchemy import text


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            text(
                """
                SELECT i.canonical_symbol, c.timeframe, COUNT(*) AS n,
                       MIN(c.open_time) AS earliest, MAX(c.open_time) AS latest
                FROM candles c
                JOIN instruments i ON i.id = c.instrument_id
                GROUP BY 1, 2
                ORDER BY 1, 2
                """
            )
        )
        rows = result.all()
        print(f"series={len(rows)}")
        for row in rows:
            print(f"{row[0]} {row[1]} n={row[2]} from={row[3]} to={row[4]}")
        print(f"total_candles={sum(int(r[2]) for r in rows)}")
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
