// Every exception names the document that caused it. Opening that document is
// the first thing anyone does with one, so it is a button rather than a field
// someone has to notice.

frappe.ui.form.on("Revenue Exception", {
	refresh(frm) {
		if (frm.is_new()) return;

		if (frm.doc.source_doctype && frm.doc.source_document) {
			frm.add_custom_button(__(frm.doc.source_doctype), () => {
				frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_document);
			}, __("Open"));
		}

		if (frm.doc.merchant) {
			frm.add_custom_button(__("Merchant 360"), () => {
				frappe.set_route("merchant-focus", "merchant", frm.doc.merchant);
			}, __("Open"));
		}

		if (frm.doc.status !== "Resolved") {
			frm.add_custom_button(__("Mark Resolved"), () => {
				frappe.prompt(
					{ fieldname: "note", fieldtype: "Small Text", label: __("What was done?"), reqd: 1 },
					(v) => {
						frm.set_value("status", "Resolved");
						frm.set_value("resolution_note", v.note);
						frm.save();
					},
					__("Resolve exception")
				);
			}).addClass("btn-primary");
		}
	},
});
