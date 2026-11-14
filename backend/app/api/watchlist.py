import re
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.market_data.assets import (
    AlpacaAssetLookup,
    AssetConfigurationError,
    AssetLookupError,
    AssetNotFoundError,
    get_asset_lookup,
)
from app.models.watchlist import WatchlistEntry

router = APIRouter(prefix="/api/watchlist", tags=["Watchlist"])


class WatchlistCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        symbol = value.strip().upper()

        if re.fullmatch(r"[A-Z][A-Z0-9.-]{0,19}", symbol) is None:
            raise ValueError("Enter a valid stock ticker symbol.")

        return symbol


class WatchlistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    name: str
    tradable: bool | None
    added_at: datetime


@router.get("", response_model=list[WatchlistOut])
def list_watchlist(
    db: Annotated[Session, Depends(get_db)],
) -> list[WatchlistEntry]:
    return list(
        db.scalars(
            select(WatchlistEntry).order_by(WatchlistEntry.symbol)
        ).all()
    )


@router.post(
    "",
    response_model=WatchlistOut,
    status_code=status.HTTP_201_CREATED,
)
def add_to_watchlist(
    payload: WatchlistCreate,
    db: Annotated[Session, Depends(get_db)],
    lookup: Annotated[AlpacaAssetLookup, Depends(get_asset_lookup)],
) -> WatchlistEntry:
    existing = db.scalar(
        select(WatchlistEntry).where(
            WatchlistEntry.symbol == payload.symbol
        )
    )

    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="This stock is already on your watchlist.",
        )

    try:
        asset = lookup.get(payload.symbol)

    except AssetNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except AssetConfigurationError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    except AssetLookupError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    entry = WatchlistEntry(
        symbol=asset.symbol,
        name=asset.name,
        tradable=asset.tradable,
    )

    db.add(entry)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This stock is already on your watchlist.",
        ) from exc

    db.refresh(entry)
    return entry


@router.delete("/{symbol}", status_code=204)
def remove_from_watchlist(
    symbol: str,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    normalized = symbol.strip().upper()

    entry = db.scalar(
        select(WatchlistEntry).where(
            WatchlistEntry.symbol == normalized
        )
    )

    if entry is None:
        raise HTTPException(
            status_code=404,
            detail="This stock is not on your watchlist.",
        )

    db.delete(entry)
    db.commit()

    return Response(status_code=204)
