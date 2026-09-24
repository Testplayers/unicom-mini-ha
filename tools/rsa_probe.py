#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""联通小程序接口探针：复现 RSA 加密，验证 getToken → sspbigball → getTicket 全链路。

用法：
    python rsa_probe.py --openid oFroJ0ZkvVVZPkAIA0AV5wRU2eOY
    python rsa_probe.py --openid ... --pubkey MIIBIjANBgkqh...

说明：
  - openid 必须是从 `POST /wxapplet/applet/findOpenid` **响应**里拿到的明文；
  - 使用前请先在微信里登录一次小程序，否则会报 1002（服务端没有绑定关系）。
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import padding
except ImportError:
    sys.exit("需要 cryptography：pip install cryptography")

# 微信小程序「中国联通」(wx56af9763578b9a93) 客户端内置的 2048 位 RSA 公钥
DEFAULT_PUBKEY = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA7vCN/AU3QMTuRcQoOsJP1fo6LbU++DxS1QQb"
    "gYrkmatPbb7Hactr7OcTLWYa/ZoOUNuYeCFQtrJ8P8YIDASn2wjIwFteCIdOeWMUcKahdaNvqiS40epA"
    "2jFSiC/4hwZXDFNlPtrWsllcCtVFPV1bEGh3rYKQNI/ZZQVMKzuccSV0BwIC/EjSwaPY1p7x7ACki5V"
    "3VPwBut2xkmVDsJDKrgwBDeevpZHKKdHJKMUV8S9NbO7Mq4MbprnTMwGt69no7KP2P38Mh+FMbMBIaI"
    "olggjudziyWE9HdaJQiY9cWb9PFJzwY3/nxDHU5nBOeTI/FEo3sWrKWLEdFILIlxGmQIDAQAB"
)

APPID = "wx56af9763578b9a93"
BASE = "https://mina.10010.com/wxapplet/weixinNew/"
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 MicroMessenger/7.0"),
    "xweb_xhr": "1",
    "X-Tingyun": "c=M|4Nl_NnGbjwY",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://servicewechat.com/%s/494/page-frame.html" % APPID,
}


def post(path: str, payload: dict, label: str) -> dict | None:
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(), method="POST", headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        print("  [%-28s] 请求异常: %r" % (label, e))
        return None
    print("  [%-28s] %s" % (label, body[:200].replace("\n", " ")))
    try:
        return json.loads(body)
    except ValueError:
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description="联通小程序接口探针")
    ap.add_argument("--openid", required=True, help="明文 openid（findOpenid 响应里那个）")
    ap.add_argument("--pubkey", default=DEFAULT_PUBKEY, help="RSA 公钥 base64（默认用内置的）")
    args = ap.parse_args()

    pub = serialization.load_der_public_key(base64.b64decode("".join(args.pubkey.split())))
    enc = lambda s: base64.b64encode(pub.encrypt(s.encode(), padding.PKCS1v15())).decode()  # noqa: E731
    print("公钥: %d 位 | 明文 openid 长度: %d" % (pub.key_size, len(args.openid)))

    print("\n=== 1) getToken ===")
    t = post("getToken", {"openid": enc(args.openid), "channel": "wxmini"}, "getToken")
    token = urllib.parse.unquote(str((t or {}).get("data") or ""))
    print("      token 长度 = %d" % len(token))
    if not token:
        sys.exit("拿不到 token，检查 openid / 网络")

    blob = enc(token + args.openid)
    print("\n=== 2) sspbigball（首页：话费/流量/语音）===")
    big = post("sspbigball", {"openid": blob, "channel": "wxmini"}, "sspbigball")
    data = (big or {}).get("data") or {}
    if isinstance(data, dict):
        for key in ("feeResource", "flowResource", "voiceResource"):
            node = data.get(key) or {}
            print("      %-14s %s" % (key, json.dumps(node, ensure_ascii=False)))
        if (big or {}).get("code") == "1002":
            print("      ⚠ 1002 = 服务端没有 openid↔手机号绑定：请先在微信里登录一次小程序")

    print("\n=== 3) getTicket（字段名是大写 openId）===")
    post("getTicket", {"openId": blob, "channel": "wxmini"}, "getTicket")

    print("\n=== 4) queryGoodsList（手机号 / 月租）===")
    goods = post("queryGoodsList", {"openid": blob, "channel": "wxmini"}, "queryGoodsList")
    res = ((goods or {}).get("data") or {}).get("res") or []
    if res and isinstance(res[0], dict):
        print("      手机号 = %s | 月租 = %s" % (res[0].get("mainNumber"), res[0].get("currentMonFee")))


if __name__ == "__main__":
    main()
