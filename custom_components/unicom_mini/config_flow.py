"""配置流程：让用户填微信小程序 openid。"""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import UnicomMiniAPI, UnicomMiniError
from .const import (
    CONF_OPENID,
    CONF_REFRESH_INTERVAL,
    DEFAULT_REFRESH_INTERVAL,
    DOMAIN,
    NAME,
)

_LOGGER = logging.getLogger(__name__)


class UnicomMiniConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """添加配置项。"""

    VERSION = 1

    def __init__(self) -> None:
        self._last_error = ""

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            openid = str(user_input[CONF_OPENID]).strip()
            api = UnicomMiniAPI(async_get_clientsession(self.hass), openid)
            try:
                data = await api.async_fetch()
            except UnicomMiniError as err:
                self._last_error = str(err)
                _LOGGER.warning("联通校验失败: %s", err)
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(openid)
                self._abort_if_unique_id_configured()
                title = "%s (%s)" % (NAME, data.get("phone") or "微信小程序")
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_OPENID: openid,
                        CONF_REFRESH_INTERVAL: int(user_input[CONF_REFRESH_INTERVAL]),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_OPENID, default=(user_input or {}).get(CONF_OPENID, "")
                ): str,
                vol.Optional(
                    CONF_REFRESH_INTERVAL,
                    default=(user_input or {}).get(CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=1440)),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={"error": self._last_error or "—"},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """选项流程。"""
        return UnicomMiniOptionsFlow()


class UnicomMiniOptionsFlow(config_entries.OptionsFlow):
    """修改刷新间隔。"""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(
            CONF_REFRESH_INTERVAL,
            self.config_entry.data.get(CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_REFRESH_INTERVAL, default=current): vol.All(
                        vol.Coerce(int), vol.Range(min=5, max=1440)
                    ),
                }
            ),
        )
