/* Injects branding from Merchant Portal Settings into the login card.
 *
 * Uses a plain fetch rather than frappe.call: on /login the desk JS bundle is
 * not guaranteed to have initialised, and branding must never depend on it.
 *
 * Reads a guest-whitelisted endpoint rather than templating server-side, which
 * keeps frappe/www/login.html untouched and therefore upgrade-safe.
 */
(function () {
	var METHOD =
		"merchant_ops.merchant_operations.doctype.merchant_portal_settings" +
		".merchant_portal_settings.branding";

	function esc(s) {
		var d = document.createElement("div");
		d.textContent = s == null ? "" : String(s);
		return d.innerHTML;
	}

	function apply(s) {
		var card = document.querySelector(".page-card, .login-content");
		if (!card || card.querySelector(".mo-brand")) return;

		if (s.accent_colour) {
			document.documentElement.style.setProperty("--mo-portal-accent", s.accent_colour);
		}
		if (s.background_image) {
			document.body.classList.add("mo-has-bg");
			document.body.style.backgroundImage = "url('" + s.background_image + "')";
		}
		if (!s.show_signup) document.body.classList.add("mo-no-signup");

		var brand = document.createElement("div");
		brand.className = "mo-brand";
		brand.innerHTML =
			(s.logo ? '<img src="' + esc(s.logo) + '" alt="">' : "") +
			'<div class="mo-brand-name">' + esc(s.brand_name) + "</div>" +
			(s.tagline ? '<div class="mo-brand-tagline">' + esc(s.tagline) + "</div>" : "");
		card.insertBefore(brand, card.firstChild);

		if (s.support_note) {
			var note = document.createElement("div");
			note.className = "mo-support";
			note.textContent = s.support_note;
			card.appendChild(note);
		}
		if (s.brand_name) document.title = s.brand_name;
	}

	function init() {
		if (!/^\/(login|update-password|forgot)/.test(window.location.pathname)) return;

		fetch("/api/method/" + METHOD, {
			headers: { Accept: "application/json" },
			credentials: "same-origin",
		})
			.then(function (r) { return r.ok ? r.json() : null; })
			.then(function (j) { if (j && j.message) apply(j.message); })
			.catch(function () {
				/* Branding is decoration. A failure here must never block sign-in. */
			});
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", init);
	} else {
		init();
	}
})();
