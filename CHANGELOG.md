# Changelog

## 0.3.0

- Added configurable bill types stored in the Bill Tracker database.
- Added native **Configure** flow in Home Assistant for adding, editing, disabling and deleting unused bill types.
- Added recurrence per bill type: monthly, every 2/3/4/6 months, or yearly.
- Default Water recurrence is bimonthly; TARI / Waste is yearly.
- Disabled bill types disappear from the add-bill selector without losing history.
- Existing v0.1/v0.2 data is migrated automatically to the new category-id based schema.
- Added payment month and competence period (`from` / `to`) for each bill.
- Competence period is automatically prefilled from the bill type recurrence and remains editable.
- Added normalized monthly cost view that spreads multi-month/yearly bills across their competence months.
- Forecast is now category-aware: each bill type follows its own recurrence and amount history.
- Added upcoming estimated bills list.
- Forecast horizon is configurable from 1 to 24 months.
- Card width is configurable from 1 to 12 Section columns through the graphical card editor.
- Added automatic refresh when Bill Tracker data/settings change.
- Dashboard card remains dependency-free; ApexCharts is not required.

## 0.2.0

- HACS-ready single integration package.
- Bundled Lovelace card served by the integration.
- Built-in actual-vs-forecast chart.

## 0.1.0

- Initial proof of concept.
