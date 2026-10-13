"""Read the clock's home menu from a screenshot.

The menu is a ring of entries around the dial; the selected one is marked by a
bright arc on the outer rim. The app draws it without accessibility text, so
the arc's angle is the only way to tell which entry is selected.
"""

from __future__ import annotations

import io
import math

from PIL import Image

CENTER = (540, 540)
RIM_RADII = (505, 512, 519)
ICON_RADIUS = 445

# Brightness depends on the display mode (dimmed, red night mode), so the arc
# is found relative to the rest of the rim: in the menu it is about 2.4 times
# brighter than the 90th percentile, on an ordinary klydo the rim is even.
ARC_SHARE = 0.85
MIN_CONTRAST = 1.8
MIN_HITS = 20
MAX_HITS = 200
MIN_CONCENTRATION = 0.9


def _brightness(image: Image.Image, radius: float, angle: float) -> int:
    x = int(CENTER[0] + radius * math.sin(angle))
    y = int(CENTER[1] - radius * math.cos(angle))
    return max(image.getpixel((x, y)))


def is_menu(image: Image.Image) -> bool:
    """Tell the home menu from a klydo: black centre disk inside a flat grey ring.

    The selection arc alone is not enough; a klydo can have a bright spot on
    the rim, and pressing Enter outside the menu toggles a favorite.
    """
    centre = sorted(
        max(image.getpixel((CENTER[0] + dx, CENTER[1] + dy)))
        for dx in range(-300, 301, 30)
        for dy in range(-300, 301, 30)
        if dx * dx + dy * dy < 330**2
    )
    if centre[len(centre) // 2] > 8:  # only the label may light up the centre
        return False
    band = sorted(
        _brightness(image, radius, math.radians(t))
        for radius in (455, 470)
        for t in range(0, 360, 2)
    )
    floor, median = band[0], band[len(band) // 2]
    # The ring is one grey (45 bright, 32 dimmed); icons only add brighter spots.
    if not (15 <= floor and median <= floor * 1.15 + 3):
        return False
    # The info key opens a ring menu of the same look with four entries
    # (one of them delete at 6 o'clock). The home menu has five, 72 degrees
    # apart: icons at 144 and 216 degrees, plain ring at 180.
    return (
        _icon_at(image, 144, floor)
        and _icon_at(image, 216, floor)
        and not _icon_at(image, 180, floor)
    )


def _icon_at(image: Image.Image, degrees: float, floor: int) -> bool:
    """Whether a menu icon sits on the icon circle at the given angle."""
    centre_x = CENTER[0] + ICON_RADIUS * math.sin(math.radians(degrees))
    centre_y = CENTER[1] - ICON_RADIUS * math.cos(math.radians(degrees))
    bright = 0
    for dx in range(-30, 31, 5):
        for dy in range(-30, 31, 5):
            if max(image.getpixel((int(centre_x + dx), int(centre_y + dy)))) > 2 * floor:
                bright += 1
    return bright >= 8


def selection_angle(png: bytes) -> float | None:
    """Return the angle (degrees clockwise from 12 o'clock) of the selection arc.

    None when the screenshot does not show the home menu.
    """
    image = Image.open(io.BytesIO(png)).convert("RGB")
    if not is_menu(image):
        return None
    samples: list[tuple[int, float]] = []
    for radius in RIM_RADII:
        for tenth in range(0, 3600, 5):
            angle = math.radians(tenth / 10)
            x = int(CENTER[0] + radius * math.sin(angle))
            y = int(CENTER[1] - radius * math.cos(angle))
            if 0 <= x < image.width and 0 <= y < image.height:
                samples.append((max(image.getpixel((x, y))), angle))
    if not samples:
        return None
    values = sorted(v for v, _ in samples)
    brightest = values[-1]
    p90 = values[int(len(values) * 0.9)]
    if brightest < MIN_CONTRAST * max(p90, 1):
        return None
    hits = [a for v, a in samples if v >= ARC_SHARE * brightest]
    if not MIN_HITS <= len(hits) <= MAX_HITS:
        return None
    sin_sum = sum(math.sin(a) for a in hits)
    cos_sum = sum(math.cos(a) for a in hits)
    if math.hypot(sin_sum, cos_sum) / len(hits) < MIN_CONCENTRATION:
        return None  # bright spots spread around the rim, not one arc
    return math.degrees(math.atan2(sin_sum, cos_sum)) % 360


def angle_distance(a: float, b: float) -> float:
    """Shortest distance between two angles in degrees."""
    d = abs(a - b) % 360
    return min(d, 360 - d)
