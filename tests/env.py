import sys
import os

# append ../Lib directory to sys.path
rootdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(rootdir, "Lib"))
