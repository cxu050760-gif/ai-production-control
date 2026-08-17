import subprocess
import sys
import time
from pathlib import Path

if len(sys.argv) > 1 and sys.argv[1] == "parent":
    child = subprocess.Popen([sys.executable, __file__, "child"])
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(str(child.pid), encoding="utf-8")
    time.sleep(30)
else:
    time.sleep(30)
