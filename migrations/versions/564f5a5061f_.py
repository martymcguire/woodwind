"""empty message

Revision ID: 564f5a5061f
Revises: 5824a5f06dd
Create Date: 2015-04-19 07:49:24.416817

"""

# revision identifiers, used by Alembic.
revision = '564f5a5061f'
down_revision = '5824a5f06dd'

from alembic import op
import sqlalchemy as sa
from woodwind.models import JsonType


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    subsc = op.create_table(
        'subscription',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
        sa.Column('feed_id', sa.Integer(), sa.ForeignKey('feed.id'), nullable=False),
        sa.Column('name', sa.String(length=256), nullable=True),
        sa.Column('tags', sa.String(length=256), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    feed = sa.table(
        'feed',
        sa.column('id', sa.Integer()),
        sa.column('name', sa.String()))

    u2f = sa.table(
        'users_to_feeds',
        sa.column('user_id', sa.Integer()),
        sa.column('feed_id', sa.Integer()))

    values = sa.select(
        [u2f.c.user_id, u2f.c.feed_id, feed.c.name]
    ).select_from(
        u2f.join(feed, feed.c.id == u2f.c.feed_id)
    )

    op.execute(subsc.insert().from_select(
        ['user_id', 'feed_id', 'name'], values))

    op.drop_table('users_to_feeds')
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    u2f = op.create_table(
        'users_to_feeds',
        sa.Column('user_id', sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column('feed_id', sa.INTEGER(), autoincrement=False, nullable=True),
        sa.ForeignKeyConstraint(['feed_id'], ['feed.id'], name='users_to_feeds_feed_id_fkey'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], name='users_to_feeds_user_id_fkey')
    )

    subsc = sa.table(
        'subscription',
        sa.Column('user_id', sa.Integer()),
        sa.Column('feed_id', sa.Integer()),
    )

    op.execute(u2f.insert().from_select(
        ['user_id', 'feed_id'],
        sa.select([subsc.c.user_id, subsc.c.feed_id])))

    op.drop_table('subscription')
    ### end Alembic commands ###
