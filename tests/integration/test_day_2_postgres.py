"""Opt-in PostgreSQL acceptance; deliberately never substitutes SQLite or mocks."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import asyncpg
import pytest

DATABASE_URL = os.getenv("DAY2_POSTGRES_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="set DAY2_POSTGRES_DATABASE_URL to an empty PostgreSQL database")


def test_day_2_migrations_and_constraints() -> None:
    env = {**os.environ, "DATABASE_STRING": DATABASE_URL}
    alembic = str(Path(sys.executable).parent / "alembic.exe")
    for command in (("upgrade", "head"), ("downgrade", "base"), ("upgrade", "head")):
        subprocess.run([alembic, *command], check=True, env=env)

    async def verify() -> None:
        connection = await asyncpg.connect(DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://"))
        try:
            await connection.execute("INSERT INTO organizations (organization_id, organization_name, created_at, modified_at) VALUES ('org_a', 'A', now(), now()), ('org_b', 'B', now(), now())")
            await connection.execute("INSERT INTO departments (department_id, organization_id, department_name, department_code, created_at, modified_at) VALUES ('dept_a', 'org_a', 'A', 'A', now(), now())")
            await connection.execute("INSERT INTO procurement_categories (category_id, organization_id, category_name, category_code, created_at, modified_at) VALUES ('cat_a', 'org_a', 'A', 'A', now(), now()), ('cat_b', 'org_b', 'B', 'B', now(), now())")
            with pytest.raises(asyncpg.UniqueViolationError):
                await connection.execute("INSERT INTO procurement_categories (category_id, organization_id, category_name, category_code, created_at, modified_at) VALUES ('cat_dup', 'org_a', 'A2', 'A', now(), now())")
            await connection.execute("INSERT INTO enterprise_users (user_id, organization_id, username, password_hash, display_name, is_active, created_at, modified_at) VALUES ('user_a', 'org_a', 'a', 'x', 'A', true, now(), now())")
            await connection.execute("INSERT INTO tasks (task_id, organization_id, created_at, modified_at) VALUES ('task_a', 'org_a', now(), now())")
            with pytest.raises(asyncpg.ForeignKeyViolationError):
                await connection.execute("INSERT INTO task_extensions (extension_id, task_id, organization_id, department_id, category_id, created_by, created_at, modified_at) VALUES ('te_bad_fk', 'task_a', 'org_a', 'dept_a', 'missing', 'user_a', now(), now())")
            with pytest.raises(asyncpg.RaiseError):
                await connection.execute("INSERT INTO task_extensions (extension_id, task_id, organization_id, department_id, category_id, created_by, created_at, modified_at) VALUES ('te_cross_org', 'task_a', 'org_a', 'dept_a', 'cat_b', 'user_a', now(), now())")
        finally:
            await connection.close()

    asyncio.run(verify())
