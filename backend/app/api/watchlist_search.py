"""Read-only company-name lookup, powered by the free Alpaca asset list."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.market_data.asset_search import (
    AlpacaAssetCatalog,
    AssetSearchUnavailable,
    get_asset_catalog,
)

router = APIRouter(prefix="/api/watchlist", tags=["Watchlist"])


class CompanySearchResult(BaseModel):
    symbol: str
    name: str
    tradable: bool


@router.get("/search", response_model=list[CompanySearchResult])
def search_companies(
    q: Annotated[str, Query(min_length=2, max_length=80)],
    catalog: Annotated[AlpacaAssetCatalog, Depends(get_asset_catalog)],
) -> list[CompanySearchResult]:
    if len(q.strip()) < 2:
        raise HTTPException(status_code=422, detail="Enter at least two characters.")
    try:
        return [CompanySearchResult.model_validate(row, from_attributes=True)
                for row in catalog.search(q)]
    except AssetSearchUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
