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
ASSET_VERSION = "11"

web_include_css = f"/assets/merchant_ops/css/portal.css?v={ASSET_VERSION}"
web_include_js = f"/assets/merchant_ops/js/portal.js?v={ASSET_VERSION}"

app_include_css = f"/assets/merchant_ops/css/hub.css?v={ASSET_VERSION}"

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
