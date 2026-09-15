import os
import re
import json
import glob
import time
import datetime
from google import genai
from google.genai import types

image_path = os.getenv("IMAGE_PATH")
course_override = os.getenv("COURSE_OVERRIDE")
api_key = os.getenv("GEMINI_API_KEY")

stats_path = "data/player_stats.json"
config_path = "config.json"

# Auto-detect latest image if IMAGE_PATH was empty
if not image_path or not os.path.exists(image_path):
    existing_images = sorted(glob.glob("images/*.jpg") + glob.glob("images/*.png") + glob.glob("images/*.jpeg"), key=os.path.getmtime, reverse=True)
    if existing_images:
        image_path = existing_images[0]
        print(f"Auto-selected latest scorecard image: {image_path}")

print(f"Final image path: {image_path}")
print(f"API key detected: {'Yes' if api_key else 'NO - GEMINI_API_KEY IS MISSING'}")

aliases = ["John", "Greco", "JG", "Johnny"]
if os.path.exists(config_path):
    try:
        with open(config_path, "r") as f:
            cfg = json.load(f)
            aliases = cfg.get("aliases", aliases)
    except Exception as e:
        print(f"Config error: {e}")

stats = {"total_rounds": 0, "scoring_average": "--", "lowest_round": "--", "rounds": []}
if os.path.exists(stats_path):
    try:
        with open(stats_path, "r") as f:
            stats = json.load(f)
    except Exception as e:
        print(f"Stats error: {e}")

extracted_data = None

if api_key and image_path and os.path.exists(image_path):
    client = genai.Client(api_key=api_key)
    with open(image_path, "rb") as f:
        image_bytes = f.read()

    prompt = f"""
    You are an expert golf scorecard reader. 
    Read this entire scorecard grid carefully. Find the player row labeled with one of these names or initials: {aliases}.
    
    Extract:
    1. "course_name": The course name printed on the card.
    2. "location": City and State if printed, otherwise "".
    3. "date": Date played (format: "MMM DD, YYYY").
    4. "holes": A list of every hole played on the card across 9 or 18 holes:
       [{{"hole": 1, "par": 4, "score": 5}}, ...]
    5. "total_putts": Total putts if visible, otherwise null.

    Return ONLY a single valid JSON object. No Markdown code blocks, no backticks.
    """

    candidate_models = ['gemini-3.6-flash', 'gemini-3.6-pro']

    for model_name in candidate_models:
        success = False
        for attempt in range(1, 4):
            try:
                print(f"Attempting extraction with {model_name} (attempt {attempt}/3)...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                        prompt
                    ]
                )
                raw_text = response.text.strip()

                clean_text = re.sub(r"^```json\s*", "", raw_text, flags=re.IGNORECASE)
                clean_text = re.sub(r"^```\s*", "", clean_text)
                clean_text = re.sub(r"```$", "", clean_text).strip()

                extracted_data = json.loads(clean_text)
                success = True
                break
            except Exception as e:
                print(f"Error on {model_name} (attempt {attempt}): {e}")
                if "503" in str(e) or "UNAVAILABLE" in str(e):
                    time.sleep(3 * attempt)
                else:
                    break

        if success:
            break

if not extracted_data:
    print("Failed extraction across all attempts, using defaults.")
    extracted_data = {
        "course_name": course_override or "Golf Course",
        "location": "",
        "date": datetime.date.today().strftime("%b %d, %Y"),
        "holes": [],
        "total_putts": None
    }

if course_override:
    extracted_data["course_name"] = course_override

raw_holes = extracted_data.get("holes", [])
clean_holes = []
for h in raw_holes:
    try:
        clean_holes.append({
            "hole": int(h.get("hole", len(clean_holes) + 1)),
            "par": int(h.get("par", 4)),
            "score": int(h.get("score", 4))
        })
    except (ValueError, TypeError):
        continue

total_score = sum(h["score"] for h in clean_holes)
total_par = sum(h["par"] for h in clean_holes)
to_par = total_score - total_par if clean_holes else 0

img_url = f"./{image_path}" if image_path else ""

new_round = {
    "course_name": extracted_data.get("course_name") or "Golf Course",
    "location": extracted_data.get("location") or "",
    "date": extracted_data.get("date") or datetime.date.today().strftime("%b %d, %Y"),
    "holes_played": len(clean_holes),
    "score": total_score,
    "to_par": to_par,
    "total_putts": extracted_data.get("total_putts") or "N/A",
    "image_url": img_url,
    "holes": clean_holes
}

# De-duplication check: if this round (same image or same date/course) already exists, update it instead of inserting a duplicate
existing_index = None
for idx, r in enumerate(stats.get("rounds", [])):
    if (img_url and r.get("image_url") == img_url) or (r.get("date") == new_round["date"] and r.get("course_name") == new_round["course_name"]):
        existing_index = idx
        break

if existing_index is not None:
    print(f"Updating existing round at index {existing_index} instead of duplicating.")
    stats["rounds"][existing_index] = new_round
else:
    stats["rounds"].insert(0, new_round)

stats["total_rounds"] = len(stats["rounds"])

# Calculate 18-hole normalized average for the summary bar ONLY
normalized_scores = []
for r in stats["rounds"]:
    s = r.get("score", 0)
    h = r.get("holes_played", len(r.get("holes", [])))
    if isinstance(s, (int, float)) and s > 0 and h > 0:
        # Scale 9-hole score to 18-hole pace: (41 / 9) * 18 = 82.0
        normalized_scores.append((s / h) * 18)

if normalized_scores:
    stats["scoring_average"] = f"{sum(normalized_scores) / len(normalized_scores):.1f}"
    valid_scores = [r["score"] for r in stats["rounds"] if isinstance(r.get("score"), (int, float)) and r["score"] > 0]
    stats["lowest_round"] = str(min(valid_scores)) if valid_scores else "--"

with open(stats_path, "w") as f:
    json.dump(stats, f, indent=2)

print(f"Finished: Total Rounds={stats['total_rounds']} | 18H Avg={stats.get('scoring_average')}")
