"""The desk sidebar for Merchant Operations.

Frappe v16 moved the sidebar out of the Workspace document. A Workspace's
`shortcuts` table now drives only the cards in the page body; the left rail is a
separate `Workspace Sidebar` document whose `items` carry their own icons. When
a workspace is first created Frappe generates a matching sidebar from the
shortcuts, and that generation does not copy the icons across — which is why a
workspace with nine distinctly-iconed shortcuts renders nine identical rows.

Two conventions taken from ERPNext's own sidebars rather than invented here:

    Icons belong on top-level items and on section breaks. Rows nested under a
    section (`child: 1`) carry no icon, because a column of icons at two
    indents reads as noise.

    `route_options` turns one doctype into several destinations. Credit Note in
    the stock Invoicing sidebar is Sales Invoice with {"is_return": 1}; the same
    mechanism gives us Past Due, Restricted and Failed Collections without a
    report or a custom page behind any of them.

    bench --site <site> execute merchant_ops.sidebar.build
"""

import json

import frappe

SIDEBAR = "Merchant Ops"

# type, label, link_type, link_to, icon, child, route_options
ITEMS = [
    ("Link", "Home", "Workspace", "Merchant Ops", "home", 0, None),
    ("Link", "Operations Console", "Page", "merchant-hub", "chart", 0, None),

    ("Section Break", "Merchants", None, None, "customer", 0, None),
    ("Link", "All Merchants", "DocType", "Customer", None, 1, None),
    ("Link", "Past Due", "DocType", "Customer", None, 1, {"account_status": "Past Due"}),
    ("Link", "Restricted", "DocType", "Customer", None, 1, {"account_status": "Restricted"}),

    ("Section Break", "Billing & Collections", None, None, "accounting", 0, None),
    ("Link", "Sales Invoices", "DocType", "Sales Invoice", None, 1, None),
    ("Link", "Overdue", "DocType", "Sales Invoice", None, 1, {"status": "Overdue"}),
    ("Link", "Subscriptions", "DocType", "Merchant Subscription", None, 1, None),
    ("Link", "Billing Plans", "DocType", "Merchant Billing Plan", None, 1, None),
    ("Link", "Usage", "DocType", "Merchant Usage", None, 1, None),
    ("Link", "Payment Attempts", "DocType", "Payment Attempt", None, 1, None),
    ("Link", "Failed Collections", "DocType", "Payment Attempt", None, 1, {"status": "Failed"}),
    ("Link", "Dunning", "DocType", "Dunning", None, 1, None),

    ("Section Break", "Processor Revenue", None, None, "money-coins-1", 0, None),
    ("Link", "Residual Imports", "DocType", "Processor Residual Import", None, 1, None),
    ("Link", "Partially Mapped", "DocType", "Processor Residual Import", None, 1,
     {"status": "Partially Mapped"}),
    ("Link", "Deposits", "DocType", "Merchant Deposit", None, 1, None),
    ("Link", "Unreconciled", "DocType", "Merchant Deposit", None, 1, {"status": "Variance"}),

    ("Section Break", "Controls", None, None, "sheet", 0, None),
    ("Link", "Revenue Exceptions", "DocType", "Revenue Exception", None, 1, None),
    ("Link", "Open Exceptions", "DocType", "Revenue Exception", None, 1, {"status": "Open"}),
    ("Link", "Approved Pricing", "DocType", "Item Price", None, 1, {"approval_status": "Approved"}),
    ("Link", "Gateway Log", "DocType", "Gateway Request Log", None, 1, None),

    ("Section Break", "Reports", None, None, "table", 0, None),
    ("Link", "Accounts Receivable", "Report", "Accounts Receivable", None, 1, None),
    ("Link", "AR Summary", "Report", "Accounts Receivable Summary", None, 1, None),

    ("Section Break", "Settings", None, None, "settings", 0, None),
    ("Link", "Login Page", "DocType", "Merchant Portal Settings", None, 1, None),
    ("Link", "Gateway", "DocType", "Gateway Settings", None, 1, None),
]


def build():
    """Rewrites the sidebar from the list above.

    The rows are replaced rather than merged. Frappe regenerates this document
    whenever the workspace changes, so anything additive would accumulate
    duplicates over a few migrations.
    """
    doc = (
        frappe.get_doc("Workspace Sidebar", SIDEBAR)
        if frappe.db.exists("Workspace Sidebar", SIDEBAR)
        else frappe.new_doc("Workspace Sidebar")
    )

    doc.title = SIDEBAR
    doc.module = "Merchant Operations"
    doc.header_icon = "card"
    doc.set("items", [])

    for kind, label, link_type, link_to, icon, child, route in ITEMS:
        if link_type == "DocType" and not frappe.db.exists("DocType", link_to):
            continue
        if link_type == "Report" and not frappe.db.exists("Report", link_to):
            continue

        doc.append("items", {
            "type": kind,
            "label": label,
            "link_type": link_type or "DocType",
            "link_to": link_to,
            "icon": icon or "",
            "child": child,
            "indent": 1 if kind == "Section Break" else 0,
            "collapsible": 1,
            "route_options": json.dumps(route) if route else None,
        })

    doc.save(ignore_permissions=True)
    frappe.clear_cache()
    frappe.db.commit()
    print(f"Sidebar rebuilt with {len(doc.items)} item(s).")
    return doc.name
