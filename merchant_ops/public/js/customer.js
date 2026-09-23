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
