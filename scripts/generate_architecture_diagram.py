#!/usr/bin/env python3
"""Regenerate docs/forgeagent-architecture.png from verified local components.

This documentation-only renderer requires Pillow (available in the contributor
environment used to maintain the project). It does not inspect or execute
capability code; node labels intentionally map to the files noted in README.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "forgeagent-architecture.png"
WIDTH, HEIGHT = 1840, 1020
INK = "#20242b"
OUTLINE = "#b9bec7"
MUTED = "#59616d"


def font(size: int) -> ImageFont.FreeTypeFont:
    """Use the system sans font in the native macOS contributor environment."""
    for candidate in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    raise RuntimeError("Architecture rendering needs a system TrueType sans font.")


def centred_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], lines: list[str], text_font: ImageFont.FreeTypeFont, fill: str = INK) -> None:
    line_heights = [draw.textbbox((0, 0), line, font=text_font)[3] for line in lines]
    gap = 4
    height = sum(line_heights) + gap * (len(lines) - 1)
    y = box[1] + (box[3] - box[1] - height) / 2
    for line, line_height in zip(lines, line_heights):
        left, _, right, _ = draw.textbbox((0, 0), line, font=text_font)
        x = box[0] + (box[2] - box[0] - (right - left)) / 2
        draw.text((x, y), line, font=text_font, fill=fill)
        y += line_height + gap


def node(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], lines: list[str], subtitle: str | None = None) -> None:
    draw.rectangle(box, fill="#ffffff", outline=OUTLINE, width=2)
    if subtitle:
        primary = font(19)
        secondary = font(14)
        primary_box = (box[0] + 10, box[1] + 10, box[2] - 10, box[3] - 30)
        centred_text(draw, primary_box, lines, primary)
        centred_text(draw, (box[0] + 10, box[3] - 31, box[2] - 10, box[3] - 8), [subtitle], secondary, MUTED)
    else:
        centred_text(draw, box, lines, font(20))


def arrow(draw: ImageDraw.ImageDraw, start: tuple[float, float], end: tuple[float, float], width: int = 2) -> None:
    draw.line([start, end], fill=INK, width=width)
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = max((dx * dx + dy * dy) ** 0.5, 1)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    tip = end
    left = (end[0] - 12 * ux + 6 * px, end[1] - 12 * uy + 6 * py)
    right = (end[0] - 12 * ux - 6 * px, end[1] - 12 * uy - 6 * py)
    draw.polygon([tip, left, right], fill=INK)


def curve(draw: ImageDraw.ImageDraw, points: tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]) -> None:
    p0, p1, p2, p3 = points
    samples: list[tuple[float, float]] = []
    for step in range(41):
        t = step / 40
        u = 1 - t
        samples.append((
            u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
            u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
        ))
    draw.line(samples, fill=INK, width=2)
    arrow(draw, samples[-2], samples[-1])


def main() -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#ffffff")
    draw = ImageDraw.Draw(image)

    client = (34, 382, 334, 460)
    mcp = (390, 382, 635, 460)
    graph = (720, 154, 970, 244)
    memory = (720, 375, 970, 467)
    packages = (1055, 222, 1325, 320)
    council = (720, 635, 970, 724)
    sandbox = (1090, 575, 1345, 654)
    policy = (925, 805, 1185, 894)
    project_policy = (565, 805, 830, 894)
    governance = (1270, 805, 1500, 894)
    audit = (1580, 805, 1805, 894)
    evaluation = (1495, 635, 1805, 724)

    node(draw, client, ["Codex / Cursor / Claude Code"])
    node(draw, mcp, ["MCP server"])
    node(draw, graph, ["Repository intelligence", "graph"])
    node(draw, memory, ["Capability memory +", "versions"])
    node(draw, packages, ["Signed capability", "packages"], "Ed25519 · import → review")
    node(draw, council, ["Foundry Council"])
    node(draw, sandbox, ["Isolated sandbox execution"])
    node(draw, project_policy, ["Project policy"], "forgeagent-policy.yml · narrows only")
    node(draw, policy, ["Policy and proof engine"])
    node(draw, governance, ["Governance decisions"])
    node(draw, audit, ["Audit log", "(SQLite + JSONL)"])
    node(draw, evaluation, ["Evaluation arena (50 cases)", "+ Live dashboard"])

    arrow(draw, (334, 421), (390, 421))
    arrow(draw, (635, 421), (720, 421))
    curve(draw, ((510, 382), (530, 275), (615, 199), (720, 199)))
    curve(draw, ((510, 460), (530, 560), (610, 680), (720, 680)))
    arrow(draw, (970, 414), (1055, 290))
    curve(draw, ((970, 420), (1015, 365), (1025, 470), (972, 440)))
    draw.text((1004, 474), "Reused instantly by", font=font(17), fill=INK)
    draw.text((1004, 496), "any agent — no rebuild", font=font(17), fill=INK)
    arrow(draw, (970, 680), (1090, 614))
    curve(draw, ((845, 724), (850, 775), (885, 827), (925, 849)))
    arrow(draw, (830, 849), (925, 849))
    arrow(draw, (1185, 849), (1270, 849))
    arrow(draw, (1500, 849), (1580, 849))
    curve(draw, ((1692, 805), (1700, 775), (1690, 752), (1650, 724)))

    image.save(OUTPUT, "PNG", optimize=True)
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({WIDTH}x{HEIGHT})")


if __name__ == "__main__":
    main()
