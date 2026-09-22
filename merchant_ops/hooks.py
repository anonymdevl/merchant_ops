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

# Bundled so every build emits a content-hashed filename. Referenced by bundle
# name, not path: Frappe resolves it through assets.json. Plain /assets/ paths
# keep one URL forever, so a browser or proxy can serve a stale copy long after
# a deploy.
web_include_css = "portal.bundle.css"
web_include_js = "portal.bundle.js"

app_include_css = "hub.bundle.css"

fixtures = [
    {
        "dt": "Custom Field",
        "filters": [["dt", "=", "Customer"], ["module", "in", [None, "Merchant Operations"]]],
    },
    {
        "dt": "Property Setter",
        "filters": [["doc_type", "=", "Customer"]],
    },
]

after_install = "merchant_ops.install.after_install"
