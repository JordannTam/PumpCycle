import requests
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

def load_response(transactionid: str) -> dict:
    """Load the raw API response from a JSON file."""
    load_dotenv()
    BASE_URL = "https://api.onegov.nsw.gov.au"

    AUTHORIZATION_HEADER = os.getenv("AUTHORIZATION_HEADER")
    API_KEY = os.getenv("API_KEY")

    response = requests.get(f"{BASE_URL}/oauth/client_credential/accesstoken?grant_type=client_credentials", headers={"Authorization": AUTHORIZATION_HEADER})

    token = response.json()["access_token"]

    response = requests.get(f"{BASE_URL}/FuelPriceCheck/v1/fuel/prices", headers={
      "Authorization": f"Bearer {token}",
      "Content-Type": "application/json; charset=utf-8",
      "apikey": API_KEY,
      "transactionid": transactionid,
      "requesttimestamp": (datetime.now() - timedelta(days=2)).strftime("%d/%m/%Y %H:%M:%S"),

    })

    return response.json()

def build_station_lookup(stations: list[dict]) -> dict[str, dict]:
    """Map station code -> station info for fast joining."""
    print(stations)
    return {s["code"]: s for s in stations}

def parse_timestamp(raw: str) -> datetime:
    """FuelCheck uses DD/MM/YYYY HH:MM:SS (Australian format)."""
    return datetime.strptime(raw, "%d/%m/%Y %H:%M:%S")

def write_structured_txt(data: dict, out_path: str) -> int:
    stations = build_station_lookup(data["stations"])
    count = 0

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"FuelCheck snapshot — written {datetime.now():%Y-%m-%d %H:%M}\n")
        f.write("=" * 60 + "\n\n")

        for price in data["prices"]:
            station = stations.get(price["stationcode"])
            if station is None:          # price with no matching station
                continue

            updated = parse_timestamp(price["lastupdated"])
            f.write(f"Station : {station['name']} ({station['brand']})\n")
            f.write(f"Address : {station['address']}\n")
            f.write(f"Fuel    : {price['fueltype']}\n")
            f.write(f"Price   : {price['price']} c/L\n")
            f.write(f"Updated : {updated:%Y-%m-%d %H:%M}\n")
            f.write("-" * 40 + "\n")
            count += 1

    return count

if __name__ == "__main__":
    data = load_response("1234567891")
    written = write_structured_txt(data, "prices_snapshot_2026-08-11.txt")
    print(f"Wrote {written} price records")