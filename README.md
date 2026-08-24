# Home Assistant Bill Tracker

Billy Tracker is a HACS custom integration for keeping a persistent history of household bills directly in Home Assistant. It supports recurring bills with different frequencies, competence periods, normalized monthly costs and category-aware forecasts.

## v0.3.0 features

- Add, edit and delete bills from a Lovelace card.
- Payment month and separate competence period.
- Persistent storage through Home Assistant `Store` (`.storage`), independent from Recorder retention.
- Bill types are managed centrally from **Settings → Devices & services → Bill Tracker → Configure**.
- Add your own bill types at any time.
- Recurrence per bill type:
  - monthly (1 month)
  - bimonthly (2 months)
  - quarterly (3 months)
  - every 4 months
  - every 6 months
  - yearly (12 months)
- Enable/disable a bill type without deleting its history.
- A bill type with history cannot be deleted accidentally; disable it instead.
- Existing v0.1/v0.2 databases are migrated automatically.
- Two chart modes:
  - **Payments**: when money was actually paid.
  - **Monthly cost**: spreads a multi-month/yearly bill across its competence months.
- Category-aware forecast: each bill is forecast using its own recurrence and recent amounts.
- Upcoming estimated bills list.
- Configurable forecast horizon (1–24 months).
- Configurable dashboard width (1–12 Section columns).
- No ApexCharts dependency.

## HACS installation

1. Open **HACS**.
2. Open the menu and choose **Custom repositories**.
3. Add:

   `https://github.com/robin994/HomeAssistant-Bill-Tracker`

4. Repository type: **Integration**.
5. Install **Bill Tracker**.
6. Restart Home Assistant.
7. Open **Settings → Devices & services → Add integration**.
8. Search for **Bill Tracker** and add it.
9. Hard-refresh the Home Assistant frontend after the first installation/update if the custom card is still cached.

The integration serves and loads `bill-tracker-card.js` automatically; nothing needs to be copied to `/config/www`.

## Configure bill types

Open:

**Settings → Devices & services → Bill Tracker → Configure**

From there you can:

- add a new bill type;
- choose its recurrence;
- choose whether it appears in the **Add bill** dropdown;
- rename it;
- change its recurrence;
- disable it while keeping all previous bills;
- delete it if it has never been used.

Default examples include Internet, Electricity, Water, Gas, Condominium, Phone, TARI / Waste and Other. Water defaults to every 2 months and TARI / Waste to yearly.

## Dashboard card

The card appears in the card picker as **Bill Tracker**. You can also add it manually:

```yaml
type: custom:bill-tracker-card
title: Bollette di casa
columns: 12
recent: 10
history_months: 12
forecast_months: 12
```

The graphical card editor lets you choose:

- title;
- width from 1 to 12 Section columns;
- number of recent bills displayed;
- history months shown in the chart;
- forecast horizon.

## Adding a bill

Press **+ Add bill** and choose:

- bill type;
- payment month;
- amount;
- competence start/end;
- optional note.

The competence range is prefilled from the type recurrence. For example, a bimonthly Water bill paid in August is initially assigned to July–August, while a yearly bill gets a 12-month competence range. You can edit the range before saving.

## Forecast model

Forecasting is performed separately for each enabled bill type:

1. Bill Tracker finds the most recent payment for that type.
2. The configured recurrence determines the next expected payment month(s).
3. The amount is estimated from recent bills of the same type with a conservative trend correction.
4. Category estimates are combined into the monthly forecast.

This means a yearly TARI bill can create an expected yearly peak without being incorrectly treated as a monthly payment.

The **Monthly cost** view also estimates a normalized recurring cost by dividing each expected bill by its recurrence interval.

Forecasts are indicative estimates, not guaranteed future charges.

## Requirements

- Home Assistant 2026.3.0 or newer.
- HACS is recommended for installation and updates.

## Validation

The repository includes GitHub Actions for:

- HACS validation;
- Home Assistant Hassfest validation.

## License

MIT
