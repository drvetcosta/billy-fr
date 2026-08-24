# Billy — Home Assistant Bill Tracker

Billy is a HACS custom integration for keeping a persistent history of household bills directly in Home Assistant. It supports recurring bills, competence periods, normalized monthly costs, forecasts and bill splitting between multiple payers.

## v0.4.5 features

- **Bollette da pagare** sums only unpaid bills; paid bills are excluded from this balance. Split reimbursements between payers are tracked separately.

### Complete bill history

The dashboard keeps the compact **Ultime bollette** list and adds a **Tutte le bollette** button. The full history opens in a paginated modal and can be filtered by bill type, by a single year, or by an arbitrary month/year range. Every row has an interactive checkmark to mark the bill paid or unpaid without opening the edit form.

### Bills and forecasts

- Add, edit and delete bills from a Lovelace card.
- Edit bills in a modal without leaving the current all-bills filter.
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

Billy calculates the outstanding split balance from **unpaid bills only**. For each unpaid bill, the configured payer is the person who advanced the bill and each other participant owes their configured share. Opposite-direction bills between the same two people are netted together. Paid bills never contribute to the current balance.

When the creditor has PayPal.Me configured, the dashboard shows **Pay with PayPal** and opens PayPal.Me with the exact outstanding EUR amount already filled in. After the external payment, use **Segna saldato**. Billy then marks every unpaid bill included in that displayed balance as paid, so their checkmarks update and the balance becomes zero.

Settlement history stores the linked bill IDs. Reversing a settlement reopens those linked bills as unpaid.


### Payment status

Every bill has an explicit **Paid** checkbox. The configured payer and the payment status are independent: selecting a payer does not automatically mark the bill as paid. New bills are unpaid by default, and older databases migrate missing payment status as unpaid. **Only unpaid bills contribute to the outstanding split balance**; marking a bill paid removes it from that balance. Paid entries show a checkmark in recent and complete-history lists. The Payments chart continues to show bills marked paid.

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

Storage schema v6 automatically migrates older Billy data. Bill history, categories, recurrence and competence periods are preserved. Historical bills without payer information remain excluded from split balances until edited.

## Requirements

- Home Assistant 2026.3.0 or newer.
- HACS is recommended for installation and updates.

## Validation

The repository includes GitHub Actions for HACS validation and Home Assistant Hassfest validation.

## License

MIT
