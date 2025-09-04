import os
import sys

# ensure 'src' is on sys.path so 'recon.*' imports resolve
ROOT = os.path.dirname(__file__)
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from recon.cli import main

if __name__ == "__main__":
    main()

