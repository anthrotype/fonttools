from __future__ import print_function, division, absolute_import
from fontTools.misc.py23 import *
import logging
from fontTools.misc.loggingTools import configLogger

try:
    from fontTools.version import version
except ImportError:
    # 'version.py' is missing; fonttools was not correctly installed
    version = None

log = logging.getLogger(__name__)

__all__ = ["version", "log", "configLogger"]
