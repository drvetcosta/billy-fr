# Changelog

## 0.4.1

### Explicit bill payment status

- Added an explicit **Bolletta pagata** checkbox to the add/edit form.
- New bills default to unpaid until the checkbox is selected.
- Existing v0.4.0 and older bills migrate as unpaid when no explicit status exists; editing them does not mark them paid automatically.
- Recent bills show a green checkmark only when they are marked paid.
- “Pagata da” is now treated as the configured payer/advance owner, independently from the paid/unpaid status.
- Only paid bills affect payer balances and outstanding split debts.
- The **Pagamenti** monthly series and “Pagato questo mese” summary include only bills explicitly marked paid.
- Forecasting and normalized competence costs continue to use the bill history regardless of payment status.
- Storage schema upgraded to v5.

## 0.4.0

### Bill splitting and payers

- Added persistent payer profiles managed from **Settings → Devices & services → Bill Tracker → Configure**.
- Each payer can have a default split share, PayPal.Me username/link and active/disabled state.
- Each bill type can define a default payer.
- Every bill can override both the payer and the percentage split.
- Added automatic netting: Billy calculates the minimum outstanding transfers between payers instead of showing reciprocal debts separately.
- Added **Pay with PayPal** links with the outstanding EUR amount pre-filled through PayPal.Me.
- Added **Mark as settled** and persistent settlement history.
- Settlements can be removed to recalculate the balance after a mistake.
- Payers referenced by history cannot be deleted accidentally; they can be disabled instead.

### Dashboard and chart

- Added an outstanding-balance panel to the Lovelace card.
- Added payer/split information to recent bill rows.
- Monthly bars are now stacked by bill type, with a stable color per category and percentage details in SVG tooltips.
- Bill type settings now include a chart color.
- Default Sections width is now `full`; numeric widths remain supported.
- Updated the visual card editor to include full-width mode.

### Data model

- Storage schema upgraded to v4.
- v0.3 databases are migrated automatically. Existing bills remain intact and are left unassigned to payers until edited, avoiding invented historical splits.
- Existing recurrence, competence-period, normalized-cost and forecast features are preserved.

## 0.3.0

- Added centrally managed bill types.
- Added monthly, bimonthly, quarterly, four-monthly, half-yearly and yearly recurrences.
- Added competence periods and normalized monthly costs.
- Added category-aware forecasts and upcoming bills.
- Added HACS-ready frontend packaging.
