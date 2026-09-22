import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


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
    create_custom_fields(CUSTOMER_FIELDS, update=True)
    _label_customer_as_merchant()
    frappe.db.commit()
    print("merchant_ops: custom fields installed on Customer")


def _label_customer_as_merchant():
    """Show Customer as 'Merchant' throughout the desk.

    A Property Setter rather than a doctype edit, so ERPNext core is untouched.
    """
    try:
        frappe.make_property_setter(
            {
                "doctype": "Customer", "doctype_or_field": "DocType",
                "property": "label", "value": "Merchant", "property_type": "Data",
            },
            is_system_generated=False,
        )
    except Exception:
        # Cosmetic only, and DocType.label is not present on every Frappe
        # version. Never fail an install over a label.
        frappe.log_error(title="merchant_ops: could not relabel Customer")
