frappe.listview_settings["Revenue Exception"] = {
	add_fields: ["status", "variance"],
	get_indicator(doc) {
		const map = {
			Open: "red",
			Investigating: "orange",
			Resolved: "green",
		};
		return [__(doc.status), map[doc.status], "status,=," + doc.status];
	},
};
