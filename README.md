# poizon选品 (poizon-xuanpin)

LV 韩国直邮 → 得物（POIZON）跨境套利**选品系统**。

抓取 LV 韩国官网的价格与是否可售，对比得物（POIZON）上的市场卖价与销量，按"差价 / 利润率 / 销量 / 库存稳定性 / 资金占用"等维度综合打分，自动选出**最值得倒卖的品**。

---

## 它解决什么

你是韩国的得物商家，做 LV 小皮具（钱包 / 皮带 / 鞋）的韩国直邮倒卖。物流、清关、退税、店铺都已打通，**唯一缺的是"选哪些品能赚钱"**。本项目把这件事自动化：

```
LV韩国官网价格(KRW) + 是否可售  ──┐
                                  ├──► 货号关联 ──► 利润&综合评分 ──► 选品榜单
得物市场卖价(CNY) + 销量/想要    ──┘
```

关联键是 **LV 官方货号**（如 `M81234`），两边都带这个字段。

## 数据来源（两条链路）

| 链路 | 取数方式 | 模块 |
|---|---|---|
| **LV 韩国** 价格 + 是否可售 | LV 移动 App 内部接口 `pass-api.louisvuitton.com`，按货号轮询（住宅代理 + curl_cffi 伪装 TLS 指纹） | `src/lv_scraper` |
| **得物** 市场价 + 销量 | 首选官方开放平台 API（`open.poizon.com`）；若官方不开放行情，则用屏幕控制得物电脑版补 | `src/dewu_source` |

> ⚠️ 得物官方 API 是否开放"任意商品行情（最低价/销量）"尚待用商家账号登录核实。见 `docs/方案.md` 阶段 1。

## 目录结构

```
config/         成本参数、评分权重、货号清单（*.example 是模板，复制去掉 .example 填真值）
src/
  lv_scraper/   LV pass-api 客户端
  dewu_source/  得物官方API + 屏幕控制
  matcher/      LV ↔ 得物 货号关联
  scorer/       选品评分算法（核心）
  pipeline/     编排 + 定时快照
  report/       Excel / HTML 榜单导出
data/           抓取快照（不入库，见 .gitignore）
docs/           方案 & 选品逻辑沉淀
```

## 快速开始

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env                      # 填代理、得物 AppKey/Secret
cp config/settings.example.yaml config/settings.yaml   # 填成本参数和权重
cp config/skus.example.csv config/skus.csv             # 填你主营的货号清单

python -m src.pipeline.run                # 跑全流程，结果出在 data/ 和 report/
```

## 现状

骨架已就绪：选品算法、LV 客户端、报表、编排可用。待接通：
- [ ] 阶段 1 — 登录 open.poizon 核实官方 API 字段，定稿 `src/dewu_source/official_api.py`
- [ ] 阶段 2 — 配韩国住宅代理，调通 LV `pass-api` 韩国区域参数
- [ ] 阶段 3 — 填真实货号清单 + 成本参数，跑通验证差价

详见 `docs/方案.md`。
