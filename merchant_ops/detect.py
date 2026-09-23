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
        "contract_drift": contract_drift,
        "rate_mismatch": rate_mismatch,
        "unapproved_rate": unapproved_rate,
        "unbilled_subscription": unbilled_subscription,
        "missing_residual": missing_residual,
        "unmapped_mid": unmapped_mid,
        "status_drift": status_drift,
    }
    if only:
        checks = {only: checks[only]}

    summary, live = {}, set()
    for label, check in checks.items():
        try:
            findings = check()
            summary[label] = sum(1 for f in findings if _record(f))
            live.update(_key(f) for f in findings)
        except Exception:
            frappe.log_error(title=f"merchant_ops sweep: {label} failed")
            summary[label] = "error"
            # A check that failed proves nothing about its findings, so its
            # existing exceptions are left alone rather than retracted on the
            # strength of an empty result.
            live.update(_open_keys(label_to_type(label)))

    summary["retracted"] = _retract(live, checks)
    frappe.db.commit()
    frappe.logger("merchant_ops").info(f"leakage sweep {nowdate()}: {summary}")
    return summary


# --- checks -------------------------------------------------------------

def contract_drift():
    """Contract against subscription, and subscription against invoice.

    This is the check the whole feature exists for, and it is the one that
    cannot be done by validating a document. Someone agrees a discount, amends
    the contract, and nobody edits the subscription. Every record that follows
    is internally consistent: the subscription is valid, the invoice matches the
    subscription, the payment matches the invoice. The disagreement only exists
    between two documents that are never opened side by side.

    Walking it needs both links present. A subscription with no contract is
    skipped rather than guessed at.
    """
    findings = []

    subscriptions = frappe.get_all(
        "Merchant Subscription",
        filters={"status": "Active", "contract": ["!=", ""]},
        fields=["name", "merchant", "contract"],
    )

    for subscription in subscriptions:
        agreed = {
            row.item: flt(row.agreed_rate)
            for row in frappe.get_all(
                "Merchant Contract Rate",
                filters={"parent": subscription.contract},
                fields=["item", "agreed_rate"],
            )
        }
        if not agreed:
            continue

        for row in frappe.get_all(
            "Merchant Subscription Item",
            filters={"parent": subscription.name},
            fields=["plan", "qty", "rate_override", "effective_to"],
        ):
            if row.effective_to and getdate(row.effective_to) < getdate(nowdate()):
                continue

            item, base_rate = frappe.db.get_value(
                "Merchant Billing Plan", row.plan, ["item", "base_rate"]
            ) or (None, 0)
            if item not in agreed:
                continue

            billing_rate = flt(row.rate_override) or flt(base_rate)
            contract_rate = agreed[item]
            drift = contract_rate - billing_rate

            if abs(drift) <= MATERIALITY:
                continue

            findings.append({
                "exception_type": "Rate Mismatch",
                "merchant": subscription.merchant,
                "expected_amount": contract_rate * flt(row.qty or 1),
                "actual_amount": billing_rate * flt(row.qty or 1),
                "source_doctype": "Merchant Subscription",
                "source_document": subscription.name,
                "detail": f"{item}: contract {subscription.contract} agrees "
                          f"{contract_rate:,.2f}, the subscription bills "
                          f"{billing_rate:,.2f}. Drift of {drift:,.2f} per cycle, "
                          f"compounding every period until someone opens both records.",
            })

    return findings


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


def unapproved_rate():
    """Invoices billed against a price nobody approved.

    Rate mismatch catches billing below an approved price. This catches the
    other direction: a price that was never approved in the first place, which
    is how a discount granted in a corridor becomes permanent. The control
    belongs upstream of the invoice, but the invoice is where it becomes
    measurable.
    """
    lines = frappe.db.sql("""
        SELECT si.name AS invoice, si.customer, si.posting_date,
               sii.item_code, sii.rate, sii.amount,
               ip.name AS price, ip.approval_status
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        JOIN `tabItem Price` ip
             ON ip.item_code = sii.item_code
            AND ip.price_list = si.selling_price_list
            AND ip.selling = 1
        WHERE si.docstatus = 1
          AND IFNULL(ip.approval_status, 'Draft') != 'Approved'
    """, as_dict=True)

    findings = []
    for line in lines:
        findings.append({
            "exception_type": "Unapproved Rate",
            "merchant": line.customer,
            "expected_amount": flt(line.amount),
            "actual_amount": flt(line.amount),
            "source_doctype": "Sales Invoice",
            "source_document": line.invoice,
            "detail": f"{line.item_code} was billed on {line.posting_date} against price "
                      f"{line.price}, which is {line.approval_status or 'Draft'} rather than "
                      f"Approved. The rate may be correct; it is not governed.",
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


def status_drift():
    """Account status against what the receivable actually says.

    account_status is set by a person and nothing reconciles it afterwards, so
    it drifts in both directions. Past Due on a merchant who has paid is noise
    in the collections queue. Restricted on a merchant who has paid is worse:
    an account blocked from new activity for a reason that stopped being true,
    which is revenue not being earned rather than revenue not being collected.

    Both directions are reported. Neither is corrected — status is somebody's
    decision, and a job that quietly reactivated a restricted merchant would be
    making a commercial call it has no business making.
    """
    rows = frappe.db.sql("""
        SELECT c.name, c.account_status,
               COALESCE(SUM(CASE WHEN si.due_date < CURDATE() THEN si.outstanding_amount END), 0) AS overdue,
               COALESCE(SUM(si.outstanding_amount), 0) AS outstanding
        FROM `tabCustomer` c
        LEFT JOIN `tabSales Invoice` si
               ON si.customer = c.name AND si.docstatus = 1 AND si.outstanding_amount > 0
        WHERE IFNULL(c.account_status, '') != ''
        GROUP BY c.name, c.account_status
    """, as_dict=True)

    findings = []
    for row in rows:
        if row.account_status in ("Past Due", "Restricted") and flt(row.overdue) <= MATERIALITY:
            detail = (
                f"Account is marked {row.account_status} with nothing overdue"
                + (f" and {flt(row.outstanding):,.2f} outstanding but not yet due."
                   if flt(row.outstanding) else " and no receivable at all.")
            )
            if row.account_status == "Restricted":
                # Restriction has causes other than non-payment — fraud, excess
                # chargebacks, a risk decision — and this check cannot see any
                # of them. It asserts only where the platform itself proposed
                # the restriction for debt; otherwise it asks.
                for_debt = frappe.db.exists("Revenue Exception", {
                    "exception_type": "Restriction Proposed", "merchant": row.name,
                })
                detail += (
                    " The restriction was proposed for non-payment, and the debt is now "
                    "cleared: the merchant is blocked from new activity for a reason that "
                    "no longer holds."
                    if for_debt else
                    " If this restriction was for non-payment the reason no longer holds. "
                    "If it was a risk or fraud decision it stands, and this finding can be "
                    "resolved with that as the note."
                )
            findings.append({
                "exception_type": "Status Mismatch",
                "merchant": row.name,
                "expected_amount": 0,
                "actual_amount": 0,
                "source_doctype": "Customer",
                "source_document": row.name,
                "detail": detail,
            })

        elif row.account_status == "Active" and flt(row.overdue) > MATERIALITY:
            findings.append({
                "exception_type": "Status Mismatch",
                "merchant": row.name,
                "expected_amount": flt(row.overdue),
                "actual_amount": 0,
                "source_doctype": "Customer",
                "source_document": row.name,
                "detail": f"Account is marked Active with {flt(row.overdue):,.2f} overdue. "
                          f"Collections will not see it on the watchlist.",
            })

    return findings


# --- retraction ---------------------------------------------------------

# Check name -> the exception type it raises. Used to decide which types a run
# is entitled to retract, and to protect a type when its check threw.
#
# contract_drift and rate_mismatch both raise Rate Mismatch. They stay
# distinguishable because retraction keys on the source document as well as the
# type, and those differ: a contract drift hangs off the subscription, an
# invoice mismatch off the invoice. Both must appear here, or a failure in one
# would let the other retract findings it never evaluated.
TYPE_BY_CHECK = {
    "contract_drift": "Rate Mismatch",
    "rate_mismatch": "Rate Mismatch",
    "unapproved_rate": "Unapproved Rate",
    "unbilled_subscription": "Unbilled Subscription",
    "missing_residual": "Missing Residual",
    "unmapped_mid": "Unmapped MID",
    "status_drift": "Status Mismatch",
}


def label_to_type(label):
    return TYPE_BY_CHECK.get(label)


def _key(finding):
    return (finding["exception_type"], finding["source_doctype"], finding["source_document"])


def _open_keys(exception_type):
    if not exception_type:
        return set()
    rows = frappe.get_all("Revenue Exception", filters={
        "exception_type": exception_type, "status": ["!=", "Resolved"],
    }, fields=["exception_type", "source_doctype", "source_document"])
    return {(r.exception_type, r.source_doctype, r.source_document) for r in rows}


def _retract(live, checks):
    """Closes open findings the sweep no longer reproduces.

    Without this the queue only ever grows. Someone corrects the invoice, the
    exception stays open, and within a fortnight the count on the console is a
    historical tally rather than a worklist — at which point people stop
    looking at it, which is the failure mode this whole feature exists to
    avoid.

    Only types this run actually evaluated are eligible, so running a single
    check from the console cannot retract another check's findings.
    """
    eligible = {TYPE_BY_CHECK[label] for label in checks if label in TYPE_BY_CHECK}
    if not eligible:
        return 0

    open_rows = frappe.get_all("Revenue Exception", filters={
        "exception_type": ["in", list(eligible)], "status": ["!=", "Resolved"],
    }, fields=["name", "exception_type", "source_doctype", "source_document"])

    closed = 0
    for row in open_rows:
        if (row.exception_type, row.source_doctype, row.source_document) in live:
            continue
        doc = frappe.get_doc("Revenue Exception", row.name)
        doc.status = "Resolved"
        doc.resolution_note = (
            f"Closed automatically on {nowdate()}: the sweep no longer finds this "
            f"discrepancy. The underlying record was corrected."
        )
        # Closing a finding must not be blocked by the finding's own contents.
        # Records raised before a field became mandatory, or by a check that
        # legitimately has no merchant, would otherwise be impossible to retire
        # and would sit in the queue forever.
        doc.flags.ignore_mandatory = True
        doc.save(ignore_permissions=True)
        closed += 1

    return closed


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
