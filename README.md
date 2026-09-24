# 联通（微信小程序）套餐余量 for Home Assistant

把微信小程序「中国联通」首页的数据接进 Home Assistant：**剩余话费 / 剩余通用流量 / 剩余语音 / 月租**，只用自己的 `openid`，不需要账号密码。

- 实测环境：Home Assistant OS 2026.9（Core `2026.9.3`，amd64）+ 微信 PC 端小程序（`wx56af9763578b9a93`，版本 494）
- 本仓库同时包含**集成源码**（`custom_components/unicom_mini/`）、**逆向工具**（`tools/`）与**完整踩坑记录**（`docs/01-逆向过程与踩坑.md`）

---

## 一、声明（请先读）

1. **仅供个人学习与自用**：用于读取**自己名下**号码的套餐余量。
2. **与官方无关**：本项目未获中国联通授权，也不是任何官方 SDK；接口协议来自**对公开请求的观察**（抓包 + 客户端包分析）。
3. **请勿滥用**：不要用于批量抓取、代查他人号码、转卖数据等用途；使用前请自行确认是否符合中国联通服务条款及当地法律法规。
4. **不收集任何账号密码**：本集成**只要一个 openid**（微信小程序里代表"你"的标识），不含手机号密码、短信验证码、登录态 Cookie。
5. **接口随时可能变**：联通改协议即失效；作者不保证可用性，使用风险自负。
6. **无意侵权**：仓库内不包含任何联通客户端代码或私有密钥（只有客户端里本来就公开下发给每个用户的 **RSA 公钥**）。若权利人认为内容不当，请提 Issue，我会立即删除。

---

## 二、数据来源（使用来源）

| 展示项 | 接口 | 说明 |
|---|---|---|
| 剩余话费 | `POST https://mina.10010.com/wxapplet/weixinNew/sspbigball` | 小程序首页"大球"数据，字段 `data.feeResource.feePersent` |
| 剩余通用流量 | 同上 | `data.flowResource.flowPersent` |
| 剩余语音 | 同上 | `data.voiceResource.voicePersent` |
| 可用余额 / 本月消费 / 欠费 / 结转话费 | `POST .../weixinNew/sspbalcbroadcast` | `CANUSE_FEE_CUST` / `REAL_FEE_CUST` / `ALLBOWE_FEE` / `CARRY_INFO_ALL_FEE` |
| 手机号 | `POST .../weixinNew/queryGoodsList` | `data.res[0].mainNumber` |
| 流量/语音/短信 **分项明细**、套餐名 | `POST https://mxx.client.10010.com/servicequerybusiness/operationservice/queryOcsPackageFlowLeftContentRevisedInJune` | 需先建立「微厅」会话，见下 |
| 微厅会话 | `GET https://mxx.client.10010.com/servicebusiness/wx/serviceEntrance?ticket=..&servicecode=YH10005&ticketChannel=XCXYLCXYY` | 响应（302）会 `Set-Cookie`：`microHallUser` / `microHallAccessToken` |
| 会话 token | `POST .../weixinNew/getToken` | 每轮刷新时重新获取 |

**鉴权方式（关键）**：这些接口的 `openid` 字段**不是明文**，而是 `RSA-2048( token + openid )` 的 base64 密文（固定 344 字符）：

```
token    = getToken( {"openid": RSA(openid)} )              # 取到后 URL 解码
任意接口  = { "openid": RSA(token + openid), "channel": "wxmini" }
```

RSA 公钥取自小程序 JS 里的 `getRsa().setPublicKey("...")`（2048 位，已内置在集成 `const.py`，可直接查看核对）。

---

## 三、逆向思路与踩坑（简版）

完整过程见 **[docs/01-逆向过程与踩坑.md](docs/01-逆向过程与踩坑.md)**，这里只列结论：

1. **已有开源集成当时全部报错**（`getTicket failed: code=9999`）——原因不是网络，而是它们仍发送**明文 openid**，而联通早已改成 RSA 加密。
2. **加密规则藏在客户端**：抓包里每个请求的 `openid` 都是 256 字节随机密文（base64 后 344 字符），每次不同 → 典型 RSA；明文只在 `findOpenid` 的**响应**里出现过。
3. **公钥从微信 PC 小程序包里挖出来**：`__APP__.wxapkg`（`V1MMWX` 加密）→ PBKDF2-SHA1(appid, `saltiest`, 1000) 作 AES-256-CBC 密钥解前 1024 字节 + 其余字节异或 `ord(appid[-2])` → 解包后在 `app-service.js` 搜 `setPublicKey`。
4. **明文是 `token + openid`**：JS 原句 `getRsa().encrypt("".concat(token).concat(openid))`，`token` 来自 `getToken`（首次是空串）。
5. **必须先用微信登录过小程序**：否则所有接口报 `1002 获取用户绑定信息异常`（服务端没有 openid↔手机号绑定）。而建立绑定的 `findMobileByOpenid` 需要微信 `wx.login` 的**一次性 code**，服务端伪造不出来 —— **这一步只能在微信里点一次**。
6. **请求头要照抄小程序**：`Referer`（指向 `servicewechat.com/<appid>/494/page-frame.html`）、`xweb_xhr`、`User-Agent`、`X-Tingyun`，缺了容易吃 `9999`。
7. **字段名大小写有区别**：`getTicket` 用 `openId`（大写 I），`sspbigball` / `queryGoodsList` 用 `openid`；写错会得到 `9999 首页大球调用异常`。
8. **报错消息经常变成 `????`**：联通服务端把中文转丢了，只能靠 `code` 判断（`1001` 鉴权失败 / `1002` 未绑定 / `9999` 调用异常）。
9. **`mxx.client.10010.com` 的明细接口需要先建"微厅会话"**：直接拿小程序的 `ticket` 去调会得到 `999999` / `用户信息获取为空` —— 因为它要的是**微厅 Cookie**。正确姿势是先 `GET /servicebusiness/wx/serviceEntrance?ticket=..&servicecode=YH10005&ticketChannel=XCXYLCXYY`，**这个请求的 302 响应会 `Set-Cookie: microHallUser / microHallAccessToken`**（`Domain=10010.com`、`Secure; HttpOnly`），带上这两个 Cookie 再去调 `queryOcsPackageFlowLeftContentRevisedInJune`，流量/语音/短信的**分项余量**就都出来了（见 `docs/01` 阶段 6）。
10. **不用装 MITM 证书也能调试微信 H5/小程序接口**：用 Playwright 直接打开上面那个 `serviceEntrance` URL（带微信 UA 即可），Playwright 天生能看到请求/响应/Cookie；纯 urllib + `http.cookiejar` 也行（本集成就是这么拿微厅 Cookie 的，**无需浏览器**）。⚠️ 302 上的 Cookie 要自己跟随重定向逐跳收集。
11. **MITM 抓包的前提是"根证书被信任"**：如果证书没装/被试掉，微信所有 HTTPS 都会 `Client TLS handshake failed ... does not trust the proxy's certificate`，表现就是"**小程序里什么都打不开**"，而抓包文件是 **0 字节** —— 遇到这种情况先查证书，别怀疑小程序。
12. **`queryGoodsList` 返回的是"推荐商品"，不是你的套餐**：`res[0]` 里 `productName` 形如「单宽带40元/月300M」，`currentMonFee` / `monthFee` 都是**那条推荐**的价格。**不要拿它当"月租"** —— 本项目第一版就踩了这个坑（把 39.0 当成了月租），后来改从 `sspbalcbroadcast` 取真实账务字段。同一个接口里唯一可信的是 `mainNumber`（你本人的号码）。
13. **使用率字段是"分段比例条"不是数字**：微厅余量响应里的顶层 `usePercent` 是 `[{"Value":"0"},...]` 这样的列表，`float()` 会失败 → 自己用 `已用/总量` 算（本项目就是这么做的）。
14. **Gitee 上的同源镜像仓库无法匿名 `git clone`**（公开仓库也返回 401），如需引用请用 GitHub 地址。

---

## 四、安装与使用教程

### 第 1 步：拿到自己的 openid

openid 是微信给"你 + 这个小程序"的标识，**必须自己抓一次**（没有网页入口）。

推荐做法（Windows + 微信 PC）：

1. 装 [mitmproxy](https://mitmproxy.org/)：`pip install mitmproxy`
2. 启动：`mitmdump -p 8080 -w unicom.mitm`，并把 Windows 系统代理指到 `127.0.0.1:8080`，浏览器访问 `http://mitm.it` 安装并信任 mitmproxy 根证书（**装到"受信任的根证书颁发机构"**）
3. 微信 PC 打开「中国联通」小程序，**登录一次**并进入首页（能看到话费/流量/剩余量）
4. 停止抓包，在抓到的流量里找：

```
POST https://mina.10010.com/wxapplet/applet/findOpenid
响应: {"code":"0000","unionid":"oAxk...","openid":"oFroJ0ZkvVVZPkAIA0AV5wRU2eOY"}
                                                      ^^^^^^^^^^^^^^^^^^^^^^^^^^ 复制这个
```

> 注意：**其它接口里的 `openid` 是加密密文**（344 字符），不要复制那个。

### 第 2 步：安装集成

把仓库里的 `custom_components/unicom_mini/` 整个目录复制到 HA 的 `/config/custom_components/` 下，然后**重启 Home Assistant**：

```
/config/custom_components/unicom_mini/
├── __init__.py
├── api.py
├── config_flow.py
├── const.py           # 内置 RSA 公钥、接口与请求头
├── manifest.json
├── sensor.py
├── strings.json
└── translations/zh-Hans.json
```

> 重启方式：设置 → 系统 → 右上角电源图标 → 重启 Home Assistant（或 `ha core restart`）。

### 第 3 步：添加集成

设置 → 设备与服务 → **添加集成** → 搜「**联通小程序话费**」→ 填入上一步的 `openid`（如需可改刷新间隔，默认 30 分钟）。

添加时会**立刻实调一次接口做校验**：成功才建配置项，失败会在表单里显示具体错误（常见就是没在小程序登录过 → `获取用户绑定信息异常`）。

### 第 4 步：你会得到 14 个实体

话费/账务（来自小程序接口）：

| 实体 ID | 名称 | 说明 |
|---|---|---|
| `sensor.lian_tong_sheng_yu_hua_fei` | 剩余话费 | 首页"大球"的剩余话费，单位 CNY，属性含手机号/信用额度 |
| `sensor.lian_tong_ke_yong_yu_e` | 可用余额 | 账户可用话费（含结转），单位 CNY |
| `sensor.lian_tong_ben_yue_xiao_fei` | 本月消费 | 当月实时消费，单位 CNY |
| `sensor.lian_tong_qian_fei` | 欠费 | 单位 CNY（0 表示没欠费，适合做"欠费提醒"） |
| `sensor.lian_tong_jie_zhuan_hua_fei` | 结转话费 | 上月结转金额，单位 CNY |
| `sensor.lian_tong_sheng_yu_tong_yong_liu_liang` | 剩余通用流量 | 单位 GB |
| `sensor.lian_tong_sheng_yu_yu_yin` | 剩余语音 | 单位 分钟 |

余量分项（来自微厅接口，属性里有**逐资源包明细**）：

| 实体 ID | 名称 | 说明 |
|---|---|---|
| `sensor.lian_tong_tao_can_ming_cheng` | 套餐名称 | 如「流量王2.0-39（广西）」，属性含通用/定向分项 |
| `sensor.lian_tong_liu_liang_zong_liang` | 流量总量 | GB，属性含已用/剩余/使用率/每个资源包 |
| `sensor.lian_tong_liu_liang_yi_yong` | 流量已用 | GB，属性 `资源包明细` 逐包列出（如「套内国内流量(50.00G)：已用 43.22/共 50」） |
| `sensor.lian_tong_liu_liang_shi_yong_lu` | 流量使用率 | %（自己算：已用/总量） |
| `sensor.lian_tong_yu_yin_zong_liang` | 语音总量 | 分钟，属性含逐包明细 |
| `sensor.lian_tong_yu_yin_yi_yong` | 语音已用 | 分钟 |
| `sensor.lian_tong_duan_xin_sheng_yu` | 短信剩余 | 条 |

> 说明：**联通侧没有暴露"套餐月租"字段**（首页只有余量，套餐接口给的是营销推荐商品）。所以本集成不提供"月租"，改为提供真实的账务字段（可用余额/本月消费/欠费/结转）。如果你要的"月租"只是想看每月固定支出，用「本月消费」+「月平均」更准。

### 第 5 步：卡片示例

```yaml
type: custom:mushroom-template-card
entity: sensor.lian_tong_sheng_yu_hua_fei
primary: "{{ states('sensor.lian_tong_sheng_yu_hua_fei') }} 元"
secondary: >-
  剩余流量 {{ states('sensor.lian_tong_sheng_yu_tong_yong_liu_liang') }} GB
  · 剩余语音 {{ states('sensor.lian_tong_sheng_yu_yu_yin') }} 分钟
icon: mdi:sim
icon_color: red
multiline_secondary: true
```

### 第 6 步：预警自动化（可选）

```yaml
# 剩余话费低于 20 元提醒一次（跨过阈值才触发，不会反复推）
- id: unicom_balance_low
  alias: 联通·话费不足提醒
  triggers:
    - trigger: numeric_state
      entity_id: sensor.lian_tong_sheng_yu_hua_fei
      below: 20
  actions:
    - action: notify.persistent_notification      # 换成你的 notify.* / rest_command.* 即可
      data:
        title: 联通话费不足
        message: >-
          剩余话费 {{ states('sensor.lian_tong_sheng_yu_hua_fei') }} 元，
          剩余流量 {{ states('sensor.lian_tong_sheng_yu_tong_yong_liu_liang') }} GB。
  mode: single

- id: unicom_data_low
  alias: 联通·流量不足提醒
  triggers:
    - trigger: numeric_state
      entity_id: sensor.lian_tong_sheng_yu_tong_yong_liu_liang
      below: 10
  actions:
    - action: notify.persistent_notification
      data:
        title: 联通流量不足
        message: "剩余通用流量 {{ states('sensor.lian_tong_sheng_yu_tong_yong_liu_liang') }} GB"
  mode: single
```

---

## 五、常见问题

**Q：添加集成时报「连接或鉴权失败」？**
A：按顺序排查：
1. 有没有先在微信里**登录过**小程序（不然服务端没有绑定，必报 `1002`）；
2. openid 是不是 `findOpenid` **响应**里那个明文（不是别处的 344 字符密文）；
3. HA 主机能不能访问 `mina.10010.com`（`curl -s -o /dev/null -w '%{http_code}' https://mina.10010.com/` 应返回 200）。

**Q：为什么有时候返回 `9999`？**
A：`9999` 是兜底错误码，最常见是**请求头/参数不对**（Referer、`channel`、字段大小写）或服务端自身异常。联通的错误消息常被转成 `????`，只能靠 code 判断。

**Q：能拿到流量分项、账单、积分吗？**
A：暂时不行。那些走 `mxx.client.10010.com` 的接口，它不认小程序 `ticket`（`用户信息获取为空`/`999999`），需要另找来源。

**Q：多久刷新一次？**
A：默认 30 分钟，可在集成「配置」里改（5~1440 分钟）。每轮会重新 `getToken`，无需自己维护 token。

**Q：会消耗流量/被风控吗？**
A：每轮 2~3 个请求，频率很低；但仍建议不要低于 5 分钟，避免给对方服务造成压力。

---

## 六、参考与致谢

- 上游思路参考：[`Cyborg2017/ha_unicom_bill`](https://github.com/Cyborg2017/ha_unicom_bill)、[`hlhk2017/homeassistant-unicom_bill_info`](https://github.com/hlhk2017/homeassistant-unicom_bill_info)（它们对应"明文 openid"时代的协议，2026-09 起因加密升级不再可用）
- PC 微信小程序包解密算法参考：[`nieweiming/pc_wxapkg_decrypt_python`](https://github.com/nieweiming/pc_wxapkg_decrypt_python)
- 抓包工具：[mitmproxy](https://mitmproxy.org/)

---

## 七、目录结构

```
├── README.md
├── docs/
│   └── 01-逆向过程与踩坑.md      # 完整过程：怎么发现加密、怎么挖公钥、每个报错怎么定位
├── custom_components/
│   └── unicom_mini/             # 集成源码（直接复制到 HA）
└── tools/
    ├── wxapkg_decrypt.py        # PC 微信小程序包解密 + 解包 + 搜 RSA 公钥
    └── rsa_probe.py             # 复现 RSA 加密，验证 getToken/sspbigball 链路
```
