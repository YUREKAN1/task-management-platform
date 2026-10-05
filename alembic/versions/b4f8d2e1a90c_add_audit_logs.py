"""add_audit_logs

Revision ID: b4f8d2e1a90c
Revises: 5da59097909e
Create Date: 2026-09-20 16:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4f8d2e1a90c'
down_revision: Union[str, Sequence[str], None] = '5da59097909e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    audit_action_enum = sa.Enum(
        'USER_REGISTERED', 'USER_UPDATED', 'USER_DEACTIVATED',
        'TEAM_CREATED', 'MEMBER_ADDED', 'MEMBER_REMOVED', 'MEMBER_ROLE_CHANGED',
        'PROJECT_CREATED', 'PROJECT_UPDATED', 'PROJECT_DELETED',
        'TASK_CREATED', 'TASK_UPDATED', 'TASK_COMPLETED', 'TASK_REOPENED',
        'TASK_ASSIGNED', 'TASK_UNASSIGNED', 'TASK_DELETED',
        name='auditaction'
    )
    

    op.create_table(
        'audit_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('actor_id', sa.UUID(), nullable=False),
        sa.Column('action', audit_action_enum, nullable=False),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('entity_id', sa.UUID(), nullable=False),
        sa.Column('team_id', sa.UUID(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id']),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_actor_id'), 'audit_logs', ['actor_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_audit_logs_entity_id'), 'audit_logs', ['entity_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_entity_type'), 'audit_logs', ['entity_type'], unique=False)
    op.create_index(op.f('ix_audit_logs_team_id'), 'audit_logs', ['team_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_audit_logs_team_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_entity_type'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_entity_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_created_at'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_actor_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_action'), table_name='audit_logs')
    op.drop_table('audit_logs')
    audit_action_enum = sa.Enum(name='auditaction')
    audit_action_enum.drop(op.get_bind(), checkfirst=True)
