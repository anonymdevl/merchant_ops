"""NACHA return code policy.

A failed debit comes back with a return code, and the code decides what you are
permitted to do next — not merely what is worth doing. Re-presenting a debit the
rules forbid is a compliance problem rather than a wasted attempt, so retry
eligibility is data here rather than a condition scattered through the scheduler.

Two families:

    FUNDS   the money was not there. Re-presentment is allowed, capped at two
            further attempts within 180 days of the original settlement date.
    AUTHORITY / ACCOUNT
            the account or the mandate is the problem. No re-presentment at
            all, and the mandate must stop being used.

Codes absent from this table are treated as non-retriable. Failing closed is the
only safe default: an unrecognised code is more likely to be an authority
problem than a funds problem, and the cost of a wrong retry is asymmetric.
"""

FUNDS = "Funds"
AUTHORITY = "Authority"
ACCOUNT = "Account"

# code -> (family, description, retriable, kill the mandate?)
RETURN_CODES = {
    "R01": (FUNDS, "Insufficient funds", True, False),
    "R09": (FUNDS, "Uncollected funds — deposits not yet cleared", True, False),
    "R02": (ACCOUNT, "Account closed", False, True),
    "R03": (ACCOUNT, "No account or unable to locate account", False, True),
    "R04": (ACCOUNT, "Invalid account number", False, True),
    "R16": (ACCOUNT, "Account frozen", False, True),
    "R20": (ACCOUNT, "Non-transaction account", False, True),
    "R07": (AUTHORITY, "Authorisation revoked by the customer", False, True),
    "R08": (AUTHORITY, "Payment stopped", False, True),
    "R10": (AUTHORITY, "Customer advises originator is not authorised", False, True),
    "R11": (AUTHORITY, "Customer advises entry not in accordance with the terms", False, True),
    "R29": (AUTHORITY, "Corporate customer advises not authorised", False, True),
}

MAX_REPRESENTMENTS = 2
RETRY_AFTER_DAYS = 4


def describe(code):
    return RETURN_CODES.get((code or "").upper().strip())


def is_retriable(code, prior_attempts=0):
    """Whether another debit may be presented for this code.

    prior_attempts counts failed attempts already made against the same invoice,
    because the cap is on re-presentments of a debit, not on codes seen.
    """
    entry = describe(code)
    if not entry:
        return False
    family, _label, retriable, _kill = entry
    return bool(retriable) and prior_attempts < MAX_REPRESENTMENTS


def should_disable_mandate(code):
    entry = describe(code)
    return bool(entry and entry[3])


def family(code):
    entry = describe(code)
    return entry[0] if entry else AUTHORITY


def label(code):
    entry = describe(code)
    return entry[1] if entry else "Unrecognised return code"


def options():
    """Select field options, ordered so the two retriable codes come first."""
    ordered = sorted(RETURN_CODES, key=lambda c: (not RETURN_CODES[c][2], c))
    return "\n".join([""] + ordered)
