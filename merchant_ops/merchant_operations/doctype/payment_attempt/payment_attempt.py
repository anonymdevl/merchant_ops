import hashlib

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, flt, nowdate

from merchant_ops import ach


class PaymentAttempt(Document):
    """One instruction sent to the gateway, and what came back.

    The document exists so that a collection is a record rather than an event in
    a log. Support can answer "what happened to this invoice" by reading a list,
    and the retry decision is visible and arguable instead of buried in a job.
    """

    def validate(self):
        self._number_the_attempt()
        self._stamp_idempotency_key()
        self._apply_return_policy()

    def on_update(self):
        if self.status == "Failed":
            self._schedule_or_escalate()

    # --- numbering and identity -----------------------------------------

    def _number_the_attempt(self):
        if self.attempt_no or not self.sales_invoice:
            return
        prior = frappe.db.count("Payment Attempt", {
            "sales_invoice": self.sales_invoice, "name": ["!=", self.name or ""],
        })
        self.attempt_no = prior + 1

    def _stamp_idempotency_key(self):
        """Derived, not random.

        A random key regenerated on a retry of the *same* attempt would let a
        duplicated job present the debit twice. Deriving it from invoice and
        attempt number means the same logical attempt always carries the same
        key, whatever re-runs it, and the gateway rejects the second copy.
        """
        if self.idempotency_key or not self.sales_invoice:
            return
        seed = f"{self.sales_invoice}:{self.attempt_no}:{flt(self.amount):.2f}"
        self.idempotency_key = hashlib.sha256(seed.encode()).hexdigest()[:32]

    # --- return code policy ---------------------------------------------

    def _apply_return_policy(self):
        """What the code means, and what may still be done about it.

        These are two different questions and they are deliberately separated.
        The meaning of a return code is a permanent fact about what the bank
        said, so label and family are kept for as long as the code is on the
        record — including after the attempt is abandoned. What changes with
        status is only whether anything further may be presented.

        An earlier version cleared the label and family whenever the status was
        not Failed, which meant recording a new mandate erased half the
        evidence of the refusal it was answering.
        """
        if not self.return_code:
            self.return_label = None
            self.return_family = None
            self.retriable = 0
            self.next_retry_on = None
            return

        self.return_label = ach.label(self.return_code)
        self.return_family = ach.family(self.return_code)

        if self.status != "Failed":
            # Abandoned or superseded: the code still means what it meant, but
            # nothing more is owed to it.
            self.retriable = 0
            self.next_retry_on = None
            return

        prior_failures = frappe.db.count("Payment Attempt", {
            "sales_invoice": self.sales_invoice,
            "status": "Failed",
            "name": ["!=", self.name or ""],
        })

        self.retriable = 1 if ach.is_retriable(self.return_code, prior_failures) else 0
        self.mandate_disabled = 1 if ach.should_disable_mandate(self.return_code) else 0
        self.next_retry_on = (
            add_days(self.attempted_on or nowdate(), ach.RETRY_AFTER_DAYS)
            if self.retriable else None
        )

    # --- what happens after a failure ------------------------------------

    def _schedule_or_escalate(self):
        if self.retriable:
            self._schedule_retry()
        else:
            self._raise_recovery_exception()

    def _schedule_retry(self):
        exists = frappe.db.exists("Payment Attempt", {
            "sales_invoice": self.sales_invoice, "status": "Scheduled",
        })
        if exists:
            return

        frappe.get_doc({
            "doctype": "Payment Attempt",
            "merchant": self.merchant,
            "sales_invoice": self.sales_invoice,
            "status": "Scheduled",
            "method": self.method,
            "amount": self.amount,
            "currency": self.currency,
            "scheduled_on": self.next_retry_on,
            "notes": f"Re-presentment after {self.return_code} "
                     f"({ach.label(self.return_code)}) on {self.attempted_on}.",
        }).insert(ignore_permissions=True)

    def _raise_recovery_exception(self):
        """A debit that cannot be re-presented needs a person, not a scheduler.

        The exception is the handover point: collections picks it up, and the
        record says why retrying is not an option, which is the part a new
        collections clerk would otherwise get wrong.
        """
        if frappe.db.exists("Revenue Exception", {
            "source_doctype": self.doctype, "source_document": self.name,
            "status": ["!=", "Resolved"],
        }):
            return

        frappe.get_doc({
            "doctype": "Revenue Exception",
            "exception_type": "Failed Collection",
            "merchant": self.merchant,
            "status": "Open",
            "detected_on": nowdate(),
            "expected_amount": flt(self.amount),
            "actual_amount": 0,
            "source_doctype": self.doctype,
            "source_document": self.name,
            "detail": f"{self.return_code} — {ach.label(self.return_code)}. "
                      f"Re-presentment is not permitted for this code; the mandate has been "
                      f"disabled and new details are required before any further attempt.",
        }).insert(ignore_permissions=True, ignore_mandatory=True)
