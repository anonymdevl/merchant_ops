// The contract is the authority; the subscription executes it. This button is
// the one-way handoff between them — it fills the subscription from the agreed
// rates at signing, and then never touches it again. Everything after that is
// the nightly sweep's job.

frappe.ui.form.on("Contract", {
	refresh(frm) {
		if (frm.is_new()) return;

		frappe.call({
			method: "merchant_ops.contract.subscription_for",
			args: { contract: frm.doc.name },
			callback: (r) => {
				if (r.message) return frm.add_custom_button(__("Billing Subscription"), () => {
					frappe.set_route("Form", "Merchant Subscription", r.message);
				});

				if (!(frm.doc.agreed_rates || []).length) return;

				frm.add_custom_button(__("Create Billing Subscription"), () => {
					frappe.confirm(
						__("Create a subscription billing the {0} agreed rate(s) on this contract?",
							[(frm.doc.agreed_rates || []).length]),
						() => {
							frappe.call({
								method: "merchant_ops.contract.create_subscription",
								args: { contract: frm.doc.name },
								freeze: true,
								freeze_message: __("Creating…"),
								callback: (res) => {
									if (!res.message) return;
									frappe.show_alert({
										message: __("Created {0}", [res.message]),
										indicator: "green",
									});
									frm.refresh();
								},
							});
						}
					);
				}).addClass("btn-primary");
			},
		});
	},
});
