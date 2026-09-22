/* Applies Merchant Portal Settings to the login page.
 *
 * Frappe's form is moved into a new layout, never rebuilt, so its fields,
 * CSRF token and submit handler are untouched.
 */
(function () {
	var METHOD =
		"merchant_ops.merchant_operations.doctype.merchant_portal_settings" +
		".merchant_portal_settings.branding";

	var ASSET = "/assets/merchant_ops/img/";

	var DEFAULTS = {
		brand_name: "Meridian Payment Solutions",
		tagline: "Merchant operations platform",
		logo: ASSET + "logo.svg",
		logo_reversed: ASSET + "logo-white.svg",
		primary: "#0e2a38",
		accent: "#2e86ab",
		on_accent: "#ffffff",
		on_primary: "#ffffff",
		background: "",
		layout: "Split",
		headline: "Every merchant, every dollar,\nin one system of record.",
		subline:
			"Onboarding, billing, collections, processor reconciliation and revenue controls.",
		form_note: "Sign in to the merchant operations console.",
		support_note: "Trouble signing in? Contact your account manager.",
		security_note: "Encrypted connection. No card data is stored in this system.",
		show_stats: true,
		stats: [
			{ value: "3,140", label: "Merchants" },
			{ value: "4", label: "Processors" },
			{ value: "99.98%", label: "Uptime" },
		],
		show_signup: false,
		show_forgot_password: true,
		show_email_link: true,
	};

	var LAYOUT_CLASS = {
		Split: "mo-layout-split",
		"Split - Brand Right": "mo-layout-split-right",
		Centred: "mo-layout-centred",
	};

	var LOCK =
		'<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
		'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">' +
		'<rect x="3" y="11" width="18" height="11" rx="2"/>' +
		'<path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>';

	function esc(s) {
		var d = document.createElement("div");
		d.textContent = s == null ? "" : String(s);
		return d.innerHTML;
	}

	function el(tag, cls, html) {
		var n = document.createElement(tag);
		if (cls) n.className = cls;
		if (html != null) n.innerHTML = html;
		return n;
	}

	// Falls back to type rather than a broken image icon.
	function brandBlock(src, name, cls) {
		if (src) return '<img src="' + esc(src) + '" alt="' + esc(name) + '">';
		return '<div class="mo-aside-name">' + esc(name) + "</div>";
	}

	/* Frappe v15+ renders four hash-routed sections (login, signup, forgot,
	   email link) as siblings under one wrapper. Move the WRAPPER, not the
	   login card, or switching to forgot-password drops out of the layout. */
	function findHost() {
		var section = document.querySelector('section[class*="for-login"], section[class*="for-forgot"]');
		if (section && section.parentElement) return section.parentElement;
		return document.querySelector(".login-content, .page-card"); // older Frappe
	}

	function build(s) {
		var host = findHost();
		if (!host || document.querySelector(".mo-split")) return;

		var root = document.documentElement.style;
		root.setProperty("--mo-primary", s.primary);
		root.setProperty("--mo-accent", s.accent);
		root.setProperty("--mo-on-accent", s.on_accent);
		root.setProperty("--mo-on-primary", s.on_primary);

		document.body.classList.add("mo-portal", LAYOUT_CLASS[s.layout] || "mo-layout-split");
		if (!s.show_signup) document.body.classList.add("mo-no-signup");
		if (!s.show_forgot_password) document.body.classList.add("mo-no-forgot");
		if (!s.show_email_link) document.body.classList.add("mo-no-email-link");
		if (s.brand_name) document.title = s.brand_name;

		var split = el("div", "mo-split");

		var aside = el("div", "mo-aside");
		if (s.background) {
			aside.classList.add("mo-has-bg");
			aside.style.backgroundImage =
				"linear-gradient(180deg, rgba(0,0,0,.55), rgba(0,0,0,.72)), url('" + s.background + "')";
		}
		aside.appendChild(el("div", "mo-aside-logo", brandBlock(s.logo_reversed, s.brand_name)));

		var body = "";
		if (s.headline) body += '<h1 class="mo-aside-head">' + esc(s.headline) + "</h1>";
		if (s.subline) body += '<p class="mo-aside-sub">' + esc(s.subline) + "</p>";
		else if (s.tagline) body += '<p class="mo-aside-sub">' + esc(s.tagline) + "</p>";
		aside.appendChild(el("div", "mo-aside-body", body));

		if (s.show_stats && s.stats && s.stats.length) {
			aside.appendChild(
				el("div", "mo-stats", s.stats.map(function (st) {
					return "<div><div class='mo-stat-value'>" + esc(st.value) +
						"</div><div class='mo-stat-label'>" + esc(st.label) + "</div></div>";
				}).join(""))
			);
		} else {
			aside.appendChild(el("div", "mo-stats-spacer"));
		}

		var main = el("div", "mo-main");
		var inner = el("div", "mo-main-inner");
		inner.appendChild(el("div", "mo-mobile-logo", brandBlock(s.logo || s.logo_reversed, s.brand_name)));

		// Attach the shell to body first so it escapes Frappe's .container,
		// then move the section wrapper in whole.
		split.appendChild(aside);
		split.appendChild(main);
		main.appendChild(inner);
		document.body.appendChild(split);
		inner.appendChild(host);

		// Our note replaces Frappe's stock subtitle only when one is configured.
		var head = document.querySelector("section[class*='for-login'] .page-card-head");
		if (head && s.form_note && !head.querySelector(".mo-form-note")) {
			head.appendChild(el("p", "mo-form-note", esc(s.form_note)));
			document.body.classList.add("mo-has-form-note");
		}

		if (s.support_note) inner.appendChild(el("div", "mo-support", esc(s.support_note)));
		if (s.security_note) {
			inner.appendChild(el("div", "mo-secure", LOCK + "<span>" + esc(s.security_note) + "</span>"));
		}
	}

	function init() {
		if (!/^\/(login|update-password|forgot)/.test(window.location.pathname)) return;

		var done = false;
		function go(settings) {
			if (done) return;
			done = true;
			try {
				build(settings);
			} catch (e) {
				if (window.console) console.warn("merchant_ops: branding skipped", e);
			}
		}

		// Never leave the page unstyled if settings are slow or unreachable.
		var fallback = setTimeout(function () { go(DEFAULTS); }, 1200);

		// Plain fetch: the desk bundle may not have initialised on /login.
		fetch("/api/method/" + METHOD, {
			headers: { Accept: "application/json" },
			credentials: "same-origin",
		})
			.then(function (r) { return r.ok ? r.json() : null; })
			.then(function (j) {
				clearTimeout(fallback);
				var s = (j && j.message) || {};
				Object.keys(DEFAULTS).forEach(function (k) {
					if (s[k] === undefined || s[k] === null || s[k] === "") s[k] = DEFAULTS[k];
				});
				if (!s.logo_reversed) s.logo_reversed = s.logo || DEFAULTS.logo_reversed;
				go(s);
			})
			.catch(function () {
				clearTimeout(fallback);
				go(DEFAULTS);
			});
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", init);
	} else {
		init();
	}
})();
