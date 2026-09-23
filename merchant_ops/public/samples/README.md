# Statement samples

Four files. `residual-statement-template.csv` is the blank template to hand a
client; the other three are worked examples used by `merchant_ops.demo.load`.

Each one exercises a different real-world awkwardness, because a parser that
only reads the file it was written against is not worth shipping:

| File | Delimiter | What it tests |
|---|---|---|
| `fiserv-2026-08-residual.csv` | comma | Two title lines above the header, quoted thousands separators, a signed figure, a TOTAL row that must not become a data row |
| `tsys-2026-08-residual.csv` | semicolon | Entirely different column names, a parenthesised negative adjustment, and four MIDs of which two are on no merchant record |
| `elavon-2026-08-residual.csv` | tab | Third naming convention again, and a live merchant absent from the file |

Column headings are matched through the alias table in
`merchant_ops/statement_parser.py`, lowercased with punctuation removed. Adding a
processor is normally a few new aliases rather than new code.

## What each file is meant to demonstrate

- **Fiserv** imports cleanly. Every MID resolves; the document ends `Imported`.
- **TSYS** ends `Partially Mapped` with two unmapped rows, and the import raises
  one `Unmapped MID` revenue exception carrying their combined value. This is
  residual revenue that arrived and cannot be attributed to anyone.
- **Elavon** imports cleanly — both MIDs map — but Harbour Point Dental is an
  active Elavon merchant with no line on the statement. Nothing about the import
  looks wrong. The nightly sweep is what finds it, as a `Missing Residual`
  exception.

That last case is the argument for the sweep: a leak where no single document is
incorrect cannot be caught by validating documents.


## A note on the names

Every merchant across these files is US small business, name plus trade, because
the instance represents a US merchant services company. It is worth stating
because the first draft of the Elavon file used Ghanaian place names carried
over from an analogy in the project notes, and a single out-of-register name in
a demo does more damage than a missing feature: it makes a reader wonder what
else was not thought about.

Lakebridge and Orchard Lane appear on the TSYS statement and deliberately do not
exist as merchants. They are the unmapped-MID case, and they have to look like
plausible merchants for that case to land.
