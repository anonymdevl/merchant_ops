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
from frappe.utils import add_days, flt, nowdate
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
    _deposits()
    _collection_history()
    frappe.db.commit()
    print("Demo data loaded. Run merchant_ops.detect.run to populate the exception queue.")


def _deposits():
    """Two deposits: one that ties out, one that does not.

    The clean one proves the match works. The short one is the interesting
    document — the processor paid 340.00 less than its own statement says,
    which is the case a finance team finds three days into a month-end.
    """
    if frappe.db.count("Merchant Deposit"):
        return

    fiserv = frappe.db.get_value("Processor Residual Import",
                                 {"processor": "Fiserv", "statement_period": "2026-08"},
                                 ["name", "net_residual"], as_dict=True)
    tsys = frappe.db.get_value("Processor Residual Import",
                               {"processor": "TSYS", "statement_period": "2026-08"},
                               ["name", "net_residual"], as_dict=True)
    if not (fiserv and tsys):
        return

    for processor, source, shortfall, reference in [
        ("Fiserv", fiserv, 0.00, "ACH-88412-0908"),
        ("TSYS", tsys, 340.00, "ACH-90117-0911"),
    ]:
        allocated = flt(source.net_residual) - shortfall
        doc = frappe.get_doc({
            "doctype": "Merchant Deposit",
            "processor": processor,
            "deposit_date": add_days(nowdate(), -12),
            "bank_reference": reference,
            "deposit_amount": allocated,
            "allocations": [{"residual_import": source.name, "allocated_amount": allocated}],
        })
        doc.insert(ignore_permissions=True)
        print(f"  {processor} deposit {doc.name}: {doc.status}")


def _collection_history():
    """Three failed collections, one per return-code family.

    R01 is retriable and produces a scheduled re-presentment. R02 and R07 are
    not, and each raises an exception instead. Side by side they demonstrate
    that the platform reads the code rather than looping.
    """
    if frappe.db.count("Payment Attempt"):
        return

    invoices = frappe.get_all(
        "Sales Invoice",
        filters={"docstatus": 1, "outstanding_amount": [">", 0]},
        fields=["name", "customer", "outstanding_amount", "currency"],
        order_by="due_date asc", limit=3,
    )

    for invoice, code in zip(invoices, ["R01", "R02", "R07"]):
        attempt = frappe.get_doc({
            "doctype": "Payment Attempt",
            "merchant": invoice.customer,
            "sales_invoice": invoice.name,
            "status": "Scheduled",
            "method": "ACH",
            "amount": flt(invoice.outstanding_amount),
            "currency": invoice.currency,
            "scheduled_on": add_days(nowdate(), -6),
        }).insert(ignore_permissions=True)

        attempt.status = "Failed"
        attempt.attempted_on = add_days(nowdate(), -6)
        attempt.return_code = code
        attempt.gateway_reference = f"DEMO-{attempt.idempotency_key[:10]}"
        attempt.save(ignore_permissions=True)
        print(f"  {invoice.name}: {code} — "
              f"{'retry scheduled' if attempt.retriable else 'escalated to collections'}")


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
        existing = frappe.db.get_value(
            "Processor Residual Import",
            {"processor": processor, "statement_period": period},
            ["name", "statement_file"], as_dict=True,
        )
        if existing and existing.statement_file:
            continue
        if existing:
            # A record from before the parser existed: its figures were typed
            # in and are fiction. Skipping it leaves the screen a mix of parsed
            # and invented numbers, which is worse than either.
            frappe.delete_doc("Processor Residual Import", existing.name,
                              force=True, ignore_permissions=True)
            print(f"  removed {existing.name} — figures predated the parser")

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
