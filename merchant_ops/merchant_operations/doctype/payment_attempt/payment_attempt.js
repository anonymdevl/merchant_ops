frappe.ui.form.on("Payment Attempt", {
	refresh(frm) {
		if (frm.is_new()) return;

		if (frm.doc.sales_invoice) {
			frm.add_custom_button(__("Invoice"), () => {
				frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
			}, __("Open"));
		}
		if (frm.doc.merchant) {
			frm.add_custom_button(__("Merchant 360"), () => {
				frappe.set_route("merchant-focus", "merchant", frm.doc.merchant);
			}, __("Open"));
		}
		if (frm.doc.idempotency_key) {
			frm.add_custom_button(__("Gateway Log"), () => {
				frappe.set_route("List", "Gateway Request Log",
					{ idempotency_key: frm.doc.idempotency_key });
			}, __("Open"));
		}

		// The decision the platform made, stated on the record rather than
		// inferred from two read-only fields.
		if (frm.doc.status === "Failed") {
			frm.dashboard.set_headline(
				frm.doc.retriable
					? __("{0} permits re-presentment. Next attempt {1}.",
						[frm.doc.return_code, frappe.datetime.str_to_user(frm.doc.next_retry_on)])
					: __("{0} may not be re-presented. The mandate was disabled and an exception raised.",
						[frm.doc.return_code]),
				frm.doc.retriable ? "orange" : "red"
			);
		}
	},
});
