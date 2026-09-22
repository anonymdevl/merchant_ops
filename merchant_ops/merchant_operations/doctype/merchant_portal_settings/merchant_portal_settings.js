frappe.ui.form.on("Merchant Portal Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Preview Login"), () => {
			window.open("/login?mo_preview=1", "_blank", "noopener");
		});

		frm.add_custom_button(__("Load Meridian Defaults"), () => {
			frappe.confirm(
				__("Replace the current brand values with the Meridian demo set?"),
				() => {
					frm.set_value({
						brand_name: "Meridian Payment Solutions",
						brand_tagline: "Merchant operations platform",
						brand_primary_colour: "#0E2A38",
						brand_accent_colour: "#2E86AB",
						login_layout: "Split",
						login_headline: "Every merchant, every dollar,\nin one system of record.",
						login_subline:
							"Onboarding, billing, collections, processor reconciliation and revenue controls.",
						form_note: "Sign in to the merchant operations console.",
						security_note:
							"Encrypted connection. No card data is stored in this system.",
						show_stats: 1,
					});
					frm.clear_table("stats");
					[
						["3,140", "Merchants"],
						["4", "Processors"],
						["99.98%", "Uptime"],
					].forEach(([v, l]) => {
						const row = frm.add_child("stats");
						row.stat_value = v;
						row.stat_label = l;
					});
					frm.refresh_field("stats");
				}
			);
		});

		render_swatch(frm);
	},

	brand_primary_colour: render_swatch,
	brand_accent_colour: render_swatch,
	login_layout: render_swatch,
});

function render_swatch(frm) {
	const primary = frm.doc.brand_primary_colour || "#0E2A38";
	const accent = frm.doc.brand_accent_colour || primary;

	frm.dashboard.clear_headline();
	frm.dashboard.set_headline(`
		<div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap">
			<div style="display:flex;align-items:center;gap:8px">
				<span style="width:22px;height:22px;border-radius:4px;display:inline-block;
					background:${frappe.utils.escape_html(primary)};
					border:1px solid rgba(0,0,0,.14)"></span>
				<span style="font-size:11px;color:var(--text-muted)">Primary</span>
			</div>
			<div style="display:flex;align-items:center;gap:8px">
				<span style="width:22px;height:22px;border-radius:4px;display:inline-block;
					background:${frappe.utils.escape_html(accent)};
					border:1px solid rgba(0,0,0,.14)"></span>
				<span style="font-size:11px;color:var(--text-muted)">Accent</span>
			</div>
			<span style="font-size:11px;color:var(--text-muted)">
				${__("Layout")}: <b>${frappe.utils.escape_html(frm.doc.login_layout || "Split")}</b>
			</span>
		</div>
	`);
}
