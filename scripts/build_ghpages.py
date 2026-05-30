#!/usr/bin/env python3
"""Build docs/ for GitHub Pages (landing only + access modal)."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
DOCS = ROOT / "docs"
CONFIG_EXAMPLE = DOCS / "config.example.js"


def main() -> None:
    DOCS.mkdir(exist_ok=True)

    for name in ("index.html", "config.js", "ghpages-bridge.js"):
        src = STATIC / name
        if not src.exists():
            raise SystemExit(f"Missing {src}")
        shutil.copy2(src, DOCS / name)

    api = os.getenv("FRONTIEROS_API", "").strip().rstrip("/")
    app = os.getenv("FRONTIEROS_APP", "").strip().rstrip("/") or (f"{api}/app" if api else "")

    CONFIG_EXAMPLE.write_text(
        f"""// Copy to config.js and set your deployed FastAPI backend.
window.FRONTIEROS_API = '{api or "https://YOUR-API.example.com"}';
window.FRONTIEROS_APP = '{app or "https://YOUR-API.example.com/app"}';
""",
        encoding="utf-8",
    )

    config_path = DOCS / "config.js"
    if api:
        config_path.write_text(
            f"window.FRONTIEROS_API = '{api}';\n"
            f"window.FRONTIEROS_APP = '{app}';\n",
            encoding="utf-8",
        )
    elif not config_path.exists():
        shutil.copy2(CONFIG_EXAMPLE, config_path)

    (DOCS / ".nojekyll").touch(exist_ok=True)

    # Inject bridge scripts if not already present
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
