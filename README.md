# Billy — Home Assistant Bill Tracker

Billy is a HACS custom integration for keeping a persistent history of household bills directly in Home Assistant. It supports recurring bills, competence periods, normalized monthly costs, forecasts and bill splitting between multiple payers.

## v0.4.3 features

- **Bollette da pagare** sums only unpaid bills; paid bills are excluded from this balance. Split reimbursements between payers are tracked separately.

### Complete bill history

The dashboard keeps the compact **Ultime bollette** list and adds a **Tutte le bollette** button. The complete list can be filtered by bill type. Every bill has an interactive checkmark: click it to mark the bill paid or unpaid immediately, without opening the edit form.

### Bills and forecasts

- Add, edit and delete bills from a Lovelace card.
- Payment month and separate competence period.
- Persistent storage through Home Assistant `Store` (`.storage`), independent from Recorder retention.
- Recurrences: monthly, bimonthly, quarterly, every 4 months, every 6 months and yearly.
- Category-aware forecast based on each bill type's recurrence and recent amounts.
- **Payments** and **Monthly cost** chart modes.
- Stacked monthly bars: each bill type has its own color, so the visual impact of each expense is immediately visible.

### Split bills

Manage payers from:

**Settings → Devices & services → Bill Tracker → Configure**

For each payer you can save:

- name;
- default split share;
- PayPal.Me username or full link;
- active/disabled state.

The shares act as weights and are normalized to 100% for new bills. For example, two active payers with shares `50` and `50` get a 50/50 split; `70` and `30` gives a 70/30 split.

For each bill type you can also choose a **default payer**. When adding a bill, Billy preselects that payer and the default split, but both can be overridden on the individual bill.

Billy calculates a net balance between payers. If one person paid most bills while the other paid some smaller ones, reciprocal debts are automatically netted into the minimum transfer required to settle the account.

When the creditor has PayPal.Me configured, the dashboard shows **Pay with PayPal** and opens PayPal.Me with the exact outstanding EUR amount already filled in. Billy does not verify the external PayPal payment; use **Mark as settled** after the payment is completed.

Settlement history is stored locally and can be reversed if it was recorded by mistake.


### Payment status

Every bill has an explicit **Paid** checkbox. The configured payer and the payment status are independent: selecting a payer does not automatically mark the bill as paid. New bills are unpaid by default, and older databases migrate missing payment status as unpaid. Only paid bills contribute to split balances and the Payments cash-flow view. Paid entries show a checkmark in the recent-bills list.

## HACS installation

1. Open **HACS**.
2. Open **Custom repositories**.
3. Add `https://github.com/robin994/billy` as an **Integration**.
4. Install Billy / Bill Tracker.
5. Restart Home Assistant.
6. Open **Settings → Devices & services → Add integration**.
7. Search for **Bill Tracker** and add it.
8. Hard-refresh the Home Assistant frontend after the first installation/update if the card is cached.

The integration serves `bill-tracker-card.js` automatically; nothing needs to be copied to `/config/www`.

## Configure payers and bill types

Open **Settings → Devices & services → Bill Tracker → Configure**.

Recommended first setup for a couple:

1. Add payer A with default share `50` and their PayPal.Me if they should receive reimbursements through PayPal.
2. Add payer B with default share `50` and their PayPal.Me.
3. Edit each bill type and select its usual default payer.
4. Optionally customize the chart color for each type.

Existing v0.3 bills are preserved during migration. They are intentionally not assigned to a payer automatically because Billy cannot safely infer who paid historical entries. Edit an old bill if you want it included in split calculations.

## Dashboard card

The card appears in the picker as **Billy - Bill Tracker**. It can also be added manually:

```yaml
type: custom:bill-tracker-card
title: Bollette di casa
columns: full
recent: 10
history_months: 12
forecast_months: 12
```

`columns: full` requests the whole available Home Assistant Sections width. Numeric values are also supported.

If the dashboard already saved explicit Sections layout metadata, Home Assistant's own `grid_options` may override the card default. In that case set the card's layout to full width from the dashboard layout controls or YAML.

## PayPal.Me

You can enter either a PayPal.Me username or a full PayPal.Me URL in the payer settings. Billy stores only the PayPal.Me handle and builds links in this form:

`https://paypal.me/<handle>/<amount>EUR`

The user still confirms and completes the payment on PayPal. No PayPal credentials, API keys or payment data are stored by Billy.

## Migration

Storage schema v4 automatically migrates v0.3 data. Bill history, categories, recurrence and competence periods are preserved. Historical bills without payer information remain excluded from split balances until edited.

## Requirements

- Home Assistant 2026.3.0 or newer.
- HACS is recommended for installation and updates.

## Validation

The repository includes GitHub Actions for HACS validation and Home Assistant Hassfest validation.

## License

MIT
