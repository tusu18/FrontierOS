#!/usr/bin/env python3
"""
Unpack FrontierOS landing bundler export → static/index.html
Wire waitlist API + EmailJS (primary) for access codes.
"""
from __future__ import annotations

import base64
import gzip
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
OUT = STATIC / "index.html"
SOURCES = [
    Path("/Users/tusu18/Downloads/FrontierOS Landing (2).html"),
    ROOT / "design" / "FrontierOS-Landing-v2.html",
    Path("/Users/tusu18/Downloads/FrontierOS Landing.html"),
    ROOT / "design" / "FrontierOS-Landing.html",
]

HEAD_INJECT = """
<link rel="icon" href="assets/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="assets/favicon.svg">
<script src="config.js"></script>
<script src="ghpages-bridge.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@emailjs/browser@4/dist/email.min.js"></script>
"""

EA_FORM_IDS = (
    ('<div class="ea-field"><label>Full name</label><input type="text" required="" placeholder="Ada Lovelace">',
     '<div class="ea-field"><label>Full name</label><input type="text" id="eaName" required placeholder="Ada Lovelace">'),
    ('<div class="ea-field"><label>Research email</label><input type="email" required="" placeholder="you@lab.edu">',
     '<div class="ea-field"><label>Research email</label><input type="email" id="eaEmail" required placeholder="you@lab.edu">'),
    ('<div class="ea-field"><label>Affiliation</label><input type="text" placeholder="University / Lab / Company">',
     '<div class="ea-field"><label>Affiliation</label><input type="text" id="eaAffil" required placeholder="University / Lab / Company">'),
    ('<div class="ea-field"><label>Primary research area</label>\n            <select required="">',
     '<div class="ea-field"><label>Primary research area</label>\n            <select id="eaArea" required>'),
    ('<div class="ea-field"><label>How will you use FrontierOS?</label>\n            <select required="">',
     '<div class="ea-field"><label>How will you use FrontierOS?</label>\n            <select id="eaUse" required>'),
    ('<button type="submit" class="pill-cta pill-green ea-submit">Request access</button>',
     '<button type="submit" id="eaSubmit" class="pill-cta pill-green ea-submit">Request access</button>'),
)

EA_MODAL_SCRIPT = r"""
    /* ---- Early access modal (API + EmailJS primary) ---- */
    (function(){
      const ov = document.getElementById('eaOverlay');
      const body = document.getElementById('eaBody');
      const original = body.innerHTML;
      function open(e){ if(e) e.preventDefault(); ov.classList.add('open'); document.body.style.overflow='hidden'; }
      function close(){ ov.classList.remove('open'); document.body.style.overflow=''; setTimeout(()=>{ if(!ov.classList.contains('open')) body.innerHTML = original; bind(); }, 200); }
      function emailJsReady() {
        const ej = window.FRONTIEROS_EMAILJS || {};
        return !!(ej.publicKey && ej.serviceId && ej.templateId && typeof emailjs !== 'undefined');
      }
      function sendEmailJS(email, name, code) {
        const ej = window.FRONTIEROS_EMAILJS;
        return emailjs.send(ej.serviceId, ej.templateId, {
          to_email: email,
          user_name: name,
          access_code: code,
          reply_to: 'tsingh98@umd.edu',
        }, { publicKey: ej.publicKey }).then(() => true).catch((err) => { console.warn('[EmailJS]', err); return false; });
      }
      function showSuccess(email, data) {
        const code = (data && (data.access_code || data.demo_code)) || '';
        const sent = data && data.email_sent;
        let extra = '';
        if (!sent && code) {
          extra = '<div class="ea-code-cap">Your access code</div><div class="ea-code">'+code+'</div>'+
            '<div class="ea-fine" style="margin-top:16px;">Email could not be sent — save this code for launch day.</div>';
        } else if (sent) {
          extra = '<div class="ea-fine" style="margin-top:16px;">Check your inbox (and spam) for your access code.</div>';
        }
        body.innerHTML = '<div class="ea-success">'+
          '<div class="es-ic"><svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg></div>'+
          '<h3>You\'re registered.</h3>'+
          '<p>We '+(sent?'emailed':'saved')+' your access code for <b>'+email+'</b>. Save it for launch day.</p>'+
          extra + '</div>';
      }
      function bind(){
        const form = document.getElementById('eaForm');
        if(!form) return;
        form.addEventListener('submit', async (e)=>{
          e.preventDefault();
          const name = (document.getElementById('eaName')||{}).value.trim();
          const email = (document.getElementById('eaEmail')||{}).value.trim();
          const affil = (document.getElementById('eaAffil')||{}).value.trim();
          const area = (document.getElementById('eaArea')||{}).value;
          const use = (document.getElementById('eaUse')||{}).value;
          if(!name||!email||!affil||!area||!use){ alert('Please fill in all fields.'); return; }
          if(!/^[^@]+@[^@]+\.[^@]+$/.test(email)){ alert('Please enter a valid email address.'); return; }
          const btn = document.getElementById('eaSubmit');
          const btnLabel = btn ? btn.textContent : 'Request access';
          if(btn){ btn.disabled = true; btn.textContent = 'Sending…'; }
          try {
            const res = await fetch(frontierApi('/api/waitlist'), {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ name, email, affiliation: affil, research_area: area, use_case: use }),
            });
            const d = await res.json();
            if (!res.ok) throw new Error((d && d.detail) || 'Signup failed');
            const code = d.access_code || d.demo_code;
            if (code && emailJsReady()) {
              d.email_sent = await sendEmailJS(email, name, code);
            }
            showSuccess(email, d);
          } catch (err) {
            alert(err.message || 'Could not reach the API. Check FRONTIEROS_API in config.js.');
            if(btn){ btn.disabled = false; btn.textContent = btnLabel; }
          }
        });
      }
      document.querySelectorAll('[data-ea]').forEach(el=>el.addEventListener('click', open));
      document.getElementById('eaClose').addEventListener('click', close);
      ov.addEventListener('click', (e)=>{ if(e.target===ov) close(); });
      document.addEventListener('keydown', (e)=>{ if(e.key==='Escape' && ov.classList.contains('open')) close(); });
      bind();
    })();
"""


def unpack_bundled(html: str) -> str:
    m = re.search(r'<script type="__bundler/manifest">(.*?)</script>', html, re.S)
    m2 = re.search(r'<script type="__bundler/template">(.*?)</script>', html, re.S)
    if not m or not m2:
        if "<!DOCTYPE html>" in html[:200] or "<html" in html[:300]:
            return html
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


def resolve_src() -> Path:
    for p in SOURCES:
        if p.exists():
            return p
    raise SystemExit("Missing landing source — place export at Downloads/FrontierOS Landing (2).html")


def inject_head(page: str) -> str:
    if "config.js" in page:
        return page
    return page.replace("</head>", HEAD_INJECT + "\n</head>", 1)


def inject_form_ids(page: str) -> str:
    for old, new in EA_FORM_IDS:
        page = page.replace(old, new)
    return page


def replace_ea_modal_script(page: str) -> str:
    pattern = re.compile(
        r"/\* ---- Early access modal ---- \*/\s*\(function\(\)\{.*?\}\)\(\);",
        re.S,
    )
    if not pattern.search(page):
        raise RuntimeError("Early access modal block not found in landing HTML")
    return pattern.sub(EA_MODAL_SCRIPT.strip(), page, count=1)


def main() -> None:
    src = resolve_src()
    print("Unpacking", src, "…")
    page = unpack_bundled(src.read_text(encoding="utf-8"))
    page = inject_head(page)
    page = inject_form_ids(page)
    page = replace_ea_modal_script(page)

    if OUT.exists():
        backup = STATIC / "index.html.prev"
        backup.write_text(OUT.read_text(encoding="utf-8"), encoding="utf-8")
        print("Backed up previous landing to", backup.name)

    OUT.write_text(page, encoding="utf-8")
    print(f"Wrote {OUT} ({len(page):,} bytes)")


if __name__ == "__main__":
    main()
