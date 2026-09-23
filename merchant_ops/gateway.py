"""The boundary between this platform and anything that moves money.

Every outbound call goes through `call()`. That is the whole point: one place
that stamps the idempotency key, applies the timeout, retries transport
failures, and writes a Gateway Request Log row whichever way it ends. A second
code path that talks to a processor directly would be a second place for a
duplicate debit to originate.

Test mode never opens a socket. It derives its answer from the idempotency key,
so the same attempt always produces the same outcome and a demo can be
rehearsed and repeated. That is a stand-in for the processor, not a stand-in
for the integration: the logging, retry, idempotency and error handling around
it are the real implementations and do not change when a base URL is filled in.

    bench --site <site> execute merchant_ops.gateway.collect --kwargs "{'attempt':'PAY-ATT-00001'}"
    bench --site <site> execute merchant_ops.gateway.ping
"""

import hashlib
import json
import time

import frappe
from frappe.utils import flt

from merchant_ops import ach

# Codes the test gateway can return, weighted the way a real ACH file looks:
# insufficient funds dominates, everything else is occasional.
TEST_CODES = ["R01"] * 6 + ["R09"] * 2 + ["R02", "R03", "R07", "R08"]

RETRIABLE_STATUS = {408, 429, 500, 502, 503, 504}


class GatewayError(Exception):
    pass


def settings():
    return frappe.get_cached_doc("Gateway Settings")


def ping():
    """Proves the layer is wired without touching a payment."""
    return call("ping", {"hello": "merchant_ops"}, idempotency_key="ping")


def collect(attempt):
    """Presents one Payment Attempt and records the outcome.

    The attempt's own idempotency key is used unchanged. Re-running this for an
    attempt already presented reaches the gateway as the same request, and a
    real gateway answers with the original result rather than debiting twice.
    """
    doc = frappe.get_doc("Payment Attempt", attempt)

    if doc.status in ("Succeeded", "Failed"):
        return {"attempt": doc.name, "status": doc.status, "note": "Already presented."}

    response = call(
        "collect",
        {
            "amount": flt(doc.amount),
            "currency": doc.currency or "USD",
            "method": doc.method,
            "merchant": doc.merchant,
            "invoice": doc.sales_invoice,
        },
        idempotency_key=doc.idempotency_key,
        reference=doc,
    )

    from merchant_ops.collections import settle

    return settle(
        doc.name,
        outcome="Succeeded" if response.get("approved") else "Failed",
        return_code=response.get("return_code"),
        reference=response.get("reference"),
    )


# --- the one door out ----------------------------------------------------

def call(operation, payload, idempotency_key=None, reference=None):
    config = settings()
    if not config.enabled:
        frappe.throw("Gateway Settings is disabled.")

    key = idempotency_key or _derive_key(operation, payload)
    started = time.monotonic()
    attempts, status_code, error = 0, None, None
    response = None

    max_attempts = max(1, int(config.max_attempts or 1))

    while attempts < max_attempts:
        attempts += 1
        try:
            if config.mode == "Test":
                status_code, response = _test_call(config, operation, payload, key)
            else:
                status_code, response = _live_call(config, operation, payload, key)

            if status_code in RETRIABLE_STATUS and attempts < max_attempts:
                # Transport failure, not a decision. Safe to repeat only
                # because the key is stable across attempts.
                time.sleep(flt(config.backoff_seconds or 1) * (2 ** (attempts - 1)))
                continue
            error = None
            break

        except Exception as exc:
            error = str(exc)
            if attempts >= max_attempts:
                break
            time.sleep(flt(config.backoff_seconds or 1) * (2 ** (attempts - 1)))

    duration = int((time.monotonic() - started) * 1000)
    _log(config, operation, key, payload, response, status_code, duration,
         attempts, error, reference)

    if error:
        raise GatewayError(f"{operation} failed after {attempts} attempt(s): {error}")
    return response or {}


def _derive_key(operation, payload):
    seed = f"{operation}:{json.dumps(payload, sort_keys=True, default=str)}"
    return hashlib.sha256(seed.encode()).hexdigest()[:32]


# --- adapters ------------------------------------------------------------

def _test_call(config, operation, payload, key):
    if operation == "ping":
        return 200, {"ok": True, "mode": "Test", "provider": config.provider}

    if config.forced_return_code:
        code = config.forced_return_code.upper().strip()
        return 200, _declined(code, key)

    if config.test_behaviour == "Always Succeed":
        return 200, _approved(key)
    if config.test_behaviour == "Always Fail":
        return 200, _declined("R01", key)

    # Deterministic: the key decides, so the same attempt always lands the
    # same way and a rehearsed demo does not change under the client's eyes.
    bucket = int(key[:8], 16) % 100
    if bucket >= flt(config.failure_rate or 0):
        return 200, _approved(key)
    return 200, _declined(TEST_CODES[int(key[8:12], 16) % len(TEST_CODES)], key)


def _live_call(config, operation, payload, key):
    import requests

    url = f"{config.base_url.rstrip('/')}/{operation}"
    reply = requests.post(
        url,
        json=payload,
        timeout=int(config.timeout or 20),
        headers={
            "Authorization": f"Bearer {config.get_password('api_key')}",
            "Idempotency-Key": key,
            "Content-Type": "application/json",
        },
    )
    try:
        body = reply.json()
    except ValueError:
        body = {"raw": reply.text[:2000]}
    return reply.status_code, body


def _approved(key):
    return {"approved": True, "reference": f"TST-{key[:12].upper()}", "return_code": None}


def _declined(code, key):
    return {
        "approved": False,
        "reference": f"TST-{key[:12].upper()}",
        "return_code": code,
        "return_label": ach.label(code),
    }


# --- the trail -----------------------------------------------------------

def _log(config, operation, key, payload, response, status_code, duration,
         attempts, error, reference):
    """Written whichever way the call ended, including when it threw.

    A log that only records successes answers none of the questions anyone
    actually asks it.
    """
    try:
        entry = frappe.new_doc("Gateway Request Log")
        entry.operation = operation
        entry.mode = config.mode
        entry.idempotency_key = key
        entry.attempts = attempts
        entry.duration_ms = duration
        entry.status_code = status_code or 0
        entry.endpoint = (f"{config.base_url}/{operation}"
                          if config.mode == "Live" and config.base_url
                          else f"test://{config.provider}/{operation}")

        if error:
            entry.status = "Error"
            entry.error = error[:2000]
        elif response and response.get("approved") is False:
            entry.status = "Failed"
        else:
            entry.status = "Success"

        if config.log_payloads:
            entry.request_body = json.dumps(payload, indent=1, default=str)
            entry.response_body = json.dumps(response, indent=1, default=str)

        if reference is not None:
            entry.reference_doctype = reference.doctype
            entry.reference_name = reference.name

        entry.insert(ignore_permissions=True)
    except Exception:
        # The log must never be the reason a payment path fails.
        frappe.log_error(title="merchant_ops: could not write the gateway log")
