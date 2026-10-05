"""Nimby3D: double-click to open the manager of the nimby3d add-on (manager/app.py) with pythonw."""
import runpy
import sys
from pathlib import Path

app = Path(__file__).resolve().with_name("manager") / "app.py"
sys.argv[0] = str(app)
runpy.run_path(str(app), run_name="__main__")
