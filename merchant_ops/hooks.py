app_name = "merchant_ops"
app_title = "Merchant Operations"
app_publisher = "Ultrasoft Systems"
app_description = "Merchant commercial-to-cash operations on ERPNext"
app_email = "michael@ultrasoftsystems.com"
app_license = "mit"

required_apps = ["frappe/erpnext"]

# Surface the console on the /apps screen (Frappe v15+).
add_to_apps_screen = [
    {
        "name": "merchant_ops",
        "logo": "/assets/merchant_ops/img/logo.svg",
        "title": "Merchant Operations",
        "route": "/app/merchant-hub",
    }
]

# ---------------------------------------------------------------------------
# Portal branding.
#
# Deliberately applied through hooks and injected assets rather than by
# overriding frappe/www/login.html. A template override would look identical
# today and break on the next upgrade, which defeats the purpose of shipping
# customisation in a separate app at all.
# ---------------------------------------------------------------------------
web_include_css = "/assets/merchant_ops/css/portal.css"
web_include_js = "/assets/merchant_ops/js/portal.js"

app_include_css = "/assets/merchant_ops/css/hub.css"

# Records that travel with the app.
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
