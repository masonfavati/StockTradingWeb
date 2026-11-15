"""Read-only offline reporting of the same prospective evidence used by the website."""

import argparse
import json
from pathlib import Path

from app.analysis.prospective_prediction import build_prediction_report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit prospective, point-in-time candidate features and future outcomes"
    )
    parser.add_argument("report", choices=["report"])
    parser.add_argument("--dir", type=Path, default=Path.home() / "StockTradingWebResearch")
    arguments = parser.parse_args()
    print(json.dumps(build_prediction_report(arguments.dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
