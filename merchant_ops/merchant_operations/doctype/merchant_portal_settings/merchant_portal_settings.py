import frappe
from frappe.model.document import Document
from frappe.utils import cint


DEFAULT_STATS = [
    {"stat_value": "3,140", "stat_label": "Merchants"},
    {"stat_value": "4", "stat_label": "Processors"},
    {"stat_value": "99.98%", "stat_label": "Uptime"},
]


class MerchantPortalSettings(Document):
    def validate(self):
        if self.login_layout in ("Split", "Split - Brand Right") and not self.brand_logo_reversed:
            if self.brand_logo:
                frappe.msgprint(
                    frappe._(
                        "No reversed logo set. The brand panel is dark, so the light "
                        "logo will be used and may be close to invisible."
                    ),
                    indicator="orange",
                    alert=True,
                )

    def on_update(self):
        frappe.cache().delete_value("merchant_portal_branding")
        if cint(self.apply_to_desk):
            self._apply_to_desk()

    def _apply_to_desk(self):
        """Push logo and name into Website Settings so the desk matches the login."""
        icon = self.brand_logo_icon or self.brand_logo
        try:
            ws = frappe.get_single("Website Settings")
            changed = False
            if icon and ws.app_logo != icon:
                ws.app_logo = icon
                changed = True
            if icon and ws.favicon != icon:
                ws.favicon = icon
                changed = True
            if self.brand_name and ws.app_name != self.brand_name:
                ws.app_name = self.brand_name
                changed = True
            if changed:
                ws.save(ignore_permissions=True)
        except Exception:
            frappe.log_error(title="merchant_ops: could not apply brand to Website Settings")


def _contrast_on(hex_colour):
    """Readable text colour for a given background, by WCAG relative luminance."""
    try:
        h = (hex_colour or "").lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))

        def lin(c):
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

        luminance = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
        return "#000000" if luminance > 0.45 else "#FFFFFF"
    except Exception:
        return "#FFFFFF"


@frappe.whitelist(allow_guest=True)
def branding():
    """Presentational settings for the login page.

    Guest-readable by necessity; exposes nothing beyond what the rendered page
    already shows.
    """
    cached = frappe.cache().get_value("merchant_portal_branding")
    if cached:
        return cached

    try:
        s = frappe.get_cached_doc("Merchant Portal Settings")
    except Exception:
        return {}

    primary = s.brand_primary_colour or "#0E2A38"
    accent = s.brand_accent_colour or primary

    stats = [
        {"value": r.stat_value, "label": r.stat_label}
        for r in (s.stats or [])
        if r.stat_value
    ]
    if cint(s.show_stats) and not stats:
        stats = [{"value": d["stat_value"], "label": d["stat_label"]} for d in DEFAULT_STATS]

    data = {
        "brand_name": s.brand_name or "",
        "tagline": s.brand_tagline or "",
        "logo": s.brand_logo or "",
        "logo_reversed": s.brand_logo_reversed or s.brand_logo or "",
        "logo_icon": s.brand_logo_icon or "",
        "primary": primary,
        "accent": accent,
        "on_accent": _contrast_on(accent),
        "on_primary": _contrast_on(primary),
        "background": s.login_background or "",
        "layout": s.login_layout or "Split",
        "headline": s.login_headline or "",
        "subline": s.login_subline or "",
        "form_note": s.form_note or "",
        "support_note": s.support_note or "",
        "security_note": s.security_note or "",
        "show_stats": bool(cint(s.show_stats)) and bool(stats),
        "stats": stats,
        "show_signup": bool(cint(s.show_signup)),
        "show_forgot_password": bool(cint(s.show_forgot_password)),
    }

    frappe.cache().set_value("merchant_portal_branding", data, expires_in_sec=300)
    return data
