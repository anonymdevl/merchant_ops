import frappe
from frappe.model.document import Document


class GatewaySettings(Document):
    def validate(self):
        if self.mode == "Live" and not (self.base_url and self.get_password("api_key", raise_exception=False)):
            frappe.throw("Live mode needs a base URL and an API key.")
        if self.mode == "Live" and self.provider == "Test":
            frappe.throw("Choose a real provider before switching to Live.")
