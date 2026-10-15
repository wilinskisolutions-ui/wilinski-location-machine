"""Census boundary shapes, simplified and packed small enough to ship to a phone.

Outlines come from the Census cartographic boundary files (the `cb_` series), which are
already generalised for display and clipped to the shoreline. Each shape is simplified
further for the zoom it is drawn at, then quantised and delta-encoded:

    ring = [x0, y0, dx1, dy1, dx2, dy2, ...]   integers, degrees * q

so a coastline of small steps costs a few characters per point instead of eighteen. The
page decodes it back to GeoJSON (`decodeRing` in atlas.js); `decode_ring` here is the
reference the tests hold the two against.
"""

from __future__ import annotations

import zipfile
from collections.abc import Iterator
from pathlib import Path

import shapefile  # pyshp
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.polygon import orient


def read_shapes(zip_path: Path) -> Iterator[tuple[dict, object]]:
    """Yield (attributes, shapely geometry) for every record in a zipped shapefile."""
    with zipfile.ZipFile(zip_path) as zf:
        stem = next(n[:-4] for n in zf.namelist() if n.endswith(".shp"))
        reader = shapefile.Reader(
            shp=zf.open(stem + ".shp"), shx=zf.open(stem + ".shx"), dbf=zf.open(stem + ".dbf")
        )
        fields = [f[0] for f in reader.fields[1:]]
        for rec in reader.iterShapeRecords():
            if rec.shape.shapeType == shapefile.NULL or not rec.shape.points:
                continue
            yield dict(zip(fields, rec.record)), shape(rec.shape.__geo_interface__)


def _polygons(geom) -> list[Polygon]:
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]


def encode_ring(coords, q: int) -> list[int]:
    out: list[int] = []
    px = py = None
    for x, y in coords:
        ix, iy = round(x * q), round(y * q)
        if px is None:
            out += [ix, iy]
        elif ix == px and iy == py:
            continue  # quantisation collapsed this vertex onto the last one
        else:
            out += [ix - px, iy - py]
        px, py = ix, iy
    return out


def decode_ring(ring: list[int], q: int) -> list[tuple[float, float]]:
    pts, x, y = [], 0, 0
    for i in range(0, len(ring), 2):
        if i == 0:
            x, y = ring[0], ring[1]
        else:
            x, y = x + ring[i], y + ring[i + 1]
        pts.append((x / q, y / q))
    return pts


def encode(geom, *, tolerance: float, q: int, min_area: float = 0.0) -> list:
    """Simplify and pack. Returns polygons -> rings -> ints; [] if nothing survives.

    `min_area` (square degrees) drops slivers and specks — islets a few metres across that
    add points and no information at the zoom this layer is drawn at.
    """
    simple = geom.simplify(tolerance, preserve_topology=True) if tolerance else geom
    packed = []
    for poly in _polygons(simple):
        if poly.is_empty or poly.area < min_area:
            continue
        # d3-geo reads a counter-clockwise exterior as "everything except this shape" and
        # fills the globe. Clockwise exterior, counter-clockwise holes, always — whatever
        # winding the shapefile happened to store.
        poly = orient(poly, sign=-1.0)
        # A ring needs at least four points. An exterior that collapses takes its holes with
        # it — a surviving hole would otherwise be drawn as the shape itself.
        exterior = encode_ring(poly.exterior.coords, q)
        if len(exterior) < 8:
            continue
        holes = [encode_ring(r.coords, q) for r in poly.interiors if Polygon(r).area >= min_area]
        packed.append([exterior, *(h for h in holes if len(h) >= 8)])
    return packed
