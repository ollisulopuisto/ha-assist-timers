"""Assist timer controls HA lacks: stop a satellite's ring, pause/unpause by timer id.

stop: stop an Assist timer ringing on an ESPHome satellite (e.g. Voice PE) from HA.

The ring plays on the satellite media player's *announcement* pipeline. HA's
media_player.media_stop sends STOP without the announcement flag, which the
device applies to its *media* pipeline, so the ring goes on. This service sends
STOP with announcement=True, as the Voice PE firmware does when "stop" is said.

It reaches into HA's ESPHome media player entity for its API client and key
(private fields). tests/test_ring_stop.py checks they still exist; if an HA
upgrade renames them, the service raises instead of silently doing nothing.

pause / unpause: by timer id (from sensor.assist_timers), through the intent
component's TimerManager, so the satellite gets the usual UPDATED event. The
HassPauseTimer intent can only pick a timer by name/area/duration, which is
ambiguous for e.g. two unnamed 5-minute timers. HA's planned timer_list entities
will offer this natively; until then this uses TimerManager (intent/timers.py).
"""

from __future__ import annotations

import voluptuous as vol
from aioesphomeapi import MediaPlayerCommand
from homeassistant.components.intent.const import TIMER_DATA
from homeassistant.components.media_player import DATA_COMPONENT
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_extract_entity_ids
from homeassistant.helpers.typing import ConfigType

DOMAIN = "assist_timer_ring"
CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def stop(call: ServiceCall) -> None:
        component = hass.data[DATA_COMPONENT]
        for entity_id in await async_extract_entity_ids(call):
            entity = component.get_entity(entity_id)
            client = getattr(entity, "_client", None)
            key = getattr(entity, "_key", None)
            info = getattr(entity, "_static_info", None)
            if client is None or key is None or info is None or not hasattr(client, "media_player_command"):
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="not_esphome",
                    translation_placeholders={"entity_id": entity_id},
                )
            client.media_player_command(
                key, command=MediaPlayerCommand.STOP, announcement=True, device_id=info.device_id
            )

    hass.services.async_register(DOMAIN, "stop", stop)

    def by_id(method: str):
        async def handler(call: ServiceCall) -> None:
            manager = hass.data[TIMER_DATA]
            timer_id = call.data["timer_id"]
            if timer_id not in manager.timers:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="timer_not_found",
                    translation_placeholders={"timer_id": timer_id},
                )
            getattr(manager, method)(timer_id)

        return handler

    schema = vol.Schema({vol.Required("timer_id"): cv.string})
    hass.services.async_register(DOMAIN, "pause", by_id("pause_timer"), schema=schema)
    hass.services.async_register(DOMAIN, "unpause", by_id("unpause_timer"), schema=schema)
    return True
