import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


# Pricing governance. ERPNext holds the rate but has no opinion about who
# agreed it, which is the gap the leakage engine exists to catch further down
# the chain. Approval state on the price itself moves the control upstream of
# the invoice, where it is cheap.
PRICING_FIELDS = {
    "Item Price": [
        {
            "fieldname": "mo_governance_section", "label": "Governance",
            "fieldtype": "Section Break", "insert_after": "price_list_rate",
        },
        {
            "fieldname": "approval_status", "label": "Approval Status",
            "fieldtype": "Select", "options": "Draft\nApproved\nRejected",
            "default": "Draft", "insert_after": "mo_governance_section",
            "in_list_view": 1, "in_standard_filter": 1, "reqd": 1,
        },
        {
            "fieldname": "off_card_reason", "label": "Reason for Off-Card Rate",
            "fieldtype": "Small Text", "insert_after": "approval_status",
            "depends_on": "eval:doc.approval_status != 'Draft'",
        },
        {
            "fieldname": "mo_governance_col", "fieldtype": "Column Break",
            "insert_after": "off_card_reason",
        },
        {
            "fieldname": "approved_by", "label": "Approved By",
            "fieldtype": "Link", "options": "User", "read_only": 1,
            "insert_after": "mo_governance_col",
        },
        {
            "fieldname": "approved_on", "label": "Approved On",
            "fieldtype": "Datetime", "read_only": 1, "insert_after": "approved_by",
        },
    ]
}

# The billing run has to be able to prove which subscription and period an
# invoice came from, otherwise re-running it safely is guesswork and a disputed
# charge cannot be traced. Two fields on the standard doctype, no override.
INVOICE_FIELDS = {
    "Sales Invoice": [
        {
            "fieldname": "mo_billing_section", "label": "Merchant Billing",
            "fieldtype": "Section Break", "insert_after": "due_date",
            "collapsible": 1,
        },
        {
            "fieldname": "merchant_subscription", "label": "Merchant Subscription",
            "fieldtype": "Link", "options": "Merchant Subscription",
            "insert_after": "mo_billing_section", "read_only": 1,
            "in_standard_filter": 1,
        },
        {
            "fieldname": "billing_period", "label": "Billing Period",
            "fieldtype": "Data", "insert_after": "merchant_subscription",
            "read_only": 1, "in_standard_filter": 1,
        },
    ]
}

# The agreement, given somewhere to hold the rates that were actually agreed.
# ERPNext's Contract carries parties, dates and terms as prose; what it has no
# field for is the commercial number, which is exactly the record the leakage
# sweep needs on one end of its comparison.
CONTRACT_FIELDS = {
    "Contract": [
        {
            "fieldname": "mo_commercial_section", "label": "Agreed Commercial Terms",
            "fieldtype": "Section Break", "insert_after": "contract_terms",
        },
        {
            "fieldname": "merchant", "label": "Merchant",
            "fieldtype": "Link", "options": "Customer",
            "insert_after": "mo_commercial_section", "in_standard_filter": 1,
        },
        {
            "fieldname": "agreed_rates", "label": "Agreed Rates",
            "fieldtype": "Table", "options": "Merchant Contract Rate",
            "insert_after": "merchant",
        },
    ]
}

CUSTOMER_FIELDS = {
    "Customer": [
        {
            "fieldname": "ms_section", "label": "Merchant Profile",
            "fieldtype": "Section Break", "insert_after": "customer_type",
        },
        {
            "fieldname": "merchant_id", "label": "Merchant ID (MID)",
            "fieldtype": "Data", "insert_after": "ms_section",
            "in_list_view": 1, "in_standard_filter": 1, "unique": 1,
        },
        {
            "fieldname": "processor", "label": "Processor", "fieldtype": "Select",
            "options": "\nFiserv\nTSYS\nElavon\nNorth",
            "insert_after": "merchant_id", "in_standard_filter": 1,
        },
        {
            "fieldname": "account_status", "label": "Account Status",
            "fieldtype": "Select",
            "options": "Active\nPast Due\nRestricted\nTerminated",
            "default": "Active", "insert_after": "processor",
            "in_list_view": 1, "in_standard_filter": 1,
        },
        {
            "fieldname": "ms_col", "fieldtype": "Column Break",
            "insert_after": "account_status",
        },
        {
            "fieldname": "risk_tier", "label": "Risk Tier", "fieldtype": "Select",
            "options": "Low\nStandard\nElevated", "default": "Standard",
            "insert_after": "ms_col",
        },
        {
            "fieldname": "go_live_date", "label": "Go-Live Date",
            "fieldtype": "Date", "insert_after": "risk_tier",
        },
        {
            "fieldname": "assigned_agent", "label": "Assigned Agent",
            "fieldtype": "Link", "options": "User", "insert_after": "go_live_date",
        },
    ]
}


def after_install():
    ensure_custom_fields()
    _label_customer_as_merchant()
    _build_sidebar()
    frappe.db.commit()
    print("merchant_ops: installed")


def ensure_custom_fields():
    """Creates every custom field the app depends on, idempotently.

    This is called from after_migrate as well as after_install, and that is the
    whole point. after_install runs once, at install; a field added to this file
    in a later release would never reach a site that was already installed. The
    symptom is quiet — a governance field that simply is not on the form, or a
    scheduled job filtering on a column that does not exist — so the fields are
    re-asserted on every migrate instead of assumed.
    """
    create_custom_fields(CUSTOMER_FIELDS, update=True)
    create_custom_fields(PRICING_FIELDS, update=True)
    create_custom_fields(INVOICE_FIELDS, update=True)
    create_custom_fields(CONTRACT_FIELDS, update=True)


def after_migrate():
    """Re-asserts everything a migrate can leave behind.

    Frappe regenerates the sidebar when the workspace changes, dropping our
    icons and drill-downs, and custom fields added after install never reach an
    existing site on their own. Both are cheap to redo and expensive to miss.
    """
    ensure_custom_fields()
    _build_sidebar()
    frappe.db.commit()


def _build_sidebar():
    from merchant_ops.sidebar import build
    try:
        build()
    except Exception:
        frappe.log_error(title="merchant_ops: could not build the sidebar")


def _label_customer_as_merchant():
    """Relabel Customer as Merchant via Property Setter."""
    try:
        frappe.make_property_setter(
            {
                "doctype": "Customer", "doctype_or_field": "DocType",
                "property": "label", "value": "Merchant", "property_type": "Data",
            },
            is_system_generated=False,
        )
    except Exception:
        # DocType.label is not present on every Frappe version; cosmetic only.
        frappe.log_error(title="merchant_ops: could not relabel Customer")


def stamp_approval(doc, method=None):
    """Records who approved a rate and when, on the Item Price itself.

    Without this the approval is a dropdown anyone can set and nobody can audit,
    which is worse than no control at all because it looks like one.
    """
    if doc.get("approval_status") == "Approved" and not doc.get("approved_by"):
        doc.approved_by = frappe.session.user
        doc.approved_on = frappe.utils.now()
    elif doc.get("approval_status") != "Approved":
        doc.approved_by = None
        doc.approved_on = None
