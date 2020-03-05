import enum
from typing import Dict, List, Optional, Tuple, Union
from fontTools.ttLib.tables import C_O_L_R_
from fontTools.ttLib.tables import C_P_A_L_
from fontTools.ttLib.tables import _n_a_m_e
from fontTools.ttLib.tables import otTables as ot
from fontTools.ttLib.tables.otTables import ExtendMode, VariableValue
from .errors import ColorLibError


def populateCOLRv0(table, colorGlyphsV0, glyphMap=None):
    colorGlyphItems = colorGlyphsV0.items()
    if glyphMap:
        colorGlyphItems = sorted(colorGlyphItems, key=lambda item: glyphMap[item[0]])
    baseGlyphRecords = []
    layerRecords = []
    for baseGlyph, layers in colorGlyphItems:
        baseRec = ot.BaseGlyphRecord()
        baseRec.BaseGlyph = baseGlyph
        baseRec.FirstLayerIndex = len(layerRecords)
        baseRec.NumLayers = len(layers)
        baseGlyphRecords.append(baseRec)

        for layerGlyph, paletteIndex in layers:
            layerRec = ot.LayerRecord()
            layerRec.LayerGlyph = layerGlyph
            layerRec.PaletteIndex = paletteIndex
            layerRecords.append(layerRec)

    table.BaseGlyphRecordCount = len(baseGlyphRecords)
    table.BaseGlyphRecordArray = ot.BaseGlyphRecordArray()
    table.BaseGlyphRecordArray.BaseGlyphRecord = baseGlyphRecords
    table.LayerRecordArray = ot.LayerRecordArray()
    table.LayerRecordArray.LayerRecord = layerRecords
    table.LayerRecordCount = len(layerRecords)


def _splitSolidAndGradientGlyphs(colorGlyphs):
    colorGlyphsV0 = {}
    colorGlyphsV1 = {}
    for baseGlyph, layers in colorGlyphs.items():
        layersV0 = []
        allSolidColors = True
        for layerGlyph, paint in layers:
            if isinstance(paint, ot.Paint):
                if (
                    paint.Format == 1
                    and paint.Color.Transparency.value == _DEFAULT_TRANSPARENCY.value
                ):
                    paint = paint.Color.PaletteIndex
                else:
                    allSolidColors = False
                    break
            elif isinstance(paint, int):
                pass
            else:
                raise TypeError(paint)
            layersV0.append((layerGlyph, paint))
        if allSolidColors:
            colorGlyphsV0[baseGlyph] = layersV0
        else:
            colorGlyphsV1[baseGlyph] = layers

    # sanity check
    assert set(colorGlyphs) == (set(colorGlyphsV0) | set(colorGlyphsV1))

    return colorGlyphsV0, colorGlyphsV1


def buildCOLR(
    colorGlyphs: Dict[str, List[Tuple[str, Union[int, ot.Paint]]]],
    version: Optional[int] = None,
    glyphMap: Optional[Dict] = None,
    varStore: Optional[ot.VarStore] = None,
) -> C_O_L_R_.table_C_O_L_R_:
    """Build COLR table from color layers mapping.

    Args:
        colorGlyphs: : map of base glyph names to lists of (layer glyph names,
            palette indices) tuples.

    Return:
        A new COLRv0 table.
    """
    self = C_O_L_R_.table_C_O_L_R_()

    if varStore is not None and version == 0:
        raise ValueError("Can't add VarStore to COLRv0")

    if version in (None, 0) and not varStore:
        # split color glyphs into v0 and v1 and encode separately
        colorGlyphsV0, colorGlyphsV1 = _splitSolidAndGradientGlyphs(colorGlyphs)
        if version == 0 and colorGlyphsV1:
            # TODO Derive "average" solid color from gradients?
            raise ValueError("Can't encode gradients in COLRv0")
    else:
        # unless explicitly requested for v1 or have variations, in which case
        # we encode all color glyph as v1
        colorGlyphsV0, colorGlyphsV1 = None, colorGlyphs

    colr = ot.COLR()

    if colorGlyphsV0:
        populateCOLRv0(colr, colorGlyphsV0, glyphMap)
    else:
        colr.BaseGlyphRecordCount = colr.LayerRecordCount = 0
        colr.BaseGlyphRecordArray = colr.LayerRecordArray = None

    if colorGlyphsV1:
        colr.BaseGlyphV1Array = buildBaseGlyphV1Array(colorGlyphsV1, glyphMap)

    if varStore:
        colr.VarStore = varStore

    if version is None:
        version = 1 if (varStore or colorGlyphsV1) else 0
    elif version not in (0, 1):
        raise NotImplementedError(version)
    self.version = colr.Version = version

    if version == 0:
        self._fromOTTable(colr)
    else:
        self.table = colr

    return self


class ColorPaletteType(enum.IntFlag):
    USABLE_WITH_LIGHT_BACKGROUND = 0x0001
    USABLE_WITH_DARK_BACKGROUND = 0x0002

    @classmethod
    def _missing_(cls, value):
        # enforce reserved bits
        if isinstance(value, int) and (value < 0 or value & 0xFFFC != 0):
            raise ValueError(f"{value} is not a valid {cls.__name__}")
        return super()._missing_(value)


# None, 'abc' or {'en': 'abc', 'de': 'xyz'}
_OptionalLocalizedString = Union[None, str, Dict[str, str]]


def buildPaletteLabels(
    labels: List[_OptionalLocalizedString], nameTable: _n_a_m_e.table__n_a_m_e
) -> List[Optional[int]]:
    return [
        nameTable.addMultilingualName(l, mac=False)
        if isinstance(l, dict)
        else C_P_A_L_.table_C_P_A_L_.NO_NAME_ID
        if l is None
        else nameTable.addMultilingualName({"en": l}, mac=False)
        for l in labels
    ]


def buildCPAL(
    palettes: List[List[Tuple[float, float, float, float]]],
    paletteTypes: Optional[List[ColorPaletteType]] = None,
    paletteLabels: Optional[List[_OptionalLocalizedString]] = None,
    paletteEntryLabels: Optional[List[_OptionalLocalizedString]] = None,
    nameTable: Optional[_n_a_m_e.table__n_a_m_e] = None,
) -> C_P_A_L_.table_C_P_A_L_:
    """Build CPAL table from list of color palettes.

    Args:
        palettes: list of lists of colors encoded as tuples of (R, G, B, A) floats
            in the range [0..1].
        paletteTypes: optional list of ColorPaletteType, one for each palette.
        paletteLabels: optional list of palette labels. Each lable can be either:
            None (no label), a string (for for default English labels), or a
            localized string (as a dict keyed with BCP47 language codes).
        paletteEntryLabels: optional list of palette entry labels, one for each
            palette entry (see paletteLabels).
        nameTable: optional name table where to store palette and palette entry
            labels. Required if either paletteLabels or paletteEntryLabels is set.

    Return:
        A new CPAL v0 or v1 table, if custom palette types or labels are specified.
    """
    if len({len(p) for p in palettes}) != 1:
        raise ColorLibError("color palettes have different lengths")

    if (paletteLabels or paletteEntryLabels) and not nameTable:
        raise TypeError(
            "nameTable is required if palette or palette entries have labels"
        )

    cpal = C_P_A_L_.table_C_P_A_L_()
    cpal.numPaletteEntries = len(palettes[0])

    cpal.palettes = []
    for i, palette in enumerate(palettes):
        colors = []
        for j, color in enumerate(palette):
            if not isinstance(color, tuple) or len(color) != 4:
                raise ColorLibError(
                    f"In palette[{i}][{j}]: expected (R, G, B, A) tuple, got {color!r}"
                )
            if any(v > 1 or v < 0 for v in color):
                raise ColorLibError(
                    f"palette[{i}][{j}] has invalid out-of-range [0..1] color: {color!r}"
                )
            # input colors are RGBA, CPAL encodes them as BGRA
            red, green, blue, alpha = color
            colors.append(
                C_P_A_L_.Color(*(round(v * 255) for v in (blue, green, red, alpha)))
            )
        cpal.palettes.append(colors)

    if any(v is not None for v in (paletteTypes, paletteLabels, paletteEntryLabels)):
        cpal.version = 1

        if paletteTypes is not None:
            if len(paletteTypes) != len(palettes):
                raise ColorLibError(
                    f"Expected {len(palettes)} paletteTypes, got {len(paletteTypes)}"
                )
            cpal.paletteTypes = [ColorPaletteType(t).value for t in paletteTypes]
        else:
            cpal.paletteTypes = [C_P_A_L_.table_C_P_A_L_.DEFAULT_PALETTE_TYPE] * len(
                palettes
            )

        if paletteLabels is not None:
            if len(paletteLabels) != len(palettes):
                raise ColorLibError(
                    f"Expected {len(palettes)} paletteLabels, got {len(paletteLabels)}"
                )
            cpal.paletteLabels = buildPaletteLabels(paletteLabels, nameTable)
        else:
            cpal.paletteLabels = [C_P_A_L_.table_C_P_A_L_.NO_NAME_ID] * len(palettes)

        if paletteEntryLabels is not None:
            if len(paletteEntryLabels) != cpal.numPaletteEntries:
                raise ColorLibError(
                    f"Expected {cpal.numPaletteEntries} paletteEntryLabels, "
                    f"got {len(paletteEntryLabels)}"
                )
            cpal.paletteEntryLabels = buildPaletteLabels(paletteEntryLabels, nameTable)
        else:
            cpal.paletteEntryLabels = [
                C_P_A_L_.table_C_P_A_L_.NO_NAME_ID
            ] * cpal.numPaletteEntries
    else:
        cpal.version = 0

    return cpal


# COLR v1 tables
# See draft proposal at: https://github.com/googlefonts/colr-gradients-spec


_DEFAULT_TRANSPARENCY = VariableValue(1.0)


def buildColor(paletteIndex, transparency=_DEFAULT_TRANSPARENCY):
    if not isinstance(transparency, VariableValue):
        transparency = VariableValue(transparency)
    self = ot.Color()
    self.PaletteIndex = paletteIndex
    self.Transparency = transparency
    return self


def buildSolidColorPaint(paletteIndex, transparency=_DEFAULT_TRANSPARENCY):
    self = ot.Paint()
    self.Format = 1
    self.Color = buildColor(paletteIndex, transparency)
    return self


def buildColorStop(stopOffset, color):
    self = ot.ColorStop()

    if not isinstance(stopOffset, VariableValue):
        stopOffset = VariableValue(stopOffset)
    self.StopOffset = stopOffset

    if isinstance(color, int):
        color = buildColor(paletteIndex=color)
    else:
        assert isinstance(color, ot.Color)
    self.Color = color

    return self


def buildColorLine(colorStops, extend=ExtendMode.PAD):
    self = ot.ColorLine()
    self.Extend = ExtendMode(extend)
    self.StopCount = len(colorStops)
    self.ColorStop = [
        stop
        if isinstance(stop, ot.ColorStop)
        else buildColorStop(stopOffset=stop[0], color=stop[1])
        for stop in colorStops
    ]
    return self


def buildPoint(x, y):
    if not isinstance(x, VariableValue):
        x = VariableValue(x)
    if not isinstance(y, VariableValue):
        y = VariableValue(y)
    self = ot.Point()
    self.x = x
    self.y = y
    return self


def buildLinearGradientPaint(colorLine, p0, p1, p2=None):
    self = ot.Paint()
    self.Format = 2

    if isinstance(colorLine, list):
        colorLine = buildColorLine(colorStops=colorLine)
    elif not isinstance(colorLine, ot.ColorLine):
        raise TypeError(colorLine)
    self.ColorLine = colorLine

    if p2 is None:
        p2 = p1
    for i, pt in enumerate((p0, p1, p2)):
        if isinstance(pt, tuple):
            pt = buildPoint(*pt)
        elif not isinstance(pt, ot.Point):
            raise TypeError(pt)
        setattr(self, f"p{i}", pt)

    return self


def buildAffine2x2(xx, xy, yx, yy):
    self = ot.Affine2x2()
    locs = locals()
    for attr in ("xx", "xy", "yx", "yy"):
        value = locs[attr]
        if not isinstance(value, VariableValue):
            value = VariableValue(value)
        setattr(self, attr, value)
    return self


def buildRadialGradientPaint(colorLine, c0, c1, r0, r1, affine=None):
    self = ot.Paint()
    self.Format = 3

    if isinstance(colorLine, list):
        colorLine = buildColorLine(colorStops=colorLine)
    elif not isinstance(colorLine, ot.ColorLine):
        raise TypeError(colorLine)
    self.ColorLine = colorLine

    for i, pt in [(0, c0), (1, c1)]:
        if isinstance(pt, tuple):
            pt = buildPoint(*pt)
        elif not isinstance(pt, ot.Point):
            raise TypeError(pt)
        setattr(self, f"c{i}", pt)

    for i, r in [(0, r0), (1, r1)]:
        if not isinstance(r, VariableValue):
            r = VariableValue(r)
        setattr(self, f"r{i}", r)

    if affine is None:
        pass
    elif isinstance(affine, tuple):
        affine = buildAffine2x2(*affine)
    elif not isinstance(affine, ot.Affine2x2):
        raise TypeError(affine)
    self.Affine = affine

    return self


def buildLayerV1Array(layers):
    self = ot.LayerV1Array()
    self.LayerCount = len(layers)
    records = []
    for layerGlyph, paint in layers:
        rec = ot.LayerV1Record()
        rec.LayerGlyph = layerGlyph
        if isinstance(paint, int):
            paletteIndex = paint
            paint = buildSolidColorPaint(paletteIndex)
        rec.Paint = paint
        records.append(rec)
    self.LayerV1Record = records
    return self


def buildBaseGlyphV1Array(colorGlyphs, glyphMap=None):
    colorGlyphItems = colorGlyphs.items()
    if glyphMap:
        colorGlyphItems = sorted(colorGlyphItems, key=lambda item: glyphMap[item[0]])
    records = []
    for baseGlyph, layers in colorGlyphItems:
        rec = ot.BaseGlyphV1Record()
        rec.BaseGlyph = baseGlyph
        rec.LayerV1Array = buildLayerV1Array(layers)
        records.append(rec)
    self = ot.BaseGlyphV1Array()
    self.BaseGlyphCount = len(records)
    self.BaseGlyphV1Record = records
    return self
