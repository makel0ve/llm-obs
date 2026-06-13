"""add_rls_policies

Revision ID: bf79868b5f76
Revises: f37d7ee64540
Create Date: 2026-05-30 18:15:52.137434

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bf79868b5f76"
down_revision: str | Sequence[str] | None = "f37d7ee64540"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE spans ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE traces ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY spans_project_isolation ON spans
        USING (project_id = current_setting('app.current_project_id', true)::uuid)
    """)
    op.execute("""
        CREATE POLICY traces_project_isolation ON traces
        USING (project_id = current_setting('app.current_project_id', true)::uuid)
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY IF EXISTS spans_project_isolation ON spans")
    op.execute("DROP POLICY IF EXISTS traces_project_isolation ON traces")
    op.execute("ALTER TABLE spans DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE traces DISABLE ROW LEVEL SECURITY")
