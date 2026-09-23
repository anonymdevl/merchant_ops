// Two views behind one page.
//
//   #merchant-focus/overdue              a cohort, merchant by merchant
//   #merchant-focus/merchant/<name>      one merchant, end to end
//
// A console tile that opens a filtered list tells you which records matched. It
// does not tell you which merchants are in trouble or why, and the reader ends
// up sorting and grouping by eye to find out. These views answer the second
// question directly: the merchant is the row, and the documents that put it
// there hang off it.

frappe.pages["merchant-focus"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Merchant Focus"),
		single_column: true,
	});
	const view = new FocusView(page);
	frappe.pages["merchant-focus"].on_page_show = () => view.route();
	page.set_primary_action(__("Refresh"), () => view.route(), "refresh");
};

// The cohort answers "which merchants and why". The aging report answers "how
// old is the money" across the whole book. Finance wants both, and routing the
// console tile here took the report away, so each view that has a natural
// report carries it.
const REPORTS = {
	overdue: { label: "AR Aging Report", report: "Accounts Receivable" },
	past_due: { label: "AR Aging Report", report: "Accounts Receivable" },
	failed: { label: "AR Aging Report", report: "Accounts Receivable" },
	restricted: { label: "AR Summary", report: "Accounts Receivable Summary" },
};

class FocusView {
	constructor(page) {
		this.page = page;
		this.$body = $('<div class="mo-hub mo-focus"></div>').appendTo(page.main);
		this.route();
	}

	route() {
		const parts = frappe.get_route().slice(1);
		if (parts[0] === "merchant" && parts[1]) return this.merchant(decodeURIComponent(parts[1]));
		return this.cohort(parts[0] || "overdue");
	}

	fmt(v) {
		return format_currency(v, this.currency || "USD");
	}

	busy() {
		this.$body.html('<div class="mo-loading">' + __("Loading…") + "</div>");
	}

	// --- cohort ---------------------------------------------------------

	cohort(view) {
		this.busy();
		frappe.call({ method: "merchant_ops.api.drilldown", args: { view } }).then((r) => {
			if (!r || !r.message) return;
			const d = r.message;
			this.currency = d.currency;
			this.page.set_title(d.title);
			this.report_action(view);
			this.$body.empty().append(this.head(d.title, d.blurb, d.rows.length));

			if (!d.rows.length) {
				this.$body.append(
					`<div class="mo-empty">${__("Nothing here — which is the result you want.")}</div>`
				);
				return;
			}
			d.rows.forEach((row) => this.$body.append(this.card(row)));
		});
	}

	report_action(view) {
		const r = REPORTS[view];
		if (!r) {
			this.page.clear_secondary_action();
			return;
		}
		this.page.set_secondary_action(__(r.label), () => {
			// Carry the company through so the report opens on data rather than
			// on an empty filter bar.
			frappe.route_options = { company: frappe.defaults.get_user_default("Company") };
			frappe.set_route("query-report", r.report);
		});
	}

	head(title, blurb, count) {
		return $(`
			<div class="mo-head">
				<div>
					<div class="mo-head-eyebrow">${__("Merchant focus")}</div>
					<div class="mo-head-title">${frappe.utils.escape_html(title)}</div>
					<div class="mo-muted mo-head-blurb">${frappe.utils.escape_html(blurb || "")}</div>
				</div>
				<div class="mo-head-meta">
					<div>${count} ${count === 1 ? __("merchant") : __("merchants")}</div>
					<div class="mo-muted">${new Date().toLocaleTimeString()}</div>
				</div>
			</div>
		`);
	}

	card(row) {
		const $c = $('<div class="mo-card"></div>');

		$c.append(`
			<div class="mo-card-head">
				<div>
					<a class="mo-card-title" href="#merchant-focus/merchant/${encodeURIComponent(row.merchant)}">
						${frappe.utils.escape_html(row.merchant)}</a>
					<div class="mo-muted">${row.merchant_id || "—"} · ${row.processor || "—"} · ${__("Risk")}: ${row.risk_tier || "—"}</div>
				</div>
				<div class="mo-card-figure">
					<div class="mo-figure">${this.fmt(row.outstanding)}</div>
					<div class="mo-muted">${__("outstanding")}</div>
				</div>
			</div>
		`);

		$c.append(this.table(__("Invoices"), row.invoices, (i) => [
			this.link("Sales Invoice", i.name),
			frappe.datetime.str_to_user(i.due_date),
			this.fmt(i.outstanding_amount),
			i.age > 0 ? `<span class="mo-age">${i.age}d</span>` : i.status,
		]));

		$c.append(this.table(__("Failed collections"), row.attempts.filter((a) => a.status === "Failed"), (a) => [
			this.link("Payment Attempt", a.name),
			`${a.return_code || "—"} · ${frappe.utils.escape_html(a.return_label || "")}`,
			this.fmt(a.amount),
			a.retriable
				? `<span class="mo-ok">${__("retry")} ${frappe.datetime.str_to_user(a.next_retry_on)}</span>`
				: `<span class="mo-bad">${__("no re-presentment")}</span>`,
		]));

		$c.append(this.table(__("Notices"), row.dunnings, (n) => [
			this.link("Dunning", n.name),
			frappe.utils.escape_html(n.dunning_type || ""),
			this.fmt(n.grand_total),
			frappe.datetime.str_to_user(n.posting_date),
		]));

		$c.append(this.table(__("Open exceptions"), row.exceptions, (e) => [
			this.link("Revenue Exception", e.name),
			frappe.utils.escape_html(e.exception_type || ""),
			this.fmt(e.variance),
			e.source_document ? this.link(e.source_doctype, e.source_document) : "—",
		]));

		return $c;
	}

	// --- one merchant ---------------------------------------------------

	merchant(name) {
		this.busy();
		frappe.call({ method: "merchant_ops.api.merchant_360", args: { merchant: name } }).then((r) => {
			if (!r || !r.message) return;
			const d = r.message;
			this.currency = d.currency;
			this.page.set_title(name);
			this.page.clear_secondary_action();
			this.$body.empty();

			const p = d.profile;
			this.$body.append(`
				<div class="mo-head">
					<div>
						<div class="mo-head-eyebrow">${__("Merchant 360")}</div>
						<div class="mo-head-title">${frappe.utils.escape_html(p.name)}</div>
						<div class="mo-muted mo-head-blurb">
							${p.merchant_id || "—"} · ${p.processor || "—"} ·
							${__("Live")} ${p.go_live_date ? frappe.datetime.str_to_user(p.go_live_date) : "—"} ·
							${__("Agent")} ${frappe.utils.escape_html(p.assigned_agent || "—")}
						</div>
					</div>
					<div class="mo-head-meta">
						<div><span class="mo-pill ${this.tone(p.account_status)}">${p.account_status || "—"}</span></div>
						<div class="mo-muted">${__("Risk")}: ${p.risk_tier || "—"}</div>
					</div>
				</div>
			`);

			const t = d.totals;
			this.$body.append(`
				<div class="mo-grid mo-grid-4">
					${this.stat(__("Outstanding"), this.fmt(t.outstanding))}
					${this.stat(__("Billed, 12 months"), this.fmt(t.billed_12m))}
					${this.stat(__("Residual earned"), this.fmt(t.residual_12m))}
					${this.stat(__("Open exceptions"), t.open_exceptions)}
				</div>
			`);

			const $c = $('<div class="mo-card"></div>');
			$c.append(this.table(__("Open invoices"), d.invoices, (i) => [
				this.link("Sales Invoice", i.name),
				frappe.datetime.str_to_user(i.due_date),
				this.fmt(i.outstanding_amount),
				i.age > 0 ? `<span class="mo-age">${i.age}d</span>` : i.status,
			]));
			$c.append(this.table(__("Collection attempts"), d.attempts, (a) => [
				this.link("Payment Attempt", a.name),
				`#${a.attempt_no} · ${a.status}`,
				this.fmt(a.amount),
				a.return_code ? `${a.return_code} ${frappe.utils.escape_html(a.return_label || "")}` : "—",
			]));
			$c.append(this.table(__("Subscriptions"), d.subscriptions, (s) => [
				this.link("Merchant Subscription", s.name),
				s.status,
				s.last_billed_period || "—",
				s.next_billing_date ? frappe.datetime.str_to_user(s.next_billing_date) : "—",
			]));
			$c.append(this.table(__("Residual earned"), d.residual, (x) => [
				`${frappe.utils.escape_html(x.processor || "")} ${x.statement_period || ""}`,
				x.mid || "—",
				this.fmt(x.sales_volume),
				this.fmt(x.net_residual),
			]));
			$c.append(this.table(__("Notices"), d.dunnings, (n) => [
				this.link("Dunning", n.name),
				frappe.utils.escape_html(n.dunning_type || ""),
				this.fmt(n.grand_total),
				frappe.datetime.str_to_user(n.posting_date),
			]));
			$c.append(this.table(__("Open exceptions"), d.exceptions, (e) => [
				this.link("Revenue Exception", e.name),
				frappe.utils.escape_html(e.exception_type || ""),
				this.fmt(e.variance),
				e.source_document ? this.link(e.source_doctype, e.source_document) : "—",
			]));
			this.$body.append($c);
		});
	}

	// --- bits -----------------------------------------------------------

	tone(status) {
		if (status === "Restricted" || status === "Terminated") return "bad";
		if (status === "Past Due") return "warn";
		return "good";
	}

	stat(label, value) {
		return `<div class="mo-tile"><div class="mo-tile-label">${label}</div>
			<div class="mo-tile-value">${value}</div></div>`;
	}

	link(doctype, name) {
		return `<a href="/app/${frappe.router.slug(doctype)}/${encodeURIComponent(name)}">${frappe.utils.escape_html(name)}</a>`;
	}

	table(title, rows, cells) {
		if (!rows || !rows.length) return "";
		const body = rows
			.map((r) => `<tr>${cells(r).map((c) => `<td>${c}</td>`).join("")}</tr>`)
			.join("");
		return `<div class="mo-sub">
			<div class="mo-sub-title">${title}</div>
			<table class="mo-table">${body}</table>
		</div>`;
	}
}
