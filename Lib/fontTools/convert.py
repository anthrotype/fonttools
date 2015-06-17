#!/usr/bin/env python
from __future__ import print_function
import os
import sys
from fontTools.misc.py23 import *
from fontTools.ttx import makeOutputFileName, guessFileType
from fontTools.ttLib import TTFont, reorderFontTables
import argparse
from subprocess import check_call, CalledProcessError


__script__ = os.path.basename(os.path.realpath(sys.argv[0]))

INPUT_FORMATS = 'ttf|otf|woff2|woff'


def make_output_name(infile, flavor, outdir=None, overwrite=False):
    """ Rename input file based on the specified 'flavor' and, optionally
    output directory.
    If flavor is "sfnt" and the original file type is either "WOFF" or
    "WOFF2", set the new extension to ".ttf" or ".otf" based on the
    'sfntVersion' value. If the original file type either "TTF", "TTC"
    or "DFONT", ".ttf" extension is used; ".otf" if file type is "OTF".
    If 'overwrite' is False and the name clashes with an existing
    file name, an incremental "#<num>" tag will be appended like in 'ttx'.
    """
    basename, orig_ext = os.path.splitext(infile)
    fileType = guessFileType(infile)
    if flavor == 'sfnt':
        if fileType in ["WOFF", "WOFF2"]:
            # if input file is woff, use either ".ttf" or ".otf" based on
            # the actual 'sfntVersion'
            if os.path.exists(infile):
                with open(infile, "rb") as f:
                    f.seek(4)
                    sfntVersion = f.read(4)
                new_ext = '.ttf' if sfntVersion == b"\0\1\0\0" else ".otf"
            else:
                raise IOError(
                    "cannot read 'sfntVersion': file '%s' not found" % infile)
        elif fileType in ["TTF", "TTC", "DFONT"]:
            new_ext = '.ttf'  # shouldn't check sfntVersion for TTC and DFONT?
        elif fileType == 'OTF':
            new_ext = '.otf'
        else:
            # else use the original extension
            new_ext = orig_ext
    else:
        # use 'flavor' as new extension
        new_ext = "."+flavor if not flavor.startswith(".") else flavor
    return makeOutputFileName(basename, outdir, new_ext, overwrite)


def parse_options():
    parser = argparse.ArgumentParser(
         description='Convert fonts between SFNT, WOFF and WOFF2 formats')
    parser.add_argument('infiles', metavar='FILE', type=str, nargs="+",
                        help='input files')
    parser.add_argument('-f', '--flavor', dest='flavor', action='store',
                        type=str, required=True,
                        choices=['sfnt', 'woff', 'woff2'],
                        help='output font format')
    outgroup = parser.add_mutually_exclusive_group()
    outgroup.add_argument('-o', '--output-file', nargs='?', type=str,
                          dest='outfile', default=None,
                          help='output file (only works with 1 input file)')
    outgroup.add_argument('-d', '--output-dir', nargs='?', type=str,
                          dest='outdir', default=None,
                          help='output folder (will be created if not exists)')
    parser.add_argument('-y', nargs='?', type=int,
                          dest='fontNumber', default=-1,
                          help='font number from collection')
    parser.add_argument('--force', action='store_true',
                        help='overwrite existing output file(s)')
    parser.add_argument('--recursive', action='store_true',
                        help='process subfolders recursively')
    parser.add_argument('--sanitise', dest='sanitise', action='store_true',
                        default=False,
                        help='run OpenType Sanitiser on the output file')
    return parser.parse_args()


def main():
    options = parse_options()

    fontfiles = []
    for fp in options.infiles:
        fp = os.path.abspath(fp)
        if os.path.isdir(fp):
            # fontfiles.extend(ls(fp, ext=INPUT_FORMATS, recursive=options.recursive))
            print("IOError: '%s' is a directory" % fp, file=sys.stderr)
            continue
        elif os.path.isfile(fp):
            fontfiles.append(fp)
        else:
            print("IOError: file '%s' not found" % fp, file=sys.stderr)
            continue

    for infile in fontfiles:
        if options.outfile:
            if len(options.infiles) > 1:
                print("%s: error: '-o' can't be used with multiple input files"
                      % __script__, file=sys.stderr)
                sys.exit(1)
            else:
                outfile = options.outfile
        else:
            if options.outdir and not os.path.isdir(options.outdir):
                # create output directory if it does not exists already
                os.makedirs(options.outdir)

            outfile = make_output_name(infile, options.flavor, options.outdir,
                                       options.force)

        font = TTFont(infile, recalcTimestamp=False, recalcBBoxes=False,
                      fontNumber=options.fontNumber)

        if options.flavor in ['woff', 'woff2']:
            font.flavor = options.flavor
        else:
            font.flavor = None

        # save converted font to temporary buffer
        tmp = StringIO()
        font.save(tmp, reorderTables=False)

        # reorder tables according to input font's table order
        tableOrder = sorted(font.reader.keys(),
                            key=lambda x: font.reader.tables[x].offset)
        tmp.seek(0)
        with open(outfile, "wb") as fd:
            reorderFontTables(tmp, fd, tableOrder)

        if options.sanitise:
            # overwrite outfile with OTS output
            try:
                check_call(['ot-sanitise', outfile, outfile])
            except OSError as e:
                if e.errno == 2:
                    print("'ot-sanitise' not found: failed to sanitise font",
                          file=sys.stderr)
                else:
                    raise
            except CalledProcessError:
                # OTS should print any errors to stderr by itself
                pass


if __name__ == '__main__':
    main()
