"""null_safe_rls_project_context

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-16 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NULL_SAFE_CONTEXT = "NULLIF(current_setting('app.current_project_id', true), '')::uuid"
STRICT_CONTEXT = "current_setting('app.current_project_id', true)::uuid"


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("DROP POLICY IF EXISTS spans_project_isolation ON spans")
    op.execute("DROP POLICY IF EXISTS traces_project_isolation ON traces")
    op.execute(f"""
        CREATE POLICY spans_project_isolation ON spans
        USING (project_id = {NULL_SAFE_CONTEXT})
    """)
    op.execute(f"""
        CREATE POLICY traces_project_isolation ON traces
        USING (project_id = {NULL_SAFE_CONTEXT})
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY IF EXISTS spans_project_isolation ON spans")
    op.execute("DROP POLICY IF EXISTS traces_project_isolation ON traces")
    op.execute(f"""
        CREATE POLICY spans_project_isolation ON spans
        USING (project_id = {STRICT_CONTEXT})
    """)
    op.execute(f"""
        CREATE POLICY traces_project_isolation ON traces
        USING (project_id = {STRICT_CONTEXT})
    """)
