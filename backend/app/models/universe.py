"""Recorded Alpaca asset-directory snapshots, captured from *now* onward.

A snapshot is an observation at captured_at, not retroactive evidence that a
symbol was listed, tradable, or available on earlier historical dates.
"""

from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UniverseCapture(Base):
    __tablename__ = "universe_captures"
    __table_args__ = (
        CheckConstraint("asset_count > 0", name="ck_universe_captures_count_positive"),
    )

    captured_on: Mapped[date] = mapped_column(Date, primary_key=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_count: Mapped[int] = mapped_column(Integer, nullable=False)


class UniverseAsset(Base):
    __tablename__ = "universe_assets"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'inactive')", name="ck_universe_assets_status"),
    )

    captured_on: Mapped[date] = mapped_column(
        Date, ForeignKey("universe_captures.captured_on", ondelete="CASCADE"), primary_key=True
    )
    alpaca_asset_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    tradable: Mapped[bool] = mapped_column(Boolean, nullable=False)
