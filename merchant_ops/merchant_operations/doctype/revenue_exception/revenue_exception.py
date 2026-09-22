import frappe
from frappe.model.document import Document
from frappe.utils import flt, nowdate


class RevenueException(Document):
    def validate(self):
        self.variance = flt(self.expected_amount) - flt(self.actual_amount)
        if self.status == "Resolved" and not self.resolved_on:
            self.resolved_on = nowdate()
        if self.status != "Resolved":
            self.resolved_on = None

    @property
    def age_in_days(self):
        from frappe.utils import date_diff
        return date_diff(nowdate(), self.detected_on) if self.detected_on else 0
