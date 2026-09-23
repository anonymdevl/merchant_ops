"""Collection runs, retries and the dunning ladder.

Three jobs, all scheduled, all idempotent:

    run_autopay        present debits for invoices that are due
    run_retries        present re-presentments that have come round
    escalate_dunning   move overdue invoices up the dunning ladder

    bench --site <site> execute merchant_ops.collections.run_autopay

None of these move money. AutoPay writes a Payment Attempt carrying an
idempotency key and, on a real deployment, hands that key to the gateway; the
gateway moves the money and calls back. On a demo instance there is no gateway,
so `settle` is called by hand or by the demo loader to represent the callback.
That boundary is deliberate and is the thing to point at when someone asks what
this system is allowed to do.
"""

import frappe
from frappe.utils import add_days, flt, getdate, nowdate

from merchant_ops import ach

# The ladder, by age in days. The labels are the *value* of Dunning Type's
# `dunning_type` field, not the document name: ERPNext names those records with
# the company abbreviation appended, so "First Notice" is stored as
# "First Notice - MPS". Resolving the name at runtime keeps this list readable
# and keeps the app working on a site with a different abbreviation.
#
# A level with no matching Dunning Type is skipped rather than raising. The
# ladder a client configures is theirs, and a missing rung must not stop the
# rungs below it from being worked.
LADDER = [
    (7, "First Notice"),
    (21, "Second Notice"),
    (45, "Final Notice"),
]

RESTRICT_AFTER_DAYS = 60


def run_autopay():
    """Create one Scheduled attempt per unpaid invoice that has come due."""
    invoices = frappe.db.sql("""
        SELECT si.name, si.customer, si.outstanding_amount, si.currency, si.due_date
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.outstanding_amount > 0
          AND si.due_date <= CURDATE()
          AND NOT EXISTS (
              SELECT 1 FROM `tabPayment Attempt` pa
              WHERE pa.sales_invoice = si.name
                AND pa.status IN ('Scheduled', 'Succeeded')
          )
          -- A return the rules forbid re-presenting is terminal for this
          -- mandate, not just for that attempt. Without this the next run
          -- would present the debit again the following day, which is the
          -- precise failure the return-code policy exists to prevent.
          AND NOT EXISTS (
              SELECT 1 FROM `tabPayment Attempt` blocked
              WHERE blocked.sales_invoice = si.name
                AND blocked.status = 'Failed'
                AND blocked.retriable = 0
          )
    """, as_dict=True)

    created, blocked = 0, 0
    for invoice in invoices:
        if frappe.db.get_value("Customer", invoice.customer, "account_status") == "Terminated":
            continue
        frappe.get_doc({
            "doctype": "Payment Attempt",
            "merchant": invoice.customer,
            "sales_invoice": invoice.name,
            "status": "Scheduled",
            "method": "ACH",
            "amount": flt(invoice.outstanding_amount),
            "currency": invoice.currency,
            "scheduled_on": nowdate(),
            "notes": "First presentment on the invoice due date.",
        }).insert(ignore_permissions=True)
        created += 1

    # Invoices held back because their mandate is dead. Reported rather than
    # silently skipped: somebody has to collect new bank details, and a count
    # of zero attempts with no explanation looks like the job failed.
    blocked = frappe.db.sql("""
        SELECT COUNT(DISTINCT si.name)
        FROM `tabSales Invoice` si
        JOIN `tabPayment Attempt` pa ON pa.sales_invoice = si.name
        WHERE si.docstatus = 1 AND si.outstanding_amount > 0
          AND pa.status = 'Failed' AND pa.retriable = 0
    """)[0][0]

    frappe.db.commit()
    return {"scheduled": created, "held_mandate_disabled": blocked}


def run_retries():
    """Presents every scheduled attempt that has come round.

    First presentments and re-presentments go through the same path, because
    the gateway does not care which it is and a separate route for retries is
    a second place for a duplicate to originate.
    """
    from merchant_ops.gateway import collect

    due = frappe.get_all(
        "Payment Attempt",
        filters={"status": "Scheduled", "scheduled_on": ["<=", nowdate()]},
        pluck="name",
    )

    presented, failed = 0, 0
    for name in due:
        try:
            outcome = collect(name)
            presented += 1
            if outcome.get("status") == "Failed":
                failed += 1
        except Exception:
            frappe.log_error(title=f"merchant_ops: presentment failed for {name}")

    frappe.db.commit()
    return {"presented": presented, "declined": failed}


def settle(attempt, outcome="Succeeded", return_code=None, reference=None):
    """Stands in for the gateway callback.

        bench execute merchant_ops.collections.settle \
            --kwargs "{'attempt':'PAY-ATT-00001','outcome':'Failed','return_code':'R01'}"

    On a real deployment this is a webhook handler verifying a signature and
    looking the attempt up by idempotency key. The logic either side of it is
    the same, which is the point of keeping the boundary this narrow.
    """
    doc = frappe.get_doc("Payment Attempt", attempt)
    doc.status = outcome
    doc.attempted_on = nowdate()
    doc.gateway_reference = reference or f"DEMO-{doc.idempotency_key[:10]}"
    if outcome == "Failed":
        doc.return_code = return_code
    doc.save(ignore_permissions=True)

    if outcome == "Succeeded":
        _record_payment(doc)

    frappe.db.commit()
    return {"attempt": doc.name, "status": doc.status, "retriable": bool(doc.retriable)}


def _record_payment(attempt):
    """Writes the Payment Entry the gateway's success implies."""
    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

    if frappe.db.exists("Payment Entry Reference", {"reference_name": attempt.sales_invoice}):
        return

    entry = get_payment_entry("Sales Invoice", attempt.sales_invoice)
    entry.reference_no = attempt.gateway_reference
    entry.reference_date = attempt.attempted_on
    entry.paid_amount = flt(attempt.amount)
    entry.received_amount = flt(attempt.amount)
    entry.insert(ignore_permissions=True)
    entry.submit()


def escalate_dunning():
    """Raise each overdue invoice to the ladder level its age has reached.

    One Dunning per invoice per level. Re-running produces nothing, which is
    what makes it safe to schedule daily.
    """
    overdue = frappe.db.sql("""
        SELECT name, customer, company, due_date, DATEDIFF(CURDATE(), due_date) AS age
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND outstanding_amount > 0 AND due_date < CURDATE()
    """, as_dict=True)

    raised, restricted, missing = 0, 0, set()

    for invoice in overdue:
        label = _level_for(invoice.age)
        if label:
            dunning_type = _resolve_type(label, invoice.company)
            if not dunning_type:
                missing.add(label)
            elif not _has_dunning(invoice.name, dunning_type):
                try:
                    _raise_dunning(invoice, dunning_type)
                    raised += 1
                except Exception:
                    # One merchant's notice failing must not stop the rest of
                    # the ladder being worked.
                    frappe.log_error(title=f"merchant_ops: dunning failed for {invoice.name}")

        if invoice.age >= RESTRICT_AFTER_DAYS and _flag_for_restriction(invoice):
            restricted += 1

    frappe.db.commit()
    result = {"dunnings_raised": raised, "flagged_for_restriction": restricted}
    if missing:
        result["missing_dunning_types"] = sorted(missing)
    return result


def _resolve_type(label, company):
    """Finds the Dunning Type record for a ladder label.

    Matches on the field rather than the name, and prefers the one belonging to
    the invoice's company so a multi-company site raises the right notice with
    the right fee and interest account.
    """
    name = frappe.db.get_value("Dunning Type", {"dunning_type": label, "company": company})
    return name or frappe.db.get_value("Dunning Type", {"dunning_type": label})


def _level_for(age):
    level = None
    for days, dunning_type in LADDER:
        if age >= days:
            level = dunning_type
    return level


def _has_dunning(invoice, dunning_type):
    return frappe.db.exists("Dunning", {
        "dunning_type": dunning_type, "docstatus": ["<", 2],
        "name": ["in", frappe.db.sql_list("""
            SELECT parent FROM `tabOverdue Payment` WHERE sales_invoice = %s
        """, invoice) or [""]],
    })


def _raise_dunning(invoice, dunning_type):
    doc = frappe.new_doc("Dunning")
    doc.customer = invoice.customer
    doc.dunning_type = dunning_type
    doc.posting_date = nowdate()
    # Taken from the invoice rather than a user default, because a scheduled
    # job has no user and the default would be empty.
    doc.company = invoice.company
    doc.append("overdue_payments", {"sales_invoice": invoice.name})
    doc.insert(ignore_permissions=True)


def _flag_for_restriction(invoice):
    """Restriction is proposed here, never applied.

    Cutting a merchant off is commercially consequential and is somebody's
    decision. The job raises the case; a human moves the status.
    """
    status = frappe.db.get_value("Customer", invoice.customer, "account_status")
    if status in ("Restricted", "Terminated"):
        return False

    if frappe.db.exists("Revenue Exception", {
        "exception_type": "Restriction Proposed",
        "merchant": invoice.customer,
        "source_document": invoice.name,
        "status": ["!=", "Resolved"],
    }):
        return False

    # Its own type, not Failed Collection. A proposal to cut a merchant off is
    # a different decision from a debit that bounced, and typing them alike let
    # an unrelated action — recording a new mandate — close it by accident.
    frappe.get_doc({
        "doctype": "Revenue Exception",
        "exception_type": "Restriction Proposed",
        "merchant": invoice.customer,
        "status": "Open",
        "detected_on": nowdate(),
        "source_doctype": "Sales Invoice",
        "source_document": invoice.name,
        "detail": f"{invoice.age} days overdue and past the {RESTRICT_AFTER_DAYS}-day "
                  f"restriction threshold. Proposed for restriction — requires approval.",
    }).insert(ignore_permissions=True, ignore_mandatory=True)
    return True


@frappe.whitelist()
def reauthorise(merchant, reference=None, note=None):
    """Records a fresh mandate and releases the hold on a merchant's invoices.

    A return like R02, R07 or R10 kills the mandate, and AutoPay holds every
    invoice for that merchant so the debit is never presented again. That hold
    is correct and it is also permanent, which means the platform needs a door:
    somebody obtains a new authorisation, records it here, and collection
    resumes.

    The failed attempts are moved to Abandoned rather than deleted. What was
    presented, what came back and when are the facts a dispute turns on, and a
    new mandate does not make the old refusal untrue.

        bench --site <site> execute merchant_ops.collections.reauthorise \\
            --kwargs "{'merchant':'Delgado Auto Service','reference':'ACH auth 2026-09-23'}"
    """
    frappe.only_for(("Accounts Manager", "System Manager"))

    blocked = frappe.get_all("Payment Attempt", filters={
        "merchant": merchant, "status": "Failed", "retriable": 0,
    }, pluck="name")

    if not blocked:
        return {"released": 0, "note": "Nothing was holding this merchant."}

    stamp = f"New authorisation recorded {nowdate()}"
    if reference:
        stamp += f" — {reference}"
    if note:
        stamp += f". {note}"

    for name in blocked:
        doc = frappe.get_doc("Payment Attempt", name)
        doc.status = "Abandoned"
        doc.mandate_disabled = 0
        doc.notes = "\n".join(filter(None, [doc.notes, stamp]))
        doc.flags.ignore_mandatory = True
        doc.save(ignore_permissions=True)

    # Closed by source document, not by merchant and type. A new mandate
    # answers the attempts it replaces and nothing else: a proposal to restrict
    # this merchant, or a rate mismatch on their subscription, is untouched.
    closed = 0
    for name in frappe.get_all("Revenue Exception", filters={
        "source_doctype": "Payment Attempt",
        "source_document": ["in", blocked],
        "status": ["!=", "Resolved"],
    }, pluck="name"):
        doc = frappe.get_doc("Revenue Exception", name)
        doc.status = "Resolved"
        doc.resolution_note = stamp
        doc.flags.ignore_mandatory = True
        doc.save(ignore_permissions=True)
        closed += 1

    frappe.db.commit()
    return {
        "released": len(blocked),
        "exceptions_closed": closed,
        "note": "AutoPay will present these invoices again on its next run.",
    }
