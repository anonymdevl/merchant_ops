import frappe
from frappe.model.document import Document
from frappe.utils import flt, nowdate

# Rounding between a processor's arithmetic and ours produces small
# differences that are not worth a person's morning. Anything at or below this
# matches; anything above it is a finding. The client will have their own
# number for this, and asking for it is one of the better questions on the list.
TOLERANCE = 1.00


class MerchantDeposit(Document):
    """One bank deposit, matched against the statements it is meant to pay.

    This is the three-way match: money that arrived, the statements that explain
    it, and what the ledger already knows. Reconciliation is hard here for one
    structural reason — a single deposit covers many merchants across one or
    more statements, so nothing lines up one-to-one and the tie-out is normally
    done by hand in a spreadsheet.
    """

    def validate(self):
        self._pull_statement_figures()
        self._match()

    def on_update(self):
        if self.status == "Variance":
            self._raise_variance_exception()

    def _pull_statement_figures(self):
        """Statement figures are read from the import, never typed on this form.

        A deposit whose expected side can be edited proves nothing.
        """
        for row in self.allocations:
            if not row.residual_import:
                continue
            processor, period, net = frappe.db.get_value(
                "Processor Residual Import", row.residual_import,
                ["processor", "statement_period", "net_residual"],
            )
            row.processor = processor
            row.statement_period = period
            row.statement_net = flt(net)
            row.variance = flt(row.allocated_amount) - flt(net)

    def _match(self):
        self.allocated_total = sum(flt(r.allocated_amount) for r in self.allocations)
        self.ledger_total = sum(flt(r.statement_net) for r in self.allocations)
        self.unallocated = flt(self.deposit_amount) - flt(self.allocated_total)
        self.ledger_variance = flt(self.ledger_total) - flt(self.allocated_total)

        problems = []
        if abs(flt(self.unallocated)) > TOLERANCE:
            problems.append(
                f"Deposit of {flt(self.deposit_amount):,.2f} against allocations of "
                f"{flt(self.allocated_total):,.2f} — {flt(self.unallocated):,.2f} unexplained."
            )
        for row in self.allocations:
            if abs(flt(row.variance)) > TOLERANCE:
                problems.append(
                    f"{row.processor} {row.statement_period}: statement says "
                    f"{flt(row.statement_net):,.2f}, allocated {flt(row.allocated_amount):,.2f}."
                )

        if not self.allocations:
            self.status = "Unmatched"
            self.match_log = "No statements allocated yet."
        elif problems:
            self.status = "Variance"
            self.match_log = "\n".join(problems)
        else:
            self.status = "Matched"
            self.match_log = (
                f"Matched {len(self.allocations)} statement(s) to the deposit "
                f"within a tolerance of {TOLERANCE:,.2f}."
            )

    def _raise_variance_exception(self):
        if frappe.db.exists("Revenue Exception", {
            "source_doctype": self.doctype, "source_document": self.name,
            "status": ["!=", "Resolved"],
        }):
            return

        frappe.get_doc({
            "doctype": "Revenue Exception",
            "exception_type": "Settlement Variance",
            "status": "Open",
            "detected_on": nowdate(),
            "expected_amount": flt(self.ledger_total),
            "actual_amount": flt(self.deposit_amount),
            "source_doctype": self.doctype,
            "source_document": self.name,
            "detail": self.match_log,
        }).insert(ignore_permissions=True, ignore_mandatory=True)
