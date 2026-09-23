// Buttons to the records either side of this one. A subscription sits between
// the contract that authorised it and the invoices it produced, and reading it
// usually means wanting one of those next.

frappe.ui.form.on("Merchant Subscription", {
	refresh(frm) {
		if (frm.is_new()) return;

		if (frm.doc.contract) {
			frm.add_custom_button(__("Contract"), () => {
				frappe.set_route("Form", "Contract", frm.doc.contract);
			}, __("Open"));
		}

		if (frm.doc.merchant) {
			frm.add_custom_button(__("Merchant 360"), () => {
				frappe.set_route("merchant-focus", "merchant", frm.doc.merchant);
			}, __("Open"));
		}

		frm.add_custom_button(__("Invoices"), () => {
			frappe.set_route("List", "Sales Invoice", { merchant_subscription: frm.doc.name });
		}, __("Open"));

		// A subscription with no contract cannot be reconciled against anything,
		// so say so on the record rather than leaving it to the nightly sweep.
		if (!frm.doc.contract) {
			frm.dashboard.set_headline(
				__("No contract linked — this subscription cannot be checked against what was agreed."),
				"orange"
			);
		}
	},

	// The grid's link arrow is easy to miss, so opening the plan is one click
	// from the row itself.
	items_on_form_rendered(frm, grid_row) {
		if (grid_row && grid_row.doc && grid_row.doc.plan) {
			grid_row.grid_form &&
				grid_row.grid_form.fields_dict.plan &&
				grid_row.grid_form.fields_dict.plan.$input_wrapper.find("a").attr("title", __("Open plan"));
		}
	},
});
