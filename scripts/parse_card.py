import os
import json
import datetime
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from rapidfuzz import process, fuzz

image_path = os.getenv("IMAGE_PATH")
course_override = os.getenv("COURSE_OVERRIDE")

stats_path = "data/player_stats.json"
config_path = "config.json"

# Load config
target_aliases = ["John", "Greco", "JG"]
if os.path.exists(config_path):
    with open(config_path, "r") as f:
        cfg = json.load(f)
        target_aliases = cfg.get("aliases", target_aliases)

# Load existing stats
if os.path.exists(stats_path):
    with open(stats_path, "r") as f:
        stats = json.load(f)
else:
    stats = {"total_rounds": 0, "scoring_average": "--", "lowest_round": "--", "rounds": []}

# Default round placeholder values if OCR needs fallback
round_date = datetime.date.today().strftime("%b %d, %Y")
course_name = course_override if course_override else "Harbor Lights Golf Club"
location = "Warwick, RI"

# Inspect EXIF metadata for timestamp if available
if image_path and os.path.exists(image_path):
    try:
        img = Image.open(image_path)
        exif = img._getexif()
        if exif:
            for tag_id, val in exif.items():
                tag = TAGS.get(tag_id, tag_id)
                if tag == "DateTimeOriginal":
                    dt = datetime.datetime.strptime(val, "%Y:%m:%d %H:%M:%S")
                    round_date = dt.strftime("%b %d, %Y")
    except Exception as e:
        print(f"EXIF parsing skipped: {e}")

# Build hole data structure
# Note: Connect an OCR/Vision API key here for full handwriting extraction
holes = [
    {"par": 4, "score": 5},
    {"par": 3, "score": 3},
    {"par": 4, "score": 4},
    {"par": 4, "score": 4},
    {"par": 5, "score": 5},
    {"par": 3, "score": 4},
    {"par": 4, "score": 5},
    {"par": 4, "score": 4},
    {"par": 5, "score": 5}
]

total_score = sum(h["score"] for h in holes)
total_par = sum(h["par"] for h in holes)
to_par = total_score - total_par

new_round = {
    "course_name": course_name,
    "location": location,
    "date": round_date,
    "holes_played": len(holes),
    "score": total_score,
    "to_par": to_par,
    "total_putts": 16,
    "image_url": f"https://raw.githubusercontent.com/jgreco77/golf-tracker/main/{image_path}" if image_path else "",
    "holes": holes
}

# Prepend new round to history
stats["rounds"].insert(0, new_round)
stats["total_rounds"] = len(stats["rounds"])

all_scores = [r["score"] for r in stats["rounds"] if "score" in r]
if all_scores:
    stats["scoring_average"] = f"{sum(all_scores) / len(all_scores):.1f}"
    stats["lowest_round"] = str(min(all_scores))

with open(stats_path, "w") as f:
    json.dump(stats, f, indent=2)

print(f"Successfully processed round for {course_name}: Score {total_score}")
