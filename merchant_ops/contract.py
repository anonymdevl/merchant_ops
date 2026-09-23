"""Turning a signed contract into the subscription that bills it.

The design position this implements: automate the creation, reconcile the
divergence. Creating the subscription from the agreement removes the
transcription error, which is the failure that happens on day one. The nightly
sweep still compares the two afterwards, because the other failure — an
amendment six months later that reaches one record and not the other — is not
something creation can prevent.

Deliberately not a sync. Nothing here rewrites a subscription that already
exists. Silently correcting a live subscription would change what a merchant is
billed without anyone deciding to, and it would also erase the very drift the
sweep is there to surface.

    bench --site <site> execute merchant_ops.contract.create_subscription \
        --kwargs "{'contract':'CON-2026-00001'}"
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate


@frappe.whitelist()
def create_subscription(contract):
    doc = frappe.get_doc("Contract", contract)

    merchant = doc.get("merchant") or _customer_from_party(doc)
    if not merchant:
        frappe.throw(_("Set the Merchant on this contract first."))

    existing = frappe.db.get_value("Merchant Subscription", {
        "contract": contract, "status": ["!=", "Cancelled"],
    })
    if existing:
        frappe.throw(
            _("{0} already bills this contract. Amend it directly — creating a second "
              "subscription would double-bill the merchant.").format(
                  frappe.utils.get_link_to_form("Merchant Subscription", existing))
        )

    rates = doc.get("agreed_rates") or []
    if not rates:
        frappe.throw(_("This contract has no agreed rates, so there is nothing to bill."))

    items, unpriced = [], []
    for rate in rates:
        plan = _plan_for(rate.item)
        if not plan:
            unpriced.append(rate.item)
            continue
        items.append({
            "plan": plan,
            "qty": 1,
            "rate_override": flt(rate.agreed_rate),
            "effective_from": rate.effective_from or doc.start_date or nowdate(),
            "note": f"Rate taken from {contract} at creation.",
        })

    if not items:
        frappe.throw(
            _("No billing plan exists for {0}. A plan defines how a charge is priced; "
              "the contract only says what was agreed.").format(", ".join(unpriced))
        )

    subscription = frappe.get_doc({
        "doctype": "Merchant Subscription",
        "merchant": merchant,
        "contract": contract,
        "status": "Active",
        "start_date": doc.start_date or nowdate(),
        "end_date": doc.end_date,
        "billing_day": 1,
        "prorate": 1,
        "items": items,
        "notes": f"Created from {contract}. Rates copied from the agreed terms.",
    }).insert(ignore_permissions=True)

    if unpriced:
        # Reported rather than invented. Creating a plan here would guess at a
        # billing model, and a flat guess against a tiered charge bills wrongly
        # and quietly.
        frappe.msgprint(
            _("Created without {0} — no billing plan exists for those items yet.").format(
                ", ".join(f"<b>{i}</b>" for i in unpriced)),
            title=_("Partially created"), indicator="orange",
        )

    return subscription.name


@frappe.whitelist()
def subscription_for(contract):
    """Lets the form show the link rather than offer to create a duplicate."""
    return frappe.db.get_value("Merchant Subscription", {
        "contract": contract, "status": ["!=", "Cancelled"],
    })


def _plan_for(item):
    return frappe.db.get_value("Merchant Billing Plan", {"item": item})


def _customer_from_party(doc):
    if doc.get("party_type") == "Customer" and doc.get("party_name"):
        return doc.party_name
    return frappe.db.get_value("Customer", {"name": doc.get("party_name")})
