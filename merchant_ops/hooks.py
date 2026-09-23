app_name = "merchant_ops"
app_title = "Merchant Operations"
app_publisher = "Ultrasoft Systems"
app_description = "Merchant commercial-to-cash operations on ERPNext"
app_email = "michael@powersoftsystem.com"
app_license = "mit"

required_apps = ["frappe/erpnext"]

# Frappe v15+
add_to_apps_screen = [
    {
        "name": "merchant_ops",
        "logo": "/assets/merchant_ops/img/logo-app.svg",
        "title": "Merchant Operations",
        "route": "/app/merchant-hub",
    }
]

# Frappe's own bundles carry a content hash in the filename, so a new build is
# a new URL. Ours are referenced by plain path and the URL never changes when
# the contents do, which leaves a browser free to serve a stale copy through
# repeated hard reloads. The query string is the version the browser sees.
#
# Referencing these by bundle name instead does not work: bundled_asset() only
# consults assets.json for names containing ".bundle." that do NOT start with
# /assets, and an unresolved name falls through to abs_url() and is requested
# from the site root, where it 404s.
#
# Defined above every use. A forward reference here raises NameError on import,
# and hooks.py is imported on every request.
#
# BUMP THIS whenever portal.css, portal.js or hub.css changes.
ASSET_VERSION = "18"

web_include_css = f"/assets/merchant_ops/css/portal.css?v={ASSET_VERSION}"
web_include_js = f"/assets/merchant_ops/js/portal.js?v={ASSET_VERSION}"

app_include_css = f"/assets/merchant_ops/css/hub.css?v={ASSET_VERSION}"

fixtures = [
    {
        "dt": "Custom Field",
        "filters": [["dt", "in", ["Customer", "Item Price", "Sales Invoice"]],
                    ["module", "in", [None, "Merchant Operations"]]],
    },
    {
        "dt": "Property Setter",
        "filters": [["doc_type", "=", "Customer"]],
    },
]

after_install = "merchant_ops.install.after_install"
after_migrate = "merchant_ops.install.after_migrate"

# What runs unattended, and what it is allowed to do.
#
# The detector is read-only against ERPNext documents: it compares layers and
# records what disagrees, and never amends an invoice, a payment or a ledger
# entry. The collection jobs do write — a Payment Attempt, a Dunning — but they
# stop short of the two consequential acts. They never move money (the gateway
# does that, on an instruction carrying an idempotency key) and they never
# restrict a merchant; restriction is proposed as an exception and a person
# decides. Everything here re-runs safely: each job checks for its own prior
# output before creating anything.
scheduler_events = {
    "daily": [
        # Billing first: an invoice raised this morning is what AutoPay
        # presents against, and what the ladder ages from.
        "merchant_ops.billing.run",
        # Present debits that have come due, then move overdue invoices up the
        # ladder. Order matters: a collection that succeeds this morning should
        # not also receive a dunning notice this afternoon.
        "merchant_ops.collections.run_autopay",
        "merchant_ops.collections.run_retries",
        "merchant_ops.collections.escalate_dunning",
    ],
    "daily_long": [
        "merchant_ops.detect.run",
    ],
}

doc_events = {
    "Item Price": {
        "validate": "merchant_ops.install.stamp_approval",
    },
}
