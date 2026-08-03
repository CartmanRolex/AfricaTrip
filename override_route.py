import json

def patch_data_json():
    with open("src/data.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Overwrite the route after Conakry (approx Sept 11 onwards)
    for day in data["days"]:
        if day["date"] >= "2025-09-12":
            if day["location"]:
                day["location"] = "FREETOWN"
            for car in day["cars"].values():
                if "Malaga" in car.get("destination", "") or "Conakry" in car.get("destination", ""):
                    car["destination"] = "Freetown"
                    
    with open("src/data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        
if __name__ == "__main__":
    patch_data_json()
