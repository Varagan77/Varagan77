#!/usr/bin/env python3
"""
Generates the full neofetch-style profile card (ASCII art + info panel)
as two SVGs (dark/light): generated/profile-dark.svg, generated/profile-light.svg.

Replaces the old dragon.svg + age-hex.svg + github-profile-summary-cards +
pacman-contribution-graph combo with a single self-contained CLI-style card,
matching the original hand-made profile.svg.

Env vars (set by the GitHub Action):
    PROFILE_TOKEN or GITHUB_TOKEN - used to query the GraphQL API.
        NOTE: the default, repo-scoped GITHUB_TOKEN cannot read
        cross-repo/profile-level data (stars across repos, follower count,
        contributionsCollection). Set a classic PAT with `read:user` and
        `public_repo` scopes as a repo secret named PROFILE_TOKEN, or the
        stats below will silently come back as 0.
    GITHUB_REPOSITORY_OWNER - the account to pull stats for

Run with no args; safe to run locally without a token (falls back to zeros).
"""
import datetime
import json
import os
import urllib.error
import urllib.request
import xml.sax.saxutils as sx

BIRTH_DATE = datetime.date(2000, 7, 7)
OUT_DIR = "generated"
USERNAME = os.environ.get("GITHUB_REPOSITORY_OWNER", "Varagan77")
TOKEN = os.environ.get("PROFILE_TOKEN") or os.environ.get("GITHUB_TOKEN", "")

BLOCKS = " ▁▂▃▄▅▆▇█"

THEMES = {
    "dark": {
        "text": "#c9d1d9",
        "key": "#ffa657",
        "value": "#a5d6ff",
        "cc": "#616e7f",
        "add": "#3fb950",
        "del": "#f85149",
    },
    "light": {
        "text": "#24292e",
        "key": "#953800",
        "value": "#0550ae",
        "cc": "#8c959f",
        "add": "#1a7f37",
        "del": "#cf222e",
    },
}

# --- ASCII art (dragon head), from the latest ascii-art export -------------
ASCII_ART = [
    '                   _,^^ⁿⁿⁿ^^-n.                      ',
    "                ,/^'   \\  \\;ⁿ≈\\,                     ",
    "               ^'(\\\\( ½,,,,,≈\\\\^                     ",
    "              /'\\/(,*~``^`;;`~,^^\\                   ",
    "             /'(/.%:.::::::::: \\\\⌡                   ",
    "            |'(//| :::.....     \\\\                   ",
    "            |./(≈ \\::....        '\\                  ",
    '             |/≈ / :. ,,___,  %æ7z¿¿,                ',
    "             |/_/½=≈±√º``''`;╜{     |                ",
    "             |^\\.;`  (     ;¿  \\__*^'                ",
    "             | ∩'//..`╜+⌐+?;|,,)'  {                 ",
    '             `\\¿`+//....     xxxxx,]                 ',
    '               \\-|///.....,x` ,,  x|                 ',
    '                 |\\////../#  ,;;, #\\                 ',
    '                 ]·(///////\\\\\\\\\\\\\\\\\\#                ',
    '               ,;\\:·##(///////\\;\\\\\\\\#`...__          ',
    '              .;.#|: ·═##\\\\\\\\\\\\\\\\\\##÷#\\ ::::`--      ',
    "           .-'|..#|:..·══########÷·÷/##\\ ::::::##    ",
    "         .,'::|..#\\:..             /..##\\  :::::##   ",
    "      #-' ::::|..##\\::...         ..##+-->  :::::##  ",
    '    ##::::::: /.##.#+:::...      /|#.#./    ::::::## ',
    '  ###::::::::|.### #|\\##::: :   /:|##./   :::::::::# ',
    ' ##::::::::: ≤───-\\#| \\`###:::::\\:|#./ ::::::::::: ##',
    " #:::::::::::'``   `|..\\``####::::\\./::::::::::::::##",
]

GQL_QUERY = """
query($login: String!) {
  user(login: $login) {
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100) {
      totalCount
      nodes { stargazerCount }
    }
    followers { totalCount }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar {
        weeks { contributionDays { contributionCount date } }
      }
    }
  }
}
"""


def fetch_stats():
    """Query GitHub's GraphQL API for live stats. Falls back to zeros offline."""
    empty = {
        "stars": 0,
        "repos": 0,
        "followers": 0,
        "commits_year": 0,
        "prs": 0,
        "issues": 0,
        "daily": [],
    }
    if not TOKEN:
        return empty
    try:
        body = json.dumps({"query": GQL_QUERY, "variables": {"login": USERNAME}}).encode()
        req = urllib.request.Request(
            "https://api.github.com/graphql",
            data=body,
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
                "User-Agent": USERNAME,
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
        user = data["data"]["user"]
        repos = user["repositories"]["nodes"]
        stars = sum(r["stargazerCount"] for r in repos)
        weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
        daily = [d["contributionCount"] for w in weeks for d in w["contributionDays"]]
        return {
            "stars": stars,
            "repos": user["repositories"]["totalCount"],
            "followers": user["followers"]["totalCount"],
            "commits_year": user["contributionsCollection"]["totalCommitContributions"],
            "prs": user["contributionsCollection"]["totalPullRequestContributions"],
            "issues": user["contributionsCollection"]["totalIssueContributions"],
            "daily": daily,
        }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        print(f"warning: stats fetch failed (HTTP {exc.code}): {body}; using zeros")
        return empty
    except Exception as exc:  # network unavailable, bad token, malformed response, etc.
        print(f"warning: stats fetch failed ({exc}); using zeros")
        return empty


def compute_age(today: datetime.date):
    years = today.year - BIRTH_DATE.year - (
        (today.month, today.day) < (BIRTH_DATE.month, BIRTH_DATE.day)
    )
    next_year = today.year if (today.month, today.day) <= (BIRTH_DATE.month, BIRTH_DATE.day) else today.year + 1
    try:
        next_bday = datetime.date(next_year, BIRTH_DATE.month, BIRTH_DATE.day)
    except ValueError:
        next_bday = datetime.date(next_year, 3, 1)
    return years, (next_bday - today).days


def compute_streak(daily):
    """Current consecutive-day streak (contributions > 0), counted backwards
    from the most recent day in the calendar."""
    streak = 0
    for count in reversed(daily):
        if count > 0:
            streak += 1
        else:
            break
    return streak


def sparkline(daily, weeks=52):
    """Collapse the last N weeks of the contribution calendar into a
    single row of block characters, GitHub-heatmap-style but in text."""
    if not daily:
        return "".join(BLOCKS[0] for _ in range(weeks))
    per_week = [daily[i:i + 7] for i in range(0, len(daily), 7)][-weeks:]
    sums = [sum(w) for w in per_week]
    peak = max(sums) or 1
    out = ""
    for s in sums:
        idx = min(len(BLOCKS) - 1, round((s / peak) * (len(BLOCKS) - 1)))
        out += BLOCKS[idx] if s else BLOCKS[0]
    return out


def esc(s):
    return sx.escape(str(s))


def row(label, value, dots_len=28, sub=None):
    """One '.  Key:  ......  value' line, optionally 'Key.Sub:'."""
    key_text = label if not sub else f"{label}.{sub}"
    dots = "." * max(3, dots_len - len(key_text))
    if sub:
        key_tspan = f'<tspan class="key">{esc(label)}</tspan>.<tspan class="key">{esc(sub)}</tspan>'
    else:
        key_tspan = f'<tspan class="key">{esc(label)}</tspan>'
    return (
        f'<tspan class="cc">. </tspan>{key_tspan}:'
        f'<tspan class="cc"> {dots} </tspan>'
        f'<tspan class="value">{esc(value)}</tspan>'
    )


def build_svg(theme_name: str, years: int, days_left: int, stats: dict) -> str:
    t = THEMES[theme_name]
    hex_age = "0x" + format(years, "X").upper()
    age_value = f"{hex_age}  ({years}, {days_left}d until)"

    graph = sparkline(stats["daily"], weeks=52)
    total_contrib = sum(stats["daily"]) if stats["daily"] else 0
    streak = compute_streak(stats["daily"])
    peak_week = max((sum(stats["daily"][i:i + 7]) for i in range(0, len(stats["daily"]), 7)), default=0)

    y = 40
    LX = 10  # left column (ascii) x
    RX = 740  # right column (panel) x — wide gap from the art
    LY = 40
    ASCII_FONT = 20

    ascii_lines = "".join(
        f'\n    <tspan x="{LX}" dy="1em">{esc(line)}</tspan>' for line in ASCII_ART
    )

    panel_lines = []
    panel_lines.append(f'<tspan x="{RX}" y="99">{esc(USERNAME)}</tspan> -——————————————————————————————————————————————-—-')
    panel_lines.append(f'<tspan x="{RX}" y="121">{row("OS", "Windows 11, Linux", 22)}</tspan>')
    panel_lines.append(f'<tspan x="{RX}" y="143">{row("Distros", "Ubuntu, Mint, Fedora", 16)}</tspan>')
    panel_lines.append(f'<tspan x="{RX}" y="165">{row("IDE", "Vscode, N++, VIM", 22)}</tspan>')
    panel_lines.append(f'<tspan x="{RX}" y="198">{row("Languages", "HTML, CSS, JS, TS, Astro", 12, sub="Frontend")}</tspan>')
    panel_lines.append(f'<tspan x="{RX}" y="220">{row("Languages", "C++, C#, Python, SQL", 7, sub="Backend")}</tspan>')
    panel_lines.append(f'<tspan x="{RX}" y="242">{row("Languages", "English, Afrikaans", 3, sub="Real")}</tspan>')

    panel_lines.append(f'<tspan x="{RX}" y="264">- About Me</tspan> -——————————————————————————————————————————————-—-')
    panel_lines.append(f'<tspan x="{RX}" y="286">{row("Hobbies", "Game Modding, Game Developing, Pixel Art", 8, sub="Night")}</tspan>')
    panel_lines.append(f'<tspan x="{RX}" y="308">{row("Hobbies", "Hiking, Cycling, Writing, Reading", 11, sub="Day")}</tspan>')
    panel_lines.append(f'<tspan x="{RX}" y="330">{row("Age", age_value, 11, sub="Lifespan")}</tspan>')

    panel_lines.append(f'<tspan x="{RX}" y="352">- Contact</tspan> -——————————————————————————————————————————————-—-')
    panel_lines.append(f'<tspan x="{RX}" y="374">{row("Email", "johanneswillemkotze@gmail.com", 18, sub="Work")}</tspan>')
    panel_lines.append(f'<tspan x="{RX}" y="396">{row("Site", "varagan77.github.io", 34)}</tspan>')
    panel_lines.append(f'<tspan x="{RX}" y="418">{row("Discord", "varagan77", 34)}</tspan>')

    panel_lines.append(f'<tspan x="{RX}" y="440">- Stats</tspan> -——————————————————————————————————————————————-—-')
    panel_lines.append(f'<tspan x="{RX}" y="462">{row("Repos", stats["repos"], 21)}</tspan>')
    panel_lines.append(f'<tspan x="{RX}" y="484">{row("Stars", stats["stars"], 21)}</tspan>')
    panel_lines.append(f'<tspan x="{RX}" y="506">{row("Followers", stats["followers"], 15)}</tspan>')
    commits_val = f"{stats['commits_year']} (this yr)"
    panel_lines.append(f'<tspan x="{RX}" y="528">{row("Commits", commits_val, 13, sub="Year")}</tspan>')
    panel_lines.append(f'<tspan x="{RX}" y="550">{row("PRs", stats["prs"], 21, sub="Merged")}</tspan>')
    panel_lines.append(f'<tspan x="{RX}" y="572">{row("Contributions", total_contrib, 11, sub="Total")}</tspan>')
    streak_val = f"{streak} day{'s' if streak != 1 else ''}"
    panel_lines.append(f'<tspan x="{RX}" y="594">{row("Streak", streak_val, 8, sub="Current")}</tspan>')
    panel_lines.append(f'<tspan x="{RX}" y="616">{row("Peak", f"{peak_week}/wk", 8, sub="Week")}</tspan>')
    panel_lines.append(
        f'<tspan x="{RX}" y="638"><tspan class="cc">. </tspan>'
        f'<tspan class="key">Activity</tspan>.<tspan class="key">52wk</tspan>:'
        f'<tspan class="cc"> .. </tspan>'
        f'<tspan class="add">{esc(graph)}</tspan></tspan>'
    )

    panel_body = "\n".join(panel_lines)

    svg = f'''<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns="http://www.w3.org/2000/svg" font-family="ConsolasFallback,Consolas,monospace" width="1350px" height="680px" font-size="10px">
<style>
@font-face {{
src: local('Consolas'), local('Consolas Bold');
font-family: 'ConsolasFallback';
font-display: swap;
-webkit-size-adjust: 109%;
size-adjust: 109%;
}}
.key {{ fill: {t['key']}; }}
.value {{ fill: {t['value']}; }}
.addColor {{ fill: {t['add']}; }}
.add {{ fill: {t['add']}; }}
.delColor {{ fill: {t['del']}; }}
.cc {{ fill: {t['cc']}; }}
text, tspan {{ white-space: pre; }}
</style>
<text x="15" y="{y}" fill="{t['text']}" font-size="{ASCII_FONT}px" class="ascii">{ascii_lines}
  </text>
<text x="{RX}" y="{LY}" fill="{t['text']}" font-size="20px">
{panel_body}
</text>
</svg>
'''
    return svg


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    today = datetime.date.today()
    years, days_left = compute_age(today)
    stats = fetch_stats()

    for theme_name in THEMES:
        svg = build_svg(theme_name, years, days_left, stats)
        path = os.path.join(OUT_DIR, f"profile-{theme_name}.svg")
        with open(path, "w") as f:
            f.write(svg)
        print(f"wrote {path}")

    print(f"age: {years} (0x{years:X}), days until next birthday: {days_left}")
    print(f"stats: {stats}")


if __name__ == "__main__":
    main()
