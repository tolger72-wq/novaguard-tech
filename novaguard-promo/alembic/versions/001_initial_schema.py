"""initial schema

Revision ID: 001
Revises:
Create Date: 2025-06-14 00:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('players',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('card_id', sa.String(64), nullable=False),
        sa.Column('name', sa.String(256), nullable=False),
        sa.Column('email', sa.String(256), nullable=True),
        sa.Column('phone', sa.String(32), nullable=True),
        sa.Column('crm_data', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('registered_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('card_id'),
    )

    op.create_table('ticket_formulas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(128), nullable=False, server_default='Varsayılan'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('live_tickets_per_hour', sa.Numeric(8, 2), nullable=False, server_default='1.0'),
        sa.Column('live_turnover_per_ticket', sa.Numeric(12, 2), nullable=False, server_default='500.0'),
        sa.Column('live_min_session_minutes', sa.Integer(), nullable=False, server_default='15'),
        sa.Column('live_rounds_per_hour', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('slot_tickets_per_hour', sa.Numeric(8, 2), nullable=False, server_default='0.5'),
        sa.Column('slot_turnover_per_ticket', sa.Numeric(12, 2), nullable=False, server_default='1000.0'),
        sa.Column('slot_min_session_minutes', sa.Integer(), nullable=False, server_default='15'),
        sa.Column('slot_rounds_per_hour', sa.Integer(), nullable=False, server_default='300'),
        sa.Column('max_tickets_per_day', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('max_tickets_per_session', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('max_pool_tickets', sa.Integer(), nullable=False, server_default='20'),
        sa.Column('consecutive_day_bonus_days', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('consecutive_day_bonus_tickets', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_by', sa.String(128), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('game_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('external_session_id', sa.String(128), nullable=True),
        sa.Column('card_id', sa.String(64), sa.ForeignKey('players.card_id'), nullable=False),
        sa.Column('game_type', sa.String(16), nullable=False),
        sa.Column('game_name', sa.String(128), nullable=True),
        sa.Column('table_id', sa.String(64), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_minutes', sa.Integer(), nullable=True),
        sa.Column('turnover_amount', sa.Numeric(14, 2), nullable=False, server_default='0'),
        sa.Column('average_bet', sa.Numeric(10, 2), nullable=True),
        sa.Column('currency', sa.String(8), nullable=False, server_default='GEL'),
        sa.Column('tickets_earned', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(16), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_game_sessions_external_id', 'game_sessions', ['external_session_id'])
    op.create_index('ix_game_sessions_card_id', 'game_sessions', ['card_id'])

    op.create_table('tickets',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('ticket_number', sa.String(32), nullable=False),
        sa.Column('card_id', sa.String(64), sa.ForeignKey('players.card_id'), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('game_sessions.id'), nullable=True),
        sa.Column('campaign_year', sa.Integer(), nullable=False),
        sa.Column('earned_date', sa.Date(), nullable=False),
        sa.Column('valid_for_tiers', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('used_in_draw_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ticket_number'),
    )
    op.create_index('ix_tickets_card_year', 'tickets', ['card_id', 'campaign_year'])
    op.create_index('ix_tickets_active', 'tickets', ['is_active', 'campaign_year'])

    op.create_table('draw_schedules',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('draw_tier', sa.String(16), nullable=False),
        sa.Column('name', sa.String(256), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('campaign_year', sa.Integer(), nullable=False),
        sa.Column('prize_amount', sa.Numeric(14, 2), nullable=False),
        sa.Column('prize_currency', sa.String(8), nullable=False, server_default='GEL'),
        sa.Column('prize_description', sa.String(512), nullable=False),
        sa.Column('annual_prize_options', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(16), nullable=False, server_default='scheduled'),
        sa.Column('created_by', sa.String(128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('tax_declaration_required', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('tax_declaration_ref', sa.String(128), nullable=True),
        sa.Column('tax_amount_paid', sa.Numeric(14, 2), nullable=True),
        sa.Column('tax_paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('tax_declared_by', sa.String(128), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_draw_schedules_tier', 'draw_schedules', ['draw_tier'])
    op.create_index('ix_draw_schedules_at', 'draw_schedules', ['scheduled_at'])

    op.create_table('draw_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('schedule_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('draw_schedules.id'), nullable=True, unique=True),
        sa.Column('winner_card_id', sa.String(64), sa.ForeignKey('players.card_id'), nullable=False),
        sa.Column('winning_ticket_number', sa.String(32), nullable=False),
        sa.Column('total_tickets_in_pool', sa.Integer(), nullable=False),
        sa.Column('total_players_in_pool', sa.Integer(), nullable=False),
        sa.Column('executed_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('executed_by', sa.String(128), nullable=True),
        sa.Column('draw_metadata', sa.JSON(), nullable=True),
        sa.Column('prize_distributed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('prize_distributed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('prize_distributed_by', sa.String(128), nullable=True),
        sa.Column('prize_notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('prize_wins',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('card_id', sa.String(64), sa.ForeignKey('players.card_id'), nullable=False),
        sa.Column('draw_tier', sa.String(16), nullable=False),
        sa.Column('draw_result_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('draw_results.id'), nullable=False),
        sa.Column('prize_amount', sa.Numeric(14, 2), nullable=False),
        sa.Column('prize_currency', sa.String(8), nullable=False, server_default='GEL'),
        sa.Column('prize_description', sa.String(512), nullable=True),
        sa.Column('campaign_year', sa.Integer(), nullable=False),
        sa.Column('won_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_prize_wins_card_year', 'prize_wins', ['card_id', 'campaign_year'])
    op.create_index('ix_prize_wins_won_at', 'prize_wins', ['won_at'])

    # Varsayılan formül kaydı
    op.execute("""
        INSERT INTO ticket_formulas (
            name, is_active,
            live_tickets_per_hour, live_turnover_per_ticket, live_min_session_minutes, live_rounds_per_hour,
            slot_tickets_per_hour, slot_turnover_per_ticket, slot_min_session_minutes, slot_rounds_per_hour,
            max_tickets_per_day, max_tickets_per_session, max_pool_tickets,
            consecutive_day_bonus_days, consecutive_day_bonus_tickets
        ) VALUES (
            'Varsayılan Formül', true,
            1.0, 500.0, 15, 30,
            0.5, 1000.0, 15, 300,
            10, 5, 20,
            3, 1
        )
    """)

    # ── Mini Bonus (Aktif Oyuncu Bonusu) ayar tablosu ──────────────────────────
    op.create_table('mini_bonus_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('prize_amount', sa.Numeric(10, 2), nullable=False, server_default='100.00'),
        sa.Column('prize_currency', sa.String(8), nullable=False, server_default='GEL'),
        sa.Column('interval_minutes', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('window_start_hour', sa.Integer(), nullable=False, server_default='14'),
        sa.Column('window_end_hour', sa.Integer(), nullable=False, server_default='6'),
        sa.Column('updated_by', sa.String(128), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )

    # Varsayılan mini bonus kaydı (kapalı halde başlar, admin panelden açılır)
    op.execute("""
        INSERT INTO mini_bonus_config (
            id, is_active, prize_amount, prize_currency,
            interval_minutes, window_start_hour, window_end_hour
        ) VALUES (
            1, false, 100.00, 'GEL', 30, 14, 6
        )
    """)


def downgrade() -> None:
    op.drop_table('mini_bonus_config')
    op.drop_table('prize_wins')
    op.drop_table('draw_results')
    op.drop_table('draw_schedules')
    op.drop_table('tickets')
    op.drop_table('game_sessions')
    op.drop_table('ticket_formulas')
    op.drop_table('players')
