"""Config and options flows for Bill Tracker."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN, INTERVAL_LABELS, SUPPORTED_INTERVALS
from .manager import BillTrackerManager


class BillTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial Bill Tracker setup."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(title="Bill Tracker", data={})
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the native Configure flow."""
        return BillTrackerOptionsFlow()


class BillTrackerOptionsFlow(config_entries.OptionsFlow):
    """Manage bill types from Settings -> Devices & services -> Configure."""

    def __init__(self) -> None:
        self._category_id: str | None = None

    def _manager(self) -> BillTrackerManager | None:
        return self.hass.data.get(DOMAIN, {}).get("manager")

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Show Bill Tracker settings menu."""
        if self._manager() is None:
            return self.async_abort(reason="not_setup")
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_category", "manage_category", "done"],
        )

    async def async_step_add_category(self, user_input: dict[str, Any] | None = None):
        """Add a selectable bill type and choose its recurrence."""
        manager = self._manager()
        if manager is None:
            return self.async_abort(reason="not_setup")

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await manager.async_add_category(
                    name=user_input["name"],
                    interval_months=int(user_input["interval_months"]),
                    enabled=bool(user_input["enabled"]),
                )
            except ValueError:
                errors["base"] = "invalid_category"
            else:
                return await self.async_step_init()

        interval_choices = {
            str(value): INTERVAL_LABELS[value] for value in SUPPORTED_INTERVALS
        }
        schema = vol.Schema(
            {
                vol.Required("name"): str,
                vol.Required("interval_months", default="1"): vol.In(interval_choices),
                vol.Required("enabled", default=True): bool,
            }
        )
        return self.async_show_form(
            step_id="add_category", data_schema=schema, errors=errors
        )

    async def async_step_manage_category(
        self, user_input: dict[str, Any] | None = None
    ):
        """Choose a bill type to edit or remove."""
        manager = self._manager()
        if manager is None:
            return self.async_abort(reason="not_setup")
        if not manager.categories:
            return await self.async_step_add_category()

        if user_input is not None:
            self._category_id = str(user_input["category_id"])
            action = user_input["action"]
            if action == "delete":
                return await self.async_step_delete_category()
            return await self.async_step_edit_category()

        categories = {
            str(item["id"]): (
                f"{item['name']} — {INTERVAL_LABELS.get(int(item['interval_months']), str(item['interval_months']))}"
                + ("" if item.get("enabled", True) else " — disattivata")
            )
            for item in manager.categories
        }
        return self.async_show_form(
            step_id="manage_category",
            data_schema=vol.Schema(
                {
                    vol.Required("category_id"): vol.In(categories),
                    vol.Required("action", default="edit"): vol.In(
                        {"edit": "Modifica", "delete": "Elimina"}
                    ),
                }
            ),
        )

    async def async_step_edit_category(self, user_input: dict[str, Any] | None = None):
        """Edit recurrence/name or hide a bill type from the add form."""
        manager = self._manager()
        if manager is None:
            return self.async_abort(reason="not_setup")
        item = manager.category(self._category_id or "")
        if item is None:
            return self.async_abort(reason="category_not_found")

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await manager.async_update_category(
                    str(item["id"]),
                    name=user_input["name"],
                    interval_months=int(user_input["interval_months"]),
                    enabled=bool(user_input["enabled"]),
                )
            except ValueError:
                errors["base"] = "invalid_category"
            else:
                self._category_id = None
                return await self.async_step_init()

        interval_choices = {
            str(value): INTERVAL_LABELS[value] for value in SUPPORTED_INTERVALS
        }
        schema = vol.Schema(
            {
                vol.Required("name", default=str(item["name"])): str,
                vol.Required(
                    "interval_months", default=str(item["interval_months"])
                ): vol.In(interval_choices),
                vol.Required("enabled", default=bool(item.get("enabled", True))): bool,
            }
        )
        return self.async_show_form(
            step_id="edit_category", data_schema=schema, errors=errors
        )

    async def async_step_delete_category(self, user_input: dict[str, Any] | None = None):
        """Confirm deletion of an unused bill type."""
        manager = self._manager()
        if manager is None:
            return self.async_abort(reason="not_setup")
        item = manager.category(self._category_id or "")
        if item is None:
            return self.async_abort(reason="category_not_found")

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await manager.async_delete_category(str(item["id"]))
            except ValueError:
                errors["base"] = "category_in_use"
            else:
                self._category_id = None
                return await self.async_step_init()

        return self.async_show_form(
            step_id="delete_category",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={"name": str(item["name"])},
        )

    async def async_step_done(self, user_input: dict[str, Any] | None = None):
        """Close settings."""
        return self.async_create_entry(title="", data={})
