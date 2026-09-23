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

# The ladder. Each level names the Dunning Type that carries its fee and
# interest, and the age at which it applies.
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
    """, as_dict=True)

    created = 0
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

    frappe.db.commit()
    return {"scheduled": created}


def run_retries():
    """Report re-presentments that have come round.

    Nothing is presented here because there is no gateway on this instance. The
    job exists so the schedule is visible and the count is real.
    """
    due = frappe.get_all(
        "Payment Attempt",
        filters={"status": "Scheduled", "scheduled_on": ["<=", nowdate()]},
        fields=["name", "sales_invoice", "attempt_no"],
    )
    return {"due_for_presentment": len(due), "attempts": [d.name for d in due]}


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
        SELECT name, customer, due_date, DATEDIFF(CURDATE(), due_date) AS age
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND outstanding_amount > 0 AND due_date < CURDATE()
    """, as_dict=True)

    raised, restricted = 0, 0
    for invoice in overdue:
        level = _level_for(invoice.age)
        if level and not _has_dunning(invoice.name, level):
            _raise_dunning(invoice, level)
            raised += 1

        if invoice.age >= RESTRICT_AFTER_DAYS:
            if _flag_for_restriction(invoice):
                restricted += 1

    frappe.db.commit()
    return {"dunnings_raised": raised, "flagged_for_restriction": restricted}


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
    doc.company = frappe.defaults.get_user_default("Company")
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
        "exception_type": "Failed Collection",
        "merchant": invoice.customer,
        "source_document": invoice.name,
        "status": ["!=", "Resolved"],
    }):
        return False

    frappe.get_doc({
        "doctype": "Revenue Exception",
        "exception_type": "Failed Collection",
        "merchant": invoice.customer,
        "status": "Open",
        "detected_on": nowdate(),
        "source_doctype": "Sales Invoice",
        "source_document": invoice.name,
        "detail": f"{invoice.age} days overdue and past the {RESTRICT_AFTER_DAYS}-day "
                  f"restriction threshold. Proposed for restriction — requires approval.",
    }).insert(ignore_permissions=True, ignore_mandatory=True)
    return True
