"""
网球比赛提醒 - ESPN API 版 v2
从 ESPN API 抓取比赛数据，自动推送关注球员赛程到邮箱

功能：
- 今日赛程（含开赛时间、球员国旗头像）
- 昨日赛果（含比分、胜负标记）
- 精美 HTML 邮件

关注球员：莱巴金娜、德约科维奇、王欣瑜
数据源：ESPN API (免费，无需 key)
"""

import json
import os
import re
import smtplib
import sys
import time
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("请安装 requests: pip install requests")
    exit(1)


# ═══════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════

EMAIL_ADDRESS = "sjj20060424@qq.com"
EMAIL_PASSWORD = "hwuumsvzhhrjbgie"
SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 587

FAVORITE_PLAYERS = {
    "莱巴金娜": {
        "keywords": ["Elena Rybakina", "Rybakina"],
        "emoji": "\U0001F338", "flag_emoji": "\U0001F1F0\U0001F1FF",
    },
    "德约科维奇": {
        "keywords": ["Novak Djokovic", "Djokovic"],
        "emoji": "\U0001F451", "flag_emoji": "\U0001F1F7\U0001F1F8",
    },
    "王欣瑜": {
        "keywords": ["Xinyu Wang", "Wang Xinyu", "Wang Xin"],
        "emoji": "\U00002B50", "flag_emoji": "\U0001F1E8\U0001F1F3",
    },
}

ESPN_ATP_URL = "https://site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard"
ESPN_WTA_URL = "https://site.api.espn.com/apis/site/v2/sports/tennis/wta/scoreboard"
ESPN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0",
}

TZ = timezone(timedelta(hours=8))


# ═══════════════════════════════════════════════
# 数据获取
# ═══════════════════════════════════════════════

def _extract_espn_id(links):
    """从 ESPN links 中提取球员 ID"""
    for link in links:
        href = link.get("href", "")
        m = re.search(r"/id/(\d+)/", href)
        if m:
            return m.group(1)
    return None


def _build_headshot_url(espn_id):
    """构建 ESPN 球员头像 URL"""
    if not espn_id:
        return None
    return f"https://a.espncdn.com/combiner/i?img=/i/headshots/tennis/players/full/{espn_id}.png&w=160&h=160"


def _parse_beijing_time(date_str):
    """将 UTC 时间转为北京时间显示"""
    if not date_str:
        return ""
    try:
        # 格式: "2026-05-27T09:00Z"
        dt_utc = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        dt_bj = dt_utc.astimezone(TZ)
        return dt_bj.strftime("%H:%M")
    except Exception:
        return ""


def fetch_espn_matches():
    """从 ESPN API 获取所有当前比赛的场次"""
    all_matches = []

    for url, tour in [(ESPN_ATP_URL, "ATP"), (ESPN_WTA_URL, "WTA")]:
        try:
            resp = requests.get(url, headers=ESPN_HEADERS, timeout=20)
            resp.raise_for_status()
            data = resp.json()

            for event in data.get("events", []):
                tournament_name = event.get("name", "Unknown")
                is_major = event.get("major", False)

                for group in event.get("groupings", []):
                    round_name = group.get("grouping", {}).get("displayName", "")

                    for comp in group.get("competitions", []):
                        match = _parse_competition(comp, tournament_name, round_name, is_major)
                        if match:
                            all_matches.append(match)

        except Exception as e:
            print(f"  [{tour}] API 错误: {e}")

    return all_matches


def _parse_competition(comp, tournament_name, round_name, is_major):
    """解析单场比赛"""
    competitors = comp.get("competitors", [])
    if len(competitors) < 2:
        return None

    status_type = comp.get("status", {}).get("type", {})
    status_state = status_type.get("state", "unknown")
    status_detail = status_type.get("description", "")

    match_date_raw = comp.get("date", "")
    match_time_bj = _parse_beijing_time(match_date_raw)

    players = []
    for c in competitors:
        athlete = c.get("athlete", {})
        name = athlete.get("displayName", "")
        short_name = athlete.get("shortName", "")
        full_name = athlete.get("fullName", "")
        is_winner = c.get("winner", False)
        flag_url = athlete.get("flag", {}).get("href", "")
        espn_id = _extract_espn_id(athlete.get("links", []))
        headshot_url = _build_headshot_url(espn_id)

        scores = []
        for ls in c.get("linescores", []):
            scores.append(str(int(ls.get("value", 0))))

        players.append({
            "name": name,
            "short_name": short_name,
            "full_name": full_name,
            "is_winner": is_winner,
            "flag_url": flag_url,
            "headshot_url": headshot_url,
            "espn_id": espn_id,
            "scores": "-".join(scores) if scores else "",
        })

    notes_list = comp.get("notes", [])
    notes_text = notes_list[0].get("text", "") if notes_list else ""

    venue = comp.get("venue", {}).get("fullName", "")

    return {
        "home": players[0],
        "away": players[1],
        "status": status_state,
        "status_detail": status_detail,
        "date": match_date_raw[:10] if match_date_raw else "",
        "time_bj": match_time_bj,
        "tournament": tournament_name,
        "round": round_name,
        "is_major": is_major,
        "notes": notes_text,
        "venue": venue,
    }


# ═══════════════════════════════════════════════
# 球员匹配
# ═══════════════════════════════════════════════

def match_favorite_player(match):
    """检查比赛是否有关注的球员"""
    search_text = f"{match['home']['name']} {match['away']['name']} {match['notes']}"

    matched = []
    for player_name, info in FAVORITE_PLAYERS.items():
        for kw in info["keywords"]:
            if kw.lower() in search_text.lower():
                matched.append(player_name)
                break

    return matched


# ═══════════════════════════════════════════════
# HTML 邮件生成
# ═══════════════════════════════════════════════

def generate_html(today_matches, yesterday_matches, today_str, yesterday_str):
    """生成 HTML 邮件"""

    def player_avatar(p):
        """球员头像 + 国旗"""
        headshot = p.get("headshot_url", "")
        flag = p.get("flag_url", "")
        name = p.get("short_name", p.get("name", "?"))[:12]

        # 头像
        img_html = ""
        if headshot:
            img_html = f'<img src="{headshot}" width="56" height="56" style="border-radius:50%;object-fit:cover;border:3px solid #e0e0e0;display:block;" onerror="this.style.display=\'none\'">'

        # 国旗小标
        flag_html = ""
        if flag:
            flag_html = f'<img src="{flag}" width="18" height="12" style="vertical-align:middle;margin-top:4px;border-radius:2px;">'

        return f"""
        <td width="38%" style="text-align:center;vertical-align:top;padding:4px 8px;">
            <div style="width:56px;height:56px;border-radius:50%;overflow:hidden;margin:0 auto 6px;background:#e8f5e9;display:flex;align-items:center;justify-content:center;font-size:28px;">
                {img_html or '🎾'}
            </div>
            <div style="font-size:13px;font-weight:700;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin:0 auto 2px;">{name}</div>
            {flag_html}
        </td>"""

    def status_badge(match):
        status = match["status"]
        labels = {
            "pre": ("#4CAF50", "即将开始"),
            "in": ("#FF5722", "比赛中"),
            "post": ("#757575", "已结束"),
        }
        color, text = labels.get(status, ("#757575", status))
        return f'<span style="background:{color};color:#fff;padding:2px 10px;border-radius:10px;font-size:11px;">{text}</span>'

    def match_card(match, players, is_result=False):
        home = match["home"]
        away = match["away"]

        # 比赛信息行
        title = f"\U0001F3BE {match['tournament']}"
        if match["is_major"]:
            title += " \U0001F3C6"
        if match["round"]:
            title += f" · {match['round']}"

        # 比分/时间行
        info_line = ""
        if match["status"] == "post":
            # 已结束 → 显示比分
            if match["notes"]:
                # 解析 notes 提取比分部分
                notes = match["notes"]
                # 格式: "(2) Elena Rybakina (KAZ) bt Veronika Erjavec (SLO) 6-2 6-2"
                if " bt " in notes:
                    score_part = notes.split(" bt ")[1]
                    # 取最后的比分 (去掉国家缩写)
                    score_match = re.search(r'[\d\-\s]+$', score_part)
                    score_display = score_match.group().strip() if score_match else score_part.split(") ")[-1]
                else:
                    score_display = notes[:50]
                info_line = f'<div style="font-size:15px;color:#E63946;font-weight:700;margin-top:4px;">{score_display}</div>'

            # 胜负标记
            home_win = home.get("is_winner", False)
            away_win = away.get("is_winner", False)
            if home_win:
                info_line += f'<div style="font-size:11px;color:#4CAF50;margin-top:2px;">{home["short_name"]} 获胜</div>'
            elif away_win:
                info_line += f'<div style="font-size:11px;color:#4CAF50;margin-top:2px;">{away["short_name"]} 获胜</div>'

        elif match["status"] in ("pre", "in"):
            # 未开始/进行中 → 显示开赛时间
            if match.get("time_bj"):
                info_line = f'<div style="font-size:15px;color:#1976D2;font-weight:700;margin-top:4px;">\U0001F552 {match["time_bj"]}</div>'

        return f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;margin-bottom:14px;box-shadow:0 1px 8px rgba(0,0,0,0.06);overflow:hidden;">
            <tr><td style="padding:10px 14px;background:#f8f9fa;border-bottom:1px solid #eee;">
                <table width="100%"><tr>
                    <td style="font-size:12px;color:#666;">{title}</td>
                    <td style="text-align:right;">{status_badge(match)}</td>
                </tr></table>
            </td></tr>
            <tr><td style="padding:14px 10px 4px;">
                <table width="100%" cellpadding="0" cellspacing="0" style="text-align:center;">
                    <tr>
                        {player_avatar(home)}
                        <td width="24%" style="vertical-align:middle;padding:0 8px;">
                            <div style="font-size:16px;color:#bbb;font-weight:bold;">VS</div>
                            {info_line}
                        </td>
                        {player_avatar(away)}
                    </tr>
                </table>
            </td></tr>
            <tr><td style="padding:6px 14px 12px;text-align:center;">
                {''.join(f'<span style="color:#333;font-size:12px;font-weight:600;margin:0 4px;">{FAVORITE_PLAYERS.get(p,{}).get("flag_emoji","")} {FAVORITE_PLAYERS.get(p,{}).get("emoji","")} {p}</span>' for p in players)}
            </td></tr>
        </table>"""

    today_html = ""
    if today_matches:
        for m in today_matches:
            today_html += match_card(m, m.get("players", []))
    else:
        today_html = '<div style="background:#f8f9fa;border-radius:12px;padding:30px;text-align:center;color:#999;margin-bottom:14px;">🎾 今天没有关注球员的比赛</div>'

    yesterday_html = ""
    if yesterday_matches:
        for m in yesterday_matches:
            yesterday_html += match_card(m, m.get("players", []), is_result=True)
    else:
        yesterday_html = '<div style="background:#f8f9fa;border-radius:12px;padding:24px;text-align:center;color:#999;">昨日无关注球员比赛</div>'

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:580px;margin:0 auto;">
<tr><td style="background:linear-gradient(135deg,#1a6b3c 0%,#228b22 50%,#0d5e2e 100%);padding:28px 24px;text-align:center;border-radius:0 0 24px 24px;">
    <div style="font-size:36px;margin-bottom:4px;">🎾</div>
    <div style="color:#fff;font-size:20px;font-weight:700;">网球每日赛程</div>
    <div style="color:rgba(255,255,255,0.7);font-size:13px;margin-top:4px;">{today_str}</div>
    <div style="margin-top:14px;">
        <span style="background:rgba(255,255,255,0.18);color:#fff;padding:4px 12px;border-radius:14px;font-size:12px;margin:0 3px;">🌸 莱巴金娜</span>
        <span style="background:rgba(255,255,255,0.18);color:#fff;padding:4px 12px;border-radius:14px;font-size:12px;margin:0 3px;">👑 德约</span>
        <span style="background:rgba(255,255,255,0.18);color:#fff;padding:4px 12px;border-radius:14px;font-size:12px;margin:0 3px;">⭐ 王欣瑜</span>
    </div>
</td></tr>
<tr><td style="padding:20px 14px 4px;">
    <div style="font-size:15px;font-weight:700;color:#1a1a1a;margin-bottom:10px;">📅 今日赛程</div>
    {today_html}
</td></tr>
<tr><td style="padding:4px 14px 20px;">
    <div style="font-size:15px;font-weight:700;color:#1a1a1a;margin-bottom:10px;">🏆 昨日赛果 · {yesterday_str}</div>
    {yesterday_html}
</td></tr>
<tr><td style="padding:16px;text-align:center;color:#bbb;font-size:11px;line-height:1.6;">
    <div>数据来源: ESPN API · Roland Garros 2026</div>
    <div>每日 08:00 自动推送</div>
</td></tr>
</table></body></html>"""


# ═══════════════════════════════════════════════
# 邮件发送
# ═══════════════════════════════════════════════

def send_email(html_content, subject):
    """发送 HTML 邮件"""
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
            print(f"[OK] 邮件发送成功: {subject}")
            return True
        except smtplib.SMTPServerDisconnected:
            print(f"[重试] SMTP 断开, 重试 ({attempt+1}/3)...")
            time.sleep(3)
        except Exception as e:
            print(f"[失败] 邮件发送: {e}")
            time.sleep(2)
    return False


# ═══════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════

def main():
    today = datetime.now(TZ)
    yesterday = today - timedelta(days=1)

    today_str = today.strftime("%Y年%m月%d日 %A")
    yesterday_str = yesterday.strftime("%m月%d日")
    today_date = today.strftime("%Y-%m-%d")
    yesterday_date = yesterday.strftime("%Y-%m-%d")

    print(f"\n{'='*50}")
    print(f"网球赛程推送 - {today_str}")
    print(f"{'='*50}")

    print(f"\n[1] 获取 ESPN 比赛数据...")
    all_matches = fetch_espn_matches()
    print(f"    共获取 {len(all_matches)} 场比赛")
    if not all_matches:
        print("    无数据，退出")
        return

    today_matches = []
    yesterday_matches = []
    seen_today = set()
    seen_yesterday = set()

    for m in all_matches:
        players = match_favorite_player(m)
        if not players:
            continue

        match_date = m["date"]
        home_name = m["home"]["name"]
        away_name = m["away"]["name"]
        key = (home_name, away_name, m["tournament"])

        if match_date == today_date:
            if key not in seen_today:
                seen_today.add(key)
                m["players"] = players
                today_matches.append(m)
        elif match_date == yesterday_date:
            if key not in seen_yesterday:
                seen_yesterday.add(key)
                m["players"] = players
                yesterday_matches.append(m)

    print(f"\n[2] 今日关注: {len(today_matches)} 场")
    for m in today_matches:
        status_text = {"pre": "即将", "in": "进行中", "post": "已结束"}.get(m["status"], m["status"])
        time_info = f" {m.get('time_bj', '')}" if m.get("time_bj") else ""
        print(f"    [{status_text}{time_info}] {m['home']['name']} vs {m['away']['name']} ({m['round']})")
        print(f"           球员: {', '.join(m['players'])}")

    print(f"\n[3] 昨日关注: {len(yesterday_matches)} 场")
    for m in yesterday_matches:
        print(f"    [完赛] {m['home']['name']} vs {m['away']['name']} ({m['round']})")
        if m["notes"]:
            print(f"           {m['notes'][:80]}")

    if today_matches or yesterday_matches:
        print(f"\n[4] 生成 HTML 邮件...")
        html = generate_html(today_matches, yesterday_matches, today_str, yesterday_str)

        subject = f"🎾 网球赛程 · {today_str}"
        if today_matches:
            seen_names = set()
            unique_names = []
            for m in today_matches:
                for p in m.get("players", []):
                    if p not in seen_names:
                        seen_names.add(p)
                        unique_names.append(p)
            subject = f"🎾 {' · '.join(unique_names)} · {today_str}"

        try:
            print(f"    主题: {subject}")
        except UnicodeEncodeError:
            pass
        send_email(html, subject)
    else:
        print(f"\n[4] 没有关注球员的比赛，不发送邮件")

    print(f"\n{'='*50}")
    print("完成!")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    main()
