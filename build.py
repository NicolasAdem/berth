#!/usr/bin/env python3
"""Assemble index.html from src/ + data/seed.json. No dependencies.

    python3 build.py            # writes index.html
"""
import pathlib
ROOT = pathlib.Path(__file__).parent
SRC = ROOT / "src"
ORDER = ["js", "chart", "views", "audit", "boot"]   # script order matters

head = (SRC / "head.html").read_text()
body = (SRC / "body.html").read_text()
seed = (ROOT / "data" / "seed.json").read_text()
scripts = "\n".join((SRC / f"{n}.html").read_text() for n in ORDER)

html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<style>:root{{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}[hidden]{{display:none!important}}img{{max-width:100%}}</style>
{head}
</head>
<body>
{body}
<script id="seed" type="application/json">{seed}</script>
{scripts}
</body>
</html>
"""
(ROOT / "index.html").write_text(html)
print(f"wrote index.html ({len(html)//1024} KB)")

# The Claude Artifact host supplies its own <!doctype>/<head>/<body> wrapper,
# so that build is the same page without one. Keeping both from one source
# means the hosted demo and the GitHub Pages site can never drift.
artifact = f"{head}\n{body}\n<script id=\"seed\" type=\"application/json\">{seed}</script>\n{scripts}"
(ROOT / "dist-artifact.html").write_text(artifact)
print(f"wrote dist-artifact.html ({len(artifact)//1024} KB)")
