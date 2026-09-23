frappe.listview_settings["Merchant Deposit"] = {
	add_fields: ["status", "unallocated"],
	get_indicator(doc) {
		const tone = { Matched: "green", Variance: "red", Unmatched: "orange", "Written Off": "gray" };
		return [__(doc.status), tone[doc.status] || "gray", `status,=,${doc.status}`];
	},
};
