frappe.pages["merchant-hub"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Merchant Operations"),
		single_column: true,
	});

	const hub = new MerchantHub(page);
	page.set_primary_action(__("Refresh"), () => hub.load(), "refresh");

	// A Frappe page is constructed once and kept. Without this, routing away to
	// a list, correcting a record and routing back shows the figures from
	// whenever the page was first opened — which reads as the console being
	// wrong rather than stale.
	frappe.pages["merchant-hub"].on_page_show = () => hub.load();
};

class MerchantHub {
	constructor(page) {
		this.page = page;
		this.$body = $('<div class="mo-hub"></div>').appendTo(page.main);
		this.load();
	}

	load() {
		if (this.loading) return;
		this.loading = true;
		this.$body.html('<div class="mo-loading">' + __("Loading…") + "</div>");
		frappe.call({ method: "merchant_ops.api.hub_summary" })
			.then((r) => {
				if (!r || !r.message) return;
				this.data = r.message;
				this.fetched_at = new Date();
				this.render();
			})
			.always(() => {
				this.loading = false;
			});
	}

	stamp() {
		// Says when the figures were read. Without it there is no way to tell a
		// refresh that returned the same numbers from one that did not happen,
		// and the honest first assumption is that the button is broken.
		const t = this.fetched_at || new Date();
		return t.toLocaleTimeString();
	}

	fmt(v) {
		return format_currency(v, this.data.currency);
	}

	render() {
		const d = this.data;
		const k = d.kpi;

		this.$body.empty();
		this.$body.append(this.header());

		// --- KPI row -------------------------------------------------------
		const tiles = [
			{
				label: __("Outstanding AR"), value: this.fmt(k.outstanding),
				sub: __("{0} overdue · aging report inside", [this.fmt(k.overdue)]),
				tone: k.overdue > 0 ? "warn" : "",
				route: () => frappe.set_route("merchant-focus", "overdue"),
			},
			{
				label: __("Value at Risk"), value: this.fmt(k.value_at_risk),
				sub: __("across {0} open exceptions", [k.open_exceptions]),
				tone: k.value_at_risk > 0 ? "bad" : "good",
				route: () => frappe.set_route("merchant-focus", "at_risk"),
			},
			{
				label: __("Residual Revenue"), value: this.fmt(k.residual),
				sub: __("imported to date"),
				route: () => frappe.set_route("List", "Processor Residual Import"),
			},
			{
				label: __("Merchants"), value: k.merchants,
				sub: __("on the platform"),
				route: () => frappe.set_route("List", "Customer"),
			},
			{
				label: __("Past Due"), value: k.past_due_merchants,
				sub: __("in collections"),
				tone: k.past_due_merchants ? "warn" : "good",
				route: () => frappe.set_route("merchant-focus", "past_due"),
			},
			{
				label: __("Restricted"), value: k.restricted_merchants,
				sub: __("blocked from new activity"),
				tone: k.restricted_merchants ? "bad" : "good",
				route: () => frappe.set_route("merchant-focus", "restricted"),
			},
		];

		const $grid = $('<div class="mo-grid"></div>').appendTo(this.$body);
		tiles.forEach((t) => {
			const $t = $(`
				<div class="mo-tile ${t.tone || ""}">
					<div class="mo-tile-label">${t.label}</div>
					<div class="mo-tile-value">${t.value}</div>
					<div class="mo-tile-sub">${t.sub}</div>
				</div>
			`).appendTo($grid);
			if (t.route) $t.addClass("clickable").on("click", t.route);
		});

		// --- panels --------------------------------------------------------
		const $cols = $('<div class="mo-cols"></div>').appendTo(this.$body);
		$cols.append(this.exceptionsPanel());
		const $right = $('<div class="mo-col"></div>').appendTo($cols);
		$right.append(this.unmappedPanel());
		$right.append(this.watchlistPanel());
	}

	header() {
		const now = frappe.datetime.str_to_user(frappe.datetime.get_today());
		return $(`
			<div class="mo-head">
				<div>
					<div class="mo-head-eyebrow">${__("Commercial-to-cash")}</div>
					<div class="mo-head-title">${__("Merchant Operations")}</div>
				</div>
				<div class="mo-head-meta">
					<div>${frappe.session.user_fullname || frappe.session.user}</div>
					<div class="mo-muted">${now} · ${__("updated")} ${this.stamp()}</div>
				</div>
			</div>
		`);
	}

	panel(title, note, $content) {
		const $p = $(`
			<div class="mo-panel">
				<div class="mo-panel-head">
					<span class="mo-panel-title">${title}</span>
					<span class="mo-panel-note">${note || ""}</span>
				</div>
			</div>
		`);
		$p.append($content);
		return $p;
	}

	empty(msg) {
		return $(`<div class="mo-empty">${msg}</div>`);
	}

	exceptionsPanel() {
		const rows = this.data.top_exceptions || [];
		const $col = $('<div class="mo-col mo-col-wide"></div>');

		if (!rows.length) {
			$col.append(this.panel(__("Revenue exceptions"), "", this.empty(__("Nothing open. Every billed amount matches its contract."))));
			return $col;
		}

		const $table = $('<table class="mo-table"></table>');
		$table.append(`
			<thead><tr>
				<th>${__("Merchant")}</th><th>${__("Type")}</th>
				<th class="num">${__("Variance")}</th><th class="num">${__("Age")}</th>
			</tr></thead>
		`);
		const $tb = $("<tbody></tbody>").appendTo($table);

		rows.forEach((r) => {
			const age = r.age || 0;
			const tone = age > 90 ? "bad" : age > 30 ? "warn" : "";
			$(`
				<tr class="clickable">
					<td><strong>${frappe.utils.escape_html(r.merchant || "—")}</strong></td>
					<td class="mo-muted">${__(r.exception_type)}</td>
					<td class="num mo-var">${this.fmt(Math.abs(r.variance))}</td>
					<td class="num"><span class="mo-age ${tone}">${age}d</span></td>
				</tr>
			`)
				.appendTo($tb)
				.on("click", () => frappe.set_route("Form", "Revenue Exception", r.name));
		});

		const $wrap = $("<div></div>").append($table);
		$(`<div class="mo-panel-foot">${__("View all exceptions")} &rarr;</div>`)
			.appendTo($wrap)
			.on("click", () => frappe.set_route("merchant-focus", "at_risk"));

		$col.append(this.panel(__("Revenue exceptions"), __("largest first"), $wrap));
		return $col;
	}

	unmappedPanel() {
		const rows = this.data.unmapped || [];
		if (!rows.length) {
			return this.panel(__("Unmapped residuals"), "", this.empty(__("Every residual line maps to a merchant.")));
		}
		const $list = $('<div class="mo-list"></div>');
		rows.forEach((r) => {
			$(`
				<div class="mo-list-row clickable">
					<div>
						<div><strong>${r.processor}</strong> <span class="mo-muted">${r.statement_period}</span></div>
						<div class="mo-muted small">${__("{0} rows unattributed", [r.rows_unmapped])}</div>
					</div>
					<div class="mo-pill bad">${r.rows_unmapped}</div>
				</div>
			`)
				.appendTo($list)
				.on("click", () => frappe.set_route("Form", "Processor Residual Import", r.name));
		});
		return this.panel(__("Unmapped residuals"), __("revenue arrived, owner unknown"), $list);
	}

	watchlistPanel() {
		const rows = this.data.watchlist || [];
		if (!rows.length) {
			return this.panel(__("Account watchlist"), "", this.empty(__("No restricted or past-due merchants.")));
		}
		const $list = $('<div class="mo-list"></div>');
		rows.forEach((r) => {
			const tone = r.account_status === "Restricted" ? "bad" : "warn";
			$(`
				<div class="mo-list-row clickable">
					<div>
						<div><strong>${frappe.utils.escape_html(r.name)}</strong></div>
						<div class="mo-muted small">${r.merchant_id || "—"} &middot; ${r.processor || "—"}</div>
					</div>
					<div class="mo-pill ${tone}">${__(r.account_status)}</div>
				</div>
			`)
				.appendTo($list)
				.on("click", () => frappe.set_route("Form", "Customer", r.name));
		});
		return this.panel(__("Account watchlist"), __("past due and restricted"), $list);
	}
}
