import os
import json
import datetime
from PIL import Image
from google import genai
from google.genai import types

image_path = os.getenv("IMAGE_PATH")
course_override = os.getenv("COURSE_OVERRIDE")
api_key = os.getenv("GEMINI_API_KEY")

stats_path = "data/player_stats.json"
config_path = "config.json"

# Target name aliases
target_player = "John"
aliases = ["John", "Greco", "JG", "Johnny"]
if os.path.exists(config_path):
    with open(config_path, "r") as f:
        cfg = json.load(f)
        target_player = cfg.get("target_player", target_player)
        aliases = cfg.get("aliases", aliases)

# Load existing stats
if os.path.exists(stats_path):
    with open(stats_path, "r") as f:
        stats = json.load(f)
else:
    stats = {"total_rounds": 0, "scoring_average": "--", "lowest_round": "--", "rounds": []}

extracted_data = None

if api_key and image_path and os.path.exists(image_path):
    try:
        client = genai.Client(api_key=api_key)
        pil_img = Image.open(image_path)

                prompt = f"""
        You are an expert golf scorecard reader. 
        Analyze the full image grid. Find the player row matching one of these names/initials: {aliases}.

        Extract these fields:
        1. "course_name": Full golf course name printed on the card.
        2. "location": City and State if printed.
        3. "date": Date played (format "MMM DD, YYYY"). Default to current date if missing.
        4. "holes": An array containing EVERY SINGLE hole played on the card (all 9 holes for a 9-hole round, or all 18 holes for an 18-hole round). 
           Do NOT stop after hole 1. Iterate through column 1 through 9 (and 10 through 18 if played).
           Each item must be: {{"hole": <int 1-18>, "par": <int>, "score": <int>}}
        5. "total_putts": Total putts integer if tracked in a row, otherwise null.

        CRITICAL: Ensure the "holes" list contains entries for every hole with a recorded score on the player's line.
        Return ONLY valid, raw JSON matching this structure without markdown fences:
        {{
          "course_name": "...",
          "location": "...",
          "date": "...",
          "holes": [
            {{"hole": 1, "par": 4, "score": 5}},
            {{"hole": 2, "par": 3, "score": 4}}
          ],
          "total_putts": null
        }}
        """
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[pil_img, prompt]
        )

        clean_text = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        extracted_data = json.loads(clean_text)
    except Exception as e:
        print(f"Error extracting scorecard with vision API: {e}")

# Fallback defaults if extraction fails
if not extracted_data:
    extracted_data = {
        "course_name": course_override or "Unknown Course",
        "location": "Local",
        "date": datetime.date.today().strftime("%b %d, %Y"),
        "holes": [{"par": 4, "score": 4}],
        "total_putts": None
    }

if course_override:
    extracted_data["course_name"] = course_override

holes = extracted_data.get("holes", [])
total_score = sum(int(h.get("score", 0)) for h in holes if str(h.get("score", "")).isdigit())
total_par = sum(int(h.get("par", 0)) for h in holes if str(h.get("par", "")).isdigit())
to_par = total_score - total_par

new_round = {
    "course_name": extracted_data.get("course_name", "Golf Course"),
    "location": extracted_data.get("location", ""),
    "date": extracted_data.get("date", datetime.date.today().strftime("%b %d, %Y")),
    "holes_played": len(holes),
    "score": total_score,
    "to_par": to_par,
    "total_putts": extracted_data.get("total_putts") or "N/A",
    "image_url": f"[https://raw.githubusercontent.com/jgreco77/golf-tracker/main/](https://raw.githubusercontent.com/jgreco77/golf-tracker/main/){image_path}" if image_path else "",
    "holes": holes
}

# Prepend the new round to stats
stats["rounds"].insert(0, new_round)
stats["total_rounds"] = len(stats["rounds"])

all_scores = [r["score"] for r in stats["rounds"] if "score" in r and isinstance(r["score"], (int, float))]
if all_scores:
    stats["scoring_average"] = f"{sum(all_scores) / len(all_scores):.1f}"
    stats["lowest_round"] = str(min(all_scores))

with open(stats_path, "w") as f:
    json.dump(stats, f, indent=2)

print(f"Recorded unique round for {new_round['course_name']}: {new_round['score']} ({new_round['to_par']})")
