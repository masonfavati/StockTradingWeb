from fastapi import FastAPI

app = FastAPI(
    title="StockTradingWeb API",
    description="Financial market analysis and portfolio tracking API",
    version="0.1.0",
)


@app.get("/api/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
