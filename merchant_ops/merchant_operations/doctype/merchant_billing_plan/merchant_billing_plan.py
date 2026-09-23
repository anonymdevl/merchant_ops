import frappe
from frappe.model.document import Document
from frappe.utils import flt


class MerchantBillingPlan(Document):
    """How one charge is priced.

    Four models, because merchant services pricing is not one shape:

        Flat     a fixed amount per period
        Tiered   each band charged at its own rate, like income tax
        Volume   the whole quantity charged at the rate of the band it lands in
        Usage    quantity times rate, with no bands

    Tiered and Volume are routinely confused and produce different numbers on
    the same tier table, which is why both exist here and the field carries a
    description rather than assuming the reader knows.
    """

    def validate(self):
        self._sort_tiers()
        self._check_bands()

    def _sort_tiers(self):
        if not self.tiers:
            return
        for index, tier in enumerate(sorted(self.tiers, key=lambda t: flt(t.from_qty)), start=1):
            tier.idx = index

    def _check_bands(self):
        if self.billing_model not in ("Tiered", "Volume"):
            return
        if not self.tiers:
            frappe.throw(f"A {self.billing_model} plan needs at least one tier.")

        previous_to = None
        for tier in sorted(self.tiers, key=lambda t: flt(t.from_qty)):
            if previous_to is not None and flt(tier.from_qty) > previous_to + 0.0001:
                frappe.throw(
                    f"Gap in the tier table between {previous_to:,.0f} and "
                    f"{flt(tier.from_qty):,.0f}. A quantity landing in the gap would "
                    f"be billed nothing."
                )
            if tier.to_qty and flt(tier.to_qty) <= flt(tier.from_qty):
                frappe.throw(f"Tier {tier.idx}: 'To' must be above 'From'.")
            previous_to = flt(tier.to_qty) if tier.to_qty else None

        if previous_to is not None:
            frappe.throw(
                "The last tier must be open-ended — leave its 'To' blank. Otherwise a "
                "merchant above the top band is billed nothing at all."
            )

    def charge_for(self, quantity):
        """Returns (amount, explanation). The explanation is shown on the invoice line."""
        quantity = flt(quantity)

        if self.billing_model == "Flat":
            return flt(self.base_rate), "Flat"

        if self.billing_model == "Usage":
            return flt(self.base_rate) * quantity, f"{quantity:,.0f} × {flt(self.base_rate):,.4f}"

        bands = sorted(self.tiers, key=lambda t: flt(t.from_qty))

        if self.billing_model == "Volume":
            for tier in bands:
                upper = flt(tier.to_qty) if tier.to_qty else float("inf")
                if flt(tier.from_qty) <= quantity <= upper:
                    amount = flt(tier.flat_fee) + flt(tier.rate) * quantity
                    return amount, f"{quantity:,.0f} all at {flt(tier.rate):,.4f}"
            return 0.0, "No band matched"

        # Tiered
        total, detail, remaining = 0.0, [], quantity
        for tier in bands:
            if remaining <= 0:
                break
            upper = flt(tier.to_qty) if tier.to_qty else float("inf")
            band_size = upper - flt(tier.from_qty)
            units = min(remaining, band_size)
            if units <= 0:
                continue
            total += flt(tier.flat_fee) + flt(tier.rate) * units
            detail.append(f"{units:,.0f} @ {flt(tier.rate):,.4f}")
            remaining -= units

        return total, " + ".join(detail) or "Nothing billable"
