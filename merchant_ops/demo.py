"""Sample data for demonstration instances.

    bench --site <site> execute merchant_ops.demo.load

Idempotent. Not for production sites.
"""

import random

import frappe
from frappe.utils import add_days, nowdate

MERCHANTS = [
    ("Northside Coffee Group", "MID-884201", "Fiserv", "Active", "Standard"),
    ("Delgado Auto Service", "MID-884377", "TSYS", "Past Due", "Elevated"),
    ("Harbour Point Dental", "MID-884512", "Elavon", "Active", "Low"),
    ("Vela Fitness Studios", "MID-884630", "Fiserv", "Restricted", "Elevated"),
    ("Kestrel Hardware Co", "MID-884711", "North", "Active", "Standard"),
    ("Brightline Pet Clinic", "MID-884890", "TSYS", "Active", "Low"),
]

EXCEPTIONS = [
    ("Northside Coffee Group", "Rate Mismatch", 6200.00, 2000.00, -152,
     "Contracted gateway rate $49.00, billed $34.00 since March. Five cycles unbilled."),
    ("Kestrel Hardware Co", "Unbilled Subscription", 149.85, 0.00, -38,
     "Terminal rental active since go-live, never added to the billing schedule."),
    ("Delgado Auto Service", "Missing Residual", 312.40, 0.00, -14,
     "No TSYS residual line for this MID in the August statement."),
    ("Vela Fitness Studios", "Rate Mismatch", 224.70, 149.70, -63,
     "Chargeback handling billed at the old rate after the March amendment."),
    ("Harbour Point Dental", "Underbilled", 89.95, 74.95, -21,
     "PCI compliance fee omitted from the August run."),
]

IMPORTS = [
    ("Fiserv", "2026-08", 4182, 0, 18422.65, "Imported"),
    ("TSYS", "2026-08", 2910, 7, 11038.20, "Partially Mapped"),
    ("Elavon", "2026-08", 1344, 0, 6721.40, "Imported"),
]


def load():
    _merchants()
    _exceptions()
    _imports()
    frappe.db.commit()
    print("Demo data loaded.")


def _merchants():
    group = _first("Customer Group", {"is_group": 0}) or "All Customer Groups"
    territory = _first("Territory", {"is_group": 0}) or "All Territories"

    for name, mid, processor, status, tier in MERCHANTS:
        if frappe.db.exists("Customer", name):
            continue
        frappe.get_doc({
            "doctype": "Customer",
            "customer_name": name,
            "customer_group": group,
            "territory": territory,
            "customer_type": "Company",
            "merchant_id": mid,
            "processor": processor,
            "account_status": status,
            "risk_tier": tier,
            "go_live_date": add_days(nowdate(), -random.randint(120, 900)),
        }).insert(ignore_permissions=True)


def _exceptions():
    if frappe.db.count("Revenue Exception"):
        return
    for merchant, kind, expected, actual, age, detail in EXCEPTIONS:
        frappe.get_doc({
            "doctype": "Revenue Exception",
            "merchant": merchant,
            "exception_type": kind,
            "expected_amount": expected,
            "actual_amount": actual,
            "detected_on": add_days(nowdate(), age),
            "status": "Open",
            "detail": detail,
        }).insert(ignore_permissions=True)


def _imports():
    for processor, period, rows, unmapped, gross, status in IMPORTS:
        if frappe.db.exists("Processor Residual Import",
                            {"processor": processor, "statement_period": period}):
            continue
        frappe.get_doc({
            "doctype": "Processor Residual Import",
            "processor": processor,
            "statement_period": period,
            "rows_imported": rows,
            "rows_unmapped": unmapped,
            "gross_residual": gross,
            "net_residual": gross * 0.92,
            "status": status,
        }).insert(ignore_permissions=True)


def _first(doctype, filters):
    rows = frappe.get_all(doctype, filters=filters, pluck="name", limit=1)
    return rows[0] if rows else None
