/*
 * merchant_ops UI kit — builders
 * ==============================
 *
 * Components from kit.css, built from data. The point is that a new page
 * should be a description of what it shows rather than a pile of markup, and
 * that every page ends up looking the same without anyone having to remember
 * to make it so.
 *
 * A page looks like this:
 *
 *   const k = merchant_ops.kit;
 *   const $body = k.page(page, { eyebrow: "Merchant focus", title: "Past Due",
 *                                blurb: "In collections, not yet restricted." });
 *   $body.append(k.tiles([
 *     { label: "Outstanding", value: k.money(1200), tone: "warn",
 *       sub: "3 invoices", route: () => frappe.set_route("List", "Sales Invoice") },
 *   ]));
 *   $body.append(k.card({
 *     title: "Delgado Auto Service", subtitle: "MID-884377 · TSYS",
 *     figure: k.money(163.95), figureLabel: "outstanding",
 *     sections: [
 *       { title: "Invoices", rows: invoices, cells: (r) => [k.link("Sales Invoice", r.name),
 *                                                           k.date(r.due_date), k.money(r.amount)] },
 *     ],
 *   }));
 *
 * Every string that reaches the DOM goes through escaping unless it came from
 * a builder. Merchant names and DBA names arrive from processor files, and a
 * statement is not a trusted source.
 */

frappe.provide("merchant_ops.kit");

merchant_ops.kit = (function () {
	const esc = (v) => frappe.utils.escape_html(String(v == null ? "" : v));

	function page(frappePage, { eyebrow, title, blurb, meta } = {}) {
		const $body = $('<div class="mok"></div>').appendTo(frappePage.main);
		if (title || eyebrow) $body.append(head({ eyebrow, title, blurb, meta }));
		return $body;
	}

	function head({ eyebrow, title, blurb, meta } = {}) {
		return $(`
			<div class="mok-head">
				<div>
					${eyebrow ? `<div class="mok-eyebrow">${esc(eyebrow)}</div>` : ""}
					<div class="mok-title">${esc(title || "")}</div>
					${blurb ? `<div class="mok-blurb">${esc(blurb)}</div>` : ""}
				</div>
				<div class="mok-meta">${meta || ""}</div>
			</div>
		`);
	}

	/** Stat tiles. Columns are chosen from the count so a page never has to. */
	function tiles(items) {
		const cols = items.length >= 6 ? 6 : items.length >= 4 ? 4 : items.length === 3 ? 3 : 2;
		const $grid = $(`<div class="mok-grid mok-grid-${cols}"></div>`);

		items.forEach((t) => {
			const $t = $(`
				<div class="mok-tile ${t.tone || ""} ${t.route ? "clickable" : ""}">
					<div class="mok-tile-label">${esc(t.label)}</div>
					<div class="mok-tile-value">${t.value}</div>
					${t.sub ? `<div class="mok-tile-sub">${t.sub}</div>` : ""}
				</div>
			`);
			if (t.route) $t.on("click", t.route);
			$grid.append($t);
		});
		return $grid;
	}

	/** A card with an optional figure and any number of titled tables. */
	function card({ title, titleRoute, subtitle, figure, figureLabel, status, sections } = {}) {
		const $c = $('<div class="mok-card"></div>');

		if (title) {
			const heading = titleRoute
				? `<a class="mok-card-title" href="${titleRoute}">${esc(title)}</a>`
				: `<span class="mok-card-title">${esc(title)}</span>`;

			$c.append(`
				<div class="mok-card-head">
					<div>
						${heading}
						${subtitle ? `<div class="mok-muted">${subtitle}</div>` : ""}
					</div>
					<div class="mok-card-figure">
						${status || ""}
						${figure ? `<div class="mok-figure">${figure}</div>` : ""}
						${figureLabel ? `<div class="mok-muted">${esc(figureLabel)}</div>` : ""}
					</div>
				</div>
			`);
		}

		(sections || []).forEach((s) => $c.append(table(s)));
		return $c;
	}

	/** A titled table. Returns "" when there are no rows, so a card can list
	 *  every section it might show without testing each one. */
	function table({ title, head: headings, rows, cells, onRow } = {}) {
		if (!rows || !rows.length) return "";

		const $wrap = $(`<div class="mok-sub">${title ? `<div class="mok-sub-title">${esc(title)}</div>` : ""}</div>`);
		const $t = $('<table class="mok-table"></table>');

		if (headings) {
			$t.append(`<tr>${headings.map((h) => `<th>${esc(h)}</th>`).join("")}</tr>`);
		}
		rows.forEach((r) => {
			const $tr = $(`<tr>${cells(r).map((c) => `<td>${c == null ? "" : c}</td>`).join("")}</tr>`);
			if (onRow) $tr.addClass("clickable").on("click", () => onRow(r));
			$t.append($tr);
		});

		return $wrap.append($t);
	}

	function empty(message) {
		return $(`<div class="mok-empty">${esc(message)}</div>`);
	}

	function loading($body) {
		$body.html(`<div class="mok-loading">${__("Loading…")}</div>`);
	}

	// --- value formatters, so pages do not each invent their own ---------

	function money(value, currency) {
		return format_currency(value, currency || merchant_ops.kit.currency || "USD");
	}

	function date(value) {
		return value ? frappe.datetime.str_to_user(value) : "—";
	}

	function link(doctype, name, label) {
		if (!name) return "—";
		return `<a href="/app/${frappe.router.slug(doctype)}/${encodeURIComponent(name)}">${esc(label || name)}</a>`;
	}

	function pill(text, tone) {
		return `<span class="mok-pill ${tone || "flat"}">${esc(text)}</span>`;
	}

	/** Age in days, coloured only once it has become a problem. */
	function age(days, { warn = 30, bad = 60 } = {}) {
		if (days == null) return "—";
		const tone = days >= bad ? "bad" : days >= warn ? "warn" : "";
		return `<span class="mok-age ${tone}">${Number(days)}d</span>`;
	}

	return { page, head, tiles, card, table, empty, loading, money, date, link, pill, age, esc };
})();
