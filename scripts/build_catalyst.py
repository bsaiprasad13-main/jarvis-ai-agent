"""Build the Catalyst Job function folder (functions/jarvis_agent) from the source.

    python scripts/build_catalyst.py
    catalyst deploy --only functions:jarvis_agent

Copies the jarvis_agent package, run.py and jarvis.config.json next to main.py, and bundles the
libraries as Linux / Python 3.12 wheels (what Catalyst runs), so the deploy never depends on the
local Python version. Only main.py, catalyst-config.json and requirements.txt are kept in git.
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FN = os.path.join(ROOT, "functions", "jarvis_agent")
KEEP = {"main.py", "catalyst-config.json", "requirements.txt", "catalyst-inputs.json"}
LIBS = ["requests~=2.34.2", "Jinja2==3.1.6", "python-dotenv==1.2.3", "zcatalyst-sdk==1.4.0"]

for name in os.listdir(FN):                                   # clean the previous build
    if name not in KEEP:
        p = os.path.join(FN, name)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)

shutil.copytree(os.path.join(ROOT, "jarvis_agent"), os.path.join(FN, "jarvis_agent"),
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
for f in ("run.py", "jarvis.config.json"):
    shutil.copy2(os.path.join(ROOT, f), FN)

subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--target", FN,
                "--platform", "manylinux2014_x86_64", "--python-version", "3.12", "--implementation", "cp",
                "--only-binary=:all:", *LIBS], check=True)
with open(os.path.join(FN, "requirements.txt"), "w") as f:      # libraries are bundled; nothing to install
    f.write("")
print("built", FN)
