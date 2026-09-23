frappe.listview_settings["Payment Attempt"] = {
	add_fields: ["status", "retriable", "return_code"],
	get_indicator(doc) {
		if (doc.status === "Succeeded") return [__("Succeeded"), "green", "status,=,Succeeded"];
		if (doc.status === "Scheduled") return [__("Scheduled"), "blue", "status,=,Scheduled"];
		if (doc.status === "Abandoned") return [__("Abandoned"), "gray", "status,=,Abandoned"];
		// A failure that may be re-presented is a different situation from one
		// that may not, and the list should say which without being opened.
		return doc.retriable
			? [__("Failed · retry due"), "orange", "status,=,Failed"]
			: [__("Failed · {0}", [doc.return_code || "no retry"]), "red", "status,=,Failed"];
	},
};
