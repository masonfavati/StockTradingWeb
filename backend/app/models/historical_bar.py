"""Provider-labelled raw daily equity bars, not an investment forecast."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HistoricalBar(Base):
    __tablename__ = "historical_bars"

    __table_args__ = (
        CheckConstraint(
            "open_price > 0 AND high_price > 0 AND low_price > 0 AND close_price > 0",
            name="ck_historical_bars_prices_positive",
        ),
        CheckConstraint(
            "high_price >= low_price AND "
            "high_price >= open_price AND high_price >= close_price AND "
            "low_price <= open_price AND low_price <= close_price",
            name="ck_historical_bars_ohlc_consistent",
        ),
        CheckConstraint("volume >= 0", name="ck_historical_bars_volume_nonnegative"),
    )

    # Natural primary key makes importing the same day twice idempotent.
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    session_date: Mapped[date] = mapped_column(Date, primary_key=True)
    feed: Mapped[str] = mapped_column(String(12), primary_key=True)
    adjustment: Mapped[str] = mapped_column(String(12), primary_key=True)

    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    bar_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    high_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    low_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    close_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    trade_count: Mapped[int | None] = mapped_column(BigInteger)
    vwap: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
