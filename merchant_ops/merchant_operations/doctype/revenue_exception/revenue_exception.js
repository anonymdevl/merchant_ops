frappe.ui.form.on("Revenue Exception", {
	refresh(frm) {
		if (frm.doc.detected_on && frm.doc.status !== "Resolved") {
			const age = frappe.datetime.get_day_diff(
				frappe.datetime.get_today(), frm.doc.detected_on
			);
			frm.dashboard.add_indicator(
				__("Open {0} days", [age]), age > 30 ? "red" : age > 7 ? "orange" : "blue"
			);
		}
		if (frm.doc.merchant) {
			frm.add_custom_button(__("Open Merchant"), () =>
				frappe.set_route("Form", "Customer", frm.doc.merchant)
			);
		}
	},
	expected_amount: calc,
	actual_amount: calc,
});

function calc(frm) {
	frm.set_value(
		"variance", flt(frm.doc.expected_amount) - flt(frm.doc.actual_amount)
	);
}
