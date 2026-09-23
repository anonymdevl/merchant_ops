import frappe
from frappe.utils import flt


@frappe.whitelist()
def hub_summary():
    """Aggregates for the operations console.

    One endpoint rather than six client-side counts, so the page paints on a
    single round trip.
    """
    frappe.has_permission("Customer", throw=True)

    outstanding = frappe.db.sql("""
        SELECT COALESCE(SUM(outstanding_amount), 0)
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND status != 'Cancelled'
    """)[0][0]

    overdue = frappe.db.sql("""
        SELECT COALESCE(SUM(outstanding_amount), 0)
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND outstanding_amount > 0 AND due_date < CURDATE()
    """)[0][0]

    leakage = frappe.db.sql("""
        SELECT COALESCE(SUM(ABS(variance)), 0)
        FROM `tabRevenue Exception`
        WHERE status != 'Resolved'
    """)[0][0]

    residual = frappe.db.sql("""
        SELECT COALESCE(SUM(gross_residual), 0)
        FROM `tabProcessor Residual Import`
    """)[0][0]

    failed_value = frappe.db.sql("""
        SELECT COALESCE(SUM(amount), 0) FROM `tabPayment Attempt`
        WHERE status = 'Failed' AND retriable = 0
    """)[0][0]

    unreconciled = frappe.db.sql("""
        SELECT COALESCE(SUM(ABS(unallocated)), 0) FROM `tabMerchant Deposit`
        WHERE status IN ('Variance', 'Unmatched')
    """)[0][0]

    return {
        "currency": frappe.defaults.get_global_default("currency") or "USD",
        "kpi": {
            "outstanding": flt(outstanding),
            "overdue": flt(overdue),
            "past_due_merchants": frappe.db.count("Customer", {"account_status": "Past Due"}),
            "restricted_merchants": frappe.db.count("Customer", {"account_status": "Restricted"}),
            "open_exceptions": frappe.db.count("Revenue Exception", {"status": ["!=", "Resolved"]}),
            "value_at_risk": flt(leakage),
            "residual": flt(residual),
            "merchants": frappe.db.count("Customer"),
            "failed_collections": frappe.db.count("Payment Attempt",
                                                  {"status": "Failed", "retriable": 0}),
            "failed_value": flt(failed_value),
            "retries_scheduled": frappe.db.count("Payment Attempt", {"status": "Scheduled"}),
            "deposits_unreconciled": frappe.db.count("Merchant Deposit",
                                                     {"status": ["in", ["Variance", "Unmatched"]]}),
            "unreconciled_value": flt(unreconciled),
        },
        "top_exceptions": frappe.db.sql("""
            SELECT name, merchant, exception_type, variance, detected_on, status,
                   DATEDIFF(CURDATE(), detected_on) AS age
            FROM `tabRevenue Exception`
            WHERE status != 'Resolved'
            ORDER BY ABS(variance) DESC
            LIMIT 6
        """, as_dict=True),
        "unmapped": frappe.db.sql("""
            SELECT name, processor, statement_period, rows_unmapped, gross_residual
            FROM `tabProcessor Residual Import`
            WHERE rows_unmapped > 0
            ORDER BY rows_unmapped DESC
            LIMIT 5
        """, as_dict=True),
        "recovery": frappe.db.sql("""
            SELECT name, merchant, sales_invoice, attempt_no, amount,
                   return_code, return_label, retriable, next_retry_on
            FROM `tabPayment Attempt`
            WHERE status = 'Failed'
            ORDER BY retriable ASC, amount DESC
            LIMIT 5
        """, as_dict=True),
        "deposits": frappe.db.sql("""
            SELECT name, processor, deposit_date, deposit_amount, unallocated, status
            FROM `tabMerchant Deposit`
            WHERE status IN ('Variance', 'Unmatched')
            ORDER BY ABS(unallocated) DESC
            LIMIT 5
        """, as_dict=True),
        "watchlist": frappe.db.sql("""
            SELECT name, merchant_id, account_status, processor, risk_tier
            FROM `tabCustomer`
            WHERE account_status IN ('Past Due', 'Restricted')
            ORDER BY FIELD(account_status, 'Restricted', 'Past Due'), name
            LIMIT 6
        """, as_dict=True),
    }
