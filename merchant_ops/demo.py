"""Sample data for demonstration instances.

    bench --site <site> execute merchant_ops.demo.load
    bench --site <site> execute merchant_ops.detect.run

The first loads merchants and imports the shipped statement files. The second
runs the leakage sweep, which is what fills the exception queue.

Idempotent. Not for production sites.
"""

import os
import random

import frappe
from frappe.utils import add_days, nowdate
from frappe.utils.file_manager import save_file

MERCHANTS = [
    ("Northside Coffee Group", "MID-884201", "Fiserv", "Active", "Standard"),
    ("Delgado Auto Service", "MID-884377", "TSYS", "Past Due", "Elevated"),
    ("Harbour Point Dental", "MID-884512", "Elavon", "Active", "Low"),
    ("Vela Fitness Studios", "MID-884630", "Fiserv", "Restricted", "Elevated"),
    ("Kestrel Hardware Co", "MID-884711", "North", "Active", "Standard"),
    ("Brightline Pet Clinic", "MID-884890", "TSYS", "Active", "Low"),
]

# Statement files shipped with the app. Totals are not listed here on purpose:
# they come out of the parser, which is the point of the exercise.
STATEMENTS = [
    ("Fiserv", "2026-08", "fiserv-2026-08-residual.csv"),
    ("TSYS", "2026-08", "tsys-2026-08-residual.csv"),
    ("Elavon", "2026-08", "elavon-2026-08-residual.csv"),
]


def load():
    _merchants()
    _statements()
    frappe.db.commit()
    print("Demo data loaded. Run merchant_ops.detect.run to populate the exception queue.")


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


def _statements():
    """Attaches each shipped statement file and lets the import parse it.

    Nothing is typed in. Row counts, unmapped counts and residual totals on the
    resulting documents are whatever the parser produced from the file, so the
    demo can be re-run against an edited statement and the figures follow.
    """
    for processor, period, filename in STATEMENTS:
        if frappe.db.exists("Processor Residual Import",
                            {"processor": processor, "statement_period": period}):
            continue

        source = os.path.join(os.path.dirname(__file__), "public", "samples", filename)
        with open(source, "rb") as handle:
            content = handle.read()

        doc = frappe.get_doc({
            "doctype": "Processor Residual Import",
            "processor": processor,
            "statement_period": period,
            "status": "Imported",
        }).insert(ignore_permissions=True)

        attachment = save_file(filename, content, doc.doctype, doc.name, is_private=1)
        doc.statement_file = attachment.file_url
        doc.save(ignore_permissions=True)

        print(f"  {processor} {period}: {doc.rows_imported} row(s), "
              f"{doc.rows_unmapped} unmapped, net {doc.net_residual:,.2f}")


def _first(doctype, filters):
    rows = frappe.get_all(doctype, filters=filters, pluck="name", limit=1)
    return rows[0] if rows else None
