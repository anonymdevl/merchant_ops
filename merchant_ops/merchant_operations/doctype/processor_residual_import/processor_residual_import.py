import frappe
from frappe.model.document import Document
from frappe.utils import nowdate


class ProcessorResidualImport(Document):
    def validate(self):
        if not self.imported_on:
            self.imported_on = nowdate()
        if self.rows_unmapped and self.status == "Imported":
            self.status = "Partially Mapped"

    def on_update(self):
        # Unmapped rows are revenue that arrived but cannot be attributed to a
        # merchant. One exception per import, so they do not pass unnoticed.
        if self.rows_unmapped and not self._has_open_exception():
            frappe.get_doc({
                "doctype": "Revenue Exception",
                "exception_type": "Unmapped MID",
                "status": "Open",
                "detected_on": nowdate(),
                "source_doctype": self.doctype,
                "source_document": self.name,
                "detail": f"{self.rows_unmapped} row(s) in the {self.processor} "
                          f"{self.statement_period} statement do not map to a merchant.",
            }).insert(ignore_permissions=True, ignore_mandatory=True)

    def _has_open_exception(self):
        return frappe.db.exists("Revenue Exception", {
            "source_document": self.name, "status": ["!=", "Resolved"],
        })
