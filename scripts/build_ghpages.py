#!/usr/bin/env python3
"""Build docs/ for GitHub Pages (landing only + access modal)."""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
DOCS = ROOT / "docs"
CONFIG_EXAMPLE = DOCS / "config.example.js"
STATIC_CONFIG = STATIC / "config.js"


def _patch_config(text: str, api: str, app: str, ej_pub: str, ej_svc: str, ej_tpl: str) -> str:
    if api:
        text = re.sub(
            r"window\.FRONTIEROS_API\s*=\s*[^;]+;",
            f"window.FRONTIEROS_API = '{api}';",
            text,
            count=1,
        )
        text = re.sub(
            r"window\.FRONTIEROS_APP\s*=\s*[^;]+;",
            f"window.FRONTIEROS_APP = '{app}';",
            text,
            count=1,
        )
    if ej_pub:
        block = (
            "window.FRONTIEROS_EMAILJS = {\n"
            f"  publicKey: '{ej_pub}',\n"
            f"  serviceId: '{ej_svc}',\n"
            f"  templateId: '{ej_tpl}',\n"
            "};"
        )
        text = re.sub(
            r"window\.FRONTIEROS_EMAILJS\s*=\s*[\s\S]*?};",
            block,
            text,
            count=1,
        )
    return text


def main() -> None:
    DOCS.mkdir(exist_ok=True)

    for name in ("index.html", "config.js", "ghpages-bridge.js"):
        src = STATIC / name
        if not src.exists():
            raise SystemExit(f"Missing {src}")
        shutil.copy2(src, DOCS / name)

    assets_src = STATIC / "assets"
    if assets_src.is_dir():
        assets_dst = DOCS / "assets"
        if assets_dst.exists():
            shutil.rmtree(assets_dst)
        shutil.copytree(assets_src, assets_dst)

    api = os.getenv("FRONTIEROS_API", "").strip().rstrip("/")
    app = os.getenv("FRONTIEROS_APP", "").strip().rstrip("/") or (f"{api}/app" if api else "")
    ej_pub = os.getenv("FRONTIEROS_EMAILJS_PUBLIC_KEY", "").strip()
    ej_svc = os.getenv("FRONTIEROS_EMAILJS_SERVICE_ID", "").strip()
    ej_tpl = os.getenv("FRONTIEROS_EMAILJS_TEMPLATE_ID", "").strip()

    base_config = STATIC_CONFIG.read_text(encoding="utf-8") if STATIC_CONFIG.exists() else ""
    CONFIG_EXAMPLE.write_text(
        _patch_config(
            base_config
            or "// Copy to config.js\nwindow.FRONTIEROS_API = '';\nwindow.FRONTIEROS_APP = '';\n"
            "window.FRONTIEROS_EMAILJS = { publicKey: '', serviceId: '', templateId: '' };\n",
            api or "https://YOUR-API.example.com",
            app or "https://YOUR-API.example.com/app",
            "",
            "",
            "",
        ),
        encoding="utf-8",
    )

    config_path = DOCS / "config.js"
    if STATIC_CONFIG.exists():
        config_text = STATIC_CONFIG.read_text(encoding="utf-8")
    else:
        config_text = CONFIG_EXAMPLE.read_text(encoding="utf-8")
    config_path.write_text(
        _patch_config(config_text, api, app, ej_pub, ej_svc, ej_tpl),
        encoding="utf-8",
    )

    (DOCS / ".nojekyll").touch(exist_ok=True)

    html = (DOCS / "index.html").read_text(encoding="utf-8")
    inject = (
        '<script src="config.js"></script>\n'
        '<script src="ghpages-bridge.js"></script>'
    )
    if "ghpages-bridge.js" not in html:
        html = html.replace("</head>", inject + "\n</head>", 1)
        (DOCS / "index.html").write_text(html, encoding="utf-8")

    print(f"Built GitHub Pages site in {DOCS} ({len(list(DOCS.iterdir()))} files)")


if __name__ == "__main__":
    main()
