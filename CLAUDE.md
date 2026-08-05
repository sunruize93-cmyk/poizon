# poizon 选品引擎 — 项目说明（给 AI）

LV→得物套利选品系统。完整流程/成本口径/工具见 `README.md`，机器上的持久记忆在 `~/.claude/.../memory`（优先看）。

## 逆向任务（得物API签名 / LV Akamai / 抓包 / JS加密）
先读集成的逆向技能路由包，按它的方法论走，别裸猜工具：
- 入口：`skills/reverse-skill/README_AI.md`（AI 引导）+ `skills/reverse-skill/RULES.md`（全局规则/作用域门）
- 路由：`skills/reverse-skill/skills/MASTER-ROUTING.md`
- 本机 tool-index 刷新：`bash skills/reverse-skill/skills/scripts/refresh-tool-index.sh`
- 当前项目实际用到的逆向点：得物 seller 后台签名锁翻页、open.poizon 签名算法、LV prodct-dtl 接口 client_id/secret 鉴权、Akamai 行为检测（详见 `docs/方案.md`、`docs/得物API.md`）

## 选品决策框架（2026-08 起：单一直发模块）
**现货与直发已合并，只做韩国 POIZON 直发**（bt=27）。看不了国内得物立即变现 → 砍掉立即变现分支。
- 排序 = 直发月利润潜力 = 直发净利(₩→¥) × 中国30天销量
- 销量分层只作优先级：好(≥10)→优先 / 适中(3-9)→备选 / 不好(≤2)→仅毛利极高才做
- 主命令：`python tools/direct_select.py`（单模块综合榜）；直发价 `direct_board.py` 抓(缓存+--refresh-top)
- 注意销量 `<5` 屏蔽估算带 `*`；LV 库存 storeSell 不代表实货，官网为准

## 常用命令
- 直发选品：`python tools/direct_board.py 60 --refresh-top 15` → `python tools/direct_select.py`
- 备查：`top5_select.py`(现货旧版) / `sku_comprehensive.py`(现货综合) / `hot_items.py`(热门) / `predict_hits.py`(爆款)
- 导出 Excel：`python tools/export_excel.py`（存 `~/Desktop/poizon选品/`）
