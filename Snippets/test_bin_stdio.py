from __future__ import print_function
from fontTools.misc.py23 import *
import sys
import os
import tempfile
import filecmp
from subprocess import check_call


PYTHON = sys.executable or "python"
CURR_DIR = os.path.abspath(os.path.dirname(os.path.realpath(__file__)))
SCRIPT = os.path.join(CURR_DIR, "pipe.py")


def diff_q(first_file, second_file):
    """Simulate call to POSIX diff with -q argument"""
    if not filecmp.cmp(first_file, second_file, shallow=False):
        print("Files %s and %s differ" % (first_file, second_file),
              file=sys.stderr)
        return 1
    return 0


def main():
    if len(sys.argv) < 2:
        sys.exit(1)
    filename = sys.argv[1]
    result = 0
    try:
        with open(filename, "rb") as infile:
            with tempfile.NamedTemporaryFile(delete=False) as outfile:
                check_call([PYTHON, SCRIPT], stdin=infile, stdout=outfile)
        result = diff_q(infile.name, outfile.name)
    finally:
        try:
            if result == 0:
                os.remove(outfile.name)
        except:
            pass
    if result != 0:
        sys.exit(1)

if __name__ == '__main__':
    main()
