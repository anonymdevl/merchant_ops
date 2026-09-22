import frappe
from frappe.model.document import Document


class MerchantPortalSettings(Document):
    pass


@frappe.whitelist(allow_guest=True)
def branding():
    """Public branding for the login page.

    allow_guest is required because this is read before authentication.
    Only presentational fields are exposed — never anything about merchants.
    """
    s = frappe.get_cached_doc("Merchant Portal Settings")
    return {
        "brand_name": s.brand_name,
        "tagline": s.tagline,
        "logo": s.logo,
        "accent_colour": s.accent_colour,
        "background_image": s.background_image,
        "support_note": s.support_note,
        "show_signup": bool(s.show_signup),
    }
