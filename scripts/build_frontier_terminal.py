#!/usr/bin/env python3
"""
Unpack FrontierOS Research Terminal.html (bundler export) and refresh app styles.

Keeps static/app.html as the functional React shell; copies embedded CSS from
the export into static/styles/ when the design system block is present.
"""
from __future__ import annotations

import base64
import gzip
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
SRC = Path(__file__).resolve().parent.parent / "design" / "FrontierOS-Research-Terminal.html"
DOWNLOADS_SRC = Path("/Users/tusu18/Downloads/FrontierOS Research Terminal.html")
OUT_REFERENCE = STATIC / "terminal.reference.html"
STYLES = STATIC / "styles"


def unpack_bundled(html: str) -> str:
    m = re.search(r'<script type="__bundler/manifest">(.*?)</script>', html, re.S)
    m2 = re.search(r'<script type="__bundler/template">(.*?)</script>', html, re.S)
    if not m or not m2:
        raise RuntimeError("Not a bundler export")
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


def extract_style_blocks(page: str) -> list[str]:
    return re.findall(r"<style[^>]*>(.*?)</style>", page, re.S | re.I)


def split_design_system(css: str) -> tuple[str, str]:
    """Heuristic split: marketing vs terminal sections."""
    marker = "/* ---- terminal"
    if marker.lower() not in css.lower():
        marker = ".app {"
    idx = css.lower().find(marker.lower())
    if idx <= 0:
        return css, ""
    return css[:idx].strip(), css[idx:].strip()


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

    # Optional full reference (gitignored — large)
    OUT_REFERENCE.write_text(page, encoding="utf-8")
    print(f"Wrote reference {OUT_REFERENCE} ({len(page):,} bytes)")

    blocks = extract_style_blocks(page)
    if not blocks:
        print("No <style> blocks found; skipping style sync")
        return

    combined = "\n\n".join(blocks)
    system_part, app_part = split_design_system(combined)
    def strip_data_fonts(css: str) -> str:
        css = re.sub(
            r'@font-face\s*\{[^}]*url\("data:[^"]+"\)[^}]*\}',
            "",
            css,
            flags=re.S,
        )
        return re.sub(r"\n{3,}", "\n\n", css).strip() + "\n"

    if system_part:
        (STYLES / "system.css").write_text(strip_data_fonts(system_part), encoding="utf-8")
        print("Updated static/styles/system.css (data-URL fonts stripped)")
    if app_part:
        existing = (STYLES / "app.css").read_text(encoding="utf-8") if (STYLES / "app.css").exists() else ""
        cleaned = strip_data_fonts(app_part)
        if len(cleaned) > len(existing) * 0.5:
            (STYLES / "app.css").write_text(cleaned, encoding="utf-8")
            print("Updated static/styles/app.css (data-URL fonts stripped)")


if __name__ == "__main__":
    main()
