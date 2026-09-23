// The Merchant 360 lives on its own page, which means it is only reachable by
// routing there. Anyone thinking about a merchant is already on this form, so
// this is where the door belongs — without it, a merchant who is neither
// overdue nor restricted appears in no cohort and has no way in at all.

frappe.ui.form.on("Customer", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Merchant 360"), () => {
			frappe.set_route("merchant-focus", "merchant", frm.doc.name);
		});

		// The door out of a dead mandate. Shown only when something is actually
		// holding this merchant, so it is not a button looking for a purpose.
		frappe.call({
			method: "frappe.client.get_count",
			args: {
				doctype: "Payment Attempt",
				filters: { merchant: frm.doc.name, status: "Failed", retriable: 0 },
			},
			callback: (r) => {
				if (!r.message) return;
				frm.dashboard.set_headline(
					__("Collection is held on {0} invoice(s): a return code disabled the mandate. Record a new authorisation to resume.",
						[r.message]),
					"red"
				);
				frm.add_custom_button(__("Record New Mandate"), () => {
					frappe.prompt(
						[
							{ fieldname: "reference", fieldtype: "Data", label: __("Authorisation reference"), reqd: 1 },
							{ fieldname: "note", fieldtype: "Small Text", label: __("How it was obtained") },
						],
						(v) => {
							frappe.call({
								method: "merchant_ops.collections.reauthorise",
								args: { merchant: frm.doc.name, reference: v.reference, note: v.note },
								freeze: true,
								callback: (res) => {
									frappe.msgprint({
										title: __("Mandate recorded"),
										message: __("Released {0} invoice(s) and closed {1} exception(s). AutoPay will present them again on its next run.",
											[res.message.released, res.message.exceptions_closed]),
										indicator: "green",
									});
									frm.refresh();
								},
							});
						},
						__("Record new authorisation"),
						__("Record")
					);
				}).addClass("btn-primary");
			},
		});

		if (frm.doc.account_status && frm.doc.account_status !== "Active") {
			// Says why the account is not Active without making anyone open a
			// second screen to find out.
			frm.dashboard.set_headline(
				__("Account status: {0}", [`<b>${frappe.utils.escape_html(frm.doc.account_status)}</b>`]),
				frm.doc.account_status === "Restricted" ? "red" : "orange"
			);
		}
	},
});
