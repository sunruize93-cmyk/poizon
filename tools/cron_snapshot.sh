#!/bin/bash
# 每日自动快照 LV 目录(纯 curl+python,无需 AI/浏览器/登录),累积"上新窗口"差分基础。
# 由 crontab 调用。得物侧需登录态,选品时再刷;此处只保证 LV 供给侧新品能被 diff 出来。
cd /Users/sunruize/poizon-xuanpin || exit 1
PY=.venv/bin/python
DATE=$(date +%Y%m%d)
LOG=data/snapshots/cron.log
mkdir -p data/snapshots

echo "=== $(date '+%Y-%m-%d %H:%M:%S') 开始快照 ===" >> "$LOG"
# 1) 拉最新 LV 目录(sitemap)
$PY tools/lv_catalog.py >> "$LOG" 2>&1
# 2) 存当日快照(含 LV 目录 + 现有得物市场数据)
$PY tools/lv_new_arrivals.py snapshot "$DATE" >> "$LOG" 2>&1

# 3) 若存在前一天/更早的快照,自动 diff 出新出现的货号,写到 data/snapshots/new_YYYYMMDD.txt
PREV=$(ls -1 data/snapshots/*.json 2>/dev/null | grep -vE "cron" | sort | grep -B1 "${DATE}.json" | head -1)
if [ -n "$PREV" ] && [ "$(basename "$PREV" .json)" != "$DATE" ]; then
  echo "--- diff $PREV → $DATE ---" >> "$LOG"
  $PY tools/lv_new_arrivals.py diff "$PREV" "data/snapshots/${DATE}.json" > "data/snapshots/new_${DATE}.txt" 2>> "$LOG"
  echo "新品差分已存 data/snapshots/new_${DATE}.txt" >> "$LOG"
fi
echo "=== 完成 ===" >> "$LOG"
