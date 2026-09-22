# Merchant Operations (`merchant_ops`)

A Frappe application demonstrating merchant commercial-to-cash operations on ERPNext v16:
merchant master, revenue leakage detection, processor residual imports, a branded portal
login, and a purpose-built operations console.

Built by **Ultrasoft Systems**.

## What it demonstrates

| Area | What this app adds |
|---|---|
| **Merchant master** | `Customer` extended with MID, processor, account status, risk tier, go-live date and assigned agent — as Custom Fields shipped in the app, not doctype edits |
| **Revenue leakage** | `Revenue Exception` doctype: expected vs actual, computed variance, owner, aging, resolution trail |
| **Processor revenue** | `Processor Residual Import` doctype, which raises an exception automatically when a statement contains rows whose MID maps to no merchant |
| **Operations console** | A custom Frappe Page (`/app/merchant-hub`) with six KPI tiles and three panels, every one deep-linking into standard ERPNext doctypes and reports |
| **Portal branding** | `Merchant Portal Settings` single doctype driving the login page — logo, accent colour, tagline, background, support note |

## What it deliberately does not do

This is a demonstration of shape and judgement, not a finished platform.

- **No real integrations.** Residual imports are records, not parsers. Statement file formats vary per processor and each one is real work.
- **No billing engine.** Stock ERPNext `Subscription` is used as-is, which is exactly the point: it handles flat recurring and nothing else. Proration, tiering, mid-cycle changes and usage billing would require a custom engine emitting standard Sales Invoices.
- **No payment gateway.** Nothing here instructs a payment. In production that path needs idempotency keys, return-code-aware retry, and duplicate prevention — the one place in this system where a bug moves real money.
- **No leakage engine.** The exceptions are seeded records. The real control is a scheduled job walking approved price → contract → subscription → invoice → payment.
- **No PCI-scoped data.** By design. Payment profiles should hold processor vault tokens only.

## Design principles

**Zero ERPNext core modifications.** Custom Fields ship as fixtures, the Customer relabel is a Property Setter, and every new object lives in this app's own module. `bench update` stays a regression run rather than a re-implementation.

**Login branding through hooks, not template overrides.** Replacing `frappe/www/login.html` would be faster and would look identical today. It also breaks on the next upgrade. Branding is injected via `web_include_css` / `web_include_js` reading a guest-whitelisted settings endpoint.

**The console is ours; everything under it is standard.** The hub renders its own layout, but every tile routes into stock list views, forms and query reports. Standard invoices, standard ledger, standard permissions.

## Install

```bash
cd frappe-bench
cp -r /path/to/merchant_ops apps/merchant_ops     # or: bench get-app <git-url>
./env/bin/pip install -e apps/merchant_ops
bench --site <your-site> install-app merchant_ops
bench build --app merchant_ops
bench --site <your-site> migrate
bench --site <your-site> clear-cache
```

Then load sample data (demo sites only):

```bash
bench --site <your-site> execute merchant_ops.demo.load
```

Console at `/app/merchant-hub`. Branding at **Merchant Portal Settings**.

## Requirements

Frappe v15–v16, ERPNext v15–v16. Developed against ERPNext v16.32.

## Licence

MIT.
