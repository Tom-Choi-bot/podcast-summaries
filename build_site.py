#!/usr/bin/env python3
"""Build a static GitHub Pages site from local podcast summary markdown files."""
from __future__ import annotations

import html
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import markdown  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Install dependency with: uv run --with markdown python build_site.py") from exc

SOURCE_ROOT = Path(os.environ.get("PODCAST_SUMMARY_SOURCE", "/home/ubuntu/podcast-summaries"))
SITE_ROOT = Path(__file__).resolve().parent
KST = ZoneInfo("Asia/Seoul")

SHOW_NAMES = {
    "park-money-lab": "박연미의 목돈연구소",
    "hand-economy": "손에 잡히는 경제",
    "samprotv": "삼프로TV",
    "kbs-economy-show": "KBS 경제쇼",
}

DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(.+)\.md$")
LOCAL_PATH_RE = re.compile(r"`?/home/ubuntu/podcast-summaries/[^`\n]+`?")

@dataclass(frozen=True)
class Episode:
    date: str
    year: str
    month: str
    day: str
    show_slug: str
    show_name: str
    title: str
    source_path: Path
    md_rel: Path
    html_rel: Path
    excerpt: str
    model: str | None
    duration: str | None
    published: str | None


def slug_to_title(slug: str) -> str:
    return SHOW_NAMES.get(slug, slug.replace("-", " ").title())


def strip_date_prefix(filename: str) -> str:
    m = DATE_RE.match(filename)
    return m.group(4) if m else Path(filename).stem


def readable_title_from_markdown(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback.replace("-", " ")


def extract_field(text: str, label: str) -> str | None:
    pat = re.compile(rf"^- \*\*{re.escape(label)}\*\*: ?(.+)$", re.MULTILINE)
    m = pat.search(text)
    return m.group(1).strip() if m else None


def extract_model(text: str) -> str | None:
    m = re.search(r"전사 모델:\s*`?([^`\n]+)`?", text)
    return m.group(1).strip() if m else None


def sanitize_markdown(text: str) -> str:
    text = re.sub(r"(?ms)^## 원본 정보\s*\n.*?(?=^## |\Z)", "", text)
    lines: list[str] = []
    skip_labels = ("오디오 파일", "전사 TXT", "전사 JSON")
    for line in text.splitlines():
        if any(f"**{label}**" in line for label in skip_labels):
            continue
        line = LOCAL_PATH_RE.sub("내부 보관", line)
        lines.append(line.rstrip())
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"
    cleaned += "\n---\n\n> 이 페이지는 자동 전사 기반 요약을 GitHub Pages용으로 정리한 공개본입니다. 로컬 오디오/전사 파일 경로는 공개본에서 제거했습니다.\n"
    return cleaned


def plain_excerpt(md_text: str, limit: int = 180) -> str:
    text = re.sub(r"```.*?```", " ", md_text, flags=re.S)
    text = re.sub(r"[#>*_`\-|\[\]()]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def page(title: str, body: str, description: str = "Korean podcast summaries") -> str:
    return f"""<!doctype html>
<html lang=\"ko\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <meta name=\"description\" content=\"{html.escape(description)}\" />
  <title>{html.escape(title)}</title>
  <link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">
  <link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>
  <link href=\"https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap\" rel=\"stylesheet\">
  <base href=\"/podcast-summaries/\" />
  <link rel=\"stylesheet\" href=\"assets/style.css\" />
</head>
<body>
  <div class=\"bg-orb orb-a\"></div>
  <div class=\"bg-orb orb-b\"></div>
  <header class=\"site-header\">
    <a class=\"brand\" href=\"\" aria-label=\"Podcast Briefs home\">
      <span class=\"brand-mark\">⌁</span>
      <span>Podcast Briefs</span>
    </a>
    <nav>
      <a href=\"\">Home</a>
      <a href=\"archive/\">Archive</a>
      <a href=\"https://github.com/Tom-Choi-bot/podcast-summaries\">GitHub</a>
    </nav>
  </header>
  {body}
  <footer class=\"site-footer\">
    <span>Generated from full-audio Korean podcast transcripts.</span>
    <span>Dates use Asia/Seoul time.</span>
  </footer>
</body>
</html>
"""


def rel_href(path: Path) -> str:
    return path.as_posix()


def collect() -> list[Episode]:
    episodes: list[Episode] = []
    for show_dir in sorted(SOURCE_ROOT.iterdir() if SOURCE_ROOT.exists() else []):
        if not show_dir.is_dir():
            continue
        show_slug = show_dir.name
        for md in sorted(show_dir.glob("20??-??-??-*.md")):
            m = DATE_RE.match(md.name)
            if not m:
                continue
            year, month, day, rest = m.groups()
            raw = md.read_text(encoding="utf-8")
            clean = sanitize_markdown(raw)
            title = readable_title_from_markdown(clean, rest)
            base = Path(rest)
            md_rel = Path("summaries") / year / month / day / show_slug / f"{base.name}.md"
            html_rel = Path("summaries") / year / month / day / show_slug / f"{base.name}.html"
            episodes.append(Episode(
                date=f"{year}-{month}-{day}", year=year, month=month, day=day,
                show_slug=show_slug, show_name=slug_to_title(show_slug), title=title,
                source_path=md, md_rel=md_rel, html_rel=html_rel,
                excerpt=plain_excerpt(clean), model=extract_model(clean),
                duration=extract_field(clean, "오디오 길이"),
                published=extract_field(clean, "방송/발행 시각"),
            ))
            out_md = SITE_ROOT / md_rel
            out_md.parent.mkdir(parents=True, exist_ok=True)
            out_md.write_text(clean, encoding="utf-8")
    return sorted(episodes, key=lambda e: (e.date, e.show_slug, e.title), reverse=True)


def render_summary(ep: Episode) -> None:
    md_text = (SITE_ROOT / ep.md_rel).read_text(encoding="utf-8")
    content = markdown.markdown(md_text, extensions=["extra", "toc", "tables", "sane_lists"])
    body = f"""
  <main class=\"container article-shell\">
    <div class=\"crumbs\"><a href=\"\">Home</a><span>/</span><a href=\"summaries/{ep.year}/{ep.month}/{ep.day}/\">{ep.date}</a><span>/</span><span>{html.escape(ep.show_name)}</span></div>
    <article class=\"article-card\">
      <div class=\"article-meta\">
        <span class=\"pill\">{html.escape(ep.show_name)}</span>
        <span>{html.escape(ep.date)} KST</span>
        {f'<span>{html.escape(ep.duration)}</span>' if ep.duration else ''}
      </div>
      <div class=\"markdown-body\">{content}</div>
      <div class=\"article-actions\">
        <a class=\"button ghost\" href=\"{rel_href(ep.md_rel)}\">Markdown 원문</a>
        <a class=\"button ghost\" href=\"summaries/{ep.year}/{ep.month}/{ep.day}/\">이 날짜 전체 보기</a>
      </div>
    </article>
  </main>
"""
    (SITE_ROOT / ep.html_rel).write_text(page(ep.title, body, ep.excerpt), encoding="utf-8")


def card(ep: Episode) -> str:
    meta = " · ".join(x for x in [ep.show_name, ep.duration, ep.model] if x)
    return f"""
      <a class=\"episode-card\" href=\"{rel_href(ep.html_rel)}\" data-show=\"{html.escape(ep.show_slug)}\" data-title=\"{html.escape(ep.title)}\">
        <div class=\"card-topline\"><span class=\"dot\"></span><span>{html.escape(meta)}</span></div>
        <h3>{html.escape(ep.title)}</h3>
        <p>{html.escape(ep.excerpt)}</p>
      </a>"""


def render_date(date: str, episodes: list[Episode]) -> None:
    year, month, day = date.split("-")
    by_show: dict[str, list[Episode]] = {}
    for ep in episodes:
        by_show.setdefault(ep.show_name, []).append(ep)
    sections = []
    for show, eps in sorted(by_show.items()):
        sections.append(f"<section class=\"show-section\"><h2>{html.escape(show)}</h2><div class=\"episode-grid\">{''.join(card(e) for e in eps)}</div></section>")
    body = f"""
  <main class=\"container\">
    <section class=\"date-hero\">
      <div class=\"eyebrow\">Daily Brief</div>
      <h1>{date} 요약</h1>
      <p>{len(episodes)}개 에피소드의 전사 기반 경제·시장 브리핑입니다.</p>
      <a class=\"button primary\" href=\"\">전체 인덱스</a>
    </section>
    {''.join(sections)}
  </main>
"""
    out = SITE_ROOT / "summaries" / year / month / day / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(f"{date} Podcast Briefs", body), encoding="utf-8")
    readme = [f"# {date} 요약", ""]
    for ep in episodes:
        readme.append(f"- [{ep.show_name} — {ep.title}]({ep.show_slug}/{ep.html_rel.name})")
    (out.parent / "README.md").write_text("\n".join(readme) + "\n", encoding="utf-8")


def render_archive(episodes: list[Episode]) -> None:
    dates = sorted({e.date for e in episodes}, reverse=True)
    items = []
    for d in dates:
        count = sum(1 for e in episodes if e.date == d)
        y, m, day = d.split("-")
        items.append(f"<a class=\"archive-row\" href=\"summaries/{y}/{m}/{day}/\"><span>{d}</span><strong>{count} episodes</strong></a>")
    body = f"""
  <main class=\"container\">
    <section class=\"date-hero\">
      <div class=\"eyebrow\">Archive</div>
      <h1>날짜별 아카이브</h1>
      <p>KST 기준으로 정리한 모든 요약입니다.</p>
    </section>
    <section class=\"archive-list\">{''.join(items)}</section>
  </main>
"""
    out = SITE_ROOT / "archive" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page("Archive · Podcast Briefs", body), encoding="utf-8")


def render_home(episodes: list[Episode]) -> None:
    latest_date = max(e.date for e in episodes) if episodes else datetime.now(KST).date().isoformat()
    latest = [e for e in episodes if e.date == latest_date]
    dates = sorted({e.date for e in episodes}, reverse=True)
    date_links = "".join(
        f'<a class="date-chip" href="summaries/{d[:4]}/{d[5:7]}/{d[8:10]}/">{d}<span>{sum(1 for e in episodes if e.date == d)}</span></a>'
        for d in dates[:12]
    )
    shows = sorted({(e.show_slug, e.show_name) for e in episodes}, key=lambda x: x[1])
    show_filters = ''.join(f'<button data-filter="{html.escape(slug)}">{html.escape(name)}</button>' for slug, name in shows)
    body = f"""
  <main>
    <section class=\"hero container\">
      <div class=\"eyebrow\">Korean Market Podcasts · KST Daily Archive</div>
      <h1>하루치 경제 팟캐스트를 한눈에.</h1>
      <p>전사 기반 요약을 날짜별로 정리합니다. Slack 첨부 대신 GitHub Pages에서 빠르게 탐색하고 검색하세요.</p>
      <div class=\"hero-actions\">
        <a class=\"button primary\" href=\"summaries/{latest_date[:4]}/{latest_date[5:7]}/{latest_date[8:10]}/\">오늘자 보기</a>
        <a class=\"button ghost\" href=\"archive/\">아카이브</a>
      </div>
      <div class=\"stats\">
        <div><strong>{len(episodes)}</strong><span>summaries</span></div>
        <div><strong>{len(dates)}</strong><span>dates</span></div>
        <div><strong>{len(shows)}</strong><span>shows</span></div>
      </div>
    </section>
    <section class=\"container control-panel\">
      <input id=\"search\" type=\"search\" placeholder=\"제목/본문 키워드 검색\" />
      <div class=\"filters\"><button data-filter=\"all\" class=\"active\">전체</button>{show_filters}</div>
    </section>
    <section class=\"container\">
      <div class=\"section-heading\"><div><span class=\"eyebrow\">Latest</span><h2>{latest_date} 요약</h2></div><a href=\"summaries/{latest_date[:4]}/{latest_date[5:7]}/{latest_date[8:10]}/\">날짜 페이지</a></div>
      <div id=\"episodes\" class=\"episode-grid\">{''.join(card(e) for e in latest)}</div>
    </section>
    <section class=\"container dates-strip\">
      <div class=\"section-heading\"><div><span class=\"eyebrow\">Dates</span><h2>최근 날짜</h2></div><a href=\"archive/\">전체 보기</a></div>
      <div class=\"date-chip-grid\">{date_links}</div>
    </section>
  </main>
  <script src=\"assets/app.js\"></script>
"""
    (SITE_ROOT / "index.html").write_text(page("Podcast Briefs", body), encoding="utf-8")


def write_assets() -> None:
    assets = SITE_ROOT / "assets"
    assets.mkdir(exist_ok=True)
    (assets / "style.css").write_text(CSS, encoding="utf-8")
    (assets / "app.js").write_text(JS, encoding="utf-8")
    (SITE_ROOT / ".nojekyll").write_text("", encoding="utf-8")
    (SITE_ROOT / ".gitignore").write_text(".DS_Store\n*.tmp\n*.log\n__pycache__/\n", encoding="utf-8")


def write_readme(episodes: list[Episode]) -> None:
    latest = max((e.date for e in episodes), default="")
    text = f"""# Podcast Briefs

Public GitHub Pages archive for Korean economic podcast summaries.

- Dates are based on Asia/Seoul time.
- Summary pages are generated from full-audio transcripts.
- Local audio/transcript file paths are removed from the public copy.

## Latest

- [{latest} summaries](summaries/{latest[:4]}/{latest[5:7]}/{latest[8:10]}/) ({sum(1 for e in episodes if e.date == latest)} episodes)

## Structure

```text
summaries/YYYY/MM/DD/<show-slug>/*.html
summaries/YYYY/MM/DD/<show-slug>/*.md
```

Generated by `build_site.py` from local sanitized summary Markdown files.
"""
    (SITE_ROOT / "README.md").write_text(text, encoding="utf-8")

CSS = r'''
:root{--bg:#08090a;--panel:#0f1011;--surface:rgba(255,255,255,.035);--surface2:rgba(255,255,255,.055);--text:#f7f8f8;--muted:#8a8f98;--soft:#d0d6e0;--line:rgba(255,255,255,.08);--line2:rgba(255,255,255,.05);--accent:#7170ff;--accent2:#5e6ad2;--green:#10b981;--max:1160px}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(circle at 50% -10%,rgba(113,112,255,.16),transparent 36rem),var(--bg);color:var(--text);font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;font-feature-settings:"cv01","ss03";letter-spacing:-.011em}.bg-orb{position:fixed;pointer-events:none;filter:blur(70px);opacity:.26;z-index:-1}.orb-a{width:420px;height:420px;background:#5e6ad2;right:-180px;top:80px}.orb-b{width:360px;height:360px;background:#10b981;left:-190px;bottom:10vh;opacity:.1}.container{width:min(var(--max),calc(100% - 40px));margin:0 auto}.site-header{position:sticky;top:0;z-index:10;display:flex;align-items:center;justify-content:space-between;padding:16px max(20px,calc((100vw - var(--max))/2));background:rgba(8,9,10,.72);backdrop-filter:blur(18px);border-bottom:1px solid var(--line2)}.brand{display:flex;align-items:center;gap:10px;color:var(--text);font-weight:510;text-decoration:none}.brand-mark{display:grid;place-items:center;width:30px;height:30px;border:1px solid var(--line);border-radius:9px;background:var(--surface2);color:#b8bbff}nav{display:flex;gap:18px}nav a,.section-heading a,.crumbs a{color:var(--soft);text-decoration:none;font-size:14px;font-weight:510}nav a:hover,.section-heading a:hover,.crumbs a:hover{color:var(--text)}.hero{padding:110px 0 52px;text-align:center}.eyebrow{display:inline-flex;align-items:center;gap:8px;margin-bottom:16px;color:#b8bbff;font:510 12px/1.4 Inter;text-transform:uppercase;letter-spacing:.12em}.hero h1,.date-hero h1{max-width:900px;margin:0 auto;color:var(--text);font-size:clamp(44px,7vw,82px);font-weight:510;line-height:.96;letter-spacing:-.055em}.hero p,.date-hero p{max-width:720px;margin:22px auto 0;color:var(--muted);font-size:18px;line-height:1.7}.hero-actions{margin-top:34px;display:flex;justify-content:center;gap:12px;flex-wrap:wrap}.button{display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:10px 16px;border-radius:8px;text-decoration:none;font-weight:510;font-size:14px;border:1px solid var(--line)}.button.primary{background:linear-gradient(180deg,#7776ff,#5e6ad2);color:white;box-shadow:0 12px 40px rgba(94,106,210,.25)}.button.ghost{background:rgba(255,255,255,.025);color:var(--soft)}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;max-width:520px;margin:42px auto 0}.stats div{padding:16px;border:1px solid var(--line);background:var(--surface);border-radius:14px}.stats strong{display:block;font-size:28px;font-weight:510}.stats span{color:var(--muted);font-size:13px}.control-panel{display:grid;gap:14px;margin-bottom:36px;padding:16px;border:1px solid var(--line);border-radius:18px;background:rgba(255,255,255,.025)}input[type=search]{width:100%;padding:15px 16px;border:1px solid var(--line);border-radius:12px;background:#0b0c0d;color:var(--text);font:400 16px Inter;outline:none}.filters{display:flex;gap:8px;flex-wrap:wrap}.filters button{padding:8px 11px;border:1px solid var(--line);border-radius:999px;background:rgba(255,255,255,.025);color:var(--soft);cursor:pointer}.filters button.active,.filters button:hover{border-color:rgba(113,112,255,.6);color:white;background:rgba(113,112,255,.18)}.section-heading{display:flex;align-items:end;justify-content:space-between;gap:20px;margin:46px 0 18px}.section-heading h2,.show-section h2{margin:0;font-size:30px;font-weight:510;letter-spacing:-.03em}.episode-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.episode-card{display:flex;flex-direction:column;min-height:230px;padding:22px;border:1px solid var(--line);border-radius:18px;background:linear-gradient(180deg,rgba(255,255,255,.05),rgba(255,255,255,.022));text-decoration:none;color:inherit;transition:transform .18s ease,border-color .18s ease,background .18s ease}.episode-card:hover{transform:translateY(-3px);border-color:rgba(113,112,255,.48);background:linear-gradient(180deg,rgba(113,112,255,.11),rgba(255,255,255,.03))}.card-topline{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:12px;margin-bottom:14px}.dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 14px rgba(16,185,129,.7)}.episode-card h3{margin:0;color:var(--text);font-size:20px;line-height:1.35;font-weight:590;letter-spacing:-.024em}.episode-card p{margin:14px 0 0;color:var(--muted);line-height:1.65;font-size:14px}.dates-strip{padding-bottom:56px}.date-chip-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.date-chip,.archive-row{display:flex;justify-content:space-between;align-items:center;padding:15px 16px;border:1px solid var(--line);border-radius:14px;background:var(--surface);color:var(--soft);text-decoration:none}.date-chip span{color:var(--muted)}.date-hero{padding:72px 0 28px}.show-section{margin:30px 0}.archive-list{display:grid;gap:10px;margin-bottom:70px}.article-shell{padding:42px 0 70px}.crumbs{display:flex;gap:10px;flex-wrap:wrap;color:var(--muted);font-size:14px;margin-bottom:18px}.article-card{border:1px solid var(--line);border-radius:22px;background:rgba(255,255,255,.03);padding:min(5vw,48px)}.article-meta{display:flex;gap:10px;flex-wrap:wrap;align-items:center;color:var(--muted);font-size:13px;margin-bottom:28px}.pill{border:1px solid rgba(113,112,255,.5);background:rgba(113,112,255,.16);color:#dedefe;border-radius:999px;padding:6px 10px}.markdown-body{color:#d9dee7;font-size:16px;line-height:1.75}.markdown-body h1{font-size:clamp(30px,4.8vw,52px);line-height:1.05;letter-spacing:-.05em;color:var(--text);margin:0 0 26px}.markdown-body h2{margin-top:44px;padding-top:20px;border-top:1px solid var(--line2);font-size:25px;color:var(--text);letter-spacing:-.025em}.markdown-body h3{margin-top:28px;color:#f1f3f4}.markdown-body a{color:#a8adff}.markdown-body blockquote{margin:22px 0;padding:18px 20px;border-left:3px solid var(--accent);background:rgba(113,112,255,.08);border-radius:12px;color:var(--soft)}.markdown-body code{font-family:'JetBrains Mono',ui-monospace,monospace;background:rgba(255,255,255,.06);padding:.15em .35em;border-radius:5px}.markdown-body table{width:100%;border-collapse:collapse;margin:22px 0;display:block;overflow-x:auto}.markdown-body th,.markdown-body td{border:1px solid var(--line);padding:10px 12px;text-align:left;vertical-align:top}.markdown-body th{background:rgba(255,255,255,.055);color:var(--text)}.article-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:34px}.site-footer{display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap;padding:28px max(20px,calc((100vw - var(--max))/2));border-top:1px solid var(--line2);color:var(--muted);font-size:13px}@media (max-width:760px){.site-header{align-items:flex-start;gap:12px;flex-direction:column}.hero{padding-top:72px}.episode-grid,.date-chip-grid,.stats{grid-template-columns:1fr}.article-card{padding:24px}.section-heading{align-items:flex-start;flex-direction:column}}
'''

JS = r'''
const search = document.querySelector('#search');
const cards = [...document.querySelectorAll('.episode-card')];
const buttons = [...document.querySelectorAll('[data-filter]')];
let active = 'all';
function apply(){
  const q = (search?.value || '').toLowerCase().trim();
  for (const card of cards){
    const show = card.dataset.show;
    const text = card.textContent.toLowerCase();
    const okFilter = active === 'all' || show === active;
    const okSearch = !q || text.includes(q);
    card.style.display = okFilter && okSearch ? '' : 'none';
  }
}
buttons.forEach(btn => btn.addEventListener('click', () => {
  active = btn.dataset.filter;
  buttons.forEach(b => b.classList.toggle('active', b === btn));
  apply();
}));
search?.addEventListener('input', apply);
'''


def main() -> None:
    # Clear generated directories, keep .git and this script.
    for name in ["assets", "archive", "summaries"]:
        path = SITE_ROOT / name
        if path.exists():
            shutil.rmtree(path)
    for name in ["index.html", "README.md", ".nojekyll", ".gitignore"]:
        path = SITE_ROOT / name
        if path.exists():
            path.unlink()
    episodes = collect()
    if not episodes:
        raise SystemExit(f"No summaries found under {SOURCE_ROOT}")
    write_assets()
    for ep in episodes:
        render_summary(ep)
    for date in sorted({e.date for e in episodes}, reverse=True):
        render_date(date, [e for e in episodes if e.date == date])
    render_archive(episodes)
    render_home(episodes)
    write_readme(episodes)
    public_metadata = []
    for e in episodes:
        public_metadata.append({
            "date": e.date,
            "show_slug": e.show_slug,
            "show_name": e.show_name,
            "title": e.title,
            "md_rel": e.md_rel.as_posix(),
            "html_rel": e.html_rel.as_posix(),
            "excerpt": e.excerpt,
            "model": e.model,
            "duration": e.duration,
            "published": e.published,
        })
    (SITE_ROOT / "metadata.json").write_text(json.dumps(public_metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Built {len(episodes)} summaries across {len(set(e.date for e in episodes))} dates")

if __name__ == "__main__":
    main()
