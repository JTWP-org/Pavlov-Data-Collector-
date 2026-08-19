#!/usr/bin/env python3

from pathlib import Path
import csv
import math

from PIL import Image, ImageDraw, ImageFont


# ============================================================
# PATHS
# ============================================================

DATA_DIR = Path(
    "/home/steam/jtwp-collector-data/"
    "global/pavlov_api"
)

TSV_FILE = DATA_DIR / "servers.tsv"

OUTPUT_DIR = DATA_DIR


# ============================================================
# IMAGE SETTINGS
# ============================================================

WIDTH = 1400

TITLE_HEIGHT = 100
HEADER_HEIGHT = 55
ROW_HEIGHT = 58

BOTTOM_PADDING = 25

ROWS_PER_IMAGE = 25


# ============================================================
# COLORS
# ============================================================

BACKGROUND = (30, 31, 34)

HEADER_BACKGROUND = (43, 45, 49)

ROW_BACKGROUND_1 = (33, 34, 38)

ROW_BACKGROUND_2 = (40, 41, 45)

TEXT = (230, 230, 230)

TEXT_DIM = (175, 175, 175)

HEADER_TEXT = (255, 255, 255)


# ============================================================
# FONTS
# ============================================================

def load_font(size, bold=False):

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

    for font_path in candidates:

        path = Path(font_path)

        if path.exists():
            return ImageFont.truetype(
                str(path),
                size
            )

    return ImageFont.load_default()


TITLE_FONT = load_font(
    38,
    bold=True
)

SUBTITLE_FONT = load_font(
    22,
    bold=False
)

HEADER_FONT = load_font(
    22,
    bold=True
)

ROW_FONT = load_font(
    22,
    bold=False
)

ROW_BOLD_FONT = load_font(
    22,
    bold=True
)


# ============================================================
# COLUMNS
# ============================================================

COLUMNS = [
    {
        "key": "Players",
        "title": "PLAYERS",
        "x": 30,
        "max_width": 125,
    },

    {
        "key": "Build",
        "title": "BUILD",
        "x": 175,
        "max_width": 185,
    },

    {
        "key": "Name",
        "title": "SERVER NAME",
        "x": 380,
        "max_width": 575,
    },

    {
        "key": "Map",
        "title": "MAP",
        "x": 975,
        "max_width": 390,
    },
]


# ============================================================
# TEXT HELPERS
# ============================================================

def text_width(draw, text, font):

    bbox = draw.textbbox(
        (0, 0),
        text,
        font=font
    )

    return bbox[2] - bbox[0]


def truncate_text(
    draw,
    text,
    font,
    max_width,
):

    text = str(
        text or ""
    )

    if (
        text_width(
            draw,
            text,
            font
        )
        <= max_width
    ):
        return text

    ellipsis = "..."

    ellipsis_width = text_width(
        draw,
        ellipsis,
        font
    )

    available = (
        max_width
        - ellipsis_width
    )

    if available <= 0:
        return ellipsis

    result = ""

    for char in text:

        test = (
            result
            + char
        )

        if (
            text_width(
                draw,
                test,
                font
            )
            > available
        ):
            break

        result = test

    return (
        result.rstrip()
        + ellipsis
    )


# ============================================================
# LOAD TSV
# ============================================================

def load_rows():

    if not TSV_FILE.exists():

        raise FileNotFoundError(
            f"TSV not found: {TSV_FILE}"
        )

    with TSV_FILE.open(
        "r",
        encoding="utf-8",
        newline=""
    ) as file:

        reader = csv.DictReader(
            file,
            delimiter="\t"
        )

        rows = list(reader)

    return rows


# ============================================================
# PLAYER SORTING
# ============================================================

def current_players(row):

    value = str(
        row.get(
            "Players",
            "0/0"
        )
    )

    try:

        current = value.split(
            "/",
            1
        )[0]

        return int(
            current
        )

    except Exception:

        return 0


# ============================================================
# REMOVE OLD IMAGES
# ============================================================

def clean_old_images():

    for image_path in OUTPUT_DIR.glob(
        "live-servers-*.png"
    ):

        try:
            image_path.unlink()

        except Exception as exc:

            print(
                f"⚠️ Could not remove "
                f"{image_path}: {exc}"
            )


# ============================================================
# DRAW IMAGE
# ============================================================

def draw_server_image(
    rows,
    part,
    total_parts,
    total_servers,
):

    image_height = (
        TITLE_HEIGHT
        + HEADER_HEIGHT
        + (
            len(rows)
            * ROW_HEIGHT
        )
        + BOTTOM_PADDING
    )

    image = Image.new(
        "RGB",
        (
            WIDTH,
            image_height
        ),
        BACKGROUND
    )

    draw = ImageDraw.Draw(
        image
    )


    # ========================================================
    # TITLE
    # ========================================================

    draw.text(
        (
            30,
            18
        ),
        "PAVLOV LIVE SERVER BROWSER",
        font=TITLE_FONT,
        fill=HEADER_TEXT
    )

    subtitle = (
        f"Part {part}/{total_parts}  •  "
        f"{total_servers} Servers"
    )

    draw.text(
        (
            30,
            63
        ),
        subtitle,
        font=SUBTITLE_FONT,
        fill=TEXT_DIM
    )


    # ========================================================
    # HEADER ROW
    # ========================================================

    header_y = TITLE_HEIGHT

    draw.rectangle(
        [
            0,
            header_y,
            WIDTH,
            header_y
            + HEADER_HEIGHT
        ],
        fill=HEADER_BACKGROUND
    )


    for column in COLUMNS:

        draw.text(
            (
                column["x"],
                header_y + 15
            ),
            column["title"],
            font=HEADER_FONT,
            fill=HEADER_TEXT
        )


    # ========================================================
    # SERVER ROWS
    # ========================================================

    y = (
        TITLE_HEIGHT
        + HEADER_HEIGHT
    )


    for index, row in enumerate(
        rows
    ):

        if index % 2 == 0:
            background = (
                ROW_BACKGROUND_1
            )
        else:
            background = (
                ROW_BACKGROUND_2
            )


        draw.rectangle(
            [
                0,
                y,
                WIDTH,
                y + ROW_HEIGHT
            ],
            fill=background
        )


        for column in COLUMNS:

            key = column["key"]

            value = row.get(
                key,
                ""
            )


            if key == "Players":
                font = ROW_BOLD_FONT
            else:
                font = ROW_FONT


            value = truncate_text(
                draw,
                value,
                font,
                column["max_width"]
            )


            draw.text(
                (
                    column["x"],
                    y + 16
                ),
                value,
                font=font,
                fill=TEXT
            )


        y += ROW_HEIGHT


    # ========================================================
    # SAVE
    # ========================================================

    output_file = (
        OUTPUT_DIR
        / f"live-servers-{part}.png"
    )


    image.save(
        output_file,
        "PNG",
        optimize=True
    )


    print(
        f"✅ Generated: {output_file}"
    )

    print(
        f"   Servers: {len(rows)}"
    )


    return output_file


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print(
        "🌐 JTWP Pavlov Live "
        "Server Image Generator"
    )
    print(
        "================================"
    )


    rows = load_rows()


    # Sort highest current player count first.
    rows.sort(
        key=current_players,
        reverse=True
    )


    total_servers = len(
        rows
    )


    if total_servers == 0:

        print(
            "❌ No servers found in servers.tsv"
        )

        return


    total_parts = math.ceil(
        total_servers
        / ROWS_PER_IMAGE
    )


    print(
        f"🖥️ Total Servers: {total_servers}"
    )

    print(
        f"📄 Servers/Image: {ROWS_PER_IMAGE}"
    )

    print(
        f"🖼️ Images: {total_parts}"
    )


    clean_old_images()


    generated = []


    for index in range(
        total_parts
    ):

        start = (
            index
            * ROWS_PER_IMAGE
        )

        end = (
            start
            + ROWS_PER_IMAGE
        )


        chunk = rows[
            start:end
        ]


        output_file = draw_server_image(
            rows=chunk,
            part=index + 1,
            total_parts=total_parts,
            total_servers=total_servers,
        )


        generated.append(
            output_file
        )


    print()
    print(
        "================================"
    )

    print(
        "✅ Image generation complete"
    )

    print(
        "================================"
    )


    for path in generated:
        print(
            f"🖼️ {path}"
        )


if __name__ == "__main__":
    main()
