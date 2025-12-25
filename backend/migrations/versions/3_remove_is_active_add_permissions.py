"""Remove is_active and add permissions

Revision ID: 3_remove_is_active_add_permissions
Revises: 2aad22c9069a
Create Date: 2025-12-25 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3_remove_is_active_add_permissions'
down_revision = '2aad22c9069a'
branch_labels = None
depends_on = None


def upgrade():
    # Remove is_active column from user table
    op.drop_column('user', 'is_active')
    
    # Add new columns to user table
    op.add_column('user', sa.Column('created_at', sa.DateTime(), nullable=True))
    op.add_column('user', sa.Column('last_login', sa.DateTime(), nullable=True))
    
    # Change default role to 'proto'
    op.alter_column('user', 'role', server_default='proto')
    
    # Create user_machine table for permissions
    op.create_table('user_machine',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.Integer(), nullable=False),
        sa.Column('visible_data', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['device_id'], ['device.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    # Drop user_machine table
    op.drop_table('user_machine')
    
    # Remove new columns
    op.drop_column('user', 'last_login')
    op.drop_column('user', 'created_at')
    
    # Add back is_active column
    op.add_column('user', sa.Column('is_active', sa.Boolean(), nullable=False, default=True))
    
    # Reset role default
    op.alter_column('user', 'role', server_default='user')
