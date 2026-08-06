from __future__ import annotations

import io
import json
import math
import re
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, ImageSequence

ITEMS = [
  {
    "index": 1,
    "resource_key": "emoji:1232374526013345833",
    "name": "0004145424241",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1232374526013345833.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 2,
    "resource_key": "emoji:1268980129338495197",
    "name": "011132",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1268980129338495197.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 3,
    "resource_key": "emoji:1171119114069221446",
    "name": "1072973978508984390",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1171119114069221446.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 4,
    "resource_key": "emoji:1468575792790507624",
    "name": "134169620572469689",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1468575792790507624.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 5,
    "resource_key": "emoji:1362391718665912502",
    "name": "193754",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1362391718665912502.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 6,
    "resource_key": "emoji:1360986724578234439",
    "name": "223455",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1360986724578234439.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 7,
    "resource_key": "emoji:1269690213303849052",
    "name": "40e6d78a4653eda3096a14aab5ad62ec",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1269690213303849052.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 8,
    "resource_key": "emoji:1375036293355929601",
    "name": "426941932",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1375036293355929601.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 9,
    "resource_key": "emoji:1446038165633896591",
    "name": "6847454",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1446038165633896591.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 10,
    "resource_key": "emoji:1462847055558082650",
    "name": "734475086617",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1462847055558082650.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 11,
    "resource_key": "emoji:1363896403767857362",
    "name": "Mygo_",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1363896403767857362.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 12,
    "resource_key": "emoji:1363896422432374844",
    "name": "Mygo_",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1363896422432374844.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 13,
    "resource_key": "emoji:1363896370322342188",
    "name": "__",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1363896370322342188.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 14,
    "resource_key": "emoji:1363896388156522615",
    "name": "__",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1363896388156522615.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 15,
    "resource_key": "emoji:1170386448227246181",
    "name": "emoji_11",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1170386448227246181.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 16,
    "resource_key": "emoji:1170386469341364305",
    "name": "emoji_11",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1170386469341364305.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 17,
    "resource_key": "emoji:1170390277169614868",
    "name": "emoji_15",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1170390277169614868.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 18,
    "resource_key": "emoji:1182369997264269392",
    "name": "emoji_35",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1182369997264269392.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 19,
    "resource_key": "emoji:1170386180072812554",
    "name": "emoji_4",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1170386180072812554.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 20,
    "resource_key": "emoji:1184253875356717157",
    "name": "emoji_40",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1184253875356717157.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 21,
    "resource_key": "emoji:1228639162912215060",
    "name": "emoji_40",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1228639162912215060.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 22,
    "resource_key": "emoji:1186988031643754536",
    "name": "emoji_41",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1186988031643754536.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 23,
    "resource_key": "emoji:1205905849009045564",
    "name": "emoji_42",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1205905849009045564.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 24,
    "resource_key": "emoji:1202209280879501382",
    "name": "emoji_43",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1202209280879501382.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 25,
    "resource_key": "emoji:1206155939242053662",
    "name": "emoji_43",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1206155939242053662.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 26,
    "resource_key": "emoji:1234179758565359638",
    "name": "emoji_44",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1234179758565359638.gif?size=128",
    "animated": true,
    "format_type": "emoji"
  },
  {
    "index": 27,
    "resource_key": "emoji:1239162150359142623",
    "name": "emoji_45",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1239162150359142623.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 28,
    "resource_key": "emoji:1239726077665087571",
    "name": "emoji_45",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1239726077665087571.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 29,
    "resource_key": "emoji:1257560298181623849",
    "name": "emoji_45",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1257560298181623849.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 30,
    "resource_key": "emoji:1253910688733073440",
    "name": "emoji_47",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1253910688733073440.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 31,
    "resource_key": "emoji:1456353775609708655",
    "name": "emoji_49",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1456353775609708655.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 32,
    "resource_key": "emoji:1456354084176134239",
    "name": "emoji_50",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1456354084176134239.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 33,
    "resource_key": "emoji:1429718474305048678",
    "name": "emoji_51",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1429718474305048678.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 34,
    "resource_key": "emoji:1456353066709160181",
    "name": "emoji_51",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1456353066709160181.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 35,
    "resource_key": "emoji:1456354465190903920",
    "name": "emoji_51",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1456354465190903920.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 36,
    "resource_key": "emoji:1508159731695616200",
    "name": "emoji_51",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1508159731695616200.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 37,
    "resource_key": "emoji:1355023580995391578",
    "name": "emoji_52",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1355023580995391578.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 38,
    "resource_key": "emoji:1363844230753157140",
    "name": "emoji_52",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1363844230753157140.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 39,
    "resource_key": "emoji:1365421159146852372",
    "name": "emoji_52",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1365421159146852372.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 40,
    "resource_key": "emoji:1374575365846208634",
    "name": "emoji_52",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1374575365846208634.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 41,
    "resource_key": "emoji:1272884702163767318",
    "name": "emoji_55",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1272884702163767318.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 42,
    "resource_key": "emoji:1278196724426342411",
    "name": "emoji_57",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1278196724426342411.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 43,
    "resource_key": "emoji:1287251862894153728",
    "name": "emoji_59",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1287251862894153728.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 44,
    "resource_key": "emoji:1287327758048821268",
    "name": "emoji_60",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1287327758048821268.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 45,
    "resource_key": "emoji:1180452016867246100",
    "name": "fu_horny",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1180452016867246100.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 46,
    "resource_key": "emoji:1178492613322621038",
    "name": "fufu_face",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1178492613322621038.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 47,
    "resource_key": "emoji:1180554547798757436",
    "name": "icant",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1180554547798757436.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 48,
    "resource_key": "emoji:1171031982550036530",
    "name": "kekw",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1171031982550036530.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 49,
    "resource_key": "emoji:1246443075258155078",
    "name": "owABGC4HfEP650465045640",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1246443075258155078.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 50,
    "resource_key": "emoji:1192507428953141259",
    "name": "photo_20240104_235049",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1192507428953141259.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 51,
    "resource_key": "emoji:1490613908527124521",
    "name": "rock",
    "resource_type": "emoji",
    "asset_url": "https://cdn.discordapp.com/emojis/1490613908527124521.png?size=128",
    "animated": false,
    "format_type": "emoji"
  },
  {
    "index": 52,
    "resource_key": "sticker:1252635208524496987",
    "name": "WTH",
    "resource_type": "sticker",
    "asset_url": "https://cdn.discordapp.com/stickers/1252635208524496987.png",
    "animated": false,
    "format_type": "1"
  },
  {
    "index": 53,
    "resource_key": "sticker:1217072879938572390",
    "name": "仙人指路",
    "resource_type": "sticker",
    "asset_url": "https://cdn.discordapp.com/stickers/1217072879938572390.png",
    "animated": false,
    "format_type": "1"
  },
  {
    "index": 54,
    "resource_key": "sticker:1487069151745933412",
    "name": "你已急哭",
    "resource_type": "sticker",
    "asset_url": "https://cdn.discordapp.com/stickers/1487069151745933412.png",
    "animated": false,
    "format_type": "1"
  },
  {
    "index": 55,
    "resource_key": "sticker:1386701773040783492",
    "name": "难道说",
    "resource_type": "sticker",
    "asset_url": "https://cdn.discordapp.com/stickers/1386701773040783492.png",
    "animated": false,
    "format_type": "1"
  },
  {
    "index": 56,
    "resource_key": "sticker:1368200316683681944",
    "name": "难道说？",
    "resource_type": "sticker",
    "asset_url": "https://cdn.discordapp.com/stickers/1368200316683681944.png",
    "animated": false,
    "format_type": "1"
  }
]

OUT = Path("expression-analysis")
ASSETS = OUT / "assets"
SHEETS = OUT / "sheets"
ASSETS.mkdir(parents=True, exist_ok=True)
SHEETS.mkdir(parents=True, exist_ok=True)

try:
    FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
    SMALL = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
except OSError:
    FONT = ImageFont.load_default()
    SMALL = ImageFont.load_default()

session = requests.Session()
session.headers.update({"User-Agent": "CharacterRelay-Expression-Review/1.0"})
manifest: list[dict[str, object]] = []
thumbs: list[tuple[dict[str, object], Image.Image]] = []

for item in ITEMS:
    url = str(item["asset_url"])
    if item["resource_type"] == "emoji":
        url = re.sub(r"size=128", "size=512", url)
        if "size=" not in url:
            url += ("&" if "?" in url else "?") + "size=512"
    response = session.get(url, timeout=30)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    stem = f'{int(item["index"]):02d}_{str(item["resource_key"]).replace(":", "_")}'
    extension = ".gif" if ("gif" in content_type or url.split("?")[0].endswith(".gif")) else ".png"
    raw_path = (ASSETS / stem).with_suffix(extension)
    raw_path.write_bytes(response.content)

    image = Image.open(io.BytesIO(response.content))
    frames: list[Image.Image] = []
    if getattr(image, "is_animated", False):
        for frame in ImageSequence.Iterator(image):
            frames.append(frame.convert("RGBA").copy())
        preview = frames[0]
        samples: list[Image.Image] = []
        for n in range(min(6, len(frames))):
            idx = round(n * (len(frames) - 1) / max(1, min(6, len(frames)) - 1))
            samples.append(frames[idx])
        strip = Image.new("RGBA", (240 * len(samples), 280), "white")
        strip_draw = ImageDraw.Draw(strip)
        for n, frame in enumerate(samples):
            sampled = frame.copy()
            sampled.thumbnail((220, 220), Image.Resampling.LANCZOS)
            x = n * 240 + (240 - sampled.width) // 2
            y = 10 + (220 - sampled.height) // 2
            strip.alpha_composite(sampled, (x, y))
            strip_draw.text((n * 240 + 8, 238), f"frame {n + 1}", fill="#2f2935", font=SMALL)
        strip.convert("RGB").save(SHEETS / f'animated_{int(item["index"]):02d}.jpg', quality=92)
    else:
        preview = image.convert("RGBA")

    preview.thumbnail((280, 280), Image.Resampling.LANCZOS)
    thumbs.append((item, preview.copy()))
    manifest.append({**item, "download_url": url, "local_file": str(raw_path), "frame_count": len(frames)})

cols, rows = 3, 3
cell_w, cell_h = 420, 420
for page in range(math.ceil(len(thumbs) / (cols * rows))):
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "#f7f1e8")
    draw = ImageDraw.Draw(sheet)
    batch = thumbs[page * cols * rows : (page + 1) * cols * rows]
    for pos, (item, image) in enumerate(batch):
        col, row = pos % cols, pos // cols
        x0, y0 = col * cell_w, row * cell_h
        draw.rounded_rectangle(
            (x0 + 8, y0 + 8, x0 + cell_w - 8, y0 + cell_h - 8),
            radius=18,
            fill="white",
            outline="#d8cde2",
            width=2,
        )
        image_x = x0 + (cell_w - image.width) // 2
        image_y = y0 + 22 + (280 - image.height) // 2
        sheet.paste(image, (image_x, image_y), image)
        draw.text((x0 + 18, y0 + 314), f'#{int(item["index"]):02d} {item["resource_type"]}', fill="#5d4d75", font=FONT)
        name = str(item["name"])
        if len(name) > 30:
            name = name[:27] + "..."
        draw.text((x0 + 18, y0 + 346), name, fill="#2f2935", font=FONT)
        resource_id = str(item["resource_key"]).split(":", 1)[1]
        draw.text((x0 + 18, y0 + 380), resource_id, fill="#71677a", font=SMALL)
    sheet.save(SHEETS / f"sheet_{page + 1:02d}.jpg", quality=94)

(OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Downloaded {len(manifest)} assets and built {math.ceil(len(thumbs) / 9)} contact sheets.")
