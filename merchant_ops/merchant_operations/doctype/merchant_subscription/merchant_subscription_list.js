frappe.listview_settings["Merchant Subscription"] = {
	add_fields: ["status", "contract", "last_billed_period"],
	get_indicator(doc) {
		if (doc.status !== "Active") {
			return [__(doc.status), doc.status === "Paused" ? "orange" : "gray", `status,=,${doc.status}`];
		}
		// A subscription with no contract cannot be reconciled against anything,
		// which is worth seeing from the list rather than discovering in a sweep.
		return doc.contract
			? [__("Active"), "green", "status,=,Active"]
			: [__("Active · no contract"), "orange", "status,=,Active"];
	},
};
