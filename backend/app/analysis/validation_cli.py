"""Run a local, read-only historical scanner signal audit.

Usage: uv run python -m app.analysis.validation_cli --horizon 20 --top 1
"""

import argparse
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from app.analysis.signal_validation import SignalValidation, validate_signals
from app.db.session import SessionLocal
from app.market_data.history_client import DailyBar
from app.models.historical_bar import HistoricalBar


def _percentage(value: Decimal | None) -> str:
    return "N/A" if value is None else f"{value * 100:+.2f}%"


def print_report(result: SignalValidation) -> None:
    print("\nHISTORICAL SCANNER SIGNAL CHECK (RESEARCH ONLY)")
    print("=" * 57)
    print("Source: saved Alpaca SIP RAW daily bars; never today's adjusted history")
    print(f"Stocks saved: {result.tracked_symbols}")
    print(f"Distinct observed dates: {result.recorded_sessions}")
    print(f"Rule: existing scanner score, top {result.top_n}, hold {result.horizon} sessions")
    print(f"Assumed trading cost: {result.cost_bps_per_side} bps per side")
    print(f"Signal dates attempted: {result.attempted_signals}")
    print(f"No eligible candidate: {result.skipped_no_candidate}")
    print(f"Missing future entry/exit: {result.skipped_incomplete_outcomes}")
    print(f"Evaluated windows: {len(result.trials)}")
    print(f"Average selected net price change: {_percentage(result.average_selected_return)}")
    print(f"Average saved-universe net price change: {_percentage(result.average_universe_return)}")
    print(f"Selected positive windows: {result.positive_selected_trials}/{len(result.trials)}")
    print(f"Selected beat saved-universe baseline: {result.selected_beat_universe}/{len(result.trials)}")
    print("\nSIGNIFICANT LIMITATIONS")
    print("- This does NOT backtest all Alpaca securities: only stocks already saved locally.")
    print("- Today's saved symbols cause selection/survivorship bias, including missing delistings.")
    print("- Raw price changes omit dividends and can be distorted by splits/corporate actions.")
    print("- Costs are an assumption, not historical spreads or actual execution fills.")
    print("- Ranking rules have not been independently frozen, calibrated, or forward-tested.")
    print("- Average window changes are NOT compounded portfolio returns or probabilities.")
    print("- No actual trades, buy recommendations, or reliable profits are established.")
    if len(result.trials) < 30 or result.tracked_symbols < 100:
        print("\nINSUFFICIENT EVIDENCE for a validated market-wide strategy.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizon", type=int, default=20, help="Holding sessions, 1–252")
    parser.add_argument("--top", type=int, default=1, help="Top signals per date, 1–20")
    parser.add_argument("--cost-bps", default="10", help="Assumed cost per trade side")
    args = parser.parse_args()
    try:
        cost = Decimal(args.cost_bps)
    except InvalidOperation:
        parser.error("--cost-bps must be a valid decimal")
    with SessionLocal() as session:
        rows = session.scalars(
            select(HistoricalBar)
            .where(
                HistoricalBar.provider == "alpaca",
                HistoricalBar.feed == "sip",
                HistoricalBar.adjustment == "raw",
            )
            .order_by(HistoricalBar.symbol, HistoricalBar.session_date)
        ).all()
    if not rows:
        raise SystemExit("No raw SIP prices stored yet. Run history_import first.")
    bars = [
        DailyBar(
            symbol=row.symbol,
            session_date=row.session_date,
            bar_timestamp=row.bar_timestamp,
            open_price=row.open_price,
            high_price=row.high_price,
            low_price=row.low_price,
            close_price=row.close_price,
            volume=row.volume,
            trade_count=row.trade_count,
            vwap=row.vwap,
        )
        for row in rows
    ]
    try:
        results = validate_signals(
            bars,
            horizon=args.horizon,
            top_n=args.top,
            cost_bps_per_side=cost,
        )
    except ValueError as exc:
        raise SystemExit(f"Signal check stopped: {exc}") from None
    print_report(results)


if __name__ == "__main__":
    main()
