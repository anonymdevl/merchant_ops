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


# --- drill-downs ---------------------------------------------------------
#
# A tile that opens a filtered list answers "which records" and leaves the
# reader to assemble "which merchants, and what is wrong with them" by eye. The
# two endpoints below return the merchant as the unit, with the documents that
# put it there attached, because that is the question somebody clicking a tile
# is actually asking.

VIEWS = {
    "overdue": {
        "title": "Overdue Receivables",
        "blurb": "Merchants carrying an invoice past its due date, oldest first.",
    },
    "restricted": {
        "title": "Restricted Accounts",
        "blurb": "Blocked from new activity, with the debt and notices behind the block.",
    },
    "past_due": {
        "title": "Past Due Accounts",
        "blurb": "In collections but not yet restricted.",
    },
    "at_risk": {
        "title": "Value at Risk",
        "blurb": "Open revenue exceptions grouped by the merchant they belong to.",
    },
    "failed": {
        "title": "Failed Collections",
        "blurb": "Debits that came back, and whether the code permits another presentment.",
    },
}


@frappe.whitelist()
def drilldown(view):
    frappe.has_permission("Customer", throw=True)
    if view not in VIEWS:
        frappe.throw(f"Unknown view: {view}")

    merchants = _merchants_for(view)
    rows = []
    for merchant in merchants:
        rows.append({
            "merchant": merchant.name,
            "merchant_id": merchant.merchant_id,
            "processor": merchant.processor,
            "account_status": merchant.account_status,
            "risk_tier": merchant.risk_tier,
            "outstanding": _outstanding(merchant.name),
            "invoices": _invoices(merchant.name),
            "dunnings": _dunnings(merchant.name),
            "exceptions": _exceptions(merchant.name),
            "attempts": _attempts(merchant.name),
        })

    rows.sort(key=lambda r: flt(r["outstanding"]), reverse=True)
    return {
        "view": view,
        "title": VIEWS[view]["title"],
        "blurb": VIEWS[view]["blurb"],
        "currency": frappe.defaults.get_global_default("currency") or "USD",
        "rows": rows,
    }


@frappe.whitelist()
def merchant_360(merchant):
    """Everything about one merchant's commercial and financial relationship."""
    frappe.has_permission("Customer", merchant, throw=True)
    doc = frappe.get_doc("Customer", merchant)

    return {
        "currency": frappe.defaults.get_global_default("currency") or "USD",
        "profile": {
            "name": doc.name,
            "merchant_id": doc.get("merchant_id"),
            "processor": doc.get("processor"),
            "account_status": doc.get("account_status"),
            "risk_tier": doc.get("risk_tier"),
            "go_live_date": doc.get("go_live_date"),
            "assigned_agent": doc.get("assigned_agent"),
        },
        "totals": {
            "outstanding": _outstanding(merchant),
            "billed_12m": flt(frappe.db.sql("""
                SELECT COALESCE(SUM(grand_total), 0) FROM `tabSales Invoice`
                WHERE customer = %s AND docstatus = 1
                  AND posting_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
            """, merchant)[0][0]),
            "residual_12m": flt(frappe.db.sql("""
                SELECT COALESCE(SUM(r.net_residual), 0)
                FROM `tabProcessor Residual Row` r
                WHERE r.merchant = %s
            """, merchant)[0][0]),
            "open_exceptions": frappe.db.count("Revenue Exception",
                                               {"merchant": merchant, "status": ["!=", "Resolved"]}),
        },
        "invoices": _invoices(merchant, limit=10),
        "attempts": _attempts(merchant, limit=10),
        "dunnings": _dunnings(merchant),
        "exceptions": _exceptions(merchant),
        "subscriptions": frappe.get_all(
            "Merchant Subscription",
            filters={"merchant": merchant},
            fields=["name", "status", "start_date", "next_billing_date", "last_billed_period"],
        ) if frappe.db.exists("DocType", "Merchant Subscription") else [],
        "residual": frappe.db.sql("""
            SELECT i.processor, i.statement_period, r.mid, r.net_residual, r.sales_volume
            FROM `tabProcessor Residual Row` r
            JOIN `tabProcessor Residual Import` i ON i.name = r.parent
            WHERE r.merchant = %s
            ORDER BY i.statement_period DESC
            LIMIT 6
        """, merchant, as_dict=True),
    }


# --- pieces ---------------------------------------------------------------

def _merchants_for(view):
    fields = ["name", "merchant_id", "processor", "account_status", "risk_tier"]

    if view == "restricted":
        return frappe.get_all("Customer", filters={"account_status": "Restricted"}, fields=fields)
    if view == "past_due":
        return frappe.get_all("Customer", filters={"account_status": "Past Due"}, fields=fields)

    if view == "overdue":
        names = frappe.db.sql_list("""
            SELECT DISTINCT customer FROM `tabSales Invoice`
            WHERE docstatus = 1 AND outstanding_amount > 0 AND due_date < CURDATE()
        """)
    elif view == "at_risk":
        names = frappe.db.sql_list("""
            SELECT DISTINCT merchant FROM `tabRevenue Exception`
            WHERE status != 'Resolved' AND IFNULL(merchant, '') != ''
        """)
    else:  # failed
        names = frappe.db.sql_list("""
            SELECT DISTINCT merchant FROM `tabPayment Attempt` WHERE status = 'Failed'
        """) if frappe.db.exists("DocType", "Payment Attempt") else []

    if not names:
        return []
    return frappe.get_all("Customer", filters={"name": ["in", names]}, fields=fields)


def _outstanding(merchant):
    return flt(frappe.db.sql("""
        SELECT COALESCE(SUM(outstanding_amount), 0) FROM `tabSales Invoice`
        WHERE customer = %s AND docstatus = 1
    """, merchant)[0][0])


def _invoices(merchant, limit=5):
    return frappe.db.sql("""
        SELECT name, posting_date, due_date, grand_total, outstanding_amount, status,
               DATEDIFF(CURDATE(), due_date) AS age
        FROM `tabSales Invoice`
        WHERE customer = %s AND docstatus = 1 AND outstanding_amount > 0
        ORDER BY due_date ASC LIMIT %s
    """, (merchant, limit), as_dict=True)


def _dunnings(merchant):
    return frappe.get_all(
        "Dunning",
        filters={"customer": merchant, "docstatus": ["<", 2]},
        fields=["name", "dunning_type", "posting_date", "grand_total", "status"],
        order_by="posting_date desc", limit=4,
    )


def _exceptions(merchant):
    return frappe.get_all(
        "Revenue Exception",
        filters={"merchant": merchant, "status": ["!=", "Resolved"]},
        fields=["name", "exception_type", "variance", "detected_on", "status",
                "source_doctype", "source_document"],
        order_by="detected_on asc", limit=6,
    )


def _attempts(merchant, limit=5):
    if not frappe.db.exists("DocType", "Payment Attempt"):
        return []
    return frappe.get_all(
        "Payment Attempt",
        filters={"merchant": merchant},
        fields=["name", "sales_invoice", "attempt_no", "status", "amount",
                "return_code", "return_label", "retriable", "next_retry_on", "attempted_on"],
        order_by="creation desc", limit=limit,
    )
