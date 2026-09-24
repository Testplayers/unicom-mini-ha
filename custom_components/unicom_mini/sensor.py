"""联通小程序话费传感器。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfInformation, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN


@dataclass(frozen=True, kw_only=True)
class UnicomSensorDescription(SensorEntityDescription):
    """带取值函数的传感器描述。"""

    value_fn: Callable[[dict[str, Any]], Any]
    attributes_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


SENSORS: tuple[UnicomSensorDescription, ...] = (
    UnicomSensorDescription(
        key="balance",
        name="剩余话费",
        icon="mdi:wallet",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="CNY",
        value_fn=lambda d: d.get("balance"),
        attributes_fn=lambda d: {
            "标题": d.get("balance_title"),
            "单位": d.get("balance_unit"),
            "预警": d.get("balance_warn"),
            "手机号": d.get("phone"),
            "信用额度": d.get("credit_limit"),
        },
    ),
    UnicomSensorDescription(
        key="data_remaining",
        name="剩余通用流量",
        icon="mdi:cellphone-link",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        value_fn=lambda d: d.get("data_remaining"),
        attributes_fn=lambda d: {
            "标题": d.get("data_title"),
            "单位": d.get("data_unit"),
            "预警": d.get("data_warn"),
        },
    ),
    UnicomSensorDescription(
        key="voice_remaining",
        name="剩余语音",
        icon="mdi:phone",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: d.get("voice_remaining"),
        attributes_fn=lambda d: {
            "标题": d.get("voice_title"),
            "单位": d.get("voice_unit"),
            "预警": d.get("voice_warn"),
        },
    ),
    UnicomSensorDescription(
        key="balance_available",
        name="可用余额",
        icon="mdi:cash-multiple",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="CNY",
        value_fn=lambda d: d.get("balance_available"),
    ),
    UnicomSensorDescription(
        key="month_cost",
        name="本月消费",
        icon="mdi:cash-clock",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="CNY",
        value_fn=lambda d: d.get("month_cost"),
    ),
    UnicomSensorDescription(
        key="owed",
        name="欠费",
        icon="mdi:alert-circle-outline",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="CNY",
        value_fn=lambda d: d.get("owed"),
    ),
    UnicomSensorDescription(
        key="carry_over",
        name="结转话费",
        icon="mdi:calendar-sync",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="CNY",
        value_fn=lambda d: d.get("carry_over"),
    ),
    # ---- 微厅余量明细（流量/语音/短信分项）----
    UnicomSensorDescription(
        key="plan_name",
        name="套餐名称",
        icon="mdi:sim-outline",
        value_fn=lambda d: d.get("plan_name"),
        attributes_fn=lambda d: {
            "流量分项": d.get("flow_sums"),
            "查询时间": d.get("flow_query_time"),
        },
    ),
    UnicomSensorDescription(
        key="flow_total",
        name="流量总量",
        icon="mdi:network",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        value_fn=lambda d: d.get("flow_total"),
        attributes_fn=lambda d: {
            "已用": d.get("flow_used"),
            "剩余": d.get("flow_remain"),
            "使用率": d.get("use_percent"),
            "资源包": d.get("flow_items"),
            "分项": d.get("flow_sums"),
        },
    ),
    UnicomSensorDescription(
        key="flow_used",
        name="流量已用",
        icon="mdi:upload-network",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        value_fn=lambda d: d.get("flow_used"),
        attributes_fn=lambda d: {"资源包明细": d.get("flow_items")},
    ),
    UnicomSensorDescription(
        key="flow_percent",
        name="流量使用率",
        icon="mdi:percent",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="%",
        value_fn=lambda d: d.get("use_percent"),
    ),
    UnicomSensorDescription(
        key="voice_total",
        name="语音总量",
        icon="mdi:phone",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: d.get("voice_total"),
        attributes_fn=lambda d: {
            "已用": d.get("voice_used"),
            "剩余": d.get("voice_remain"),
            "资源包": d.get("voice_items"),
        },
    ),
    UnicomSensorDescription(
        key="voice_used",
        name="语音已用",
        icon="mdi:phone-in-talk",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: d.get("voice_used"),
    ),
    UnicomSensorDescription(
        key="sms_remain",
        name="短信剩余",
        icon="mdi:message-text",
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="条",
        value_fn=lambda d: d.get("sms_remain"),
        attributes_fn=lambda d: {"总量": d.get("sms_total"), "已用": d.get("sms_used")},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """建立传感器实体。"""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        UnicomSensor(coordinator, entry, desc) for desc in SENSORS
    )


class UnicomSensor(CoordinatorEntity, SensorEntity):
    """一个联通数据传感器。"""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator, entry: ConfigEntry, description: UnicomSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = "%s_%s" % (entry.entry_id, description.key)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": DEFAULT_NAME,
            "manufacturer": "中国联通",
            "model": "微信小程序",
        }

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        return self.entity_description.value_fn(data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        fn = self.entity_description.attributes_fn
        if not fn:
            return {}
        return {k: v for k, v in fn(self.coordinator.data or {}).items() if v is not None}
