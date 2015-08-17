from __future__ import print_function
from fontTools.misc.py23 import *
import sys


with open_stdin('rb', 8192*2) as bytes_input:
    data = bytes_input.read()
with open_stdout('wb', 8192*2) as bytes_output:
    bytes_output.write(data)

# with reopen_stdin('r', encoding='utf-8', newline='') as unicode_input:
#     data = unicode_input.read()
# with reopen_stdout('w', encoding='utf-8', newline='') as unicode_output:
#     unicode_output.write(data)
# with reopen_stderr('w', encoding='ascii', errors='backslashreplace') as safe_stderr:
#     print(data, file=safe_stderr)
