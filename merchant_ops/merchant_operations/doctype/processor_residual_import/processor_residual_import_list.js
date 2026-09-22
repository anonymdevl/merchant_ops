frappe.listview_settings["Processor Residual Import"] = {
	add_fields: ["status", "rows_unmapped"],
	get_indicator(doc) {
		const map = {
			Imported: "green",
			"Partially Mapped": "orange",
			Failed: "red",
		};
		return [__(doc.status), map[doc.status], "status,=," + doc.status];
	},
};
