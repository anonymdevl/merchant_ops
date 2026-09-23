/* The merchant's half of the login screen.
 *
 * Frappe's login.html is not forked. It carries CSRF handling, the email-link
 * flow and the reset-password path, and owning a copy of that through every
 * upgrade is too high a price for moving a logo.
 *
 * The one piece of new DOM is .mo-brand-panel, which holds no form control and
 * touches no credential. Frappe renders one section at a time, so whichever of
 * login / signup / forgot / email-link is visible becomes the pane beside the
 * panel on its own. Nothing is moved, and a renamed class degrades the page to
 * Frappe's own layout rather than breaking it.
 *
 * Values come from Merchant Portal Settings at render time, so branding a
 * deployment is configuration and never a code change.
 */
(function () {
	var ENDPOINT =
		"/api/method/merchant_ops.merchant_operations.doctype" +
		".merchant_portal_settings.merchant_portal_settings.branding";

	var ASSET = "/assets/merchant_ops/img/";
	var CACHE_KEY = "mo_portal_brand_v1";

	var LAYOUTS = {
		Split: "split",
		"Split - Brand Right": "split-right",
		Centred: "centred",
	};

	var LOCK =
		'<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
		'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
		'<rect x="3" y="11" width="18" height="11" rx="2"/>' +
		'<path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>';

	/* ------------------------------------------------------------------ */

	function readCache() {
		try {
			var raw = window.localStorage.getItem(CACHE_KEY);
			return raw ? JSON.parse(raw) : null;
		} catch (e) {
			return null;
		}
	}

	function writeCache(data) {
		try {
			window.localStorage.setItem(CACHE_KEY, JSON.stringify(data));
		} catch (e) {
			/* Quota, private mode, blocked site data. Not worth a broken page. */
		}
	}

	function el(tag, className, html) {
		var node = document.createElement(tag);
		if (className) node.className = className;
		if (html != null) node.innerHTML = html;
		return node;
	}

	function esc(s) {
		var d = document.createElement("div");
		d.textContent = s == null ? "" : String(s);
		return d.innerHTML;
	}

	/* Black or white on the accent, whichever stays readable. Relative
	 * luminance rather than average brightness: blue and green of the same
	 * value are not equally bright to the eye. Computed here as well as on the
	 * server, because the cached paint runs before any response arrives. */
	function inkFor(colour) {
		var hex = String(colour || "").trim().replace(/^#/, "");
		if (hex.length === 3) {
			hex = hex.replace(/./g, "$&$&");
		}
		if (hex.length !== 6) return "#ffffff";
		var channel = function (i) {
			var c = parseInt(hex.substr(i, 2), 16) / 255;
			return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
		};
		var L = 0.2126 * channel(0) + 0.7152 * channel(2) + 0.0722 * channel(4);
		return L > 0.45 ? "#000000" : "#ffffff";
	}

	/* At most two words, first letters. The fallback when no logo is set, or
	 * when the one that is set fails to load. */
	function initials(name) {
		var words = String(name || "")
			.trim()
			.split(/\s+/)
			.filter(Boolean)
			.slice(0, 2);
		return words.map(function (w) { return w[0].toUpperCase(); }).join("") || "M";
	}

	/* ------------------------------------------------------------------ */

	function buildPanel(content) {
		var panel = el("div", "mo-brand-panel");
		panel.appendChild(el("div", "mo-brand-mark"));
		panel.appendChild(el("div", "mo-brand-body"));
		panel.appendChild(el("div", "mo-brand-foot"));
		content.insertBefore(panel, content.firstChild);
		return panel;
	}

	function paint(panel, brand) {
		var root = document.documentElement;
		var primary = brand.primary || "#0e2a38";
		var accent = brand.accent || primary;

		root.style.setProperty("--mo-primary", primary);
		root.style.setProperty("--mo-accent", accent);
		root.style.setProperty("--mo-on-accent", brand.on_accent || inkFor(accent));
		root.style.setProperty("--mo-on-primary", brand.on_primary || inkFor(primary));

		/* Layout is an attribute rather than a class: a class on #page-login
		 * sits alongside Frappe's own and invites a collision. */
		var page = document.getElementById("page-login");
		if (page) {
			page.setAttribute("data-mo-layout", LAYOUTS[brand.layout] || "split");
		}

		var body = document.body;
		body.classList.toggle("mo-no-signup", !brand.show_signup);
		body.classList.toggle("mo-no-forgot", !brand.show_forgot_password);
		body.classList.toggle("mo-no-email-link", !brand.show_email_link);

		if (brand.background) {
			panel.style.backgroundImage =
				"linear-gradient(180deg, rgba(0,0,0,.45), rgba(0,0,0,.68)), url('" +
				brand.background +
				"')";
			panel.setAttribute("data-has-bg", "1");
		}

		/* --- mark ------------------------------------------------------- */
		var mark = panel.querySelector(".mo-brand-mark");
		mark.textContent = "";
		var logo = brand.logo_reversed || brand.logo || ASSET + "logo-white.svg";
		if (logo) {
			var img = document.createElement("img");
			img.alt = brand.brand_name || "";
			/* A logo URL that 404s would leave a broken-image glyph on the most
			 * public page there is. Fall back to a monogram instead. */
			img.onerror = function () {
				mark.textContent = "";
				mark.appendChild(el("div", "mo-brand-initials", esc(initials(brand.brand_name))));
			};
			img.src = logo;
			mark.appendChild(img);
		} else {
			mark.appendChild(el("div", "mo-brand-initials", esc(initials(brand.brand_name))));
		}

		/* --- body ------------------------------------------------------- */
		var pbody = panel.querySelector(".mo-brand-body");
		pbody.textContent = "";
		if (brand.headline) {
			pbody.appendChild(el("h1", "mo-brand-head", esc(brand.headline)));
		}
		var sub = brand.subline || brand.tagline;
		if (sub) {
			pbody.appendChild(el("p", "mo-brand-sub", esc(sub)));
		}

		/* --- foot ------------------------------------------------------- */
		var foot = panel.querySelector(".mo-brand-foot");
		foot.textContent = "";
		if (brand.show_stats && brand.stats && brand.stats.length) {
			brand.stats.forEach(function (s) {
				foot.appendChild(
					el(
						"div",
						"mo-stat",
						'<div class="mo-stat-value">' + esc(s.value) +
						'</div><div class="mo-stat-label">' + esc(s.label) + "</div>"
					)
				);
			});
		}

		/* --- the form side ---------------------------------------------- */
		/* Frappe's own subtitle is rewritten rather than hidden and replaced,
		 * so there is never a moment with two of them on screen. */
		if (brand.form_note) {
			var subtitle = document.querySelector(".page-card-subtitle");
			if (subtitle) subtitle.textContent = brand.form_note;
		}

		/* Notes attach to every card. Frappe shows one at a time, so only the
		 * visible one is ever seen, and switching to forgot-password keeps
		 * them without any of them being moved. */
		document.querySelectorAll(".login-content, .page-card").forEach(function (card) {
			var existing = card.querySelector(".mo-card-notes");
			if (existing) existing.remove();
			if (!brand.support_note && !brand.security_note) return;
			var notes = el("div", "mo-card-notes");
			if (brand.support_note) {
				notes.appendChild(el("div", "mo-support", esc(brand.support_note)));
			}
			if (brand.security_note) {
				notes.appendChild(
					el("div", "mo-secure", LOCK + "<span>" + esc(brand.security_note) + "</span>")
				);
			}
			card.appendChild(notes);
		});

		if (brand.brand_name) document.title = brand.brand_name;
		panel.setAttribute("data-ready", "1");
	}

	/* ------------------------------------------------------------------ */

	function start() {
		/* web_include_js loads on every website page. Only the login page has
		 * anything to do here. */
		var page = document.getElementById("page-login");
		if (!page) return;

		var content = page.querySelector(".page_content");
		if (!content || content.querySelector(".mo-brand-panel")) return;

		var panel = buildPanel(content);

		/* Paint from cache first so a return visit is branded before the
		 * network answers. */
		var cached = readCache();
		if (cached) {
			try {
				paint(panel, cached);
			} catch (e) {
				/* A cache written by an older version. Ignore and wait for live. */
			}
		}

		fetch(ENDPOINT, {
			headers: { Accept: "application/json" },
			credentials: "same-origin",
		})
			.then(function (r) { return r.ok ? r.json() : null; })
			.then(function (payload) {
				var brand = payload && payload.message;
				if (!brand) return;
				paint(panel, brand);
				writeCache(brand);
			})
			.catch(function () {
				/* Offline, or the endpoint is gone. A cached paint may already be
				 * on screen; if not the panel stays a plain brand-coloured field
				 * and the form beside it works exactly as Frappe shipped it. */
				panel.setAttribute("data-ready", "1");
			});
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", start);
	} else {
		start();
	}
})();
