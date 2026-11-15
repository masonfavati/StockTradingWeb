"""Manage offline SEC submissions.zip SIC metadata; no requests are made by this command."""

import argparse
from pathlib import Path

from app.market_data.sec_identity import SecIdentityError, load_reference
from app.market_data.sec_industry import (
    SecIndustryError,
    SicReference,
    import_industry_archive,
    import_industry_files,
    load_industry_reference,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("import", "import-files", "urls", "status"))
    parser.add_argument("--source", type=Path, action="append")
    parser.add_argument("--symbol", action="append", default=[])
    parser.add_argument("--dir", type=Path, default=Path.home() / "StockTradingWebResearch")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    result: SicReference | None
    try:
        if args.action == "urls":
            reference = load_reference(args.dir)
            if reference is None:
                parser.exit(2, "Import the ticker-to-CIK reference first (3E.5).\n")
            if not (1 <= len(args.symbol) <= 30):
                parser.error("urls requires 1–30 --symbol TICKER values")
            for symbol in args.symbol:
                matches = reference.entries.get(symbol, ())
                if len(matches) != 1:
                    print(f"{symbol}: unknown or ambiguous SEC CIK; cannot provide URL")
                else:
                    print(f"{symbol}: https://data.sec.gov/submissions/CIK{matches[0].cik}.json")
            return
        if args.action in ("import", "import-files"):
            if not args.source:
                parser.error("import requires --source FILE (repeat for import-files)")
            ticker = load_reference(args.dir)
            if ticker is None:
                parser.exit(2, "Import the ticker-to-CIK reference first (3E.5).\n")
            if args.action == "import":
                if len(args.source) != 1:
                    parser.error("bulk import requires exactly one --source ZIP")
                result = import_industry_archive(args.source[0], args.dir, ticker,
                                                 replace=args.replace)
            else:
                result = import_industry_files(args.source, args.dir, ticker,
                                               replace=args.replace)
        else:
            result = load_industry_reference(args.dir)
        if result is None:
            print("NO LOCAL SEC SIC REFERENCE: optional industry evidence cannot approve stock ideas.")
        else:
            print(f"SEC SIC FILER CATEGORIES: {len(result.entries):,} mapped CIKs")
            print(f"Imported at UTC: {result.imported_at_utc.isoformat()}")
            print(f"SEC source kind: {result.source_kind}")
            print(f"Source SHA-256: {result.source_sha256}")
            print(f"Pinned ticker reference SHA-256: {result.ticker_source_sha256}")
            print(f"Skipped oversized CIK members: {result.skipped_large_members}")
            print("Current filer SIC metadata only: NOT point-in-time industry or certified sector exposure.")
    except (SecIdentityError, SecIndustryError, OSError) as exc:
        parser.exit(2, f"SEC SIC reference unavailable: {exc}\n")


if __name__ == "__main__":
    main()
