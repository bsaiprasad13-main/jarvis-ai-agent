"""Build the showcase page from a run file.

    python showcase/build.py              # uses showcase/run.json
Writes showcase/index.html (a self-contained page: the run data is embedded).
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(HERE, "run.json"), encoding="utf-8") as f:
    run = json.load(f)
with open(os.path.join(HERE, "page.html"), encoding="utf-8") as f:
    page = f.read()

data = json.dumps(run, ensure_ascii=False).replace("</", "<\\/")   # safe inside <script>
with open(os.path.join(HERE, "index.html"), "w", encoding="utf-8") as f:
    f.write(page.replace("/*RUN_JSON*/", data))
print("wrote showcase/index.html")
