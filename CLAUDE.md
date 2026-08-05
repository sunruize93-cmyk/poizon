# poizon 选品引擎 — 项目说明（给 AI）

LV→得物套利选品系统。完整流程/成本口径/工具见 `README.md`，机器上的持久记忆在 `~/.claude/.../memory`（优先看）。

## 逆向任务（得物API签名 / LV Akamai / 抓包 / JS加密）
先读集成的逆向技能路由包，按它的方法论走，别裸猜工具：
- 入口：`skills/reverse-skill/README_AI.md`（AI 引导）+ `skills/reverse-skill/RULES.md`（全局规则/作用域门）
- 路由：`skills/reverse-skill/skills/MASTER-ROUTING.md`
- 本机 tool-index 刷新：`bash skills/reverse-skill/skills/scripts/refresh-tool-index.sh`
- 当前项目实际用到的逆向点：得物 seller 后台签名锁翻页、open.poizon 签名算法、LV prodct-dtl 接口 client_id/secret 鉴权、Akamai 行为检测（详见 `docs/方案.md`、`docs/得物API.md`）

## 选品决策框架（2026-08 起）
按「过去30天销量」分三档定变现策略（阈值在 `tools/top5_select.py` 顶部可调）：
- 销量好(≥10) → 挂普通单，不考虑立即变现
- 销量不好(≤2) → 立即变现 + 考虑取消风险；但立即变现价与72小时销量要进软件看 → 先预判值不值得进软件
- 销量适中(3-9) → 备选
输出清单只保留 **Top 5**：`python tools/top5_select.py`（自动带出「精确到尺码」明细，见 tools/top5_skus.py——同一货号不同 版本×尺码 净利差可达¥5000+，进货务必看 SKU 级）。

## 常用命令
- 选品出榜：`python tools/run_select.py --brand LV`
- Top5 清单：`python tools/top5_select.py`
- 导出 Excel：`python tools/export_excel.py`（存 `~/Desktop/poizon选品/`）
