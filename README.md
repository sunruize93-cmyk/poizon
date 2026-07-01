# poizon 选品引擎

> **一句话**：自主从品牌官网(现 LV)发现商品 → 判断哪些有潜力 → 只对高潜力的抓价、和得物(POIZON)对比销量利润 → 排出**最值得倒卖的品**。一套**可迁移**引擎(换品牌/平台只写适配器)。

面向使用者：韩国得物商家，做 LV 小皮具(钱包/皮带/鞋)韩国直邮倒卖。物流/清关/退税已通，**痛点是选品**。

---

## 🤖 给 Agent 的操作手册（照此即可自主选品）

> 你(Agent)拿到这个仓库后，按下面的漏斗逐层跑。**核心原则：便宜信号在前、昂贵操作在后，每层大幅减量**，不要全量爬对比。

### 0. 一次性准备
```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
npm install                                    # patchright(LV 抓取用)
cp .env.example .env                           # 填得物 AppKey/Secret、LV_PROXY(可选)
cp config/settings.example.yaml config/settings.yaml   # 成本参数+评分权重
cp config/skus.example.csv config/skus.csv     # 可空;引擎会自动发现货号
```

### 漏斗 5 层（附每层命令 + 该用的模型）

| 层 | 做什么 | 命令 | 成本/模型 |
|---|---|---|---|
| **L0 发现** | 拉 LV sitemap 全量商品(货号+品类) | `python tools/lv_catalog.py` | 免费·无需模型 |
| **L1 潜力初判** | 规则砍到目标品类 → **LLM 给商品名打潜力分** | `python tools/run_engine.py --top 200` 导出待打分 → 打分 → `--apply` | **Sonnet 子代理**打分 |
| **L2 LV 报价** | 只给高潜力 shortlist 批量抓 LV 现价+可售 | `node tools/lv_prices.mjs <货号...>` | **Sonnet 子代理**跑 |
| **L3 得物廉价信号** | 官方 API 查在售/想要人数 | (引擎内 DewuMarket 自动) | 便宜·无需模型 |
| **L4 得物成交核验** | 只对入围品屏幕 OCR 抓「最近购买」真实成交 | `.venv/bin/python tools/uia.py do "act;ocr"` | **Sonnet 子代理**抓+读 |
| **出榜** | 算净利/利润率+热度综合分排序 | `python tools/run_engine.py --full` | Opus 定最终判断 |

**L1 的 LLM 打分怎么做**：读 `data/lv_judge_batch.json`(规则存活的 Top-N)，按「韩中价差潜力 × 系列热度 × 经典 vs 冷门」给每个 0~1 分，写 `data/lv_llm_scores_full.json`（格式 `{"scores":{"<货号>":{"score":..,"reason":..}}}`），再 `python tools/run_engine.py --apply data/lv_llm_scores_full.json` 回填出 `data/lv_shortlist.json`。**这步派 Sonnet 子代理做**。

### ⚠️ 关键操作纪律（Agent 必须遵守）
- **模型路由**：机械活(LV 抓价 / 得物屏幕 OCR / 商品名批量打分)一律派 **Sonnet 子代理**；Opus 只留最终选品判断、算利润口径、写代码。省 token。
- **LV 抓取绕 Akamai**：每次抓价用**全新 profile 名**(`LV_PROFILE=tools/.lv_profile_<随机>`)。封禁是 profile 级，换名即恢复；别傻等 IP。搜索/分类接口(search-merch)对自动化 403 不可用——**发现只走 sitemap**，报价走 `prodct-dtl`。
- **得物只采近 7 天成交**(周销量信号)，别全爬；读数据用 `uia.py ocr` 出文本，**别整屏截图喂模型**。
- **绝不点得物「立即购买」**(详情页右下绿色按钮)，防误购。
- **凭证/业务数据永不入库**：`.env`/`config/skus.csv`/`config/settings.yaml`/`data/` 均已 gitignore。

---

## 算法（两步，选品的核心）

### ① 算净利（每个「码数×包装」单独算）
```
采购成本(CNY) = LV含税价(KRW) × (10/11 − 券率3% + 出口申报1%) ÷ 汇率  + 物流(中程×重量+顺丰+包装)
得物到手(CNY) = 成交价 × (1 − 技术费 − 转账费1%) − 操作费¥38 − 邮补¥8.72
净利 = 到手 − 总成本      利润率 = 净利 / 总成本      （普通挂单 / 立即变现 两场景取高）
```
口径：得物成交价=买家付含税价；结算价=含税÷(1+跨境税)，税档 `<5000→9.1%`、`≥5000→20%`。参数在 `config/settings.yaml`。

### ② 综合分（先硬过滤，再加权）
硬过滤：`净利<¥100` 或 `利润率<6%` 或 `90天0成交(滞销)` → 淘汰。
幸存者 8 指标 min-max 归一化后加权：
```
综合分 = 0.45×流动性(月化速度/最近成交/想要/买家) + 0.40×盈利(净利/利润率) − 0.15×风险(竞争/价格波动)
```
代码 `src/scorer/heat.py`。跨境资金有限、压货即亏，故「卖得快」与「赚得多」并重。

---

## 可迁移架构（换品牌/平台只写适配器）

```
src/engine/     引擎核心(品牌无关)
  base.py         数据契约 RawItem→Priced→Signaled→Opportunity + 接口 SourceAdapter/MarketAdapter/PotentialJudge + BrandProfile
  judge.py        HybridJudge：规则(品类/价带/热门冷门系列) + LLM(Claude)精排，可插拔
  funnel.py       漏斗编排，每层 cap 控成本
  profiles.py     各品牌域知识(LV：主营品类/价带/热门系列/冷门信号)
src/sources/    供给侧适配器：lv.py(sitemap 发现 + prodct-dtl 报价)   ← 换品牌加 gucci.py 等
src/markets/    需求侧适配器：dewu.py(官方API信号 + 屏幕OCR核验)      ← 换平台加新的
src/scorer/     利润模型 + 评分(品牌无关)   src/fx.py 实时汇率
tools/          lv_catalog.py(发现) lv_prices.mjs(报价) uia.py(屏幕控制+OCR) run_engine.py(跑漏斗) run_sales.py(逐码数榜单)
data/  config/  docs/    产出/配置/文档(gitignore)
```

**接新品牌**：写一个 `SourceAdapter`(discover+price) + 一个 `BrandProfile`(域知识/成本参数)，其余(判官/漏斗/评分/得物侧)复用。

---

## 现状
- ✅ 引擎闭环跑通：LV sitemap 发现 6450 品 → 规则+Claude 精排 → 得物成交核验出机会榜(实测 1AK8BN 综合分0.86)
- ✅ LV 抓价打通(prodct-dtl，货号即可)；得物屏幕 OCR 抓价打通(近7天，本地 OCR 省 token)
- ✅ 成本模型按实拍成本校验、实时汇率、双变现场景
- 🔜 待完善：全量候选 LLM 打分常态化；L2 报价接入 funnel 自动跑；接第二个品牌验证可迁移性

详见 `docs/方案.md`。
