"""one screening decision and one coding record per video

The project no longer double-screens or double-codes (researcher user
testing, v3), so each video has a single screening decision and a single
coding record. These unique constraints enforce that at the database level.

Additive only -- no rows are changed or deleted. It fails (and changes
nothing) if a video already has more than one row; any such legacy
duplicates must be resolved by hand first. Production had none when this
was written.

Revision ID: 8b1d6e4f2c70
Revises: 3f9c2a7d4e1b
Create Date: 2026-10-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '8b1d6e4f2c70'
down_revision: Union[str, Sequence[str], None] = '3f9c2a7d4e1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint(
        'uq_screening_study_video', 'screening_decisions', ['study_id', 'video_id']
    )
    op.create_unique_constraint(
        'uq_video_coding_study_video', 'video_coding', ['study_id', 'video_id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_video_coding_study_video', 'video_coding', type_='unique')
    op.drop_constraint('uq_screening_study_video', 'screening_decisions', type_='unique')
