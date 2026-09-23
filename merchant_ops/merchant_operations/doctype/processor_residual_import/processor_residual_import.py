import frappe
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from merchant_ops.statement_parser import parse

# A statement row whose MID matches no merchant is unattributed revenue. A row
# that matches a merchant the statement calls something else is worth flagging
# too, because it is usually a boarding record that was never updated.
NAME_MISMATCH_NOTE = "Statement DBA name does not match the merchant record."


class ProcessorResidualImport(Document):
    def validate(self):
        if not self.imported_on:
            self.imported_on = nowdate()

        if self._file_changed():
            self._import_file()

        self._map_rows()
        self._check_processor()
        self._roll_up()

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
                "expected_amount": self._unmapped_value(),
                "actual_amount": 0,
                "detail": f"{self.rows_unmapped} row(s) in the {self.processor} "
                          f"{self.statement_period} statement do not map to a merchant: "
                          f"{self._unmapped_mids()}.",
            }).insert(ignore_permissions=True, ignore_mandatory=True)

    # --- import ---------------------------------------------------------

    def _file_changed(self):
        """True when there is a file whose rows are not yet in the table.

        Three cases, and the third is the one that bit us: a new document, a
        changed attachment, and a document whose file was attached without the
        parse ever running. Keying only on "the field changed" left the third
        case silently empty, and the figures on screen were whatever had been
        there before.
        """
        if not self.statement_file:
            return False
        if self.is_new() or not self.rows:
            return True

        previous = self.get_doc_before_save()
        if not previous:
            return True
        return self.statement_file != previous.statement_file

    def _import_file(self):
        """Replaces the row table from the attached file.

        Re-reading on every change of attachment rather than appending, so a
        corrected statement cannot leave the previous version's rows behind and
        double-count the period.
        """
        try:
            content = frappe.get_doc("File", {"file_url": self.statement_file}).get_content()
        except Exception:
            frappe.throw(f"Could not read {self.statement_file}. Re-attach the statement file.")

        rows, warnings = parse(content)
        if not rows:
            self.status = "Failed"
            self.import_log = "\n".join(warnings) or "No rows parsed."
            frappe.throw(self.import_log)

        self.set("rows", [])
        for row in rows:
            self.append("rows", row)

        self.import_log = "\n".join(
            [f"Parsed {len(rows)} row(s) from {self.statement_file.rsplit('/', 1)[-1]}."] + warnings
        )

    def _check_processor(self):
        """Reject a statement whose merchants belong to a different processor.

        Nothing in a residual file names the processor, so the document\'s own
        Processor field is the only claim — and a file attached to the wrong
        record parses perfectly and produces confident, wrong figures. The
        merchants it maps to are the available evidence: if the mapped MIDs sit
        overwhelmingly with another processor, the attachment is on the wrong
        document.
        """
        mapped = [r for r in self.rows if r.merchant]
        if len(mapped) < 2:
            return

        processors = frappe.get_all(
            "Customer",
            filters={"name": ["in", [r.merchant for r in mapped]]},
            fields=["name", "processor"],
        )
        counts = {}
        for row in processors:
            counts[row.processor] = counts.get(row.processor, 0) + 1
        if not counts:
            return

        dominant, hits = max(counts.items(), key=lambda kv: kv[1])
        if dominant and dominant != self.processor and hits / len(mapped) >= 0.6:
            frappe.throw(
                f"This statement maps to {hits} of {len(mapped)} merchants on "
                f"<b>{dominant}</b>, but the document is set to <b>{self.processor}</b>. "
                f"Either the file is attached to the wrong import or the processor is wrong."
            )

    def _map_rows(self):
        """Resolves each MID to a merchant.

        MID is the join key because it is the only identifier the processor and
        the CRM are guaranteed to share; DBA names diverge constantly and are
        used only to raise a mismatch note.
        """
        mids = [(r.mid or "").strip() for r in self.rows if r.mid]
        if not mids:
            return

        merchants = frappe.get_all(
            "Customer",
            filters={"merchant_id": ["in", mids]},
            fields=["name", "merchant_id", "customer_name"],
        )
        by_mid = {m.merchant_id: m for m in merchants}

        for row in self.rows:
            match = by_mid.get((row.mid or "").strip())
            row.merchant = match.name if match else None
            row.mapped = 1 if match else 0
            if not match:
                row.row_note = "No merchant carries this MID."
            elif row.dba_name and _loose(row.dba_name) != _loose(match.customer_name):
                row.row_note = NAME_MISMATCH_NOTE
            elif row.row_note in (NAME_MISMATCH_NOTE, "No merchant carries this MID."):
                row.row_note = None

    def _roll_up(self):
        self.rows_imported = len(self.rows)
        self.rows_unmapped = sum(1 for r in self.rows if not r.mapped)
        self.gross_residual = sum(flt(r.income) for r in self.rows)
        self.net_residual = sum(flt(r.net_residual) for r in self.rows)

    # --- helpers --------------------------------------------------------

    def _unmapped_value(self):
        return sum(flt(r.net_residual) for r in self.rows if not r.mapped)

    def _unmapped_mids(self):
        mids = [r.mid for r in self.rows if not r.mapped][:5]
        return ", ".join(mids) + (" …" if self.rows_unmapped > 5 else "")

    def _retract_exception(self):
        """Closes the finding once the rows it described are gone.

        A detector that only ever creates is a detector nobody trusts: the
        queue grows past the point of being worked, and the count on the
        console stops meaning anything. Retraction is what makes the number on
        the tile a live figure rather than a tally.
        """
        stale = frappe.get_all("Revenue Exception", filters={
            "source_doctype": self.doctype, "source_document": self.name,
            "exception_type": "Unmapped MID", "status": ["!=", "Resolved"],
        }, pluck="name")

        for name in stale:
            doc = frappe.get_doc("Revenue Exception", name)
            doc.status = "Resolved"
            doc.resolution_note = (
                f"Closed automatically: the {self.processor} {self.statement_period} "
                f"statement no longer carries unmapped rows."
            )
            doc.save(ignore_permissions=True)

    def _has_open_exception(self):
        return frappe.db.exists("Revenue Exception", {
            "source_document": self.name, "status": ["!=", "Resolved"],
        })


def _loose(value):
    return "".join(c for c in (value or "").lower() if c.isalnum())
