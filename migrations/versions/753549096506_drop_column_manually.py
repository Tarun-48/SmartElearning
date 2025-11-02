"""drop column manually

Revision ID: 753549096506
Revises: 8f13079bb19f
Create Date: 2025-11-03 04:11:58.404137

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '753549096506'
down_revision = '8f13079bb19f'
branch_labels = None
depends_on = None


def upgrade():
    # SQLite doesn't support DROP COLUMN, so ignore error for local dev
    try:
        op.drop_column('note', 'uploaded_at')
    except:
        pass  # Column already removed or sqlite doesn't support drop column


def downgrade():
    # Restore column in case rollback
    op.add_column('note', sa.Column('uploaded_at', sa.DateTime(), nullable=True))
