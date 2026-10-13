"""add accuracy_notes to video_coding

Free-text accuracy observations captured in the Characteristics tab, which
replace the claim-level accuracy assessment for new coding (researcher user
testing). Additive and nullable: existing rows are untouched, and the legacy
accuracy_claims/accuracy_review_status tables are kept as they are.

Revision ID: 3f9c2a7d4e1b
Revises: 658c4b61b5e1
Create Date: 2026-10-13 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f9c2a7d4e1b'
down_revision: Union[str, Sequence[str], None] = '658c4b61b5e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('video_coding', sa.Column('accuracy_notes', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('video_coding', 'accuracy_notes')
