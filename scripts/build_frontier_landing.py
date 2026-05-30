#!/usr/bin/env python3
"""
Build static/index.html from FrontierOS Landing.html export (exact design)
and inject signup form + API wiring from index.html.bak.
"""
from __future__ import annotations

import base64
import gzip
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
SRC = Path(__file__).resolve().parent.parent / "design" / "FrontierOS-Landing.html"
DOWNLOADS_SRC = Path("/Users/tusu18/Downloads/FrontierOS Landing.html")
BAK = STATIC / "index.html.bak"
OUT = STATIC / "index.html"


def unpack_bundled(html: str) -> str:
    m = re.search(r'<script type="__bundler/manifest">(.*?)</script>', html, re.S)
    m2 = re.search(r'<script type="__bundler/template">(.*?)</script>', html, re.S)
    if not m or not m2:
        raise RuntimeError("Not a bundler export — missing manifest/template")
    manifest = json.loads(m.group(1))
    template = json.loads(m2.group(1))
    for uuid, entry in manifest.items():
        raw = base64.b64decode(entry["data"])
        if entry.get("compressed"):
            raw = gzip.decompress(raw)
        mime = entry.get("mime", "application/octet-stream")
        data_url = f"data:{mime};base64,{base64.b64encode(raw).decode()}"
        template = template.replace(uuid, data_url)
    return template


def extract_block(text: str, start_marker: str, end_marker: str) -> str:
    i = text.find(start_marker)
    if i < 0:
        return ""
    j = text.find(end_marker, i)
    if j < 0:
        return ""
    return text[i:j]


def resolve_src() -> Path:
    if SRC.exists():
        return SRC
    if DOWNLOADS_SRC.exists():
        return DOWNLOADS_SRC
    raise SystemExit(f"Missing source: {SRC} or {DOWNLOADS_SRC}")


def main():
    src = resolve_src()

    print("Unpacking", src.name, "…")
    page = unpack_bundled(src.read_text(encoding="utf-8"))

    # Production links (keep exact layout)
    page = page.replace('href="app.html"', 'href="/app?signin=1"')
    page = page.replace("href='app.html'", "href='/app?signin=1'")
    page = page.replace('href="/app?signin=1">Launch dashboard', 'href="#signup">Get access code')
    page = page.replace('href="/app?signin=1">Launch dashboard →', 'href="#signup">Get access code →')

    # Nav: add Sign up
    page = page.replace(
        '<a href="#use">Use cases</a>',
        '<a href="#signup">Sign up</a>\n        <a href="#use">Use cases</a>',
        1,
    )

    # Hero primary CTA → signup
    page = page.replace(
        '<a class="pill-cta pill-green" href="/app?signin=1">Launch dashboard →</a>',
        '<a class="pill-cta pill-green" href="#signup">Get your access code →</a>',
        1,
    )

    # Signup section + script from previous landing (if backup exists)
    if BAK.exists():
        bak = BAK.read_text(encoding="utf-8")
        signup_section = extract_block(
            bak,
            '<!-- Sign up',
            '<!-- Use cases -->',
        ) or extract_block(bak, '<section class="wrap reveal" id="signup"', '<!-- Use cases -->')
        signup_script = ""
        if "// Demo request form" in bak or "// Signup" in bak:
            si = bak.find("// Demo request form")
            if si < 0:
                si = bak.find("const demoForm")
            ei = bak.rfind("</script>")
            if si > 0 and ei > si:
                signup_script = f"\n  <script>\n{bak[si:ei].strip()}\n  </script>\n"

        if signup_section.strip():
            marker = '  <section class="usecases wrap" id="use">'
            if marker in page:
                page = page.replace(marker, signup_section + "\n\n" + marker, 1)
                print("Injected signup section")
        if signup_script and signup_script not in page:
            page = page.replace("</body>", signup_script + "</body>", 1)
            print("Injected signup script")

    if OUT.exists():
        (STATIC / "index.export.html").write_text(OUT.read_text(encoding="utf-8"), encoding="utf-8")

    OUT.write_text(page, encoding="utf-8")
    print(f"Wrote {OUT} ({len(page):,} bytes)")


if __name__ == "__main__":
    main()
