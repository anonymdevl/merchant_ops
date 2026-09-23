# Interface conventions

Every screen this app adds is built from `css/kit.css` and `js/kit.js`. If you
are adding a page, start there — not from a copy of another page's markup.

## Why a kit at all

Two pages that look almost the same are worse than two that look nothing alike,
because the near-miss reads as carelessness. The kit exists so that the
resemblance is structural rather than remembered.

It also prevents a specific failure this app already had once. The Merchant
Focus styles were appended to the console's stylesheet reusing its class names,
and because they came later in the file they silently overrode the console's
table padding. Text ended up against the card edge on a page nobody had
touched. Everything in the kit is prefixed `mok-` for that reason.

## The components

| Builder | What it is |
|---|---|
| `kit.page(page, {eyebrow, title, blurb, meta})` | The page shell and header. Returns the body to append to |
| `kit.tiles([...])` | Stat tiles. Column count is chosen from how many you pass |
| `kit.card({title, subtitle, figure, sections})` | A record card with any number of titled tables |
| `kit.table({title, head, rows, cells, onRow})` | A titled table. Returns `""` when empty |
| `kit.empty(message)` | The empty state |

Formatters — `money`, `date`, `link`, `pill`, `age` — exist so that a figure is
rendered the same way on every screen. A page that formats its own currency
will drift from the rest within one release.

## Rules worth keeping

**Colour means something is wrong.** A tile is neutral until its number needs
attention; an age is plain text until it crosses a threshold. Colouring every
row trains people to stop seeing the colour, which costs you the one case that
mattered.

**Escape anything that came from data.** Merchant names and DBA names arrive
from processor statement files. `kit.esc()` is applied inside the builders; if
you assemble markup yourself, apply it.

**Tokens, not literals.** Colours resolve against Frappe's own CSS variables
with a fallback, so the kit follows the desk into dark mode instead of fighting
it. A hardcoded `#fff` will look correct until someone switches theme.

**A custom page still needs a width.** Frappe gives a Page the full viewport
with no gutters, which reads as unfinished on a wide monitor. `.mok` sets a
max width and centres.

## List views

The doctype list views are standard Frappe, improved through
`*_list.js` rather than replaced: indicators that say what the row's state is,
and a default filter and sort where the queue has an obvious reading order.
Replacing a list view costs you the filters, the bulk actions, the keyboard
shortcuts and the export, none of which are worth losing for a nicer row.
