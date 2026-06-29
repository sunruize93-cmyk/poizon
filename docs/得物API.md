# 得物开放平台 API（选品相关）— 核实结论

登录 open.poizon.com 核实（已验签通过，code 200 Successful）。**选品所需数据官方 API 全部提供，无需屏幕控制。**

## 账号现状
控制台已有 4 个应用，选品用 **`compare_price`**（已含商品/比价权限）。AppKey/AppSecret 存本地
`.env`（gitignored）。网关基址 `https://open.poizon.com`，接口路径即下表 `apiUrl`。

## 选品三条核心接口

### 1. 货号 → SKU 信息（关联键）
- `id=140` `POST /dop/api/v1/pop/api/v1/intl-commodity/intl/sku/sku-basic-info/by-article-number`
- 入：`articleNumber`(LV官方货号) `region`(KR) `language` `sellerStatusEnable` `buyStatusEnable`
- 出：`data.spuInfo`{spuId, articleNumber, title, brandName, category…, status(上架), buyStatus(可买)}；
  `data.skuInfoList[]`{skuId, globalSkuId, dwSkuId, barCode, status, buyStatus, 尺码}
- 批量版同类目下亦有（by Brand Official Item Number - Batch）。

### 2. SKU → 市场行情（30天成交价）
- `id=93` `POST /dop/api/v1/pop/api/v1/recommend-bid/price`（批量 `id=141` `/recommend-bid/batchPrice`，≤20）
- 入：`skuId`(或 globalSkuId) `region`(KR) `currency`(CNY/KRW) `biddingType`(20自发货直邮/25寄售) `saleType`(0现货/7预售)
- 出：`data`{**minPrice/maxPrice/averagePrice**(近30天最低/最高/平均成交价), globalMinPrice,
  **otherPlatformMinPrice**(其他平台最低价), highDemandPrice, localMinPrice, usMinPrice, priceRangeItems[]}
- 价格单位为「货币最小单位」（如分），换算时注意。

### 3. barCode → 销量
- `id=181` `POST /dop/api/v1/pop/api/v1/intl-commodity/intl/sku/sku-basic-info/by-barcodes`（≤100）
- 出：`...commoditySales`(商品销量) `localSoldNum30`(近30天本地销量) 等
- 另：`id=86 Get New Product List` 提供 `globalReference30DaySales`(POIZON30天销量参考)、`globalSales`、`localSales` 及趋势。

## 选品数据链路
```
LV货号 ─140(region=KR)→ skuId + barCode + 上架/可买状态
   skuId  ─93(KR,CNY,20)→ 30天成交 min/max/avg、其他平台最低价
   barCode ─181→ 近30天销量
```

## 签名算法（已验证可用）
1. 全部业务参数 + `app_key` + `timestamp`(ms) 放入一个对象。
2. 去掉空值，按 key 升序（ASCII）。
3. 每个键值用 Java URLEncoder 编码（空格→`+`，保留 `-_.*`），拼成 `k=v&k=v`（末尾无 `&`）。
4. 数组值：把数组内 JSON 对象用逗号拼接后再整体编码。
5. 末尾直接接 `app_secret`，对整串做 MD5(32位)，转大写 = `sign`。
- 实现见 `src/dewu_source/official_api.py:make_sign`。POST application/json，body 含 app_key/timestamp/sign + 业务参数。

## 官方 API 未直接提供、需注意
- **想要人数 / 在售卖家数（竞争度）**：核实的接口里未见明确字段；评分中 `wish_count`/`seller_count`
  暂留空或后续用屏幕控制(`screen_control.py`)补，不影响主链路。
- 价格是「成交价」维度（min/max/avg + 其他平台最低价），已足够做差价与波动判断。

## 全量目录
116 个接口的完整抓取见 `data/poizon_docs/catalog.json`（gitignored，可用 tools/poizon_catalog.mjs 重抓）。
10 个大类：Item / Listing & Inventory / Consignment / Order / Fulfillment / Bill / Return / Merchant / Smart Listing / Bonded。
