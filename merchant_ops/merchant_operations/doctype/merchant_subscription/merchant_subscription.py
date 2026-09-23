import calendar

import frappe
from frappe.model.document import Document
from frappe.utils import add_months, flt, getdate, nowdate


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
        self._price_the_rows()
        self._set_next_billing_date()

    def _date_the_rows(self):
        for row in self.items:
            if not row.effective_from:
                row.effective_from = self.start_date

    def _price_the_rows(self):
        """Shows what each row bills, and what the subscription costs a cycle.

        A subscription whose form shows no number is a subscription nobody can
        check. The rate lives on the plan unless an override was agreed, and
        without resolving that here the grid shows a blank column and the
        reader has to open the plan to find out what is being charged.

        Metered plans are deliberately excluded from the total rather than
        guessed at. Their price is whatever the usage turns out to be, and a
        figure that looks like a commitment but is not would be worse than no
        figure at all.
        """
        total, metered = 0.0, []

        for row in self.items:
            model, base_rate = frappe.db.get_value(
                "Merchant Billing Plan", row.plan, ["billing_model", "base_rate"]
            ) or (None, 0)

            if model == "Flat":
                row.effective_rate = flt(row.rate_override) or flt(base_rate)
                total += flt(row.effective_rate) * flt(row.qty or 1)
            else:
                row.effective_rate = 0
                metered.append(f"{row.plan} ({model})")

        self.recurring_total = total
        self.metered_note = (
            ", ".join(metered) + " — priced from usage at billing time" if metered else None
        )

    def _set_next_billing_date(self):
        if self.status != "Active":
            self.next_billing_date = None
            return

        anchor = getdate(self.last_billed_period + "-01") if self.last_billed_period else None
        base = add_months(anchor, 1) if anchor else getdate(self.start_date)
        due = billing_date_for(base, self.billing_day)

        # Roll forward past any date already behind us. A subscription that
        # started in March and has never been billed should say when it bills
        # next, not print a date six months in the past and look broken.
        today = getdate(nowdate())
        while due < today:
            due = billing_date_for(add_months(due, 1), self.billing_day)

        self.next_billing_date = due

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
