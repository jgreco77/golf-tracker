import os
import re
import json
import datetime
from PIL import Image
from google import genai

image_path = os.getenv("IMAGE_PATH")
course_override = os.getenv("COURSE_OVERRIDE")
api_key = os.getenv("GEMINI_API_KEY")

stats_path = "data/player_stats.json"
config_path = "config.json"

print(f"Target image path: {image_path}")
print(f"API key detected: {'Yes' if api_key else 'NO - GEMINI_API_KEY IS MISSING'}")

# Load target aliases
aliases = ["John", "Greco", "JG", "Johnny"]
if os.path.exists(config_path):
    try:
        with open(config_path, "r") as f:
            cfg = json.load(f)
            aliases = cfg.get("aliases", aliases)
    except Exception as e:
        print(f"Error reading config.json: {e}")

# Load existing stats
stats = {"total_rounds": 0, "scoring_average": "--", "lowest_round": "--", "rounds": []}
if os.path.exists(stats_path):
    try:
        with open(stats_path, "r") as f:
            stats = json.load(f)
    except Exception as e:
        print(f"Could not read existing stats.json, initializing fresh: {e}")

extracted_data = None

if api_key and image_path and os.path.exists(image_path):
    try:
        client = genai.Client(api_key=api_key)
        pil_img = Image.open(image_path)

        prompt = f"""
        You are an expert golf scorecard digitizer.
        Analyze this full scorecard photo. Find the player row corresponding to one of these aliases: {aliases}.
        
        Extract:
        1. "course_name": Name of the golf course.
        2. "location": City and State if printed on card, otherwise empty string.
        3. "date": Date played (format: "MMM DD, YYYY").
        4. "holes": A full list of all holes played with integer values for hole, par, and score:
           [{{"hole": 1, "par": 4, "score": 5}}, ...]
        5. "total_putts": Total putts if recorded, otherwise null.

        Return ONLY a JSON object. Do not wrap in markdown tags or backticks.
        """

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[pil_img, prompt]
        )

        raw_text = response.text.strip()
        print(f"Raw model response:\n{raw_text}")

        # Strip potential markdown fences
        clean_text = re.sub(r"^```json\s*", "", raw_text, flags=re.IGNORECASE)
        clean_text = re.sub(r"^```\s*", "", clean_text)
        clean_text = re.sub(r"```$", "", clean_text).strip()

        extracted_data = json.loads(clean_text)

    except Exception as e:
        print(f"Extraction failed with error: {e}")

# Fallback defaults if extraction fails
if not extracted_data:
    print("Using fallback round structure.")
    extracted_data = {
        "course_name": course_override or "Unknown Golf Course",
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

new_round = {
    "course_name": extracted_data.get("course_name", "Golf Course"),
    "location": extracted_data.get("location", ""),
    "date": extracted_data.get("date", datetime.date.today().strftime("%b %d, %Y")),
    "holes_played": len(clean_holes),
    "score": total_score,
    "to_par": to_par,
    "total_putts": extracted_data.get("total_putts") or "N/A",
    "image_url": f"[https://raw.githubusercontent.com/jgreco77/golf-tracker/main/](https://raw.githubusercontent.com/jgreco77/golf-tracker/main/){image_path}" if image_path else "",
    "holes": clean_holes
}

# Prepend new round to the top
stats["rounds"].insert(0, new_round)
stats["total_rounds"] = len(stats["rounds"])

all_scores = [r["score"] for r in stats["rounds"] if isinstance(r.get("score"), (int, float)) and r["score"] > 0]
if all_scores:
    stats["scoring_average"] = f"{sum(all_scores) / len(all_scores):.1f}"
    stats["lowest_round"] = str(min(all_scores))

with open(stats_path, "w") as f:
    json.dump(stats, f, indent=2)

print(f"Successfully processed round: {new_round['course_name']} | Score: {new_round['score']}")
