"""
网球比赛提醒 - 每日推送脚本 v2.1
- 精美 HTML 邮件（体育媒体风格，球员照片）
- 昨日赛果 + 今日赛程
- 关注球员：莱巴金娜、德约科维奇、王欣瑜
"""

import json
import os
import smtplib
import time
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ── 配置（直接改这里）──
EMAIL_ADDRESS = "sjj20060424@qq.com"
EMAIL_PASSWORD = "gjqnuyrnieareiib"   # QQ邮箱SMTP授权码
SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 587

# 关注球员
FAVORITE_PLAYERS = {
    "莱巴金娜": {
        "keywords": ["Rybakina", "Elena Rybakina"],
        "color": "#FF6B9D",
        "emoji": "🌸",
        "flag": "🇰🇿",
    },
    "德约科维奇": {
        "keywords": ["Djokovic", "Novak Djokovic"],
        "color": "#1E3A5F",
        "emoji": "👑",
        "flag": "🇷🇸",
    },
    "王欣瑜": {
        "keywords": ["Xinyu Wang", "Wang Xinyu"],
        "color": "#E63946",
        "emoji": "⭐",
        "flag": "🇨🇳",
    },
}

# ── 数据获取 ──

def fetch_events(date_str):
    """从 SofaScore 获取指定日期的赛事"""
    if not HAS_REQUESTS:
        print("requests 未安装，跳过数据获取")
        return []
    
    url = f"https://www.sofascore.com/api/v1/sport/tennis/scheduled-events/{date_str}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://www.sofascore.com/",
        "Origin": "https://www.sofascore.com",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        events = data.get("events", [])
        print(f"  {date_str}: 获取到 {len(events)} 条赛事")
        return events
    except Exception as e:
        print(f"  获取 {date_str} 赛程失败: {e}")
        return []


def parse_event(ev):
    """解析单条赛事数据"""
    home_team = ev.get("homeTeam", {})
    away_team = ev.get("awayTeam", {})
    tournament = ev.get("tournament", {})
    round_info = ev.get("roundInfo", {})
    status = ev.get("status", {})

    # 比分
    hs = ev.get("homeScore", {})
    aws = ev.get("awayScore", {})
    period_scores = []
    for p in hs.get("periods", []):
        h = p.get("home", 0) or 0
        a = p.get("away", 0) or 0
        period_scores.append(f"{h}-{a}")
    score_str = " / ".join(period_scores) if period_scores else ""

    # 时间
    start_ts = ev.get("startTimestamp", 0)
    if start_ts:
        if start_ts > 1e12:
            start_ts = start_ts / 1000
        dt = datetime.fromtimestamp(start_ts, tz=timezone(timedelta(hours=8)))
        time_str = dt.strftime("%H:%M")
        date_display = dt.strftime("%m/%d")
    else:
        time_str = "TBD"
        date_display = ""

    # 胜者
    winner = None
    if status.get("type") == "finished":
        try:
            if int(hs.get("display", 0)) > int(aws.get("display", 0)):
                winner = "home"
            else:
                winner = "away"
        except (ValueError, TypeError):
            pass

    return {
        "home": home_team.get("name", ""),
        "away": away_team.get("name", ""),
        "home_id": home_team.get("id", ""),
        "away_id": away_team.get("id", ""),
        "home_img": f"https://api.sofascore.com/api/v1/team/{home_team.get('id', '')}/image" if home_team.get("id") else "",
        "away_img": f"https://api.sofascore.com/api/v1/team/{away_team.get('id', '')}/image" if away_team.get("id") else "",
        "tournament": tournament.get("name", ""),
        "round": round_info.get("round", ""),
        "time": time_str,
        "date": date_display,
        "status": status.get("type", "notstarted"),
        "score": score_str,
        "winner": winner,
    }


def is_favorite_match(m):
    """检查是否有关注球员"""
    text = f"{m['home']} {m['away']}"
    matched = []
    for player_name, info in FAVORITE_PLAYERS.items():
        for kw in info["keywords"]:
            if kw.lower() in text.lower():
                matched.append(player_name)
                break
    return matched


# ── HTML 生成 ──

def generate_html(today_matches, yesterday_matches, today_str, yesterday_str):
    PLAYER_STYLES = {
        "莱巴金娜": {"color": "#FF6B9D", "emoji": "🌸", "flag": "🇰🇿"},
        "德约科维奇": {"color": "#1E3A5F", "emoji": "👑", "flag": "🇷🇸"},
        "王欣瑜": {"color": "#E63946", "emoji": "⭐", "flag": "🇨🇳"},
    }

    def player_badges(players):
        html = ""
        for p in players:
            s = PLAYER_STYLES.get(p, {"color": "#333", "emoji": "🎾", "flag": ""})
            html += f'<span style="background:{s["color"]};color:#fff;padding:3px 10px;border-radius:12px;font-size:12px;margin-right:6px;">{s["flag"]} {s["emoji"]} {p}</span>'
        return html

    def status_badge(status):
        mapping = {
            "notstarted": ("未开始", "#4CAF50"),
            "inprogress": ("🔴 进行中", "#FF5722"),
            "finished": ("已结束", "#9E9E9E"),
        }
        text, color = mapping.get(status, ("未知", "#9E9E9E"))
        return f'<span style="background:{color};color:#fff;padding:3px 10px;border-radius:10px;font-size:11px;">{text}</span>'

    def match_card(m, is_result=False):
        players = m.get("players", [])
        border_color = PLAYER_STYLES.get(players[0], {}).get("color", "#333") if players else "#333"
        home_img = m.get("home_img", "")
        away_img = m.get("away_img", "")
        home_winner = m.get("winner") == "home"
        away_winner = m.get("winner") == "away"
        img_size = 56

        return f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:14px;margin-bottom:12px;box-shadow:0 2px 10px rgba(0,0,0,0.07);border-left:4px solid {border_color};">
            <tr><td style="padding:12px 16px 6px;">
                <table width="100%"><tr>
                    <td style="font-size:12px;color:#888;">🎾 {m.get('tournament','')} · {m.get('round','')}</td>
                    <td style="text-align:right;">{status_badge(m.get('status','notstarted'))}</td>
                </tr></table>
            </td></tr>
            <tr><td style="padding:0 16px 8px;">
                <table width="100%" cellpadding="0" cellspacing="0" style="text-align:center;">
                <tr>
                    <td width="33%" style="text-align:center;">
                        <div style="width:{img_size}px;height:{img_size}px;border-radius:50%;overflow:hidden;border:3px solid {'#4CAF50' if home_winner else '#ddd'};margin:0 auto;">
                            <img src="{home_img}" width="{img_size}" height="{img_size}" style="object-fit:cover;" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 56 56%22><rect fill=%22%23eee%22 width=%2256%22 height=%2256%22/><text x=%2228%22 y=%2232%22 text-anchor=%22middle%22 font-size=%2224%22>🎾</text></svg>'">
                        </div>
                        <div style="font-size:11px;font-weight:{'700' if home_winner else '400'};margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100px;margin-left:auto;margin-right:auto;">{m['home'][:14]}</div>
                    </td>
                    <td width="34%" style="text-align:center;vertical-align:middle;">
                        <div style="font-size:18px;color:#999;font-weight:bold;">VS</div>
                        {'<div style="font-size:12px;color:#E63946;font-weight:700;margin-top:2px;">' + (m.get('score','') or '').replace(' / ','<br>') + '</div>' if is_result and m.get('score') else ''}
                    </td>
                    <td width="33%" style="text-align:center;">
                        <div style="width:{img_size}px;height:{img_size}px;border-radius:50%;overflow:hidden;border:3px solid {'#4CAF50' if away_winner else '#ddd'};margin:0 auto;">
                            <img src="{away_img}" width="{img_size}" height="{img_size}" style="object-fit:cover;" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 56 56%22><rect fill=%22%23eee%22 width=%2256%22 height=%2256%22/><text x=%2228%22 y=%2232%22 text-anchor=%22middle%22 font-size=%2224%22>🎾</text></svg>'">
                        </div>
                        <div style="font-size:11px;font-weight:{'700' if away_winner else '400'};margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100px;margin-left:auto;margin-right:auto;">{m['away'][:14]}</div>
                    </td>
                </tr>
                </table>
            </td></tr>
            <tr><td style="padding:4px 16px 12px;text-align:center;">
                {player_badges(players)}
                <div style="margin-top:6px;font-size:13px;color:#666;">
                    {'⏰ ' + m.get('time','TBD') if not is_result else '📅 ' + m.get('date','')}
                </div>
            </td></tr>
        </table>"""

    today_cards = ""
    if today_matches:
        for m in today_matches:
            today_cards += match_card(m, is_result=False)
    else:
        today_cards = '<div style="background:#f8f9fa;border-radius:14px;padding:30px;text-align:center;color:#999;margin-bottom:16px;"><div style="font-size:40px;margin-bottom:8px;">🎾</div><div style="font-size:15px;">今天没有关注的球员比赛</div></div>'

    yesterday_cards = ""
    if yesterday_matches:
        for m in yesterday_matches:
            yesterday_cards += match_card(m, is_result=True)
    else:
        yesterday_cards = '<div style="background:#f8f9fa;border-radius:14px;padding:20px;text-align:center;color:#999;"><div style="font-size:13px;">昨日无关注球员比赛</div></div>'

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;margin:0 auto;">
<tr><td style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 50%,#0f3460 100%);padding:28px 24px;text-align:center;border-radius:0 0 24px 24px;">
    <div style="font-size:36px;margin-bottom:6px;">🎾</div>
    <div style="color:#fff;font-size:22px;font-weight:700;">网球每日赛程</div>
    <div style="color:rgba(255,255,255,0.6);font-size:13px;margin-top:4px;">{today_str}</div>
    <div style="margin-top:14px;">
        <span style="background:#FF6B9D;color:#fff;padding:4px 14px;border-radius:14px;font-size:12px;margin:0 3px;">🌸 莱巴金娜</span>
        <span style="background:#1E3A5F;color:#fff;padding:4px 14px;border-radius:14px;font-size:12px;margin:0 3px;">👑 德约科维奇</span>
        <span style="background:#E63946;color:#fff;padding:4px 14px;border-radius:14px;font-size:12px;margin:0 3px;">⭐ 王欣瑜</span>
    </div>
</td></tr>
<tr><td style="padding:20px 16px 8px;"><div style="font-size:16px;font-weight:700;color:#1a1a1a;margin-bottom:12px;">📅 今日赛程</div>{today_cards}</td></tr>
<tr><td style="padding:8px 16px 20px;"><div style="font-size:16px;font-weight:700;color:#1a1a1a;margin-bottom:12px;">🏆 昨日赛果 · {yesterday_str}</div>{yesterday_cards}</td></tr>
<tr><td style="padding:16px;text-align:center;color:#bbb;font-size:11px;line-height:1.6;">
    <div>数据来源: SofaScore API · ATP/WTA Official</div>
    <div>由 Hermes Agent 自动推送 · 每天 08:00</div>
</td></tr>
</table></body></html>"""


# ── 邮件发送 ──

def send_email(html_content, subject):
    msg = MIMEMultipart("alternative")
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = EMAIL_ADDRESS
    msg["Subject"] = subject
    msg.attach(MIMEText("请查看HTML版本邮件", "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    for attempt in range(3):
        try:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
            server.quit()
            print(f"邮件发送成功: {subject}")
            return True
        except smtplib.SMTPServerDisconnected:
            print(f"SMTP断开，重试({attempt+1}/3)...")
            time.sleep(3)
        except Exception as e:
            print(f"发送失败: {e}")
            time.sleep(2)
    return False


# ── 主流程 ──

def main():
    tz = timezone(timedelta(hours=8))
    today = datetime.now(tz)
    yesterday = today - timedelta(days=1)

    today_str = today.strftime("%Y年%m月%d日 %A")
    yesterday_str = yesterday.strftime("%m月%d日")
    today_date = today.strftime("%Y-%m-%d")
    yesterday_date = yesterday.strftime("%Y-%m-%d")

    print(f"获取今日赛程: {today_date}")
    today_events = fetch_events(today_date)
    print(f"获取昨日赛果: {yesterday_date}")
    yesterday_events = fetch_events(yesterday_date)

    # 筛选今日赛程
    today_matches, seen = [], set()
    for ev in today_events:
        m = parse_event(ev)
        players = is_favorite_match(m)
        if players:
            key = (m["home"], m["away"], m["tournament"])
            if key not in seen:
                seen.add(key)
                m["players"] = players
                today_matches.append(m)

    # 筛选昨日赛果
    yesterday_matches, seen2 = [], set()
    for ev in yesterday_events:
        if ev.get("status", {}).get("type") != "finished":
            continue
        m = parse_event(ev)
        players = is_favorite_match(m)
        if players:
            key = (m["home"], m["away"], m["tournament"])
            if key not in seen2:
                seen2.add(key)
                m["players"] = players
                yesterday_matches.append(m)

    print(f"今日关注: {len(today_matches)} 场, 昨日关注: {len(yesterday_matches)} 场")
    for m in today_matches:
        print(f"  今日: {m['home']} vs {m['away']} ({m['time']}) - {','.join(m['players'])}")
    for m in yesterday_matches:
        print(f"  昨日: {m['home']} {m['score']} {m['away']} - {','.join(m['players'])}")

    html = generate_html(today_matches, yesterday_matches, today_str, yesterday_str)
    send_email(html, f"🎾 网球赛程 · {today_str}")


if __name__ == "__main__":
    main()
