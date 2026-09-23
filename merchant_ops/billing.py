"""The monthly billing run.

Stock ERPNext Subscription bills a fixed amount on a fixed cycle. Merchant
services does not work that way: rates are tiered, a plan changes mid-cycle, a
merchant goes live on the 14th, and some charges are priced on volume the
processor reports after the fact. That is the whole reason this is a build
rather than a configuration.

What it emits is deliberately ordinary. Every run produces a normal Sales
Invoice with normal items, so AR, tax, the ledger, dunning and every stock
report keep working and none of them know this engine exists.

    bench --site <site> execute merchant_ops.billing.run
    bench --site <site> execute merchant_ops.billing.run --kwargs "{'period':'2026-08'}"
    bench --site <site> execute merchant_ops.billing.preview --kwargs "{'subscription':'MSUB-00001'}"
"""

import calendar

import frappe
from frappe.utils import add_days, add_months, flt, getdate, nowdate

from merchant_ops.merchant_operations.doctype.merchant_subscription.merchant_subscription import (
    billing_date_for,
)


def run(period=None, merchant=None, submit=True):
    """Bills every active subscription due for the period.

    Idempotent on subscription and period: a run that has already produced an
    invoice for a period produces nothing on a second pass. This is the control
    that makes the job safe to schedule daily, and safe to re-run by hand after
    a failure without anyone checking first.
    """
    period = period or _previous_period()
    period_start, period_end = _period_bounds(period)

    filters = {"status": "Active"}
    if merchant:
        filters["merchant"] = merchant

    results = {"period": period, "invoiced": 0, "skipped": 0, "nothing_to_bill": 0, "errors": 0}

    for name in frappe.get_all("Merchant Subscription", filters=filters, pluck="name"):
        try:
            outcome = _bill_one(name, period, period_start, period_end, submit)
            results[outcome] = results.get(outcome, 0) + 1
        except Exception:
            frappe.log_error(title=f"merchant_ops billing: {name} failed for {period}")
            results["errors"] += 1

    frappe.db.commit()
    return results


def preview(subscription, period=None):
    """Same arithmetic, nothing written. For answering 'why is this merchant billed that'."""
    period = period or _previous_period()
    period_start, period_end = _period_bounds(period)
    doc = frappe.get_doc("Merchant Subscription", subscription)
    return {
        "subscription": subscription,
        "period": period,
        "lines": _lines_for(doc, period, period_start, period_end),
    }


# --- one subscription ----------------------------------------------------

def _bill_one(name, period, period_start, period_end, submit):
    doc = frappe.get_doc("Merchant Subscription", name)

    if getdate(doc.start_date) > period_end:
        return "skipped"
    if doc.end_date and getdate(doc.end_date) < period_start:
        return "skipped"
    if _already_billed(name, period):
        return "skipped"

    lines = _lines_for(doc, period, period_start, period_end)
    if not lines:
        return "nothing_to_bill"

    invoice = frappe.new_doc("Sales Invoice")
    invoice.customer = doc.merchant
    invoice.set_posting_time = 1
    invoice.posting_date = billing_date_for(period_end, doc.billing_day)
    invoice.due_date = add_days(invoice.posting_date, 10)
    invoice.merchant_subscription = name
    invoice.billing_period = period
    if doc.currency:
        invoice.currency = doc.currency

    for line in lines:
        invoice.append("items", {
            "item_code": line["item"],
            "qty": 1,
            "rate": flt(line["amount"]),
            "description": line["description"],
        })

    invoice.insert(ignore_permissions=True)
    if submit:
        invoice.submit()

    doc.db_set("last_billed_period", period)
    doc.db_set("next_billing_date", billing_date_for(add_months(period_end, 1), doc.billing_day))
    return "invoiced"


def _already_billed(subscription, period):
    return frappe.db.exists("Sales Invoice", {
        "merchant_subscription": subscription,
        "billing_period": period,
        "docstatus": ["<", 2],
    })


def _lines_for(doc, period, period_start, period_end):
    lines = []
    days_in_period = (period_end - period_start).days + 1

    for entry in doc.plans_for(period_start, period_end):
        row = entry["row"]
        plan = frappe.get_doc("Merchant Billing Plan", row.plan)

        quantity = _quantity_for(plan, doc.merchant, period, row)
        amount, working = plan.charge_for(quantity)

        if row.rate_override:
            amount = flt(row.rate_override) * flt(row.qty or 1)
            working = f"Agreed rate {flt(row.rate_override):,.2f}"
        elif plan.billing_model == "Flat":
            amount = flt(amount) * flt(row.qty or 1)

        covered = (entry["to"] - entry["from"]).days + 1
        partial = covered < days_in_period

        if partial and doc.prorate and plan.prorate and plan.billing_model in ("Flat",):
            # Only a fixed periodic charge is prorated. A usage or tiered charge
            # is already proportional to what happened, so scaling it by days
            # would discount the same activity twice.
            full = amount
            amount = flt(amount) * covered / days_in_period
            working = (f"{working} · prorated {covered}/{days_in_period} days "
                       f"from {flt(full):,.2f}")

        if abs(flt(amount)) < 0.005:
            continue

        lines.append({
            "item": plan.item,
            "amount": flt(amount, 2),
            "description": f"{plan.plan_name} — {period} ({working})",
        })

    return lines


def _quantity_for(plan, merchant, period, row):
    """Where the number being priced comes from.

    Flat plans price the row quantity. Everything else prices measured usage,
    read from Merchant Usage rather than typed on the subscription, so a
    disputed charge can be traced to the figure it was calculated from.
    """
    if plan.billing_model == "Flat":
        return flt(row.qty or 1)

    quantity = frappe.db.get_value("Merchant Usage", {
        "merchant": merchant, "period": period, "metric": plan.usage_metric,
    }, "quantity")

    return flt(quantity)


# --- periods -------------------------------------------------------------

def _previous_period():
    today = getdate(nowdate())
    first = today.replace(day=1)
    return add_days(first, -1).strftime("%Y-%m")


def _period_bounds(period):
    start = getdate(f"{period}-01")
    last = calendar.monthrange(start.year, start.month)[1]
    return start, start.replace(day=last)
