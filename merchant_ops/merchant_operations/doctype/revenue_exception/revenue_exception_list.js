// Standard list, better signal. An exception queue is read by scanning, so the
// status has to be visible without reading the row.
frappe.listview_settings["Revenue Exception"] = {
	add_fields: ["status", "variance", "detected_on"],
	get_indicator(doc) {
		const tone = { Open: "red", Investigating: "orange", Resolved: "green" };
		return [__(doc.status), tone[doc.status] || "gray", `status,=,${doc.status}`];
	},
	onload(list) {
		// Open first, oldest first: the queue should present the thing that has
		// been waiting longest, not the thing entered most recently.
		list.filter_area.add([["Revenue Exception", "status", "!=", "Resolved"]]);
		list.sort_selector.sort_by = "detected_on";
		list.sort_selector.sort_order = "asc";
	},
};
