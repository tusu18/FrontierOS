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
    ej_pub = os.getenv("FRONTIEROS_EMAILJS_PUBLIC_KEY", "").strip()
    ej_svc = os.getenv("FRONTIEROS_EMAILJS_SERVICE_ID", "").strip()
    ej_tpl = os.getenv("FRONTIEROS_EMAILJS_TEMPLATE_ID", "").strip()

    CONFIG_EXAMPLE.write_text(
        f"""// Copy to config.js and set your deployed FastAPI backend.
window.FRONTIEROS_API = '{api or "https://YOUR-API.example.com"}';
window.FRONTIEROS_APP = '{app or "https://YOUR-API.example.com/app"}';
window.FRONTIEROS_EMAILJS = {{ publicKey: '', serviceId: '', templateId: '' }};
""",
        encoding="utf-8",
    )

    config_path = DOCS / "config.js"
    if api or ej_pub:
        lines = []
        if api:
            lines.append(f"window.FRONTIEROS_API = '{api}';")
            lines.append(f"window.FRONTIEROS_APP = '{app}';")
        ej_block = (
            f"window.FRONTIEROS_EMAILJS = {{ publicKey: '{ej_pub}', "
            f"serviceId: '{ej_svc}', templateId: '{ej_tpl}' }};"
        )
        if ej_pub:
            lines.append(ej_block)
        elif config_path.exists():
            existing = config_path.read_text(encoding="utf-8")
            if "FRONTIEROS_EMAILJS" in existing:
                for line in existing.splitlines():
                    if "FRONTIEROS_EMAILJS" in line:
                        lines.append(line)
        config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
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
