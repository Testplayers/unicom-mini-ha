"""联通小程序（微信）接口客户端。

鉴权方式（2026-09 实测，逆自小程序包）：
  1. 取明文 openid（小程序 findOpenid 响应里的 openid）
  2. token  = POST getToken            body: {"openid": RSA(openid),            "channel": "wxmini"}
  3. 其后所有接口的 openid 字段都传  RSA(token + openid) 的 base64（token 需 URL 解码）
  4. sspbigball 返回首页大球数据（剩余话费/流量/语音）
  5. queryGoodsList 返回手机号(mainNumber)与月费(currentMonFee)
"""
from __future__ import annotations

import base64
import json
import logging
import urllib.parse
from typing import Any

import aiohttp
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .const import (
    API_GET_TOKEN,
    API_QUERY_GOODS_LIST,
    API_SSPBIGBALL,
    HEADERS_JSON,
    PUBKEY_B64,
)

_LOGGER = logging.getLogger(__name__)


class UnicomMiniError(Exception):
    """接口调用失败。"""


class UnicomMiniAPI:
    """联通小程序接口封装。"""

    def __init__(self, session: aiohttp.ClientSession, openid: str) -> None:
        self._session = session
        self._openid = openid
        try:
            self._pub = serialization.load_der_public_key(base64.b64decode(PUBKEY_B64))
        except Exception as err:  # noqa: BLE001
            raise UnicomMiniError("RSA 公钥解析失败: %s" % err) from err

    def _enc(self, text: str) -> str:
        """RSA_PKCS1v15 加密后 base64（接口要求 344 字符密文）。"""
        return base64.b64encode(
            self._pub.encrypt(text.encode("utf-8"), padding.PKCS1v15())
        ).decode()

    async def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            async with self._session.post(
                url, json=payload, headers=HEADERS_JSON,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                text = await resp.text()
        except aiohttp.ClientError as err:
            raise UnicomMiniError("网络错误: %s" % err) from err

        try:
            data = json.loads(text)
        except ValueError as err:
            raise UnicomMiniError("响应不是 JSON: %s" % text[:120]) from err
        if not isinstance(data, dict):
            raise UnicomMiniError("响应结构异常: %s" % text[:120])
        return data

    async def async_get_token(self) -> str:
        """取会话 token（同一 openid 稳定，返回体是 URL 编码的）。"""
        data = await self._post(API_GET_TOKEN, {"openid": self._enc(self._openid), "channel": "wxmini"})
        if data.get("code") != "0000":
            raise UnicomMiniError("getToken 失败: %s" % data)
        return urllib.parse.unquote(str(data.get("data") or ""))

    async def async_fetch(self) -> dict[str, Any]:
        """拉取一次全量数据（token 每次刷新，避免会话过期）。"""
        token = await self.async_get_token()
        blob = self._enc(token + self._openid)

        overview_raw = await self._post(API_SSPBIGBALL, {"openid": blob, "channel": "wxmini"})
        if overview_raw.get("code") != "0000":
            raise UnicomMiniError("sspbigball 失败: code=%s msg=%s" % (
                overview_raw.get("code"), overview_raw.get("msg")))
        overview = overview_raw.get("data") or {}
        if not isinstance(overview, dict):
            raise UnicomMiniError("sspbigball data 结构异常: %s" % str(overview)[:120])

        # 手机号 / 月费（失败不影响主数据）
        phone = None
        month_fee = None
        try:
            goods = await self._post(API_QUERY_GOODS_LIST, {"openid": blob, "channel": "wxmini"})
            if goods.get("code") == "0000":
                res = (goods.get("data") or {}).get("res") or []
                if res and isinstance(res[0], dict):
                    item = res[0]
                    phone = item.get("mainNumber") or None
                    fee = item.get("currentMonFee")
                    if fee is not None:
                        month_fee = float(fee)
        except (UnicomMiniError, TypeError, ValueError) as err:
            _LOGGER.debug("queryGoodsList 解析失败（忽略）: %s", err)

        fee_res = overview.get("feeResource") or {}
        flow_res = overview.get("flowResource") or {}
        voice_res = overview.get("voiceResource") or {}

        def _num(node: dict, key: str) -> float | None:
            try:
                return float(node.get(key))
            except (TypeError, ValueError):
                return None

        return {
            "balance": _num(fee_res, "feePersent"),
            "balance_unit": fee_res.get("newUnit") or "元",
            "balance_title": fee_res.get("dynamicFeeTitle") or "剩余话费",
            "balance_warn": str(fee_res.get("isWarn", "0")) == "1",
            "data_remaining": _num(flow_res, "flowPersent"),
            "data_unit": flow_res.get("newUnit") or "GB",
            "data_title": flow_res.get("dynamicFlowTitle") or "剩余通用流量",
            "data_warn": str(flow_res.get("isWarn", "0")) == "1",
            "voice_remaining": _num(voice_res, "voicePersent"),
            "voice_unit": voice_res.get("newUnit") or "分钟",
            "voice_title": voice_res.get("dynamicVoiceTitle") or "剩余语音",
            "voice_warn": str(voice_res.get("isWarn", "0")) == "1",
            "phone": phone,
            "month_fee": month_fee,
            "raw_overview": overview,
        }
