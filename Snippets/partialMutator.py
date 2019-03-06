from __future__ import print_function, division, absolute_import
from fontTools.misc.py23 import *
from fontTools.misc.fixedTools import floatToFixedToFloat
from fontTools.varLib import _GetCoordinates, _SetCoordinates
from fontTools.varLib.models import (
    supportScalar,
    normalizeValue,
    piecewiseLinearMap,
)
from fontTools.varLib.iup import iup_delta
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import GlyphCoordinates
import os
import logging


log = logging.getLogger("fontTools.varlib.partialMutator")


def _normalizeLocation(location, axes):
    out = {}
    for tag, triple in axes.items():
        if tag not in location:
            continue
        v = location[tag]
        out[tag] = normalizeValue(v, triple)
    return out


def _partialGvarGlyph(varfont, location, glyphname):
    gvar = varfont["gvar"]
    variations = gvar.variations[glyphname]
    coordinates, _ = _GetCoordinates(varfont, glyphname)
    origCoords, endPts = None, None
    newVariations = []
    pinnedAxes = set(location.keys())
    defaultModified = False
    for var in variations:
        tupleAxes = set(var.axes.keys())
        pinnedTupleAxes = tupleAxes & pinnedAxes
        if not pinnedTupleAxes:
            # A tuple for only axes being kept is untouched
            newVariations.append(var)
            continue
        else:
            # compute influence at pinned location only for the pinned axes
            pinnedAxesSupport = {a: var.axes[a] for a in pinnedTupleAxes}
            scalar = supportScalar(location, pinnedAxesSupport)
            if not scalar:
                # no influence (default value or out of range); drop tuple
                continue
            deltas = var.coordinates
            hasUntouchedPoints = None in deltas
            if hasUntouchedPoints:
                if origCoords is None:
                    origCoords, control = _GetCoordinates(varfont, glyphname)
                    numberOfContours = control[0]
                    isComposite = numberOfContours == -1
                    if isComposite:
                        endPts = list(range(len(control[1])))
                    else:
                        endPts = control[1]
                deltas = iup_delta(deltas, origCoords, endPts)
            scaledDeltas = GlyphCoordinates(deltas) * scalar
            if tupleAxes.issubset(pinnedAxes):
                # A tuple for only axes being pinned is discarded, and
                # it's contribution is reflected into the base outlines
                coordinates += scaledDeltas
                defaultModified = True
            else:
                # A tuple for some axes being pinned has to be adjusted
                var.coordinates = scaledDeltas
                for axis in pinnedTupleAxes:
                    del var.axes[axis]
                newVariations.append(var)
    if defaultModified:
        _SetCoordinates(varfont, glyphname, coordinates)
    gvar.variations[glyphname] = newVariations


def partialGvar(varfont, location):
    log.info("Mutating glyf/gvar tables")

    gvar = varfont['gvar']
    glyf = varfont['glyf']
    # get list of glyph names in gvar sorted by component depth
    glyphnames = sorted(
        gvar.variations.keys(),
        key=lambda name: (
            glyf[name].getCompositeMaxpValues(glyf).maxComponentDepth
            if glyf[name].isComposite() else 0,
            name
        )
    )
    for glyphname in glyphnames:
        _partialGvarGlyph(varfont, location, glyphname)


def partialVariableFont(varfont, location):
    fvar = varfont['fvar']
    axes = {
        a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in fvar.axes
    }
    location = _normalizeLocation(location, axes)
    if 'avar' in varfont:
        # 'warp' the default normalization using avar
        maps = varfont['avar'].segments
        location = {
            k: piecewiseLinearMap(v, maps[k]) for k, v in location.items()
        }
    # Quantize to F2Dot14, to avoid surprise interpolations.
    location = {k: floatToFixedToFloat(v, 14) for k, v in location.items()}
    # Location is normalized now
    log.info("Normalized location: %s", location)

    if "gvar" in varfont:
        partialGvar(varfont, location)


def main(args=None):
    from fontTools import configLogger
    import argparse

    parser = argparse.ArgumentParser(
        "fonttools varLib.partialMutator",
        description="Partially instantiate a variable font"
    )
    parser.add_argument(
        "input", metavar="INPUT.ttf", help="Input variable TTF file.")
    parser.add_argument(
        "locargs", metavar="AXIS=LOC", nargs="*",
        help="List of space separated locations. A location consist in "
        "the name of a variation axis, followed by '=' and a number. E.g.: "
        " wdth=100")
    parser.add_argument(
        "-o", "--output", metavar="OUTPUT.ttf", default=None,
        help="Output instance TTF file (default: INPUT-instance.ttf).")
    logging_group = parser.add_mutually_exclusive_group(required=False)
    logging_group.add_argument(
        "-v", "--verbose", action="store_true", help="Run more verbosely.")
    logging_group.add_argument(
        "-q", "--quiet", action="store_true", help="Turn verbosity off.")
    options = parser.parse_args(args)

    varfilename = options.input
    outfile = (
        os.path.splitext(varfilename)[0] + '-partial.ttf'
        if not options.output else options.output)
    configLogger(
        level=(
            "DEBUG" if options.verbose
            else "ERROR" if options.quiet
            else "INFO"
        )
    )

    loc = {}
    for arg in options.locargs:
        try:
            tag, val = arg.split('=')
            assert len(tag) <= 4
            loc[tag.ljust(4)] = float(val)
        except (ValueError, AssertionError):
            parser.error("invalid location argument format: %r" % arg)
    log.info("Location: %s", loc)

    log.info("Loading variable font")
    varfont = TTFont(varfilename)

    partialVariableFont(varfont, loc)

    log.info("Saving partial variable font %s", outfile)
    varfont.save(outfile)


if __name__ == "__main__":
    import sys
    sys.exit(main())
