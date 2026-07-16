"""runtime_database_role_grants

Revision ID: d4e5f6a7b8c9
Revises: c7e4a9b2d135
Create Date: 2026-07-16 00:00:00.000000

"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.sql.sqltypes import String

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c7e4a9b2d135"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _role_sql() -> tuple[str, str] | None:
    app_user = os.getenv("POSTGRES_APP_USER")
    app_password = os.getenv("POSTGRES_APP_PASSWORD")
    if not app_user:
        return None

    bind = op.get_bind()
    preparer = bind.dialect.identifier_preparer
    role = preparer.quote(app_user)

    if app_password:
        literal_processor = String().literal_processor(bind.dialect)
        password = literal_processor(app_password) if literal_processor else None
        if password is not None:
            exists = bind.execute(
                sa.text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :role)"),
                {"role": app_user},
            ).scalar_one()
            if exists:
                op.execute(
                    f"ALTER ROLE {role} WITH LOGIN PASSWORD {password} "
                    "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"
                )
            else:
                op.execute(
                    f"CREATE ROLE {role} LOGIN PASSWORD {password} "
                    "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS"
                )

    return app_user, role


def upgrade() -> None:
    """Upgrade schema."""
    role_info = _role_sql()
    if role_info is None:
        return

    _, role = role_info
    op.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}"
    )
    op.execute(
        f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {role}"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {role}"
    )


def downgrade() -> None:
    """Downgrade schema."""
    role_info = _role_sql()
    if role_info is None:
        return

    _, role = role_info
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {role}"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE USAGE, SELECT, UPDATE ON SEQUENCES FROM {role}"
    )
    op.execute(
        f"REVOKE USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public FROM {role}"
    )
    op.execute(
        "REVOKE SELECT, INSERT, UPDATE, DELETE "
        f"ON ALL TABLES IN SCHEMA public FROM {role}"
    )
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {role}")
