"""Keep databases that previously applied the withdrawn Day 9 migration readable.

The Day 9 orchestration fields are no longer part of ProcureRPA's scope.
This revision intentionally does nothing for new databases, but remains in
the migration chain for existing development databases stamped at ent_007.
"""

revision = "ent_007"
down_revision = "ent_006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
