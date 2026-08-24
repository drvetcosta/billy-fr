"""Bill Tracker integration for Home Assistant."""
from __future__ import annotations

from pathlib import Path

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, FRONTEND_VERSION, SUPPORTED_INTERVALS
from .manager import BillTrackerManager

PLATFORMS = ["sensor"]
FRONTEND_PATH = Path(__file__).parent / "frontend" / "bill-tracker-card.js"
FRONTEND_URL = "/bill_tracker/bill-tracker-card.js"
FRONTEND_MODULE_URL = f"{FRONTEND_URL}?v={FRONTEND_VERSION}"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Bill Tracker and its frontend module."""
    for command in (
        ws_list,
        ws_add,
        ws_delete,
        ws_update,
        ws_set_paid,
        ws_category_add,
        ws_category_update,
        ws_category_delete,
        ws_payer_add,
        ws_payer_update,
        ws_payer_delete,
        ws_settlement_add,
        ws_settlement_delete,
    ):
        websocket_api.async_register_command(hass, command)

    await hass.http.async_register_static_paths(
        [StaticPathConfig(FRONTEND_URL, str(FRONTEND_PATH), False)]
    )
    add_extra_js_url(hass, FRONTEND_MODULE_URL)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Bill Tracker from a config entry."""
    manager = BillTrackerManager(hass)
    await manager.async_load()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager
    hass.data[DOMAIN]["manager"] = manager
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Bill Tracker config entry."""
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        manager = hass.data.get(DOMAIN, {}).get(entry.entry_id)
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if hass.data.get(DOMAIN, {}).get("manager") is manager:
            hass.data[DOMAIN].pop("manager", None)
    return ok


def _manager(hass: HomeAssistant) -> BillTrackerManager:
    manager = hass.data.get(DOMAIN, {}).get("manager")
    if manager is None:
        raise RuntimeError("Bill Tracker non è configurato")
    return manager


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/list",
        vol.Optional("forecast_months", default=12): vol.All(vol.Coerce(int), vol.Range(min=1, max=24)),
    }
)
@websocket_api.async_response
async def ws_list(hass, connection, msg):
    try:
        result = _manager(hass).snapshot(msg["forecast_months"])
    except RuntimeError as err:
        connection.send_error(msg["id"], "not_configured", str(err))
        return
    connection.send_result(msg["id"], result)


_SPLIT_ITEM_SCHEMA = vol.Schema(
    {
        vol.Required("payer_id"): str,
        vol.Required("percentage"): vol.Coerce(float),
    }
)

_EXPENSE_SCHEMA = {
    vol.Required("year"): vol.Coerce(int),
    vol.Required("month"): vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
    vol.Optional("category_id"): str,
    vol.Optional("category"): str,
    vol.Required("amount"): vol.Coerce(float),
    vol.Optional("note", default=""): str,
    vol.Optional("period_start_year"): vol.Coerce(int),
    vol.Optional("period_start_month"): vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
    vol.Optional("period_end_year"): vol.Coerce(int),
    vol.Optional("period_end_month"): vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
    vol.Optional("payer_id"): str,
    vol.Optional("split"): [_SPLIT_ITEM_SCHEMA],
    vol.Optional("paid"): bool,
}


def _expense_kwargs(msg):
    return {
        "year": msg["year"],
        "month": msg["month"],
        "category_id": msg.get("category_id"),
        "category_name": msg.get("category"),
        "amount": msg["amount"],
        "note": msg["note"],
        "period_start_year": msg.get("period_start_year"),
        "period_start_month": msg.get("period_start_month"),
        "period_end_year": msg.get("period_end_year"),
        "period_end_month": msg.get("period_end_month"),
        "payer_id": msg.get("payer_id"),
        "split": msg.get("split"),
        "paid": msg.get("paid"),
    }


@websocket_api.websocket_command({vol.Required("type"): "bill_tracker/add", **_EXPENSE_SCHEMA})
@websocket_api.async_response
async def ws_add(hass, connection, msg):
    try:
        item = await _manager(hass).async_add(**_expense_kwargs(msg))
    except (ValueError, RuntimeError) as err:
        connection.send_error(msg["id"], "invalid_expense", str(err))
        return
    connection.send_result(msg["id"], item)


@websocket_api.websocket_command(
    {vol.Required("type"): "bill_tracker/update", vol.Required("expense_id"): str, **_EXPENSE_SCHEMA}
)
@websocket_api.async_response
async def ws_update(hass, connection, msg):
    try:
        item = await _manager(hass).async_update(msg["expense_id"], **_expense_kwargs(msg))
    except (ValueError, RuntimeError) as err:
        connection.send_error(msg["id"], "invalid_expense", str(err))
        return
    if item is None:
        connection.send_error(msg["id"], "not_found", "Spesa non trovata")
        return
    connection.send_result(msg["id"], item)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/set_paid",
        vol.Required("expense_id"): str,
        vol.Required("paid"): bool,
    }
)
@websocket_api.async_response
async def ws_set_paid(hass, connection, msg):
    try:
        item = await _manager(hass).async_set_paid(msg["expense_id"], msg["paid"])
    except RuntimeError as err:
        connection.send_error(msg["id"], "not_configured", str(err))
        return
    if item is None:
        connection.send_error(msg["id"], "not_found", "Spesa non trovata")
        return
    connection.send_result(msg["id"], item)


@websocket_api.websocket_command(
    {vol.Required("type"): "bill_tracker/delete", vol.Required("expense_id"): str}
)
@websocket_api.async_response
async def ws_delete(hass, connection, msg):
    try:
        deleted = await _manager(hass).async_delete(msg["expense_id"])
    except RuntimeError as err:
        connection.send_error(msg["id"], "not_configured", str(err))
        return
    connection.send_result(msg["id"], {"deleted": deleted})


_CATEGORY_COMMON = {
    vol.Required("name"): str,
    vol.Required("interval_months"): vol.In(SUPPORTED_INTERVALS),
    vol.Optional("enabled", default=True): bool,
    vol.Optional("default_payer_id"): str,
    vol.Optional("color"): str,
}


@websocket_api.websocket_command({vol.Required("type"): "bill_tracker/category/add", **_CATEGORY_COMMON})
@websocket_api.async_response
async def ws_category_add(hass, connection, msg):
    try:
        category = await _manager(hass).async_add_category(
            name=msg["name"],
            interval_months=msg["interval_months"],
            enabled=msg["enabled"],
            default_payer_id=msg.get("default_payer_id"),
            color=msg.get("color"),
        )
    except (ValueError, RuntimeError) as err:
        connection.send_error(msg["id"], "invalid_category", str(err))
        return
    connection.send_result(msg["id"], category)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/category/update",
        vol.Required("category_id"): str,
        **_CATEGORY_COMMON,
    }
)
@websocket_api.async_response
async def ws_category_update(hass, connection, msg):
    try:
        category = await _manager(hass).async_update_category(
            msg["category_id"],
            name=msg["name"],
            interval_months=msg["interval_months"],
            enabled=msg["enabled"],
            default_payer_id=msg.get("default_payer_id"),
            color=msg.get("color"),
        )
    except (ValueError, RuntimeError) as err:
        connection.send_error(msg["id"], "invalid_category", str(err))
        return
    if category is None:
        connection.send_error(msg["id"], "not_found", "Tipo di bolletta non trovato")
        return
    connection.send_result(msg["id"], category)


@websocket_api.websocket_command(
    {vol.Required("type"): "bill_tracker/category/delete", vol.Required("category_id"): str}
)
@websocket_api.async_response
async def ws_category_delete(hass, connection, msg):
    try:
        deleted = await _manager(hass).async_delete_category(msg["category_id"])
    except (ValueError, RuntimeError) as err:
        connection.send_error(msg["id"], "category_in_use", str(err))
        return
    connection.send_result(msg["id"], {"deleted": deleted})


_PAYER_COMMON = {
    vol.Required("name"): str,
    vol.Optional("share_percent", default=50.0): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
    vol.Optional("paypal_me", default=""): str,
    vol.Optional("enabled", default=True): bool,
}


@websocket_api.websocket_command({vol.Required("type"): "bill_tracker/payer/add", **_PAYER_COMMON})
@websocket_api.async_response
async def ws_payer_add(hass, connection, msg):
    try:
        payer = await _manager(hass).async_add_payer(
            name=msg["name"],
            share_percent=msg["share_percent"],
            paypal_me=msg["paypal_me"],
            enabled=msg["enabled"],
        )
    except (ValueError, RuntimeError) as err:
        connection.send_error(msg["id"], "invalid_payer", str(err))
        return
    connection.send_result(msg["id"], payer)


@websocket_api.websocket_command(
    {vol.Required("type"): "bill_tracker/payer/update", vol.Required("payer_id"): str, **_PAYER_COMMON}
)
@websocket_api.async_response
async def ws_payer_update(hass, connection, msg):
    try:
        payer = await _manager(hass).async_update_payer(
            msg["payer_id"],
            name=msg["name"],
            share_percent=msg["share_percent"],
            paypal_me=msg["paypal_me"],
            enabled=msg["enabled"],
        )
    except (ValueError, RuntimeError) as err:
        connection.send_error(msg["id"], "invalid_payer", str(err))
        return
    if payer is None:
        connection.send_error(msg["id"], "not_found", "Pagante non trovato")
        return
    connection.send_result(msg["id"], payer)


@websocket_api.websocket_command(
    {vol.Required("type"): "bill_tracker/payer/delete", vol.Required("payer_id"): str}
)
@websocket_api.async_response
async def ws_payer_delete(hass, connection, msg):
    try:
        deleted = await _manager(hass).async_delete_payer(msg["payer_id"])
    except (ValueError, RuntimeError) as err:
        connection.send_error(msg["id"], "payer_in_use", str(err))
        return
    connection.send_result(msg["id"], {"deleted": deleted})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/settlement/add",
        vol.Required("from_payer_id"): str,
        vol.Required("to_payer_id"): str,
        vol.Required("amount"): vol.Coerce(float),
        vol.Optional("note", default=""): str,
    }
)
@websocket_api.async_response
async def ws_settlement_add(hass, connection, msg):
    try:
        item = await _manager(hass).async_add_settlement(
            from_payer_id=msg["from_payer_id"],
            to_payer_id=msg["to_payer_id"],
            amount=msg["amount"],
            note=msg["note"],
        )
    except (ValueError, RuntimeError) as err:
        connection.send_error(msg["id"], "invalid_settlement", str(err))
        return
    connection.send_result(msg["id"], item)


@websocket_api.websocket_command(
    {vol.Required("type"): "bill_tracker/settlement/delete", vol.Required("settlement_id"): str}
)
@websocket_api.async_response
async def ws_settlement_delete(hass, connection, msg):
    try:
        deleted = await _manager(hass).async_delete_settlement(msg["settlement_id"])
    except RuntimeError as err:
        connection.send_error(msg["id"], "not_configured", str(err))
        return
    connection.send_result(msg["id"], {"deleted": deleted})
