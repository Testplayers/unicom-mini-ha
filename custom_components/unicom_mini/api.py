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
    API_BALANCE_BROADCAST,
    API_GET_TICKET,
    API_GET_TOKEN,
    API_MXX_FLOW,
    API_QUERY_GOODS_LIST,
    API_SSPBIGBALL,
    HEADERS_FORM,
    HEADERS_JSON,
    PUBKEY_B64,
    SERVICE_CHANNEL,
    SERVICE_CODE,
    SERVICE_ENTRANCE,
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

    async def _async_microhall_cookies(self, ticket: str) -> dict[str, str]:
        """微营业厅会话：serviceEntrance 的响应里带 microHallUser/microHallAccessToken。

        纯服务端可复现（无需浏览器 / 无需装证书）：手动跟随 302 并收集每一跳的 Set-Cookie。
        """
        cookies: dict[str, str] = {}
        url: str | None = SERVICE_ENTRANCE
        params: dict[str, str] | None = {
            "ticket": ticket, "servicecode": SERVICE_CODE, "ticketChannel": SERVICE_CHANNEL}
        for _ in range(4):
            if not url:
                break
            async with self._session.get(
                url, params=params, headers=HEADERS_FORM, allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                for key, morsel in resp.cookies.items():
                    cookies[key] = morsel.value
                location = resp.headers.get("Location")
                await resp.read()
                if resp.status in (301, 302, 303, 307, 308) and location:
                    url, params = location, None
                    continue
                break
        return cookies

    async def _async_mxx_flow(self, ticket: str, cookie_header: str) -> dict[str, Any]:
        """余量明细（流量/语音/短信分项）。"""
        form = {
            "duanlianjieabc": "", "channelCode": "", "serviceType": "", "saleChannel": "",
            "externalSources": "", "contactCode": "", "ticket": ticket, "ticketPhone": "wx",
            "ticketChannel": SERVICE_CHANNEL, "language": "chinese",
        }
        headers = dict(HEADERS_FORM)
        if cookie_header:
            headers["Cookie"] = cookie_header
        try:
            async with self._session.post(
                API_MXX_FLOW, data=form, headers=headers,
                timeout=aiohttp.ClientTimeout(total=40),
            ) as resp:
                text = await resp.text()
        except aiohttp.ClientError as err:
            raise UnicomMiniError("微厅余量接口网络错误: %s" % err) from err
        try:
            data = json.loads(text)
        except ValueError as err:
            raise UnicomMiniError("微厅余量接口返回非 JSON: %s" % text[:120]) from err
        if not isinstance(data, dict):
            raise UnicomMiniError("微厅余量接口结构异常: %s" % text[:120])
        return data

    @staticmethod
    def _parse_flow_detail(detail: dict[str, Any]) -> dict[str, Any]:
        """把微厅余量响应拆成传感器可用的字段（流量按 MB→GB）。"""

        def _num(value: Any) -> float | None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        def _mb_to_gb(value: Any) -> float | None:
            num = _num(value)
            return round(num / 1024, 2) if num is not None else None

        blocks: dict[str, dict] = {}
        for item in detail.get("resources") or []:
            if isinstance(item, dict):
                blocks[str(item.get("type", "")).lower()] = item

        def _block(kind: str) -> dict:
            return blocks.get(kind) or {}

        flow_blk, voice_blk, sms_blk = _block("flow"), _block("voice"), _block("smslist")

        def _items(blk: dict, scale: float) -> list[dict[str, Any]]:
            out = []
            for det in (blk.get("details") or []):
                if not isinstance(det, dict):
                    continue
                used, remain, total = _num(det.get("use")), _num(det.get("remain")), _num(det.get("total"))
                row: dict[str, Any] = {
                    "名称": det.get("addUpItemName"),
                    "套餐": det.get("feePolicyName"),
                }
                if used is not None:
                    row["已用"] = round(used / scale, 2)
                if remain is not None:
                    row["剩余"] = round(remain / scale, 2)
                if total is not None:
                    row["总量"] = round(total / scale, 2)
                if det.get("usedPercent") is not None:
                    row["使用率"] = "%s%%" % det.get("usedPercent")
                if _num(det.get("beforeTotal")):
                    row["上月结转"] = round(_num(det.get("beforeTotal")) / scale, 2)
                out.append(row)
            return out

        flow_used = _mb_to_gb(flow_blk.get("userResource"))
        flow_remain = _mb_to_gb(flow_blk.get("remainResource"))
        flow_total = (round(flow_used + flow_remain, 2)
                      if flow_used is not None and flow_remain is not None else None)

        voice_used, voice_remain = _num(voice_blk.get("userResource")), _num(voice_blk.get("remainResource"))
        voice_total = (voice_used + voice_remain
                       if voice_used is not None and voice_remain is not None else None)
        sms_used, sms_remain = _num(sms_blk.get("userResource")), _num(sms_blk.get("remainResource"))

        # 通用/定向/闲时/漫游 分项（flowtype: 1 通用 2 专属 3 闲时区域 4 国际）
        type_map = {"1": "通用流量", "2": "专属流量", "3": "闲时/区域流量", "4": "国际漫游流量"}
        sums: dict[str, Any] = {}
        for item in detail.get("fresSumList") or []:
            if not isinstance(item, dict):
                continue
            label = type_map.get(str(item.get("flowtype")))
            if not label:
                continue
            used = _mb_to_gb(item.get("xusedvalue"))
            remain = _mb_to_gb(item.get("xcanusevalue"))
            if used is None and remain is None:
                continue
            sums[label] = {"已用": used, "剩余": remain,
                           "总量": round((used or 0) + (remain or 0), 2)}

        # 注意：顶层 usePercent 是「分段比例条」的列表（不是单值），自己算才可靠
        percent = (round(flow_used / flow_total * 100, 2)
                   if flow_used is not None and flow_total else None)

        return {
            "plan_name": detail.get("packageName"),
            "flow_total": flow_total,
            "flow_used": flow_used,
            "flow_remain": flow_remain,
            "flow_exceed": _num(detail.get("flowExceed")),
            "use_percent": percent,
            "voice_total": voice_total,
            "voice_used": voice_used,
            "voice_remain": voice_remain,
            "sms_total": (sms_used + sms_remain) if (sms_used, sms_remain) != (None, None) else None,
            "sms_used": sms_used,
            "sms_remain": sms_remain,
            "flow_items": _items(flow_blk, 1024),
            "voice_items": _items(voice_blk, 1),
            "flow_sums": sums,
            "flow_query_time": detail.get("time"),
        }

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

        # 手机号（queryGoodsList 的 res[0].mainNumber）
        # 注意：同一条 res[0] 里也有 currentMonFee / monthFee，但那是「推荐商品」的价格
        # （productName 形如「单宽带40元/月300M」），不是本机套餐月租，别拿来当月租。
        phone = None
        try:
            goods = await self._post(API_QUERY_GOODS_LIST, {"openid": blob, "channel": "wxmini"})
            if goods.get("code") == "0000":
                res = (goods.get("data") or {}).get("res") or []
                if res and isinstance(res[0], dict):
                    phone = res[0].get("mainNumber") or None
        except (UnicomMiniError, TypeError, ValueError) as err:
            _LOGGER.debug("queryGoodsList 解析失败（忽略）: %s", err)

        # 账务明细（余额播报 sspbalcbroadcast）：可用余额/本月消费/欠费/结转/信用额度
        acct: dict[str, Any] = {}
        try:
            bc = await self._post(API_BALANCE_BROADCAST, {"openid": blob, "channel": "wxmini"})
            if bc.get("code") == "0000":
                rows = bc.get("data") or []
                if rows and isinstance(rows[0], dict):
                    acct = rows[0]
        except (UnicomMiniError, TypeError, ValueError) as err:
            _LOGGER.debug("sspbalcbroadcast 解析失败（忽略）: %s", err)

        def _acct(key: str) -> float | None:
            try:
                return float(acct.get(key))
            except (TypeError, ValueError):
                return None

        # 微厅链路：getTicket → serviceEntrance 取 microHall Cookie → 余量明细（流量/语音/短信分项）
        ticket = ""
        flow_detail: dict[str, Any] = {}
        try:
            t = await self._post(API_GET_TICKET, {"openId": blob, "channel": "wxmini"})
            if t.get("code") == "0000":
                ticket = str(t.get("data") or "")
        except (UnicomMiniError, TypeError, ValueError) as err:
            _LOGGER.debug("getTicket 失败（忽略）: %s", err)

        if ticket:
            try:
                cookies = await self._async_microhall_cookies(ticket)
                if cookies.get("microHallUser"):
                    cookie_header = "; ".join("%s=%s" % (k, v) for k, v in cookies.items())
                    flow_detail = self._parse_flow_detail(
                        await self._async_mxx_flow(ticket, cookie_header))
                else:
                    _LOGGER.warning("微厅未下发 microHall Cookie（收到 %s）", sorted(cookies))
            except (UnicomMiniError, TypeError, ValueError) as err:
                _LOGGER.warning("微厅余量明细失败（不影响基础数据）: %s", err)

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
            "balance_available": _acct("CANUSE_FEE_CUST"),
            "month_cost": _acct("REAL_FEE_CUST"),
            "owed": _acct("ALLBOWE_FEE"),
            "carry_over": _acct("CARRY_INFO_ALL_FEE"),
            "credit_limit": _acct("CREDIT_VALUE"),
            # 微厅余量明细（可能为空 dict：拿不到微厅会话时）
            **flow_detail,
            "raw_overview": overview,
        }
