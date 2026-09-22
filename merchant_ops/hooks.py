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

# Portal branding. See public/css/portal.css.
web_include_css = "/assets/merchant_ops/css/portal.css"
web_include_js = "/assets/merchant_ops/js/portal.js"

app_include_css = "/assets/merchant_ops/css/hub.css"

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
