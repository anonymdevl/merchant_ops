"""Reads a processor residual statement into structured rows.

Processors do not agree on column headings. Fiserv exports SALES_VOLUME where
TSYS exports GROSS_VOLUME and Elavon exports "Volume"; all three mean the same
thing. Rather than one parser per processor, headings are normalised through an
alias table, so a new processor is usually a few extra aliases rather than new
code.
"""

import csv
import io
import re

from frappe.utils import flt, cint

# Canonical field -> headings seen in the wild. Compared lowercased with
# non-alphanumerics stripped, so "Net Residual", "NET_RESIDUAL" and
# "net-residual" all collapse to the same key.
ALIASES = {
    "mid": ["mid", "merchantnumber", "merchantid", "merchantaccount", "outletmid"],
    "dba_name": ["dbaname", "dba", "merchantname", "businessname", "outletname"],
    "sales_volume": ["salesvolume", "grossvolume", "volume", "processingvolume", "bankcardvolume"],
    "sales_count": ["salescount", "transactioncount", "txncount", "items", "trancount"],
    "income": ["income", "grossincome", "revenue", "grossresidual"],
    "expense": ["expense", "expenses", "cost", "interchange", "totalexpense"],
    "net_residual": ["netresidual", "net", "residual", "netincome", "agentresidual"],
    "split_pct": ["splitpct", "split", "splitpercent", "sharepct", "residualsplit"],
    "agent_code": ["agentcode", "agent", "office", "officecode", "repcode"],
}

_NORM = re.compile(r"[^a-z0-9]")


def _norm(value):
    return _NORM.sub("", (value or "").lower())


def _money(value):
    """Statements bring currency symbols, thousands separators and (123.45) for negatives."""
    text = str(value or "").strip()
    if not text:
        return 0.0
    negative = text.startswith("(") and text.endswith(")")
    text = re.sub(r"[^0-9.\-]", "", text)
    if not text or text in {"-", "."}:
        return 0.0
    amount = flt(text)
    return -amount if negative else amount


def build_header_map(header_row):
    """Maps column index -> canonical fieldname. Unrecognised columns are ignored."""
    lookup = {}
    for canonical, variants in ALIASES.items():
        for variant in variants:
            lookup[variant] = canonical

    mapping = {}
    for index, cell in enumerate(header_row):
        canonical = lookup.get(_norm(cell))
        if canonical and canonical not in mapping.values():
            mapping[index] = canonical
    return mapping


def parse(content):
    """Returns (rows, warnings). Rows are plain dicts; nothing is written here.

    Kept free of Frappe document calls so it can be unit tested against a
    statement file without a site.
    """
    warnings = []
    text = content.decode("utf-8-sig", errors="replace") if isinstance(content, bytes) else content

    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.reader(io.StringIO(text), dialect)
    table = [row for row in reader if any((cell or "").strip() for cell in row)]
    if not table:
        return [], ["The file is empty."]

    # Portal exports often carry a title line or two above the real header.
    header_index, mapping = None, {}
    for index, row in enumerate(table[:10]):
        candidate = build_header_map(row)
        if "mid" in candidate.values():
            header_index, mapping = index, candidate
            break

    if header_index is None:
        return [], ["No MID column found. Check the file is the residual statement "
                    "rather than a transaction detail export."]

    missing = [f for f in ("net_residual",) if f not in mapping.values()]
    if missing:
        warnings.append("No net residual column found; net will be derived from income less expense.")

    rows = []
    for line in table[header_index + 1:]:
        record = {}
        for index, canonical in mapping.items():
            if index < len(line):
                record[canonical] = line[index]

        mid = str(record.get("mid") or "").strip()
        if not mid or _norm(mid) in {"total", "totals", "grandtotal"}:
            continue

        income = _money(record.get("income"))
        expense = _money(record.get("expense"))
        net = _money(record.get("net_residual")) if "net_residual" in record else 0.0
        if not net:
            net = income - expense

        rows.append({
            "mid": mid,
            "dba_name": (record.get("dba_name") or "").strip(),
            "sales_volume": _money(record.get("sales_volume")),
            "sales_count": cint(_money(record.get("sales_count"))),
            "income": income,
            "expense": expense,
            "net_residual": net,
            "split_pct": _money(record.get("split_pct")),
            "agent_code": (record.get("agent_code") or "").strip(),
        })

    if not rows:
        warnings.append("Header found but no data rows followed it.")
    return rows, warnings
