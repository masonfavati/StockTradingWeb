"""Manually import a free SEC ticker/CIK/exchange reference; no network access."""

import argparse
from pathlib import Path

from app.market_data.sec_identity import (
    SecIdentityError,
    SecReference,
    install_reference,
    load_reference,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("import", "status"))
    parser.add_argument("--dir", type=Path, default=Path.home() / "StockTradingWebResearch")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    reference: SecReference | None
    try:
        if args.action == "import":
            if args.source is None:
                parser.error("import requires --source SEC_JSON_FILE")
            reference = install_reference(args.source, args.dir, replace=args.replace)
        else:
            reference = load_reference(args.dir)
        if reference is None:
            print("NO LOCAL SEC REFERENCE: optional issuer cross-check will retain stock slices as cash.")
        else:
            ambiguous = sum(len(rows) != 1 for rows in reference.entries.values())
            print(f"SEC TICKER–CIK CROSS-REFERENCE: {len(reference.entries):,} supported tickers")
            print(f"Ambiguous ticker entries (fail closed): {ambiguous:,}")
            print(f"Imported at UTC: {reference.imported_at_utc.isoformat()}")
            print(f"SEC source SHA-256: {reference.source_sha256}")
            print("Filer ID only: NOT verified common shares, industry, sector, or point-in-time status.")
    except (OSError, SecIdentityError) as exc:
        parser.exit(2, f"SEC reference unavailable: {exc}\n")


if __name__ == "__main__":
    main()
