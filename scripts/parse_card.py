import os
import re
import json
import glob
import datetime
from google import genai
from google.genai import types

image_path = os.getenv("IMAGE_PATH")
course_override = os.getenv("COURSE_OVERRIDE")
api_key = os.getenv("GEMINI_API_KEY")

stats_path = "data/player_stats.json"
config_path = "config.json"

# Auto-detect latest image if IMAGE_PATH was empty (e.g. manual Run Workflow)
if not image_path or not os.path.exists(image_path):
    existing_images = sorted(glob.glob("images/*.jpg") + glob.glob("images/*.png") + glob.glob("images/*.jpeg"), key=os.path.getmtime, reverse=True)
    if existing_images:
        image_path = existing_images[0]
        print(f"Auto-selected latest scorecard image: {image_path}")

print(f"Final image path: {image_path}")
print(f"API key detected: {'Yes' if api_key else 'NO - GEMINI_API_KEY IS MISSING'}")

# Load target aliases
aliases = ["John", "Greco", "JG", "Johnny"]
if os.path.exists(config_path):
    try:
        with open(config_path, "r") as f:
            cfg = json.load(f)
            aliases = cfg.get("aliases", aliases)
    except Exception as e:
        print(f"Config error: {e}")

# Load existing stats
stats = {"total_rounds": 0, "scoring_average": "--", "lowest_round": "--", "rounds": []}
if os.path.exists(stats_path):
    try:
        with open(stats_path, "r") as f:
            stats = json.load(f)
    except Exception as e:
        print(f"Stats error: {e}")

extracted_data = None

if api_key and image_path and os.path.exists(image_path):
    try:
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

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                prompt
            ]
        )

        raw_text = response.text.strip()
        print(f"Model output:\n{raw_text}")

        clean_text = re.sub(r"^```json\s*", "", raw_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"^```\s*", "", clean_text)
        clean_text = re.sub(r"```$", "", clean_text).strip()

        extracted_data = json.loads(clean_text)

    except Exception as e:
        print(f"Vision API error: {e}")

if not extracted_data:
    print("Failed extraction, using defaults.")
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

# Format the image URL so it renders in the app
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

stats["rounds"].insert(0, new_round)
stats["total_rounds"] = len(stats["rounds"])

all_scores = [r["score"] for r in stats["rounds"] if isinstance(r.get("score"), (int, float)) and r["score"] > 0]
if all_scores:
    stats["scoring_average"] = f"{sum(all_scores) / len(all_scores):.1f}"
    stats["lowest_round"] = str(min(all_scores))

with open(stats_path, "w") as f:
    json.dump(stats, f, indent=2)

print(f"Processed: {new_round['course_name']} | Score: {new_round['score']} | Holes: {len(clean_holes)}")
