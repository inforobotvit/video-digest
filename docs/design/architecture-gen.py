#!/usr/bin/env python3
"""Generate docs/design/architecture-{light,dark}.{html,svg,png} for Video Digest.

Usage: python3 docs/design/architecture-gen.py docs/design
Writes the HTML and SVG, then runs architecture-check.mjs in headless Chromium (Playwright from
frontend/node_modules): every <text> is measured with getBBox against its box inset by 12 px; any overflow
is listed, the exit code is non-zero and no PNG is written. One layout, two token sets (light / dark from
frontend/src/styles/tokens.css). Slide-16x9 preset: viewBox 0 0 1280 720, PNG 3840x2160.

Picture as of 2026-10-04 (step G): the browser talks to Cloudflare Turnstile itself and jobs-api verifies the
token; six n8n workflows; Postgres with five tables; Deepgram and OpenAI as the external providers, both
replaceable by self-hosted endpoints through environment variables.
"""
import pathlib, subprocess, sys

OUT = pathlib.Path(sys.argv[1])
HERE = pathlib.Path(__file__).resolve().parent
PAD = 12  # the fit check: text stays this far from every edge of its box

THEMES = {
    "light": dict(
        paper="#fafafa", ink="#18181b", muted="#52525b", soft="#71717a",
        ink_rgb="24,24,27", accent="#4c5fd5", accent_tint="rgba(76,95,213,0.08)",
        link="#0e8a80", backend_fill="#ffffff", muted_rgb="82,82,91",
    ),
    "dark": dict(
        paper="#111113", ink="#f4f4f5", muted="#a1a1aa", soft="#8b8b94",
        ink_rgb="244,244,245", accent="#5b6bb8", accent_tint="rgba(91,107,184,0.14)",
        link="#2f8a82", backend_fill="#18181b", muted_rgb="161,161,170",
    ),
}

SANS = "'IBM Plex Sans', system-ui, sans-serif"
MONO = "'IBM Plex Mono', ui-monospace, Menlo, monospace"

# ---- geometry (multiples of 4) ------------------------------------------------------
NODE_H = 72
ROW1, ROW2, ROW3 = 144, 272, 416
C1, C2 = ROW1 + 36, ROW2 + 36            # 180, 308
PG_H = 112                                # Postgres: title and three lines of tables
C3 = ROW3 + 40                            # arrows enter Postgres and OpenAI at 456

ZONE_COMPOSE = (48, 68, 936, 500)          # x, y, w, h
ZONE_N8N = (488, 112, 272, 436)
ZONE_EXT = (1000, 68, 240, 500)

NODES = {
    # key: (x, w, top, h, kind, title, title_size, [sub lines], sub_font)
    "front":    (64,   192, ROW1, NODE_H, "input",    "Фронт",                20, ["React · документ с глубиной"], SANS),
    "nginx":    (304,  160, ROW1, NODE_H, "external", "nginx",                20, ["TLS · лимиты по адресу"],      SANS),
    "jobs":     (504,  240, ROW1, NODE_H, "backend",  "jobs-api",             20, ["probe · jobs · feedback · limits"], MONO),
    "pipeline": (504,  240, ROW2, NODE_H, "focal",    "pipeline",             20, ["этапы · валидация · повтор"],  SANS),
    "media":    (788,  200, ROW1, NODE_H, "backend",  "Media Service",        20, ["FastAPI · yt-dlp · ffmpeg"],   MONO),
    "pg":       (788,  200, ROW3, PG_H,   "store",    "Postgres",             20, ["jobs · events", "settings · feedback", "turnstile_used"], MONO),
    "cf":       (1012, 216, ROW1, NODE_H, "provider", "Cloudflare Turnstile", 17, ["виджет в браузере · siteverify"], SANS),
    "stt":      (1012, 216, ROW2, NODE_H, "provider", "Deepgram",             20, ["распознавание речи · nova-3"], SANS),
    "llm":      (1012, 216, ROW3, NODE_H, "provider", "OpenAI",               20, ["чистка · выжимка · критика"],  SANS),
}

# the four helper workflows: full-width rows under pipeline, name left (mono), purpose right (sans)
SMALL = [
    ("llm-call",    "вызов модели, валидация"),
    ("on-error",    "страховка пайплайна"),
    ("log-events",  "события в Postgres"),
    ("maintenance", "чистка раз в час"),
]
SMALL_X, SMALL_W, SMALL_H, SMALL_TOP, SMALL_GAP = 504, 240, 40, 360, 4

STAGES = [  # (label, focal); box width from the label length
    ("ССЫЛКА ИЛИ ФАЙЛ", False),
    ("СУБТИТРЫ ИЛИ АУДИО", False),
    ("ТРАНСКРИПТ", True),
    ("ЧИСТКА", False),
    ("ВЫЖИМКА", True),
    ("ДОП. БЛОКИ", False),
    ("ДОКУМЕНТ", False),
]
STAGE_H, STAGE_Y, STAGE_GAP = 44, 632, 28


def node_style(kind, t):
    ink = t["ink_rgb"]
    return {
        "focal":    (t["accent_tint"], t["accent"]),
        "backend":  (t["backend_fill"], t["ink"]),
        "store":    (f"rgba({ink},0.05)", t["muted"]),
        "external": (f"rgba({ink},0.03)", f"rgba({ink},0.30)"),
        "input":    (f"rgba({t['muted_rgb']},0.10)", t["soft"]),
        "provider": (f"rgba({ink},0.02)", f"rgba({ink},0.35)"),
    }[kind]


def box_attr(x, y, w, h, pad=PAD):
    return f' data-box="{x},{y},{w},{h},{pad}"'


def build_svg(theme):
    t = THEMES[theme]
    ink = t["ink_rgb"]
    slug = "vd-arch" if theme == "light" else "vd-arch-dark"
    o = []
    a = o.append

    a(f'<svg viewBox="0 0 1280 720" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="{slug}-title {slug}-desc">')
    a(f'<title id="{slug}-title">Video Digest – от ссылки до документа</title>')
    a(f'<desc id="{slug}-desc">Архитектура сервиса: фронт и nginx, оркестрация в n8n (jobs-api, pipeline и четыре служебных флоу: llm-call, on-error, log-events, maintenance), Media Service и Postgres с пятью таблицами в одном docker compose; Cloudflare Turnstile проверяет браузер, Deepgram распознаёт речь, OpenAI делает чистку, выжимку и критику – оба провайдера заменяются локальными через переменные окружения; внизу этапы от ссылки до документа.</desc>')
    a('<defs>')
    a(f'<marker id="{slug}-arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="{t["muted"]}"/></marker>')
    a(f'<marker id="{slug}-arrow-accent" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="{t["accent"]}"/></marker>')
    a(f'<marker id="{slug}-arrow-link" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="{t["link"]}"/></marker>')
    a('</defs>')
    a(f'<rect x="0" y="0" width="1280" height="720" fill="{t["paper"]}"/>')

    def header(x, text):
        a(f'<text x="{x}" y="52" fill="{t["soft"]}" font-size="12" font-weight="500" font-family="{SANS}" text-anchor="middle" letter-spacing="0.16em">{text}</text>')
    header(264, "КЛИЕНТ")
    header(624, "ОРКЕСТРАЦИЯ")
    header(888, "ОБРАБОТКА")
    header(1120, "ВНЕШНИЕ API")

    # zones; the label sits inside the frame, so it is checked against the zone like any other text
    def zone(zx, label, dashed=False):
        x, y, w, h = zx
        dash = ' stroke-dasharray="4,3"' if dashed else ""
        a(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="rgba({ink},0.02)" stroke="rgba({ink},0.10)" stroke-width="0.8"{dash}/>')
        a(f'<text x="{x + 16}" y="{y + 26}" fill="rgba({ink},0.45)" font-size="12" font-family="{MONO}" letter-spacing="0.14em"{box_attr(*zx)}>{label}</text>')
    zone(ZONE_COMPOSE, "DOCKER COMPOSE · VPS · NGINX + HTTPS · DEPLOY BY COMMIT SHA")
    zone(ZONE_N8N, "N8N · 6 ФЛОУ")
    zone(ZONE_EXT, "ЗАМЕНЯЕМЫ ЛОКАЛЬНЫМИ", dashed=True)

    M, A, L = f"url(#{slug}-arrow)", f"url(#{slug}-arrow-accent)", f"url(#{slug}-arrow-link)"
    a(f'<path d="M 256,{C1} H 304" fill="none" stroke="{t["link"]}" stroke-width="1.6" marker-end="{L}"/>')
    a(f'<path d="M 464,{C1} H 504" fill="none" stroke="{t["link"]}" stroke-width="1.6" marker-end="{L}"/>')
    # jobs-api -> pipeline (RUN)
    a(f'<path d="M 624,{ROW1 + NODE_H} V {ROW2}" fill="none" stroke="{t["accent"]}" stroke-width="2" marker-end="{A}"/>')
    # jobs-api -> Cloudflare siteverify, above the nodes, under the zone labels
    a(f'<path d="M 680,{ROW1} V 108 Q 680,100 688,100 H 1112 Q 1120,100 1120,108 V {ROW1}" fill="none" stroke="{t["link"]}" stroke-width="1.4" marker-end="{L}"/>')
    # pipeline -> media (up through the gap at x=772)
    a(f'<path d="M 744,{C2 - 16} H 764 Q 772,{C2 - 16} 772,{C2 - 24} V {C1 + 8} Q 772,{C1} 780,{C1} H 788" fill="none" stroke="{t["muted"]}" stroke-width="1.6" marker-end="{M}"/>')
    # pipeline -> Deepgram (AUDIO)
    a(f'<path d="M 744,{C2} H 1012" fill="none" stroke="{t["link"]}" stroke-width="1.6" marker-end="{L}"/>')
    # pipeline -> OpenAI (TEXT), down the gap right of Postgres
    a(f'<path d="M 744,{C2 + 16} H 992 Q 1000,{C2 + 16} 1000,{C2 + 24} V {C3 - 8} Q 1000,{C3} 1008,{C3} H 1012" fill="none" stroke="{t["link"]}" stroke-width="1.6" marker-end="{L}"/>')
    # pipeline -> Postgres (STATUS · RESULT), down the gap at x=772
    a(f'<path d="M 744,{C2 + 30} H 764 Q 772,{C2 + 30} 772,{C2 + 38} V {C3 - 8} Q 772,{C3} 780,{C3} H 788" fill="none" stroke="{t["muted"]}" stroke-width="1.6" marker-end="{M}"/>')

    # arrow labels: a paper mask under the text; the mask is the text's box for the check (pad 2)
    def alabel(cx, y_top, w, text, color):
        a(f'<rect x="{cx - w // 2}" y="{y_top}" width="{w}" height="20" rx="2" fill="{t["paper"]}"/>')
        a(f'<text x="{cx}" y="{y_top + 14}" fill="{color}" font-size="12" font-family="{MONO}" text-anchor="middle" letter-spacing="0.06em"{box_attr(cx - w // 2, y_top, w, 20, 2)}>{text}</text>')
    alabel(280, C1 - 26, 52, "HTTPS", t["link"])
    alabel(484, C1 - 26, 44, "REST", t["link"])
    alabel(656, (ROW1 + NODE_H + ROW2) // 2 - 9, 40, "RUN", t["accent"])
    alabel(900, 82, 100, "SITEVERIFY", t["link"])
    alabel(888, C2 - 26, 60, "AUDIO", t["link"])
    alabel(888, C2 + 24, 52, "TEXT", t["link"])
    alabel(888, C3 - 38, 136, "STATUS · RESULT", t["soft"])

    for key, (x, w, top, h, kind, title, tsize, subs, fam) in NODES.items():
        fill, stroke = node_style(kind, t)
        cx = x + w // 2
        a(f'<!-- Node: {title} -->')
        a(f'<rect x="{x}" y="{top}" width="{w}" height="{h}" rx="6" fill="{t["paper"]}"/>')
        a(f'<rect x="{x}" y="{top}" width="{w}" height="{h}" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>')
        a(f'<text x="{cx}" y="{top + 32}" fill="{t["ink"]}" font-size="{tsize}" font-weight="600" font-family="{SANS}" text-anchor="middle"{box_attr(x, top, w, h)}>{title}</text>')
        sub_size = 11 if fam == MONO else 12
        for i, sub in enumerate(subs):
            a(f'<text x="{cx}" y="{top + 56 + i * 18}" fill="{t["muted"]}" font-size="{sub_size}" font-family="{fam}" text-anchor="middle"{box_attr(x, top, w, h)}>{sub}</text>')

    for i, (name, purpose) in enumerate(SMALL):
        top = SMALL_TOP + i * (SMALL_H + SMALL_GAP)
        a(f'<rect x="{SMALL_X}" y="{top}" width="{SMALL_W}" height="{SMALL_H}" rx="4" fill="{t["backend_fill"]}" stroke="rgba({ink},0.30)" stroke-width="1"/>')
        a(f'<text x="{SMALL_X + PAD}" y="{top + 25}" fill="{t["ink"]}" font-size="12" font-weight="600" font-family="{MONO}"{box_attr(SMALL_X, top, SMALL_W, SMALL_H)}>{name}</text>')
        a(f'<text x="{SMALL_X + SMALL_W - PAD}" y="{top + 25}" fill="{t["muted"]}" font-size="11" font-family="{SANS}" text-anchor="end"{box_attr(SMALL_X, top, SMALL_W, SMALL_H)}>{purpose}</text>')

    zx, zy, zw, zh = ZONE_EXT
    for i, line in enumerate(["Локальный контур: STT и LLM", "на своих серверах, переключение", "переменными окружения"]):
        a(f'<text x="{zx + zw // 2}" y="{ROW3 + NODE_H + 28 + i * 18}" fill="{t["soft"]}" font-size="11.5" font-family="{SANS}" text-anchor="middle"{box_attr(*ZONE_EXT)}>{line}</text>')

    a(f'<line x1="48" y1="596" x2="1240" y2="596" stroke="rgba({ink},0.10)" stroke-width="0.8"/>')
    widths = [int(len(label) * 10.6) + 2 * PAD + 8 for label, _ in STAGES]  # upper-case Cyrillic with tracking
    total = sum(widths) + STAGE_GAP * (len(STAGES) - 1)
    x = (1280 - total) // 2
    for i, ((label, focal), w) in enumerate(zip(STAGES, widths)):
        if focal:
            a(f'<rect x="{x}" y="{STAGE_Y}" width="{w}" height="{STAGE_H}" rx="4" fill="{t["accent_tint"]}" stroke="{t["accent"]}" stroke-width="1"/>')
            color = t["accent"]
        else:
            a(f'<rect x="{x}" y="{STAGE_Y}" width="{w}" height="{STAGE_H}" rx="4" fill="transparent" stroke="rgba({ink},0.30)" stroke-width="1"/>')
            color = t["muted"]
        a(f'<text x="{x + w // 2}" y="{STAGE_Y + 26}" fill="{color}" font-size="12" font-weight="500" font-family="{SANS}" text-anchor="middle" letter-spacing="0.12em"{box_attr(x, STAGE_Y, w, STAGE_H)}>{label}</text>')
        if i < len(STAGES) - 1:
            a(f'<line x1="{x + w + 4}" y1="{STAGE_Y + STAGE_H // 2}" x2="{x + w + STAGE_GAP - 4}" y2="{STAGE_Y + STAGE_H // 2}" stroke="{t["muted"]}" stroke-width="1.2" marker-end="{M}"/>')
        x += w + STAGE_GAP

    a('</svg>')
    return "\n".join(o)


def build_html(theme, svg):
    t = THEMES[theme]
    return f"""<!DOCTYPE html>
<html lang="ru" data-theme="{theme}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Video Digest · Architecture ({theme})</title>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{ --paper:{t["paper"]}; --ink:{t["ink"]}; --font-sans:{SANS}; --font-mono:{MONO}; }}
    body {{ font-family:var(--font-sans); background:var(--paper); color:var(--ink); min-height:100vh;
      display:flex; align-items:center; justify-content:center; padding:2rem; }}
    .frame {{ max-width:1280px; width:100%; }}
    svg {{ width:100%; display:block; }}
  </style>
</head>
<body>
  <div class="frame">
{svg}
  </div>
</body>
</html>
"""


for theme in ("light", "dark"):
    svg = build_svg(theme)
    (OUT / f"architecture-{theme}.svg").write_text(svg, encoding="utf-8")
    (OUT / f"architecture-{theme}.html").write_text(build_html(theme, svg), encoding="utf-8")
    print("wrote", OUT / f"architecture-{theme}.html", "and .svg")

# Fit check and PNG in the same headless browser: no green check, no PNG.
check = subprocess.run(["node", str(HERE / "architecture-check.mjs")])
sys.exit(check.returncode)
