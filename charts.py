# chart shapes shared by the status page and the dashboard's server stats. charts are
# svg polygons drawn in a fixed viewBox, which the page then stretches to fit its card

PADDING = 4


def scale(
    values: list[float],
    lo: float,
    hi: float,
    height: float,
) -> list[float]:
    # flat data sits in the middle instead of hiding under the card border
    if hi == lo:
        return [height / 2] * len(values)

    usable_height = height - (PADDING * 2)
    return [
        height - PADDING - ((value - lo) / (hi - lo)) * usable_height
        for value in values
    ]


def line_points(ys: list[float], width: float) -> str:
    if not ys:
        return ""
    if len(ys) == 1:
        return f"0,{ys[0]:.2f} {width},{ys[0]:.2f}"

    step = width / (len(ys) - 1)
    return " ".join(f"{i * step:.2f},{y:.2f}" for i, y in enumerate(ys))


def area_points(ys: list[float], width: float, height: float) -> str:
    line = line_points(ys, width)
    if not line:
        return ""
    return f"0,{height} {line} {width},{height}"


def band_points(top_ys: list[float], bottom_ys: list[float], width: float) -> str:
    # the area between two lines, for the upper series of a stacked chart
    top = line_points(top_ys, width)
    bottom = line_points(bottom_ys, width)
    if not top:
        return ""
    return f"{top} {' '.join(reversed(bottom.split()))}"


def tooltip_points(
    whens: list[str],
    ys: list[float],
    height: float,
    series: list[tuple[str, list[float], str, str]],
) -> list[dict]:
    # series are (label, values, unit, key), where key picks the tooltip's color square,
    # series-1 for the main color and series-2 for the lighter one
    return [
        {
            "when": when,
            "y": round(ys[i] / height * 100, 2),
            "rows": [
                [label, f"{round(values[i]):,}{unit}", key]
                for label, values, unit, key in series
            ],
        }
        for i, when in enumerate(whens)
    ]
