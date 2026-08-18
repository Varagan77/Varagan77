
import datetime
import os
import xml.sax.saxutils as sx

BIRTH_DATE = datetime.date(2000, 7, 7)

OUT_DIR = "generated"

THEMES = {
    "dark": {
        "bg": None,          
        "border": "
        "key": "
        "value": "
        "text": "
        "accent": "
    },
    "light": {
        "bg": None,
        "border": "
        "key": "
        "value": "
        "text": "
        "accent": "
    },
}


def compute_age(today: datetime.date):
    years = today.year - BIRTH_DATE.year - (
        (today.month, today.day) < (BIRTH_DATE.month, BIRTH_DATE.day)
    )

    next_bday_year = today.year if (today.month, today.day) <= (BIRTH_DATE.month, BIRTH_DATE.day) else today.year + 1
    try:
        next_bday = datetime.date(next_bday_year, BIRTH_DATE.month, BIRTH_DATE.day)
    except ValueError:
        
        next_bday = datetime.date(next_bday_year, 3, 1)
    days_left = (next_bday - today).days

    return years, days_left


def hexify(n: int) -> str:
    return "0x" + format(n, "X")


def build_svg(theme: dict, years: int, days_left: int) -> str:
    hex_age = hexify(years)
    width = 460
    line_h = 22
    pad_top = 34
    height = pad_top + 2 * line_h + 24

    def row(label, value, dots_len=28):
        dots = "." * max(3, dots_len - len(label))
        return (
            f'<tspan class="key">{sx.escape(label)}</tspan>'
            f'<tspan class="dim">{dots}</tspan> '
            f'<tspan class="value">{sx.escape(value)}</tspan>'
        )

    row1 = row("Age (hex): ", f"{hex_age}  ({years} yrs)")
    row2 = row("Next birthday: ", f"{days_left} day{'s' if days_left != 1 else ''}")

    svg = f'''<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns="http://www.w3.org/2000/svg" font-family="ConsolasFallback,Consolas,monospace" width="{width}px" height="{height}px" font-size="13px">
<style>
@font-face {{
src: local('Consolas'), local('Consolas Bold');
font-family: 'ConsolasFallback';
font-display: swap;
-webkit-size-adjust: 109%;
size-adjust: 109%;
}}
.border {{ fill: none; stroke: {theme['border']}; stroke-width: 1; }}
.title {{ fill: {theme['accent']}; font-weight: bold; }}
.key {{ fill: {theme['key']}; }}
.value {{ fill: {theme['value']}; }}
.dim {{ fill: {theme['border']}; }}
text, tspan {{ white-space: pre; }}
</style>
<rect class="border" x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="6" ry="6"/>
<text x="16" y="24" class="title">-- Age --------------------------------------</text>
<text x="16" y="{24 + line_h}">{row1}</text>
<text x="16" y="{24 + 2 * line_h}">{row2}</text>
</svg>
'''
    return svg


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    today = datetime.date.today()
    years, days_left = compute_age(today)

    for name, theme in THEMES.items():
        svg = build_svg(theme, years, days_left)
        path = os.path.join(OUT_DIR, f"age-hex-{name}.svg")
        with open(path, "w") as f:
            f.write(svg)
        print(f"wrote {path}")

    print(f"age: {years} ({hexify(years)}), days until next birthday: {days_left}")


if __name__ == "__main__":
    main()
