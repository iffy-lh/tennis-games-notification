# 🎾 网球比赛提醒

每日自动抓取网球比赛数据，推送关注球员赛程到 QQ 邮箱。

## 关注球员

- 莱巴金娜 (Elena Rybakina)
- 德约科维奇 (Novak Djokovic)
- 王欣瑜 (Wang Xinyu)

## 功能

- 昨日赛果（含比分、胜负标记）
- 今日赛程（含北京时间开赛时间、球员国旗头像）
- HTML 精美邮件
- 支持单打/双打

## 数据源

ESPN API（免费，无需 key）

## 使用方法

```bash
pip install requests
python tennis_reminder.py
```

## 定时运行

**Linux/WSL (cron):**
```bash
0 8 * * * cd /path/to/tennis-reminder && python3 scripts/tennis_reminder.py
```

**Windows (任务计划程序):**
```
程序: pythonw.exe
参数: scripts\tennis_reminder.py
触发器: 每天 08:00
```
