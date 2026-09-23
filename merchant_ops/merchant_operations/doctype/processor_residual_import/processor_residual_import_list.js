frappe.listview_settings["Processor Residual Import"] = {
	add_fields: ["status", "rows_unmapped"],
	get_indicator(doc) {
		if (doc.status === "Failed") return [__("Failed"), "red", "status,=,Failed"];
		if (doc.rows_unmapped)
			return [__("{0} unmapped", [doc.rows_unmapped]), "orange", "status,=,Partially Mapped"];
		return [__("Imported"), "green", "status,=,Imported"];
	},
};
