"""Create wallet tables and immutable ledger trigger.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), server_default="customer", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('customer', 'admin')", name="ck_users_role"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "price_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("buy_price_dzd_per_gram", sa.Numeric(18, 4), nullable=False),
        sa.Column("sell_price_dzd_per_gram", sa.Numeric(18, 4), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_type", sa.String(length=16), nullable=False),
        sa.Column("grams", sa.Numeric(18, 4), nullable=False),
        sa.Column("price_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("entry_type IN ('buy', 'sell', 'adjustment')", name="ck_ledger_entries_entry_type"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_ledger_entries_user_id_users"),
        sa.ForeignKeyConstraint(["price_snapshot_id"], ["price_snapshots.id"], name="fk_ledger_entries_price_snapshot_id_price_snapshots"),
        sa.UniqueConstraint("idempotency_key", name="uq_ledger_entries_idempotency_key"),
    )
    op.create_table(
        "inventory",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("grams", sa.Numeric(18, 4), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute(
        """CREATE FUNCTION prevent_ledger_entries_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'ledger_entries are immutable';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """CREATE TRIGGER ledger_entries_immutable
        BEFORE UPDATE OR DELETE ON ledger_entries
        FOR EACH ROW EXECUTE FUNCTION prevent_ledger_entries_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS ledger_entries_immutable ON ledger_entries")
    op.execute("DROP FUNCTION IF EXISTS prevent_ledger_entries_mutation()")
    op.drop_table("inventory")
    op.drop_table("ledger_entries")
    op.drop_table("price_snapshots")
    op.drop_table("users")
