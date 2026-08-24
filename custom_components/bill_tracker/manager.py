"""Persistent data model and forecasting for Bill Tracker."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime
from math import isfinite
from statistics import mean
from typing import Any
from uuid import uuid4

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DEFAULT_CATEGORIES,
    EVENT_UPDATED,
    STORAGE_KEY,
    STORAGE_SCHEMA_VERSION,
    STORAGE_VERSION,
    SUPPORTED_INTERVALS,
)


class BillTrackerManager:
    """Persistent bill store, categories and aggregation logic."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.expenses: list[dict[str, Any]] = []
        self.categories: list[dict[str, Any]] = []

    async def async_load(self) -> None:
        """Load and migrate the persistent database."""
        data = await self._store.async_load() or {}
        self.categories = [dict(x) for x in data.get("categories", [])]
        self.expenses = [dict(x) for x in data.get("expenses", [])]

        changed = False
        if not self.categories:
            self.categories = deepcopy(DEFAULT_CATEGORIES)
            changed = True

        changed |= self._normalize_categories()
        changed |= self._migrate_expenses()
        self._sort()

        if changed or data.get("schema_version") != STORAGE_SCHEMA_VERSION:
            await self._save()

    # ---------------------------------------------------------------------
    # Categories
    # ---------------------------------------------------------------------
    def category(self, category_id: str) -> dict[str, Any] | None:
        """Return a category by id."""
        return next((x for x in self.categories if x.get("id") == category_id), None)

    def category_by_name(self, name: str) -> dict[str, Any] | None:
        """Return a category by case-insensitive name."""
        wanted = name.strip().casefold()
        return next(
            (x for x in self.categories if str(x.get("name", "")).casefold() == wanted),
            None,
        )

    async def async_add_category(
        self, *, name: str, interval_months: int, enabled: bool = True
    ) -> dict[str, Any]:
        """Create a selectable bill type."""
        name = name.strip()
        self._validate_category(name, interval_months)
        if self.category_by_name(name):
            raise ValueError("Esiste già una bolletta con questo nome")

        item = {
            "id": uuid4().hex,
            "name": name,
            "interval_months": int(interval_months),
            "enabled": bool(enabled),
        }
        self.categories.append(item)
        await self._save_and_notify()
        return dict(item)

    async def async_update_category(
        self,
        category_id: str,
        *,
        name: str,
        interval_months: int,
        enabled: bool,
    ) -> dict[str, Any] | None:
        """Edit a bill type without breaking historic entries."""
        name = name.strip()
        self._validate_category(name, interval_months)
        duplicate = self.category_by_name(name)
        if duplicate and duplicate.get("id") != category_id:
            raise ValueError("Esiste già una bolletta con questo nome")

        item = self.category(category_id)
        if item is None:
            return None
        item.update(
            {
                "name": name,
                "interval_months": int(interval_months),
                "enabled": bool(enabled),
            }
        )
        await self._save_and_notify()
        return dict(item)

    async def async_delete_category(self, category_id: str) -> bool:
        """Delete an unused category. Categories with history must be disabled instead."""
        if any(x.get("category_id") == category_id for x in self.expenses):
            raise ValueError(
                "Questa bolletta ha uno storico: disattivala invece di eliminarla"
            )
        before = len(self.categories)
        self.categories = [x for x in self.categories if x.get("id") != category_id]
        changed = len(self.categories) != before
        if changed:
            await self._save_and_notify()
        return changed

    # ---------------------------------------------------------------------
    # Expenses
    # ---------------------------------------------------------------------
    async def async_add(
        self,
        *,
        year: int,
        month: int,
        category_id: str | None,
        category_name: str | None,
        amount: float,
        note: str = "",
        period_start_year: int | None = None,
        period_start_month: int | None = None,
        period_end_year: int | None = None,
        period_end_month: int | None = None,
    ) -> dict[str, Any]:
        """Add a bill payment."""
        category = self._resolve_category(category_id, category_name)
        self._validate_date(year, month)
        if not isfinite(amount) or amount < 0:
            raise ValueError("Importo non valido")

        sy, sm, ey, em = self._normalize_period(
            year,
            month,
            int(category["interval_months"]),
            period_start_year,
            period_start_month,
            period_end_year,
            period_end_month,
        )

        item = {
            "id": uuid4().hex,
            "paid_year": int(year),
            "paid_month": int(month),
            "category_id": str(category["id"]),
            "amount": round(float(amount), 2),
            "period_start_year": sy,
            "period_start_month": sm,
            "period_end_year": ey,
            "period_end_month": em,
            "note": note.strip(),
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        self.expenses.append(item)
        self._sort()
        await self._save_and_notify()
        return self._public_expense(item)

    async def async_update(
        self,
        expense_id: str,
        *,
        year: int,
        month: int,
        category_id: str | None,
        category_name: str | None,
        amount: float,
        note: str = "",
        period_start_year: int | None = None,
        period_start_month: int | None = None,
        period_end_year: int | None = None,
        period_end_month: int | None = None,
    ) -> dict[str, Any] | None:
        """Update a bill payment."""
        category = self._resolve_category(category_id, category_name)
        self._validate_date(year, month)
        if not isfinite(amount) or amount < 0:
            raise ValueError("Importo non valido")

        sy, sm, ey, em = self._normalize_period(
            year,
            month,
            int(category["interval_months"]),
            period_start_year,
            period_start_month,
            period_end_year,
            period_end_month,
        )

        for item in self.expenses:
            if item.get("id") != expense_id:
                continue
            item.update(
                {
                    "paid_year": int(year),
                    "paid_month": int(month),
                    "category_id": str(category["id"]),
                    "amount": round(float(amount), 2),
                    "period_start_year": sy,
                    "period_start_month": sm,
                    "period_end_year": ey,
                    "period_end_month": em,
                    "note": note.strip(),
                }
            )
            self._sort()
            await self._save_and_notify()
            return self._public_expense(item)
        return None

    async def async_delete(self, expense_id: str) -> bool:
        """Delete a bill payment."""
        before = len(self.expenses)
        self.expenses = [x for x in self.expenses if x.get("id") != expense_id]
        changed = len(self.expenses) != before
        if changed:
            await self._save_and_notify()
        return changed

    # ---------------------------------------------------------------------
    # Public snapshot / aggregations
    # ---------------------------------------------------------------------
    def snapshot(self, forecast_months: int = 12) -> dict[str, Any]:
        """Return data used by the dashboard card."""
        forecast_months = max(1, min(int(forecast_months), 24))
        return {
            "schema_version": STORAGE_SCHEMA_VERSION,
            "categories": [dict(x) for x in self.categories],
            "active_categories": [dict(x) for x in self.categories if x.get("enabled", True)],
            "expenses": [self._public_expense(x) for x in self.expenses],
            "monthly": self.monthly_totals(),
            "normalized_monthly": self.normalized_monthly_totals(),
            "forecast": self.forecast(forecast_months),
            "normalized_forecast": self.normalized_forecast(forecast_months),
            "upcoming": self.upcoming(forecast_months),
            "summary": self.summary(),
        }

    def monthly_totals(self) -> list[dict[str, Any]]:
        """Cash-flow totals grouped by payment month."""
        if not self.expenses:
            return []

        buckets: dict[tuple[int, int], dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        for item in self.expenses:
            key = (int(item["paid_year"]), int(item["paid_month"]))
            buckets[key][str(item["category_id"])] += float(item["amount"])

        first = min(buckets)
        today = date.today()
        last = max(max(buckets), (today.year, today.month))
        return self._rows_from_buckets(buckets, first, last)

    def normalized_monthly_totals(self) -> list[dict[str, Any]]:
        """Distribute each bill across its competence months."""
        if not self.expenses:
            return []

        buckets: dict[tuple[int, int], dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        for item in self.expenses:
            months = self._month_range(
                int(item["period_start_year"]),
                int(item["period_start_month"]),
                int(item["period_end_year"]),
                int(item["period_end_month"]),
            )
            if not months:
                continue
            share = float(item["amount"]) / len(months)
            for key in months:
                buckets[key][str(item["category_id"])] += share

        first = min(buckets)
        today = date.today()
        last = max(max(buckets), (today.year, today.month))
        return self._rows_from_buckets(buckets, first, last)

    def forecast(self, months_ahead: int = 12) -> list[dict[str, Any]]:
        """Forecast actual payment months using each category recurrence."""
        months_ahead = max(1, min(int(months_ahead), 24))
        today = date.today()
        start = self._next_month(today.year, today.month)
        future_months = []
        y, m = start
        for _ in range(months_ahead):
            future_months.append((y, m))
            y, m = self._next_month(y, m)

        buckets: dict[tuple[int, int], dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )

        for category in self.categories:
            if not category.get("enabled", True):
                continue
            cat_id = str(category["id"])
            history = sorted(
                [x for x in self.expenses if x.get("category_id") == cat_id],
                key=lambda x: (int(x["paid_year"]), int(x["paid_month"])),
            )
            if not history:
                continue

            estimate = self._estimate_category_amount(history)
            interval = int(category["interval_months"])
            due = (int(history[-1]["paid_year"]), int(history[-1]["paid_month"]))
            due = self._add_months(due[0], due[1], interval)
            while due < start:
                due = self._add_months(due[0], due[1], interval)

            end = future_months[-1]
            while due <= end:
                buckets[due][cat_id] += estimate
                due = self._add_months(due[0], due[1], interval)

        rows: list[dict[str, Any]] = []
        for year, month in future_months:
            by_category = self._named_category_values(buckets[(year, month)])
            rows.append(
                {
                    "year": year,
                    "month": month,
                    "key": f"{year:04d}-{month:02d}",
                    "total": round(sum(by_category.values()), 2),
                    "categories": by_category,
                }
            )
        return rows

    def normalized_forecast(self, months_ahead: int = 12) -> list[dict[str, Any]]:
        """Estimate the normalized monthly cost of recurring bills."""
        months_ahead = max(1, min(int(months_ahead), 24))
        today = date.today()
        y, m = self._next_month(today.year, today.month)

        recurring: dict[str, float] = {}
        for category in self.categories:
            if not category.get("enabled", True):
                continue
            cat_id = str(category["id"])
            history = sorted(
                [x for x in self.expenses if x.get("category_id") == cat_id],
                key=lambda x: (int(x["paid_year"]), int(x["paid_month"])),
            )
            if not history:
                continue
            recurring[cat_id] = self._estimate_category_amount(history) / max(
                1, int(category["interval_months"])
            )

        rows: list[dict[str, Any]] = []
        for _ in range(months_ahead):
            by_category = self._named_category_values(recurring)
            rows.append(
                {
                    "year": y,
                    "month": m,
                    "key": f"{y:04d}-{m:02d}",
                    "total": round(sum(by_category.values()), 2),
                    "categories": by_category,
                }
            )
            y, m = self._next_month(y, m)
        return rows

    def upcoming(self, months_ahead: int = 12) -> list[dict[str, Any]]:
        """Return forecasted individual bills, useful for the upcoming list."""
        items: list[dict[str, Any]] = []
        for row in self.forecast(months_ahead):
            for category_name, amount in row["categories"].items():
                if amount <= 0:
                    continue
                category = self.category_by_name(category_name)
                items.append(
                    {
                        "year": row["year"],
                        "month": row["month"],
                        "key": row["key"],
                        "category_id": category.get("id") if category else None,
                        "category": category_name,
                        "amount": round(float(amount), 2),
                    }
                )
        return items

    def summary(self) -> dict[str, Any]:
        """Return compact headline statistics."""
        monthly = self.monthly_totals()
        normalized = self.normalized_monthly_totals()
        today = date.today()
        current_key = f"{today.year:04d}-{today.month:02d}"
        current = next((x for x in monthly if x["key"] == current_key), None)
        normalized_current = next(
            (x for x in normalized if x["key"] == current_key), None
        )
        past_values = [float(x["total"]) for x in monthly if x["key"] <= current_key]
        avg6 = (
            round(mean(past_values[-min(6, len(past_values)) :]), 2)
            if past_values
            else 0.0
        )
        future = self.forecast(12)
        return {
            "current_month": round(float(current["total"]), 2) if current else 0.0,
            "average_6_months": avg6,
            "next_month_estimate": future[0]["total"] if future else 0.0,
            "normalized_current_month": (
                round(float(normalized_current["total"]), 2)
                if normalized_current
                else 0.0
            ),
            "year_total": round(
                sum(
                    float(x["amount"])
                    for x in self.expenses
                    if int(x["paid_year"]) == today.year
                ),
                2,
            ),
            "entries": len(self.expenses),
            "active_categories": sum(1 for x in self.categories if x.get("enabled", True)),
        }

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------
    def _public_expense(self, item: dict[str, Any]) -> dict[str, Any]:
        category = self.category(str(item.get("category_id", "")))
        name = category.get("name") if category else "Bolletta rimossa"
        return {
            **dict(item),
            # v0.2 compatibility aliases
            "year": int(item["paid_year"]),
            "month": int(item["paid_month"]),
            "category": str(name),
        }

    def _rows_from_buckets(
        self,
        buckets: dict[tuple[int, int], dict[str, float]],
        first: tuple[int, int],
        last: tuple[int, int],
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        y, m = first
        while (y, m) <= last:
            by_category = self._named_category_values(buckets[(y, m)])
            result.append(
                {
                    "year": y,
                    "month": m,
                    "key": f"{y:04d}-{m:02d}",
                    "total": round(sum(by_category.values()), 2),
                    "categories": by_category,
                }
            )
            y, m = self._next_month(y, m)
        return result

    def _named_category_values(self, values: dict[str, float]) -> dict[str, float]:
        result: dict[str, float] = {}
        for category in self.categories:
            amount = float(values.get(str(category["id"]), 0.0))
            if amount:
                result[str(category["name"])] = round(amount, 2)
        # Preserve unknown ids if a very old/corrupt database contains one.
        for category_id, amount in values.items():
            if self.category(str(category_id)) is None and amount:
                result[f"Categoria {category_id}"] = round(float(amount), 2)
        return result

    def _estimate_category_amount(self, history: list[dict[str, Any]]) -> float:
        amounts = [float(x["amount"]) for x in history if isfinite(float(x["amount"]))]
        if not amounts:
            return 0.0
        recent = amounts[-min(4, len(amounts)) :]
        base = mean(recent)
        if len(recent) >= 2:
            slope = (recent[-1] - recent[0]) / (len(recent) - 1)
            # Keep a trend correction deliberately conservative.
            correction = max(-base * 0.20, min(base * 0.20, slope * 0.35))
            base += correction
        return round(max(0.0, base), 2)

    def _resolve_category(
        self, category_id: str | None, category_name: str | None
    ) -> dict[str, Any]:
        category = self.category(category_id or "") if category_id else None
        if category is None and category_name:
            category = self.category_by_name(category_name)
        if category is None:
            raise ValueError("Tipo di bolletta non valido")
        return category

    def _normalize_period(
        self,
        paid_year: int,
        paid_month: int,
        interval: int,
        start_year: int | None,
        start_month: int | None,
        end_year: int | None,
        end_month: int | None,
    ) -> tuple[int, int, int, int]:
        if end_year is None or end_month is None:
            end_year, end_month = paid_year, paid_month
        self._validate_date(int(end_year), int(end_month))

        if start_year is None or start_month is None:
            start_year, start_month = self._add_months(
                int(end_year), int(end_month), -(max(1, interval) - 1)
            )
        self._validate_date(int(start_year), int(start_month))

        if (int(start_year), int(start_month)) > (int(end_year), int(end_month)):
            raise ValueError("Il periodo di competenza iniziale è successivo a quello finale")
        if len(
            self._month_range(
                int(start_year), int(start_month), int(end_year), int(end_month)
            )
        ) > 36:
            raise ValueError("Periodo di competenza troppo lungo")
        return int(start_year), int(start_month), int(end_year), int(end_month)

    def _normalize_categories(self) -> bool:
        changed = False
        seen_ids: set[str] = set()
        seen_names: set[str] = set()
        normalized: list[dict[str, Any]] = []
        for raw in self.categories:
            name = str(raw.get("name", "")).strip()
            if not name:
                changed = True
                continue
            category_id = str(raw.get("id") or uuid4().hex)
            while category_id in seen_ids:
                category_id = uuid4().hex
                changed = True
            interval = int(raw.get("interval_months", 1) or 1)
            if interval not in SUPPORTED_INTERVALS:
                interval = 1
                changed = True
            folded = name.casefold()
            if folded in seen_names:
                changed = True
                continue
            seen_ids.add(category_id)
            seen_names.add(folded)
            item = {
                "id": category_id,
                "name": name,
                "interval_months": interval,
                "enabled": bool(raw.get("enabled", True)),
            }
            if item != raw:
                changed = True
            normalized.append(item)
        self.categories = normalized
        return changed

    def _migrate_expenses(self) -> bool:
        changed = False
        migrated: list[dict[str, Any]] = []
        for raw in self.expenses:
            item = dict(raw)
            paid_year = int(item.get("paid_year", item.get("year", 0)) or 0)
            paid_month = int(item.get("paid_month", item.get("month", 0)) or 0)
            try:
                self._validate_date(paid_year, paid_month)
            except ValueError:
                changed = True
                continue

            category_id = str(item.get("category_id", ""))
            category = self.category(category_id) if category_id else None
            legacy_name = str(item.get("category", "")).strip()
            if category is None and legacy_name:
                category = self.category_by_name(legacy_name)
            if category is None:
                category = {
                    "id": uuid4().hex,
                    "name": legacy_name or "Altro",
                    "interval_months": 1,
                    "enabled": True,
                }
                duplicate = self.category_by_name(category["name"])
                if duplicate:
                    category = duplicate
                else:
                    self.categories.append(category)
                changed = True

            interval = int(category["interval_months"])
            sy = item.get("period_start_year")
            sm = item.get("period_start_month")
            ey = item.get("period_end_year")
            em = item.get("period_end_month")
            try:
                sy, sm, ey, em = self._normalize_period(
                    paid_year,
                    paid_month,
                    interval,
                    int(sy) if sy is not None else None,
                    int(sm) if sm is not None else None,
                    int(ey) if ey is not None else None,
                    int(em) if em is not None else None,
                )
            except ValueError:
                sy, sm = self._add_months(paid_year, paid_month, -(interval - 1))
                ey, em = paid_year, paid_month
                changed = True

            amount = float(item.get("amount", 0.0) or 0.0)
            if not isfinite(amount) or amount < 0:
                changed = True
                continue

            new_item = {
                "id": str(item.get("id") or uuid4().hex),
                "paid_year": paid_year,
                "paid_month": paid_month,
                "category_id": str(category["id"]),
                "amount": round(amount, 2),
                "period_start_year": sy,
                "period_start_month": sm,
                "period_end_year": ey,
                "period_end_month": em,
                "note": str(item.get("note", "")).strip(),
                "created_at": str(
                    item.get("created_at")
                    or datetime.now().astimezone().isoformat(timespec="seconds")
                ),
            }
            if new_item != raw:
                changed = True
            migrated.append(new_item)
        self.expenses = migrated
        return changed

    async def _save_and_notify(self) -> None:
        await self._save()
        self.hass.bus.async_fire(EVENT_UPDATED)

    async def _save(self) -> None:
        await self._store.async_save(
            {
                "schema_version": STORAGE_SCHEMA_VERSION,
                "categories": self.categories,
                "expenses": self.expenses,
            }
        )

    def _sort(self) -> None:
        self.expenses.sort(
            key=lambda x: (
                int(x.get("paid_year", 0)),
                int(x.get("paid_month", 0)),
                str(x.get("created_at", "")),
            ),
            reverse=True,
        )

    @staticmethod
    def _validate_category(name: str, interval_months: int) -> None:
        if not name:
            raise ValueError("Nome obbligatorio")
        if len(name) > 60:
            raise ValueError("Nome troppo lungo")
        if int(interval_months) not in SUPPORTED_INTERVALS:
            raise ValueError("Periodicità non supportata")

    @staticmethod
    def _validate_date(year: int, month: int) -> None:
        if int(year) < 2000 or int(year) > 2200:
            raise ValueError("Anno non valido")
        if int(month) < 1 or int(month) > 12:
            raise ValueError("Mese non valido")

    @staticmethod
    def _next_month(year: int, month: int) -> tuple[int, int]:
        return BillTrackerManager._add_months(year, month, 1)

    @staticmethod
    def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
        absolute = year * 12 + (month - 1) + delta
        return absolute // 12, absolute % 12 + 1

    @staticmethod
    def _month_range(
        start_year: int, start_month: int, end_year: int, end_month: int
    ) -> list[tuple[int, int]]:
        if (start_year, start_month) > (end_year, end_month):
            return []
        result: list[tuple[int, int]] = []
        y, m = start_year, start_month
        while (y, m) <= (end_year, end_month) and len(result) <= 36:
            result.append((y, m))
            y, m = BillTrackerManager._next_month(y, m)
        return result
