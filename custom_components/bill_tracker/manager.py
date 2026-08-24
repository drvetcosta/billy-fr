"""Persistent data model, bill splitting and forecasting for Bill Tracker."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime
from math import isfinite
from statistics import mean
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DEFAULT_CATEGORIES,
    EVENT_UPDATED,
    FALLBACK_COLORS,
    STORAGE_KEY,
    STORAGE_SCHEMA_VERSION,
    STORAGE_VERSION,
    SUPPORTED_INTERVALS,
)


class BillTrackerManager:
    """Persistent bill store, categories, payers, settlements and aggregation logic."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.expenses: list[dict[str, Any]] = []
        self.categories: list[dict[str, Any]] = []
        self.payers: list[dict[str, Any]] = []
        self.settlements: list[dict[str, Any]] = []

    async def async_load(self) -> None:
        """Load and migrate the persistent database."""
        data = await self._store.async_load() or {}
        self.categories = [dict(x) for x in data.get("categories", [])]
        self.expenses = [dict(x) for x in data.get("expenses", [])]
        self.payers = [dict(x) for x in data.get("payers", [])]
        self.settlements = [dict(x) for x in data.get("settlements", [])]

        changed = False
        changed |= self._normalize_payers()
        if not self.categories:
            self.categories = deepcopy(DEFAULT_CATEGORIES)
            changed = True
        changed |= self._normalize_categories()
        changed |= self._migrate_expenses()
        changed |= self._migrate_settlements()
        self._sort()

        if changed or data.get("schema_version") != STORAGE_SCHEMA_VERSION:
            await self._save()

    # ------------------------------------------------------------------
    # Payers
    # ------------------------------------------------------------------
    def payer(self, payer_id: str) -> dict[str, Any] | None:
        return next((x for x in self.payers if x.get("id") == payer_id), None)

    def payer_by_name(self, name: str) -> dict[str, Any] | None:
        wanted = name.strip().casefold()
        return next(
            (x for x in self.payers if str(x.get("name", "")).casefold() == wanted),
            None,
        )

    async def async_add_payer(
        self,
        *,
        name: str,
        share_percent: float = 50.0,
        paypal_me: str = "",
        enabled: bool = True,
    ) -> dict[str, Any]:
        name = name.strip()
        self._validate_payer(name, share_percent)
        if self.payer_by_name(name):
            raise ValueError("Esiste già un pagante con questo nome")
        item = {
            "id": uuid4().hex,
            "name": name,
            "share_percent": round(float(share_percent), 2),
            "paypal_me": self._normalize_paypal_me(paypal_me),
            "enabled": bool(enabled),
        }
        self.payers.append(item)
        await self._save_and_notify()
        return dict(item)

    async def async_update_payer(
        self,
        payer_id: str,
        *,
        name: str,
        share_percent: float,
        paypal_me: str,
        enabled: bool,
    ) -> dict[str, Any] | None:
        name = name.strip()
        self._validate_payer(name, share_percent)
        duplicate = self.payer_by_name(name)
        if duplicate and duplicate.get("id") != payer_id:
            raise ValueError("Esiste già un pagante con questo nome")
        item = self.payer(payer_id)
        if item is None:
            return None
        item.update(
            {
                "name": name,
                "share_percent": round(float(share_percent), 2),
                "paypal_me": self._normalize_paypal_me(paypal_me),
                "enabled": bool(enabled),
            }
        )
        await self._save_and_notify()
        return dict(item)

    async def async_delete_payer(self, payer_id: str) -> bool:
        if any(x.get("payer_id") == payer_id for x in self.expenses):
            raise ValueError("Questo pagante è presente nello storico: disattivalo invece di eliminarlo")
        if any(
            any(part.get("payer_id") == payer_id for part in x.get("split", []))
            for x in self.expenses
        ):
            raise ValueError("Questo pagante è presente nello storico: disattivalo invece di eliminarlo")
        if any(x.get("default_payer_id") == payer_id for x in self.categories):
            raise ValueError("Questo pagante è impostato come pagatore predefinito di una bolletta")
        if any(
            x.get("from_payer_id") == payer_id or x.get("to_payer_id") == payer_id
            for x in self.settlements
        ):
            raise ValueError("Questo pagante è presente nello storico rimborsi: disattivalo invece di eliminarlo")
        before = len(self.payers)
        self.payers = [x for x in self.payers if x.get("id") != payer_id]
        changed = len(self.payers) != before
        if changed:
            await self._save_and_notify()
        return changed

    def active_payers(self) -> list[dict[str, Any]]:
        return [dict(x) for x in self.payers if x.get("enabled", True)]

    def default_split(self) -> list[dict[str, Any]]:
        """Return normalized percentages based on active payer weights."""
        active = [x for x in self.payers if x.get("enabled", True)]
        if not active:
            return []
        weights = [max(0.0, float(x.get("share_percent", 0.0) or 0.0)) for x in active]
        total = sum(weights)
        if total <= 0:
            weights = [1.0 for _ in active]
            total = float(len(active))
        result: list[dict[str, Any]] = []
        running = 0.0
        for index, (payer, weight) in enumerate(zip(active, weights)):
            if index == len(active) - 1:
                pct = round(100.0 - running, 2)
            else:
                pct = round(weight / total * 100.0, 2)
                running += pct
            result.append({"payer_id": str(payer["id"]), "percentage": pct})
        return result

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------
    def category(self, category_id: str) -> dict[str, Any] | None:
        return next((x for x in self.categories if x.get("id") == category_id), None)

    def category_by_name(self, name: str) -> dict[str, Any] | None:
        wanted = name.strip().casefold()
        return next(
            (x for x in self.categories if str(x.get("name", "")).casefold() == wanted),
            None,
        )

    async def async_add_category(
        self,
        *,
        name: str,
        interval_months: int,
        enabled: bool = True,
        default_payer_id: str | None = None,
        color: str | None = None,
    ) -> dict[str, Any]:
        name = name.strip()
        self._validate_category(name, interval_months)
        if self.category_by_name(name):
            raise ValueError("Esiste già una bolletta con questo nome")
        payer_id = self._validate_optional_payer(default_payer_id)
        item = {
            "id": uuid4().hex,
            "name": name,
            "interval_months": int(interval_months),
            "enabled": bool(enabled),
            "default_payer_id": payer_id,
            "color": self._normalize_color(color, len(self.categories)),
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
        default_payer_id: str | None = None,
        color: str | None = None,
    ) -> dict[str, Any] | None:
        name = name.strip()
        self._validate_category(name, interval_months)
        duplicate = self.category_by_name(name)
        if duplicate and duplicate.get("id") != category_id:
            raise ValueError("Esiste già una bolletta con questo nome")
        item = self.category(category_id)
        if item is None:
            return None
        payer_id = self._validate_optional_payer(default_payer_id)
        item.update(
            {
                "name": name,
                "interval_months": int(interval_months),
                "enabled": bool(enabled),
                "default_payer_id": payer_id,
                "color": self._normalize_color(color or item.get("color"), 0),
            }
        )
        await self._save_and_notify()
        return dict(item)

    async def async_delete_category(self, category_id: str) -> bool:
        if any(x.get("category_id") == category_id for x in self.expenses):
            raise ValueError("Questa bolletta ha uno storico: disattivala invece di eliminarla")
        before = len(self.categories)
        self.categories = [x for x in self.categories if x.get("id") != category_id]
        changed = len(self.categories) != before
        if changed:
            await self._save_and_notify()
        return changed

    # ------------------------------------------------------------------
    # Expenses
    # ------------------------------------------------------------------
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
        payer_id: str | None = None,
        split: list[dict[str, Any]] | None = None,
        paid: bool = False,
    ) -> dict[str, Any]:
        category = self._resolve_category(category_id, category_name)
        self._validate_date(year, month)
        self._validate_amount(amount)
        sy, sm, ey, em = self._normalize_period(
            year, month, int(category["interval_months"]),
            period_start_year, period_start_month, period_end_year, period_end_month,
        )
        resolved_payer = self._resolve_expense_payer(category, payer_id)
        normalized_split = self._resolve_expense_split(split, resolved_payer)
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
            "payer_id": resolved_payer,
            "split": normalized_split,
            "paid": bool(paid),
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
        payer_id: str | None = None,
        split: list[dict[str, Any]] | None = None,
        paid: bool | None = None,
    ) -> dict[str, Any] | None:
        category = self._resolve_category(category_id, category_name)
        self._validate_date(year, month)
        self._validate_amount(amount)
        sy, sm, ey, em = self._normalize_period(
            year, month, int(category["interval_months"]),
            period_start_year, period_start_month, period_end_year, period_end_month,
        )
        resolved_payer = self._resolve_expense_payer(category, payer_id)
        normalized_split = self._resolve_expense_split(split, resolved_payer)
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
                    "payer_id": resolved_payer,
                    "split": normalized_split,
                    "paid": bool(paid) if paid is not None else bool(item.get("paid", False)),
                    "note": note.strip(),
                }
            )
            self._sort()
            await self._save_and_notify()
            return self._public_expense(item)
        return None

    async def async_delete(self, expense_id: str) -> bool:
        before = len(self.expenses)
        self.expenses = [x for x in self.expenses if x.get("id") != expense_id]
        changed = len(self.expenses) != before
        if changed:
            await self._save_and_notify()
        return changed

    # ------------------------------------------------------------------
    # Settlements / debt netting
    # ------------------------------------------------------------------
    async def async_add_settlement(
        self,
        *,
        from_payer_id: str,
        to_payer_id: str,
        amount: float,
        note: str = "",
    ) -> dict[str, Any]:
        source = self.payer(from_payer_id)
        target = self.payer(to_payer_id)
        if source is None or target is None or from_payer_id == to_payer_id:
            raise ValueError("Paganti non validi")
        self._validate_amount(amount, allow_zero=False)
        outstanding = next(
            (
                float(x["amount"])
                for x in self.debts()
                if x["from_payer_id"] == from_payer_id and x["to_payer_id"] == to_payer_id
            ),
            0.0,
        )
        if outstanding <= 0:
            raise ValueError("Non esiste un debito aperto tra questi paganti")
        if float(amount) > outstanding + 0.01:
            raise ValueError("Il rimborso supera il debito aperto")
        item = {
            "id": uuid4().hex,
            "from_payer_id": from_payer_id,
            "to_payer_id": to_payer_id,
            "amount": round(float(amount), 2),
            "note": note.strip(),
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        self.settlements.append(item)
        self._sort()
        await self._save_and_notify()
        return self._public_settlement(item)

    async def async_delete_settlement(self, settlement_id: str) -> bool:
        before = len(self.settlements)
        self.settlements = [x for x in self.settlements if x.get("id") != settlement_id]
        changed = len(self.settlements) != before
        if changed:
            await self._save_and_notify()
        return changed

    def balances(self) -> list[dict[str, Any]]:
        """Return net position by payer. Positive means they should receive money."""
        positions: dict[str, float] = {str(x["id"]): 0.0 for x in self.payers}
        for item in self.expenses:
            if not bool(item.get("paid", False)):
                continue
            payer_id = str(item.get("payer_id") or "")
            if payer_id not in positions:
                continue
            amount = float(item.get("amount", 0.0))
            positions[payer_id] += amount
            for part in item.get("split", []):
                participant = str(part.get("payer_id") or "")
                if participant not in positions:
                    continue
                positions[participant] -= amount * float(part.get("percentage", 0.0)) / 100.0
        for item in self.settlements:
            source = str(item.get("from_payer_id") or "")
            target = str(item.get("to_payer_id") or "")
            amount = float(item.get("amount", 0.0))
            if source in positions:
                positions[source] += amount
            if target in positions:
                positions[target] -= amount
        rows = []
        for payer in self.payers:
            value = round(positions.get(str(payer["id"]), 0.0), 2)
            rows.append(
                {
                    "payer_id": str(payer["id"]),
                    "name": str(payer["name"]),
                    "balance": value,
                    "status": "credit" if value > 0.009 else "debt" if value < -0.009 else "even",
                }
            )
        return rows

    def debts(self) -> list[dict[str, Any]]:
        """Convert net payer positions to a minimal list of outstanding transfers."""
        balances = self.balances()
        creditors = [[x, float(x["balance"])] for x in balances if float(x["balance"]) > 0.009]
        debtors = [[x, -float(x["balance"])] for x in balances if float(x["balance"]) < -0.009]
        creditors.sort(key=lambda x: x[1], reverse=True)
        debtors.sort(key=lambda x: x[1], reverse=True)
        result: list[dict[str, Any]] = []
        ci = di = 0
        while ci < len(creditors) and di < len(debtors):
            creditor, credit = creditors[ci]
            debtor, debt = debtors[di]
            amount = round(min(credit, debt), 2)
            if amount > 0:
                target = self.payer(str(creditor["payer_id"]))
                paypal_me = str(target.get("paypal_me", "")) if target else ""
                result.append(
                    {
                        "from_payer_id": str(debtor["payer_id"]),
                        "from_name": str(debtor["name"]),
                        "to_payer_id": str(creditor["payer_id"]),
                        "to_name": str(creditor["name"]),
                        "amount": amount,
                        "paypal_me": paypal_me,
                        "paypal_url": self._paypal_url(paypal_me, amount),
                    }
                )
            credit = round(credit - amount, 2)
            debt = round(debt - amount, 2)
            creditors[ci][1] = credit
            debtors[di][1] = debt
            if credit <= 0.009:
                ci += 1
            if debt <= 0.009:
                di += 1
        return result

    # ------------------------------------------------------------------
    # Public snapshot / aggregations
    # ------------------------------------------------------------------
    def snapshot(self, forecast_months: int = 12) -> dict[str, Any]:
        forecast_months = max(1, min(int(forecast_months), 24))
        return {
            "schema_version": STORAGE_SCHEMA_VERSION,
            "categories": [dict(x) for x in self.categories],
            "active_categories": [dict(x) for x in self.categories if x.get("enabled", True)],
            "payers": [dict(x) for x in self.payers],
            "active_payers": self.active_payers(),
            "default_split": self.default_split(),
            "expenses": [self._public_expense(x) for x in self.expenses],
            "settlements": [self._public_settlement(x) for x in self.settlements],
            "balances": self.balances(),
            "debts": self.debts(),
            "monthly": self.monthly_totals(),
            "normalized_monthly": self.normalized_monthly_totals(),
            "forecast": self.forecast(forecast_months),
            "normalized_forecast": self.normalized_forecast(forecast_months),
            "upcoming": self.upcoming(forecast_months),
            "summary": self.summary(),
        }

    def monthly_totals(self) -> list[dict[str, Any]]:
        if not self.expenses:
            return []
        buckets: dict[tuple[int, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for item in self.expenses:
            if not bool(item.get("paid", False)):
                continue
            buckets[(int(item["paid_year"]), int(item["paid_month"]))][str(item["category_id"])] += float(item["amount"])
        if not buckets:
            return []
        first = min(buckets)
        today = date.today()
        last = max(max(buckets), (today.year, today.month))
        return self._rows_from_buckets(buckets, first, last)

    def normalized_monthly_totals(self) -> list[dict[str, Any]]:
        if not self.expenses:
            return []
        buckets: dict[tuple[int, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for item in self.expenses:
            months = self._month_range(
                int(item["period_start_year"]), int(item["period_start_month"]),
                int(item["period_end_year"]), int(item["period_end_month"]),
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
        months_ahead = max(1, min(int(months_ahead), 24))
        today = date.today()
        start = self._next_month(today.year, today.month)
        future_months = []
        y, m = start
        for _ in range(months_ahead):
            future_months.append((y, m))
            y, m = self._next_month(y, m)
        buckets: dict[tuple[int, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
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
            due = self._add_months(int(history[-1]["paid_year"]), int(history[-1]["paid_month"]), interval)
            while due < start:
                due = self._add_months(due[0], due[1], interval)
            end = future_months[-1]
            while due <= end:
                buckets[due][cat_id] += estimate
                due = self._add_months(due[0], due[1], interval)
        rows = []
        for year, month in future_months:
            by_category = self._named_category_values(buckets[(year, month)])
            rows.append({"year": year, "month": month, "key": f"{year:04d}-{month:02d}", "total": round(sum(by_category.values()), 2), "categories": by_category})
        return rows

    def normalized_forecast(self, months_ahead: int = 12) -> list[dict[str, Any]]:
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
            if history:
                recurring[cat_id] = self._estimate_category_amount(history) / max(1, int(category["interval_months"]))
        rows = []
        for _ in range(months_ahead):
            by_category = self._named_category_values(recurring)
            rows.append({"year": y, "month": m, "key": f"{y:04d}-{m:02d}", "total": round(sum(by_category.values()), 2), "categories": by_category})
            y, m = self._next_month(y, m)
        return rows

    def upcoming(self, months_ahead: int = 12) -> list[dict[str, Any]]:
        items = []
        for row in self.forecast(months_ahead):
            for category_name, amount in row["categories"].items():
                if amount <= 0:
                    continue
                category = self.category_by_name(category_name)
                items.append({"year": row["year"], "month": row["month"], "key": row["key"], "category_id": category.get("id") if category else None, "category": category_name, "amount": round(float(amount), 2)})
        return items

    def summary(self) -> dict[str, Any]:
        monthly = self.monthly_totals()
        normalized = self.normalized_monthly_totals()
        today = date.today()
        current_key = f"{today.year:04d}-{today.month:02d}"
        current = next((x for x in monthly if x["key"] == current_key), None)
        normalized_current = next((x for x in normalized if x["key"] == current_key), None)
        past_values = [float(x["total"]) for x in monthly if x["key"] <= current_key]
        avg6 = round(mean(past_values[-min(6, len(past_values)):]), 2) if past_values else 0.0
        future = self.forecast(12)
        debts = self.debts()
        return {
            "current_month": round(float(current["total"]), 2) if current else 0.0,
            "average_6_months": avg6,
            "next_month_estimate": future[0]["total"] if future else 0.0,
            "normalized_current_month": round(float(normalized_current["total"]), 2) if normalized_current else 0.0,
            "year_total": round(sum(float(x["amount"]) for x in self.expenses if int(x["paid_year"]) == today.year and bool(x.get("paid", False))), 2),
            "entries": len(self.expenses),
            "paid_entries": sum(1 for x in self.expenses if bool(x.get("paid", False))),
            "unpaid_entries": sum(1 for x in self.expenses if not bool(x.get("paid", False))),
            "active_categories": sum(1 for x in self.categories if x.get("enabled", True)),
            "active_payers": sum(1 for x in self.payers if x.get("enabled", True)),
            "outstanding_total": round(sum(float(x["amount"]) for x in debts), 2),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _public_expense(self, item: dict[str, Any]) -> dict[str, Any]:
        category = self.category(str(item.get("category_id", "")))
        payer = self.payer(str(item.get("payer_id", ""))) if item.get("payer_id") else None
        split = []
        for part in item.get("split", []):
            participant = self.payer(str(part.get("payer_id", "")))
            split.append({**dict(part), "name": str(participant.get("name")) if participant else "Pagante rimosso"})
        return {
            **dict(item),
            "year": int(item["paid_year"]),
            "month": int(item["paid_month"]),
            "category": str(category.get("name")) if category else "Bolletta rimossa",
            "category_color": str(category.get("color", "#A0A7B4")) if category else "#A0A7B4",
            "payer": str(payer.get("name")) if payer else "",
            "split": split,
        }

    def _public_settlement(self, item: dict[str, Any]) -> dict[str, Any]:
        source = self.payer(str(item.get("from_payer_id", "")))
        target = self.payer(str(item.get("to_payer_id", "")))
        return {
            **dict(item),
            "from_name": str(source.get("name")) if source else "Pagante rimosso",
            "to_name": str(target.get("name")) if target else "Pagante rimosso",
        }

    def _rows_from_buckets(self, buckets, first, last) -> list[dict[str, Any]]:
        result = []
        y, m = first
        while (y, m) <= last:
            by_category = self._named_category_values(buckets[(y, m)])
            result.append({"year": y, "month": m, "key": f"{y:04d}-{m:02d}", "total": round(sum(by_category.values()), 2), "categories": by_category})
            y, m = self._next_month(y, m)
        return result

    def _named_category_values(self, values: dict[str, float]) -> dict[str, float]:
        result: dict[str, float] = {}
        for category in self.categories:
            amount = float(values.get(str(category["id"]), 0.0))
            if amount:
                result[str(category["name"])] = round(amount, 2)
        for category_id, amount in values.items():
            if self.category(str(category_id)) is None and amount:
                result[f"Categoria {category_id}"] = round(float(amount), 2)
        return result

    def _estimate_category_amount(self, history: list[dict[str, Any]]) -> float:
        amounts = [float(x["amount"]) for x in history if isfinite(float(x["amount"]))]
        if not amounts:
            return 0.0
        recent = amounts[-min(4, len(amounts)):]
        base = mean(recent)
        if len(recent) >= 2:
            slope = (recent[-1] - recent[0]) / (len(recent) - 1)
            correction = max(-base * 0.20, min(base * 0.20, slope * 0.35))
            base += correction
        return round(max(0.0, base), 2)

    def _resolve_category(self, category_id: str | None, category_name: str | None) -> dict[str, Any]:
        category = self.category(category_id or "") if category_id else None
        if category is None and category_name:
            category = self.category_by_name(category_name)
        if category is None:
            raise ValueError("Tipo di bolletta non valido")
        return category

    def _resolve_expense_payer(self, category: dict[str, Any], payer_id: str | None) -> str | None:
        wanted = str(payer_id or category.get("default_payer_id") or "")
        if wanted:
            if self.payer(wanted) is None:
                raise ValueError("Pagatore non valido")
            return wanted
        active = self.active_payers()
        return str(active[0]["id"]) if active else None

    def _resolve_expense_split(self, split: list[dict[str, Any]] | None, payer_id: str | None) -> list[dict[str, Any]]:
        if payer_id is None:
            return []
        if split is None:
            split = self.default_split()
        return self._normalize_split(split)

    def _normalize_split(self, split: list[dict[str, Any]]) -> list[dict[str, Any]]:
        combined: dict[str, float] = defaultdict(float)
        for raw in split:
            payer_id = str(raw.get("payer_id") or "")
            percentage = float(raw.get("percentage", 0.0) or 0.0)
            if self.payer(payer_id) is None:
                raise ValueError("La divisione contiene un pagante non valido")
            if not isfinite(percentage) or percentage < 0 or percentage > 100:
                raise ValueError("Percentuale di divisione non valida")
            if percentage > 0:
                combined[payer_id] += percentage
        if not combined:
            raise ValueError("La divisione della bolletta è vuota")
        total = sum(combined.values())
        if abs(total - 100.0) > 0.05:
            raise ValueError("Le quote della bolletta devono sommare al 100%")
        result = [{"payer_id": payer_id, "percentage": round(value, 2)} for payer_id, value in combined.items() if value > 0]
        # absorb tiny rounding errors in the last share
        if result:
            delta = round(100.0 - sum(float(x["percentage"]) for x in result), 2)
            result[-1]["percentage"] = round(float(result[-1]["percentage"]) + delta, 2)
        return result

    def _normalize_period(self, paid_year, paid_month, interval, start_year, start_month, end_year, end_month) -> tuple[int, int, int, int]:
        if end_year is None or end_month is None:
            end_year, end_month = paid_year, paid_month
        self._validate_date(int(end_year), int(end_month))
        if start_year is None or start_month is None:
            start_year, start_month = self._add_months(int(end_year), int(end_month), -(max(1, interval) - 1))
        self._validate_date(int(start_year), int(start_month))
        if (int(start_year), int(start_month)) > (int(end_year), int(end_month)):
            raise ValueError("Il periodo di competenza iniziale è successivo a quello finale")
        if len(self._month_range(int(start_year), int(start_month), int(end_year), int(end_month))) > 36:
            raise ValueError("Periodo di competenza troppo lungo")
        return int(start_year), int(start_month), int(end_year), int(end_month)

    def _normalize_payers(self) -> bool:
        changed = False
        seen_ids: set[str] = set()
        seen_names: set[str] = set()
        normalized = []
        for raw in self.payers:
            name = str(raw.get("name", "")).strip()
            if not name:
                changed = True
                continue
            payer_id = str(raw.get("id") or uuid4().hex)
            while payer_id in seen_ids:
                payer_id = uuid4().hex
                changed = True
            if name.casefold() in seen_names:
                changed = True
                continue
            share = float(raw.get("share_percent", 50.0) or 0.0)
            if not isfinite(share) or share < 0 or share > 100:
                share = 50.0
                changed = True
            item = {
                "id": payer_id,
                "name": name,
                "share_percent": round(share, 2),
                "paypal_me": self._normalize_paypal_me(str(raw.get("paypal_me", ""))),
                "enabled": bool(raw.get("enabled", True)),
            }
            if item != raw:
                changed = True
            normalized.append(item)
            seen_ids.add(payer_id)
            seen_names.add(name.casefold())
        self.payers = normalized
        return changed

    def _normalize_categories(self) -> bool:
        changed = False
        seen_ids: set[str] = set()
        seen_names: set[str] = set()
        normalized = []
        for index, raw in enumerate(self.categories):
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
            if name.casefold() in seen_names:
                changed = True
                continue
            default_payer = str(raw.get("default_payer_id") or "") or None
            if default_payer and self.payer(default_payer) is None:
                default_payer = None
                changed = True
            item = {
                "id": category_id,
                "name": name,
                "interval_months": interval,
                "enabled": bool(raw.get("enabled", True)),
                "default_payer_id": default_payer,
                "color": self._normalize_color(raw.get("color"), index),
            }
            if item != raw:
                changed = True
            normalized.append(item)
            seen_ids.add(category_id)
            seen_names.add(name.casefold())
        self.categories = normalized
        return changed

    def _migrate_expenses(self) -> bool:
        changed = False
        migrated = []
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
                    "id": uuid4().hex, "name": legacy_name or "Altro", "interval_months": 1,
                    "enabled": True, "default_payer_id": None,
                    "color": self._normalize_color(None, len(self.categories)),
                }
                duplicate = self.category_by_name(category["name"])
                if duplicate:
                    category = duplicate
                else:
                    self.categories.append(category)
                changed = True
            interval = int(category["interval_months"])
            try:
                sy, sm, ey, em = self._normalize_period(
                    paid_year, paid_month, interval,
                    int(item["period_start_year"]) if item.get("period_start_year") is not None else None,
                    int(item["period_start_month"]) if item.get("period_start_month") is not None else None,
                    int(item["period_end_year"]) if item.get("period_end_year") is not None else None,
                    int(item["period_end_month"]) if item.get("period_end_month") is not None else None,
                )
            except ValueError:
                sy, sm = self._add_months(paid_year, paid_month, -(interval - 1))
                ey, em = paid_year, paid_month
                changed = True
            amount = float(item.get("amount", 0.0) or 0.0)
            if not isfinite(amount) or amount < 0:
                changed = True
                continue
            payer_id = str(item.get("payer_id") or "") or None
            if payer_id and self.payer(payer_id) is None:
                payer_id = None
                changed = True
            split: list[dict[str, Any]] = []
            if payer_id and isinstance(item.get("split"), list):
                try:
                    split = self._normalize_split([dict(x) for x in item.get("split", [])])
                except (ValueError, TypeError):
                    split = []
                    changed = True
            new_item = {
                "id": str(item.get("id") or uuid4().hex),
                "paid_year": paid_year, "paid_month": paid_month,
                "category_id": str(category["id"]), "amount": round(amount, 2),
                "period_start_year": sy, "period_start_month": sm,
                "period_end_year": ey, "period_end_month": em,
                "payer_id": payer_id, "split": split,
                # v0.4.0 and older had no explicit payment status. Never infer it:
                # migrated historical bills are unpaid until the user checks them.
                "paid": bool(item.get("paid", False)),
                "note": str(item.get("note", "")).strip(),
                "created_at": str(item.get("created_at") or datetime.now().astimezone().isoformat(timespec="seconds")),
            }
            if new_item != raw:
                changed = True
            migrated.append(new_item)
        self.expenses = migrated
        return changed

    def _migrate_settlements(self) -> bool:
        changed = False
        migrated = []
        for raw in self.settlements:
            source = str(raw.get("from_payer_id") or "")
            target = str(raw.get("to_payer_id") or "")
            amount = float(raw.get("amount", 0.0) or 0.0)
            if not source or not target or source == target or self.payer(source) is None or self.payer(target) is None or not isfinite(amount) or amount <= 0:
                changed = True
                continue
            item = {
                "id": str(raw.get("id") or uuid4().hex),
                "from_payer_id": source, "to_payer_id": target,
                "amount": round(amount, 2), "note": str(raw.get("note", "")).strip(),
                "created_at": str(raw.get("created_at") or datetime.now().astimezone().isoformat(timespec="seconds")),
            }
            if item != raw:
                changed = True
            migrated.append(item)
        self.settlements = migrated
        return changed

    async def _save_and_notify(self) -> None:
        await self._save()
        self.hass.bus.async_fire(EVENT_UPDATED)

    async def _save(self) -> None:
        await self._store.async_save(
            {
                "schema_version": STORAGE_SCHEMA_VERSION,
                "categories": self.categories,
                "payers": self.payers,
                "expenses": self.expenses,
                "settlements": self.settlements,
            }
        )

    def _sort(self) -> None:
        self.expenses.sort(key=lambda x: (int(x.get("paid_year", 0)), int(x.get("paid_month", 0)), str(x.get("created_at", ""))), reverse=True)
        self.settlements.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)

    def _validate_optional_payer(self, payer_id: str | None) -> str | None:
        value = str(payer_id or "")
        if not value:
            return None
        if self.payer(value) is None:
            raise ValueError("Pagatore predefinito non valido")
        return value

    @staticmethod
    def _validate_payer(name: str, share_percent: float) -> None:
        if not name:
            raise ValueError("Nome obbligatorio")
        if len(name) > 60:
            raise ValueError("Nome troppo lungo")
        share = float(share_percent)
        if not isfinite(share) or share < 0 or share > 100:
            raise ValueError("Quota predefinita non valida")

    @staticmethod
    def _validate_category(name: str, interval_months: int) -> None:
        if not name:
            raise ValueError("Nome obbligatorio")
        if len(name) > 60:
            raise ValueError("Nome troppo lungo")
        if int(interval_months) not in SUPPORTED_INTERVALS:
            raise ValueError("Periodicità non supportata")

    @staticmethod
    def _validate_amount(amount: float, allow_zero: bool = True) -> None:
        value = float(amount)
        if not isfinite(value) or value < 0 or (not allow_zero and value <= 0):
            raise ValueError("Importo non valido")

    @staticmethod
    def _validate_date(year: int, month: int) -> None:
        if int(year) < 2000 or int(year) > 2200:
            raise ValueError("Anno non valido")
        if int(month) < 1 or int(month) > 12:
            raise ValueError("Mese non valido")

    @staticmethod
    def _normalize_paypal_me(value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        text = text.split("?", 1)[0].rstrip("/")
        if "/" in text:
            text = text.rsplit("/", 1)[-1]
        return "".join(ch for ch in text if ch.isalnum() or ch in "._-")[:80]

    @staticmethod
    def _paypal_url(handle: str, amount: float) -> str:
        if not handle:
            return ""
        return f"https://paypal.me/{quote(handle, safe='._-')}/{float(amount):.2f}EUR"

    @staticmethod
    def _normalize_color(value: Any, index: int) -> str:
        text = str(value or "").strip()
        if len(text) == 7 and text.startswith("#") and all(ch in "0123456789abcdefABCDEF" for ch in text[1:]):
            return text.upper()
        return FALLBACK_COLORS[index % len(FALLBACK_COLORS)]

    @staticmethod
    def _next_month(year: int, month: int) -> tuple[int, int]:
        return BillTrackerManager._add_months(year, month, 1)

    @staticmethod
    def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
        absolute = year * 12 + (month - 1) + delta
        return absolute // 12, absolute % 12 + 1

    @staticmethod
    def _month_range(start_year: int, start_month: int, end_year: int, end_month: int) -> list[tuple[int, int]]:
        if (start_year, start_month) > (end_year, end_month):
            return []
        result = []
        y, m = start_year, start_month
        while (y, m) <= (end_year, end_month) and len(result) <= 36:
            result.append((y, m))
            y, m = BillTrackerManager._next_month(y, m)
        return result
