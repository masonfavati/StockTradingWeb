/** Display an amount in dollars without changing the underlying ledger value. */
export const currency = (amount: number | string): string =>
  `$${Number(amount).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
