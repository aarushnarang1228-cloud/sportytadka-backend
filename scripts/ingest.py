"""
Manual data ingestion script.
Run this to immediately fetch and store match data without waiting for the scheduler.

Usage: python -m scripts.ingest
"""

import asyncio
import logging
import sys
import os

# Add parent dir to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import Base, engine
from app.tasks.ingestion import ingest_matches

logging.basicConfig(level=logging.INFO)


async def main():
    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("Running manual ingestion...")
    await ingest_matches()
    print("Done!")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
