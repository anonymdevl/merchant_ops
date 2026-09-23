"""Nightly revenue leakage sweep.

Four independent checks walk the commercial chain and record every point at
which two layers disagree:

    approved price -> contract -> subscription -> invoice -> payment
    processor statement -> MID -> merchant -> expected residual

Each check is a plain function returning a list of candidate findings, so one
failing check cannot stop the others and any of them can be run on its own from
the console while investigating.

    bench --site <site> execute merchant_ops.detect.run
    bench --site <site> execute merchant_ops.detect.run --kwargs "{'only':'rate_mismatch'}"
"""

import frappe
from frappe.utils import flt, nowdate, getdate

# Rounding and part-month proration produce small differences that are not
# leakage. Anything at or below this is noise and is not reported.
MATERIALITY = 1.00


def run(only=None):
    """Scheduler entry point. Returns a per-check count so the log is readable."""
    checks = {
        "rate_mismatch": rate_mismatch,
        "unbilled_subscription": unbilled_subscription,
        "missing_residual": missing_residual,
        "unmapped_mid": unmapped_mid,
    }
    if only:
        checks = {only: checks[only]}

    summary = {}
    for label, check in checks.items():
        try:
            findings = check()
            summary[label] = sum(1 for f in findings if _record(f))
        except Exception:
            frappe.log_error(title=f"merchant_ops sweep: {label} failed")
            summary[label] = "error"

    frappe.db.commit()
    frappe.logger("merchant_ops").info(f"leakage sweep {nowdate()}: {summary}")
    return summary


# --- checks -------------------------------------------------------------

def rate_mismatch():
    """Invoiced rate against the rate on the merchant's price list.

    The price list is the approved-price layer. An invoice line billed below it
    is revenue that was contracted for and never charged; this is the leak that
    survives longest, because the invoice itself looks perfectly correct.
    """
    lines = frappe.db.sql("""
        SELECT si.name AS invoice, si.customer, si.posting_date,
               sii.item_code, sii.qty, sii.rate, sii.amount,
               ip.price_list_rate
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        JOIN `tabItem Price` ip
             ON ip.item_code = sii.item_code
            AND ip.price_list = si.selling_price_list
            AND ip.selling = 1
        WHERE si.docstatus = 1
          AND ip.price_list_rate > 0
          AND sii.rate < ip.price_list_rate
    """, as_dict=True)

    findings = []
    for line in lines:
        expected = flt(line.price_list_rate) * flt(line.qty)
        if expected - flt(line.amount) <= MATERIALITY:
            continue
        findings.append({
            "exception_type": "Rate Mismatch",
            "merchant": line.customer,
            "expected_amount": expected,
            "actual_amount": flt(line.amount),
            "source_doctype": "Sales Invoice",
            "source_document": line.invoice,
            "detail": f"{line.item_code} billed at {flt(line.rate):,.2f} against an approved "
                      f"price of {flt(line.price_list_rate):,.2f} on {line.posting_date}.",
        })
    return findings


def unbilled_subscription():
    """An active subscription whose period has closed with no invoice against it.

    This is the opposite failure to a rate mismatch: the price was right and the
    invoice never happened at all, so there is nothing in AR to notice.
    """
    subscriptions = frappe.get_all(
        "Subscription",
        filters={"status": ["in", ["Active", "Past Due Date"]], "party_type": "Customer"},
        fields=["name", "party", "current_invoice_start", "current_invoice_end"],
    )

    findings = []
    for subscription in subscriptions:
        period_end = subscription.current_invoice_end
        if not period_end or getdate(period_end) >= getdate(nowdate()):
            continue

        invoiced = frappe.db.exists("Subscription Invoice", {
            "parent": subscription.name,
        }) and frappe.db.sql("""
            SELECT 1 FROM `tabSubscription Invoice` sub
            JOIN `tabSales Invoice` si ON si.name = sub.invoice
            WHERE sub.parent = %s AND si.docstatus = 1
              AND si.posting_date >= %s
            LIMIT 1
        """, (subscription.name, subscription.current_invoice_start))

        if invoiced:
            continue

        expected = flt(frappe.db.sql("""
            SELECT COALESCE(SUM(sp.cost * sps.qty), 0)
            FROM `tabSubscription Plan Detail` sps
            JOIN `tabSubscription Plan` sp ON sp.name = sps.plan
            WHERE sps.parent = %s
        """, subscription.name)[0][0])

        if expected <= MATERIALITY:
            continue

        findings.append({
            "exception_type": "Unbilled Subscription",
            "merchant": subscription.party,
            "expected_amount": expected,
            "actual_amount": 0,
            "source_doctype": "Subscription",
            "source_document": subscription.name,
            "detail": f"Period {subscription.current_invoice_start} to {period_end} closed "
                      f"with no submitted invoice.",
        })
    return findings


def missing_residual():
    """An active merchant absent from the most recent statement for its processor.

    Residual arrives as a file per processor per month. A merchant that is live,
    processing and simply not on the file is the quietest of the two revenue
    leaks, because no document anywhere is wrong.
    """
    latest = frappe.db.sql("""
        SELECT processor, MAX(statement_period) AS period
        FROM `tabProcessor Residual Import`
        WHERE status != 'Failed'
        GROUP BY processor
    """, as_dict=True)

    findings = []
    for entry in latest:
        paid_mids = {row[0] for row in frappe.db.sql("""
            SELECT prr.mid
            FROM `tabProcessor Residual Row` prr
            JOIN `tabProcessor Residual Import` pri ON pri.name = prr.parent
            WHERE pri.processor = %s AND pri.statement_period = %s
        """, (entry.processor, entry.period))}

        merchants = frappe.get_all(
            "Customer",
            filters={"processor": entry.processor, "account_status": ["in", ["Active", "Past Due"]]},
            fields=["name", "merchant_id"],
        )

        for merchant in merchants:
            if not merchant.merchant_id or merchant.merchant_id in paid_mids:
                continue
            findings.append({
                "exception_type": "Missing Residual",
                "merchant": merchant.name,
                "expected_amount": 0,
                "actual_amount": 0,
                "source_doctype": "Customer",
                "source_document": merchant.name,
                "detail": f"No {entry.processor} residual line for {merchant.merchant_id} "
                          f"in the {entry.period} statement.",
            })
    return findings


def unmapped_mid():
    """Catches imports whose unmapped rows were never raised.

    The import itself raises one of these on save. This check exists for rows
    that predate the mapping logic, and for a merchant record that was deleted
    after its statement was imported.
    """
    imports = frappe.get_all(
        "Processor Residual Import",
        filters={"rows_unmapped": [">", 0]},
        fields=["name", "processor", "statement_period", "rows_unmapped"],
    )

    findings = []
    for entry in imports:
        value = flt(frappe.db.sql("""
            SELECT COALESCE(SUM(net_residual), 0) FROM `tabProcessor Residual Row`
            WHERE parent = %s AND mapped = 0
        """, entry.name)[0][0])
        findings.append({
            "exception_type": "Unmapped MID",
            "merchant": None,
            "expected_amount": value,
            "actual_amount": 0,
            "source_doctype": "Processor Residual Import",
            "source_document": entry.name,
            "detail": f"{entry.rows_unmapped} row(s) in the {entry.processor} "
                      f"{entry.statement_period} statement do not map to a merchant.",
        })
    return findings


# --- writing ------------------------------------------------------------

def _record(finding):
    """Inserts a finding unless the same one is already open.

    The sweep runs every night over the same data, so without this every
    unresolved leak would produce a fresh exception daily and the queue would be
    useless within a week. Identity is the source document plus the type: the
    same invoice underbilled for the same reason is one finding, not thirty.
    """
    if frappe.db.exists("Revenue Exception", {
        "source_doctype": finding["source_doctype"],
        "source_document": finding["source_document"],
        "exception_type": finding["exception_type"],
        "status": ["!=", "Resolved"],
    }):
        return False

    doc = frappe.get_doc(dict(finding, doctype="Revenue Exception",
                              status="Open", detected_on=nowdate()))
    doc.insert(ignore_permissions=True, ignore_mandatory=True)
    return True
