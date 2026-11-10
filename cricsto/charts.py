"""On-brand Cricsto charts: navy ground, cricket-ball red accent, cream text.

Every chart is 1600x900 px (16:9, displays fully in the X timeline) with a title,
optional subtitle, a source line and the @cricsto watermark.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "output"
FONTS_DIR = ROOT / "fonts"

NAVY = "#0E1A2B"
RED = "#D94B3D"
CREAM = "#F2E8D5"
MUTED = "#C9C2B3"
GRID = "#24324A"
DIM_BAR = "#5B6B85"       # non-highlighted bars
SECOND = "#E8A33D"        # second series (amber: differs from red in lightness too)

HANDLE = "@cricsto"


def _register_fonts() -> tuple[str, str]:
    """Use Space Grotesk / Inter if available (system or ./fonts), else fall back."""
    if FONTS_DIR.exists():
        for f in list(FONTS_DIR.glob("*.ttf")) + list(FONTS_DIR.glob("*.otf")):
            font_manager.fontManager.addfont(str(f))
    names = {f.name for f in font_manager.fontManager.ttflist}
    heading = "Space Grotesk" if "Space Grotesk" in names else ("Inter" if "Inter" in names else "DejaVu Sans")
    body = "Inter" if "Inter" in names else "DejaVu Sans"
    return heading, body


HEADING_FONT, BODY_FONT = _register_fonts()


def _style() -> None:
    plt.rcParams.update({
        "figure.facecolor": NAVY,
        "axes.facecolor": NAVY,
        "axes.edgecolor": NAVY,
        "axes.labelcolor": MUTED,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 1,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelsize": 12,
        "ytick.labelsize": 12,
        "font.family": BODY_FONT,
        "text.color": CREAM,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.spines.left": False,
        "axes.spines.bottom": False,
    })


def _frame(title: str, subtitle: str | None, source: str):
    _style()
    fig = plt.figure(figsize=(8, 4.5), dpi=200)
    ax = fig.add_axes([0.08, 0.14, 0.86, 0.62])
    ax.set_axisbelow(True)  # grid behind bars and lines
    fig.text(0.04, 0.93, title, fontsize=20, fontweight="bold", family=HEADING_FONT,
             color=CREAM, va="top")
    if subtitle:
        fig.text(0.04, 0.845, subtitle, fontsize=11.5, color=MUTED, va="top")
    fig.text(0.04, 0.035, source, fontsize=9, color=MUTED)
    fig.text(0.96, 0.035, HANDLE, fontsize=11, fontweight="bold", family=HEADING_FONT,
             color=RED, ha="right")
    return fig, ax


def bar(labels, values, title: str, subtitle: str | None = None,
        source: str = "Data: Cricsheet", highlight=None, value_fmt: str = "{:.1f}",
        horizontal: bool = True, xlabel: str | None = None):
    """Ranked bar chart. `highlight` = a label (or list of labels) drawn in red; others dimmed.
    With no highlight, all bars are red."""
    labels, values = list(labels), list(values)
    hl = {highlight} if isinstance(highlight, str) else set(highlight or [])
    colors = [RED if (not hl or l in hl) else DIM_BAR for l in labels]
    fig, ax = _frame(title, subtitle, source)
    if horizontal:
        pos = range(len(labels))[::-1]  # first item on top
        ax.barh(list(pos), values, color=colors, height=0.68)
        ax.set_yticks(list(pos), labels)
        ax.grid(axis="y", visible=False)
        for p, v in zip(pos, values):
            ax.text(v, p, "  " + value_fmt.format(v), va="center", fontsize=11, color=CREAM)
        ax.set_xlim(0, max(values) * 1.15 if values else 1)
        if xlabel:
            ax.set_xlabel(xlabel)
    else:
        ax.bar(range(len(labels)), values, color=colors, width=0.68)
        ax.set_xticks(range(len(labels)), labels)
        ax.grid(axis="x", visible=False)
        for i, v in enumerate(values):
            ax.text(i, v, value_fmt.format(v), ha="center", va="bottom", fontsize=11, color=CREAM)
        ax.set_ylim(0, max(values) * 1.15 if values else 1)
        if xlabel:
            ax.set_ylabel(xlabel)
    ax.tick_params(length=0)
    return fig


def line(x, series: dict, title: str, subtitle: str | None = None,
         source: str = "Data: Cricsheet", ylabel: str | None = None, label_ends: bool = True):
    """Trend chart. `series` = {name: values}; first series is red, second amber, rest dimmed.
    Series are labelled at their right end instead of with a legend."""
    palette = [RED, SECOND] + [DIM_BAR] * 10
    fig, ax = _frame(title, subtitle, source)
    if label_ends:
        ax.set_position([0.08, 0.14, 0.74, 0.62])  # room for end labels
    x = list(x)
    for (name, ys), color in zip(series.items(), palette):
        ys = list(ys)
        ax.plot(x, ys, color=color, linewidth=3, marker="o", markersize=5)
        if label_ends and ys:
            ax.annotate(f" {name}", (x[-1], ys[-1]), color=color, fontsize=11,
                        fontweight="bold", va="center", annotation_clip=False)
    ax.grid(axis="x", visible=False)
    ax.tick_params(length=0)
    if ylabel:
        ax.set_ylabel(ylabel)
    if len(x) > 12:
        step = max(1, len(x) // 10)
        ax.set_xticks(x[::step])
    return fig


def save(fig, name: str) -> Path:
    """Save to output/<name>.png at 1600x900 and close the figure."""
    OUT_DIR.mkdir(exist_ok=True)
    path = OUT_DIR / f"{name}.png"
    fig.savefig(path, dpi=200, facecolor=NAVY)
    plt.close(fig)
    return path
