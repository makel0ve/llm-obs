"""force_rls_on_trace_tables

Revision ID: 3b9f1a2c4d6e
Revises: 6d4b8a2e9c11
Create Date: 2026-07-10 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3b9f1a2c4d6e"
down_revision: str | Sequence[str] | None = "6d4b8a2e9c11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE spans FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE traces FORCE ROW LEVEL SECURITY")
    op.execute("""
        DO $$
        DECLARE
            partition_name regclass;
        BEGIN
            FOR partition_name IN
                SELECT child.oid::regclass
                FROM pg_inherits
                JOIN pg_class parent ON parent.oid = pg_inherits.inhparent
                JOIN pg_class child ON child.oid = pg_inherits.inhrelid
                WHERE parent.relname IN ('spans', 'traces')
            LOOP
                EXECUTE format(
                    'ALTER TABLE %s ENABLE ROW LEVEL SECURITY',
                    partition_name
                );
                EXECUTE format(
                    'ALTER TABLE %s FORCE ROW LEVEL SECURITY',
                    partition_name
                );
            END LOOP;
        END $$;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("""
        DO $$
        DECLARE
            partition_name regclass;
        BEGIN
            FOR partition_name IN
                SELECT child.oid::regclass
                FROM pg_inherits
                JOIN pg_class parent ON parent.oid = pg_inherits.inhparent
                JOIN pg_class child ON child.oid = pg_inherits.inhrelid
                WHERE parent.relname IN ('spans', 'traces')
            LOOP
                EXECUTE format(
                    'ALTER TABLE %s NO FORCE ROW LEVEL SECURITY',
                    partition_name
                );
                EXECUTE format(
                    'ALTER TABLE %s DISABLE ROW LEVEL SECURITY',
                    partition_name
                );
            END LOOP;
        END $$;
    """)
    op.execute("ALTER TABLE spans NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE traces NO FORCE ROW LEVEL SECURITY")
