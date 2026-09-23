# Merchant Operations

A Frappe application for merchant commercial-to-cash operations on ERPNext v16:
merchant master data, revenue leakage detection, processor residual imports, a
branded portal login, and an operations console.

Built on ERPNext v16.32. Requires Frappe and ERPNext v15 or v16.

## Install

```bash
cd frappe-bench
bench get-app https://github.com/<you>/merchant_ops.git
bench --site <site> install-app merchant_ops
bench build --app merchant_ops
bench --site <site> migrate
```

Sample data, for demonstration sites only:

```bash
bench --site <site> execute merchant_ops.demo.load
```

## What it adds

**Doctypes**

| | |
|---|---|
| `Revenue Exception` | Expected against actual, with computed variance, assignee, aging and resolution trail |
| `Processor Residual Import` | Statement ingestion metadata. Raises a Revenue Exception when rows carry a MID that maps to no merchant |
| `Merchant Portal Settings` | Brand, colour, layout and copy for the login page |
| `Merchant Portal Stat` | Child table for the login stat strip |

**Customer** is extended with MID, processor, account status, risk tier,
go-live date and assigned agent. These install as Custom Fields, not edits to
the shipped doctype.

**Operations console** at `/app/merchant-hub`. Six KPI tiles, the largest open
exceptions, unmapped residual imports, and an account watchlist. Tiles and rows
route into standard list views, forms and query reports. `api.hub_summary`
serves the whole page in one call.

**Portal login** in three layouts — split, split with brand right, and centred —
configured from Merchant Portal Settings. Applied through `web_include_css` and
`web_include_js`; `www/login.html` is not overridden.

The only new DOM is `.mo-brand-panel`, a sibling inserted at the top of
`.page_content` that contains no form control. Frappe renders one section at a
time, so the visible section — login, signup, forgot or email link — becomes
the pane beside the panel on its own. Nothing is moved and no credential is
touched, so authentication behaviour is untouched by any layout, and a class
renamed in a future Frappe degrades the page to Frappe's stock layout rather
than breaking it.

Brand colours are cached in `localStorage` and applied before the network
answers, so a return visit is branded without a flash.

Assets are referenced by plain `/assets/` path with a `?v=` suffix from
`ASSET_VERSION` in `hooks.py`. Frappe's own bundles carry a content hash, so a
new build is a new URL; these do not, and without the query string a browser
will serve a stale copy through repeated hard reloads. **Bump `ASSET_VERSION`
whenever `portal.css`, `portal.js` or `hub.css` changes.**

## Scope

A demonstration of structure, not a finished platform. Deliberately absent:

- **Statement parsers.** Residual imports are records. Formats differ by
  processor and each needs its own parser.
- **Billing engine.** Stock `Subscription` is used as shipped, which covers flat
  recurring only. Proration, tiered pricing, mid-cycle changes and usage billing
  would need a custom engine emitting standard Sales Invoices.
- **Payment gateway.** Nothing here instructs a payment. That path needs
  idempotency keys, return-code-aware retry and duplicate prevention.
- **Leakage engine.** Exceptions are seeded. The control is a scheduled job
  comparing approved price, contract, subscription, invoice and payment.
- **Payment profiles.** Omitted rather than stubbed — they should hold processor
  vault tokens only, and a placeholder implementation invites the wrong one.

## Notes

All customisation lives in this app. ERPNext core is unmodified: custom fields
ship as fixtures, the Customer relabel is a Property Setter, and new objects sit
in the app's own module. Upgrades remain a regression run.

Text placed on brand colours is resolved server-side from WCAG relative
luminance rather than picked by hand.

## Brand assets

`merchant_ops/public/img/` — horizontal lockup, reversed lockup, mark and app
tile, in SVG and PNG. Palette: `#0E2A38` ink, `#2E86AB` accent, `#6B7A85` muted.

## Maintainer

Ultrasoft Systems — Michael Appiah
<michael@powersoftsystem.com> · <kubiappiahmichael@gmail.com>

## Licence

MIT. See `license.txt`.
