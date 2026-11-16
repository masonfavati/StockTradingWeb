# 3J — Explain stock history in everyday language

## Goal

Make the app useful to people who have never bought a share or learned market terminology. Keep the real-source provenance and safety limits intact.

## Historical chart insight calculations

The existing single, bounded historical request provides daily, split/dividend/spin-off-adjusted closes. The 3J summary uses **only observations displayed in the chart**:

- Highest and lowest adjusted close and their actual dates.
- Largest observed percentage decline from a preceding high to a later low (not a maximum future loss).
- Mean of absolute percentage differences between consecutive *available observations* (not an estimated future volatility; missing sessions may increase the gap).
- Number of positive, negative, and zero differences between observed dates.
- When the SPY comparison has at least two aligned sessions: SPY's first-to-last price change and the stock-minus-SPY change in percentage points. If unavailable, neither is fabricated.

High/low symbols are shown on the price chart. Historical prices are retrospective corporate-action-adjusted values, not executable prices or model training labels. The 3F model only estimates relative SPY outperformance over 20 sessions, not a price trajectory, so 3J does not draw a future-price line.

## Beginner experience

New `/start` route links to stock lookup, price history, market search, and educational budget examples. Shared definitions explain stock, ticker, fund, SPY, cash, adjusted prices, price changes, big drops, similar historical movements, SEC identity/industry records, the experimental prediction and what-if losses. Native HTML `<details>` lets users choose how much detail to read, including keyboard navigation.

Existing page controls, URL paths, and backend API settings remain compatible. Default copy stresses: watching a stock is not buying; historical screening is not future prediction; SPY outperformance can still mean an absolute loss; illustrative budget values do not execute trades; withheld experimental money stays as cash.

## Scope limits

This is an interface and retrospective descriptive analysis milestone, **not** a new price-prediction model, calibrated investment recommendation, financial adviser, or trading feature. Do not imply that a high past return indicates a higher chance of success. New data is drawn from the existing price-history API and does not create an extra paid dependency.
