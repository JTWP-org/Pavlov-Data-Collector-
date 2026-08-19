#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


DEFAULT_PROJECT_ROOT = Path(
    "/home/steam/jtwp-collector/Pavlov-Data-Collector-"
)
DEFAULT_TSV = (
    DEFAULT_PROJECT_ROOT
    / "scripts"
    / "servers"
    / "servers.tsv"
)
DEFAULT_OUTPUT_DIR = Path(
    "/home/steam/jtwp-collector-data/global/pavlov_api"
)

WIDTH = 1600
TITLE_HEIGHT = 100
HEADER_HEIGHT = 48
ROW_HEIGHT = 44
BOTTOM_PADDING = 24
ROWS_PER_IMAGE = 25

COLUMNS = [
    ("Players", "PLAYERS", 30, 105),
    ("Build", "BUILD", 150, 165),
    ("Name", "SERVER NAME", 330, 410),
    ("Map", "MAP", 760, 320),
    ("Region", "REGION", 1100, 160),
    ("Company", "COMPANY", 1280, 290),
]


def load_font(size: int, bold: bool = False):
    if bold:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]

    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)

    return ImageFont.load_default()


TITLE_FONT = load_font(34, True)
SUBTITLE_FONT = load_font(18, False)
HEADER_FONT = load_font(20, True)
ROW_FONT = load_font(18, False)


def text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def truncate_text(
    draw: ImageDraw.ImageDraw,
    text: object,
    font,
    max_width: int,
) -> str:
    value = str(text or "")
    if text_width(draw, value, font) <= max_width:
        return value

    suffix = "..."
    suffix_width = text_width(draw, suffix, font)
    allowed = max_width - suffix_width
    if allowed <= 0:
        return suffix

    result = ""
    for char in value:
        candidate = result + char
        if text_width(draw, candidate, font) > allowed:
            break
        result = candidate

    return result.rstrip() + suffix


def load_rows(tsv_file: Path) -> list[dict[str, str]]:
    if not tsv_file.is_file():
        raise SystemExit(f"TSV not found: {tsv_file}")

    with tsv_file.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        return list(
            csv.DictReader(
                handle,
                delimiter="\t",
            )
        )


def current_players(row: dict[str, str]) -> int:
    try:
        return int(
            str(row.get("Players", "0/0")).split("/", 1)[0]
        )
    except (TypeError, ValueError):
        return 0


def clean_old_images(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for image_path in output_dir.glob("live-servers-*.png"):
        try:
            image_path.unlink()
        except OSError as exc:
            print(f"⚠️ Could not remove {image_path}: {exc}")


def draw_page(
    rows: list[dict[str, str]],
    output_file: Path,
    part: int,
    total_parts: int,
    total_servers: int,
) -> None:
    image_height = (
        TITLE_HEIGHT
        + HEADER_HEIGHT
        + len(rows) * ROW_HEIGHT
        + BOTTOM_PADDING
    )

    image = Image.new(
        "RGB",
        (WIDTH, image_height),
        (30, 31, 34),
    )
    draw = ImageDraw.Draw(image)

    draw.text(
        (30, 23),
        "PAVLOV LIVE SERVER BROWSER",
        font=TITLE_FONT,
        fill=(255, 255, 255),
    )

    subtitle = (
        f"{total_servers} Servers • Page {part}/{total_parts}"
    )
    draw.text(
        (30, 67),
        subtitle,
        font=SUBTITLE_FONT,
        fill=(190, 190, 190),
    )

    header_y = TITLE_HEIGHT
    draw.rectangle(
        [0, header_y, WIDTH, header_y + HEADER_HEIGHT],
        fill=(43, 45, 49),
    )

    for _key, title, x, _max_width in COLUMNS:
        draw.text(
            (x, header_y + 12),
            title,
            font=HEADER_FONT,
            fill=(255, 255, 255),
        )

    y = header_y + HEADER_HEIGHT

    for index, row in enumerate(rows):
        if index % 2:
            draw.rectangle(
                [0, y, WIDTH, y + ROW_HEIGHT],
                fill=(38, 39, 43),
            )

        for key, _title, x, max_width in COLUMNS:
            value = truncate_text(
                draw,
                row.get(key, ""),
                ROW_FONT,
                max_width,
            )
            draw.text(
                (x, y + 11),
                value,
                font=ROW_FONT,
                fill=(225, 225, 225),
            )

        y += ROW_HEIGHT

    image.save(output_file, "PNG")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tsv",
        default=str(DEFAULT_TSV),
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
    )
    parser.add_argument(
        "--rows-per-image",
        type=int,
        default=ROWS_PER_IMAGE,
    )
    args = parser.parse_args()

    tsv_file = Path(args.tsv).expanduser()
    output_dir = Path(args.output_dir).expanduser()
    rows_per_image = max(1, int(args.rows_per_image))

    rows = load_rows(tsv_file)
    rows.sort(key=current_players, reverse=True)

    if not rows:
        raise SystemExit(f"No server rows found in {tsv_file}")

    clean_old_images(output_dir)

    total_servers = len(rows)
    total_parts = (
        total_servers + rows_per_image - 1
    ) // rows_per_image

    for part in range(1, total_parts + 1):
        start = (part - 1) * rows_per_image
        page_rows = rows[start:start + rows_per_image]
        output_file = output_dir / f"live-servers-{part}.png"

        draw_page(
            page_rows,
            output_file,
            part,
            total_parts,
            total_servers,
        )

        print(f"✅ Generated: {output_file}")

    print(f"🖥️ Servers: {total_servers}")
    print(f"🖼️ Images: {total_parts}")


if __name__ == "__main__":
    main()
