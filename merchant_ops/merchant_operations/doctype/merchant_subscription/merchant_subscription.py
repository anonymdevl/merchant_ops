import calendar

import frappe
from frappe.model.document import Document
from frappe.utils import add_months, getdate, nowdate


class MerchantSubscription(Document):
    """What a merchant is signed up to, and when each line applies.

    Stock ERPNext Subscription is deliberately not extended here. It models a
    fixed recurring amount and its invoicing is driven from its own period
    fields; bending it to carry proration and dated plan changes means fighting
    its state machine on every upgrade. This holds the commercial agreement and
    emits ordinary Sales Invoices, so everything downstream — AR, tax, the
    ledger, the reports — remains stock.
    """

    def validate(self):
        self._date_the_rows()
        self._set_next_billing_date()

    def _date_the_rows(self):
        for row in self.items:
            if not row.effective_from:
                row.effective_from = self.start_date

    def _set_next_billing_date(self):
        if self.status != "Active":
            self.next_billing_date = None
            return

        anchor = getdate(self.last_billed_period + "-01") if self.last_billed_period else None
        base = add_months(anchor, 1) if anchor else getdate(self.start_date)
        self.next_billing_date = billing_date_for(base, self.billing_day)

    def plans_for(self, period_start, period_end):
        """Rows in force at any point in the period, with the dates they covered.

        A plan added or ended mid-month appears with its own narrower window,
        which is what makes proration possible without a separate amendment
        document for every change.
        """
        active = []
        for row in self.items:
            row_from = getdate(row.effective_from or self.start_date)
            row_to = getdate(row.effective_to) if row.effective_to else None

            if row_from > period_end:
                continue
            if row_to and row_to < period_start:
                continue

            active.append({
                "row": row,
                "from": max(row_from, period_start),
                "to": min(row_to, period_end) if row_to else period_end,
            })
        return active


def billing_date_for(date, day):
    """The billing day, clamped to the length of that month.

    A subscription billed on the 31st must still bill in February. Clamping
    rather than skipping is the behaviour finance teams expect, and getting it
    wrong loses a month of revenue once a year.
    """
    date = getdate(date)
    day = int(day or 1)
    last = calendar.monthrange(date.year, date.month)[1]
    return date.replace(day=min(day, last))
