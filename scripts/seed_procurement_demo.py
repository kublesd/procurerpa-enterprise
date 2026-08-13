"""Create the minimal procurement users and scope needed by the smoke task."""

import asyncio

from enterprise.procurement.seed import seed_procurement_data
from skyvern.forge import app
from skyvern.forge.forge_app_initializer import start_forge_app


async def main() -> None:
    async with app.DATABASE.Session() as session:
        created = await seed_procurement_data(session)
        await session.commit()
    print(created)


if __name__ == "__main__":
    start_forge_app()
    asyncio.run(main())
