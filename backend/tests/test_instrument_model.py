import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.instrument import Instrument


def test_instrument_can_be_stored_and_retrieved() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            Instrument(
                symbol="TEST",
                name="Example Corporation",
                asset_type="stock",
                currency="USD",
            )
        )
        session.commit()

        result = session.scalar(
            select(Instrument).where(Instrument.symbol == "TEST")
        )

        assert result is not None
        assert result.name == "Example Corporation"
        assert result.asset_type == "stock"

    engine.dispose()


def test_duplicate_symbols_are_rejected() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add_all(
            [
                Instrument(
                    symbol="TEST",
                    name="First Company",
                    asset_type="stock",
                ),
                Instrument(
                    symbol="TEST",
                    name="Second Company",
                    asset_type="stock",
                ),
            ]
        )

        with pytest.raises(IntegrityError):
            session.commit()

        session.rollback()

    engine.dispose()
