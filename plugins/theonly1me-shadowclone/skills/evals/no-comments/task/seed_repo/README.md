# ledger

A small subscription billing library. All money is integer cents.

Run the tests with `python -m pytest`.

- `ledger/models.py`: plain dataclasses
- `ledger/storage.py`: in-memory store
- `ledger/invoices.py`: builds an invoice for one billing period
- `ledger/billing.py`: `BillingService`, the public entry point
