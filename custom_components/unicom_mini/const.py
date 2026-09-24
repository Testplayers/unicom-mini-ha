"""Constants for the 联通小程序话费 integration."""
from homeassistant.const import Platform

DOMAIN = "unicom_mini"
NAME = "联通小程序话费"

PLATFORMS = [Platform.SENSOR]

CONF_OPENID = "openid"
CONF_REFRESH_INTERVAL = "refresh_interval"

DEFAULT_REFRESH_INTERVAL = 30  # minutes
DEFAULT_NAME = "联通"

# 微信小程序（中国联通）接口
APPID = "wx56af9763578b9a93"
API_BASE = "https://mina.10010.com/wxapplet/weixinNew/"
API_GET_TOKEN = API_BASE + "getToken"
API_SSPBIGBALL = API_BASE + "sspbigball"
API_QUERY_GOODS_LIST = API_BASE + "queryGoodsList"
API_BALANCE_BROADCAST = API_BASE + "sspbalcbroadcast"
API_GET_TICKET = API_BASE + "getTicket"

# ---- 微营业厅（mxx）链路：拿 microHall Cookie 后可查流量/语音/短信分项 ----
SERVICE_ENTRANCE = "https://mxx.client.10010.com/servicebusiness/wx/serviceEntrance"
SERVICE_CODE = "YH10005"        # 余量查询页
SERVICE_CHANNEL = "XCXYLCXYY"   # 与小程序 webview 一致
API_MXX_FLOW = ("https://mxx.client.10010.com/servicequerybusiness/operationservice/"
                "queryOcsPackageFlowLeftContentRevisedInJune")
API_MXX_BALANCE = "https://mxx.client.10010.com/servicequerybusiness/balancenew/accountBalancenew.htm"

# 小程序 JS 里 getRsa().setPublicKey("...") 的固定 2048 位公钥（DER/SPKI，base64）
# 用途：接口的 openid 字段必须是 RSA_PKCS1v15(明文) 的 base64，
# 明文 = token + openid（token 来自 getToken，首次为空串）
PUBKEY_B64 = (
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA7vCN/AU3QMTuRcQoOsJP1fo6LbU++DxS1QQbgYrkmatPbb7Hactr7O"
    "cTLWYa/ZoOUNuYeCFQtrJ8P8YIDASn2wjIwFteCIdOeWMUcKahdaNvqiS40epA2jFSiC/4hwZXDFNlPtrWsllcCtVFPV1bEGh3"
    "rYKQNI/ZZQVMKzuccSV0BwIC/EjSwaPY1p7x7ACki5V3VPwBut2xkmVDsJDKrgwBDeevpZHKKdHJKMUV8S9NbO7Mq4MbprnTMw"
    "Gt69no7KP2P38Mh+FMbMBIaIolggjjudziyWE9HdaJQiY9cWb9PFJzwY3/nxDHU5nBOeTI/FEo3sWrKWLEdFILIlxGmQIDAQAB"
)

# 照抄小程序的请求头（Referer 指向小程序版本页，缺失会被判 9999）
_REFERER = "https://servicewechat.com/%s/494/page-frame.html" % APPID
_WX_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 MicroMessenger/7.0"
)
HEADERS_JSON = {
    "Content-Type": "application/json",
    "User-Agent": _WX_UA,
    "xweb_xhr": "1",
    "X-Tingyun": "c=M|4Nl_NnGbjwY",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": _REFERER,
}

# 微厅（mxx）接口用表单提交，且需要小程序 webview 的 UA
HEADERS_FORM = {
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": _WX_UA,
    "xweb_xhr": "1",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": _REFERER,
}
