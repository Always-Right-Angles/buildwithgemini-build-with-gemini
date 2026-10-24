"""Seed script for populating the Firestore 'destinations' collection.

Hardcodes project ID as required to avoid runtime project number resolution bugs.
"""
from google.cloud import firestore

FIRESTORE_PROJECT = "qwiklabs-gcp-01-310a79347b6d"

DESTINATIONS = [
    {
        "destination_id": "kyoto",
        "name": "Kyoto",
        "country": "Japan",
        "region": "Asia",
        "budget_tier": "moderate",
        "best_season": "Spring (Cherry Blossoms) or Autumn (Foliage)",
        "estimated_daily_cost_usd": 160,
        "highlights": [
            "Fushimi Inari Shrine",
            "Arashiyama Bamboo Grove",
            "Kinkaku-ji Temple",
            "Gion Geisha District",
        ],
        "description": "Ancient cultural capital of Japan with historic wooden temples, Zen rock gardens, and traditional kaiseki cuisine.",
        "tags": ["culture", "history", "temples", "culinary", "walkable"],
    },
    {
        "destination_id": "amalfi-coast",
        "name": "Amalfi Coast",
        "country": "Italy",
        "region": "Europe",
        "budget_tier": "luxury",
        "best_season": "May to September",
        "estimated_daily_cost_usd": 350,
        "highlights": [
            "Positano cliffside village",
            "Path of the Gods hike",
            "Capri boat tour",
            "Ravello cliffside gardens",
        ],
        "description": "Breathtaking Mediterranean coastline with pastel-colored villages perched dramatically over azure waters.",
        "tags": ["scenic", "luxury", "beach", "romantic", "culinary"],
    },
    {
        "destination_id": "banff",
        "name": "Banff National Park",
        "country": "Canada",
        "region": "North America",
        "budget_tier": "moderate",
        "best_season": "Summer (hiking) or Winter (skiing)",
        "estimated_daily_cost_usd": 200,
        "highlights": [
            "Lake Louise turquoise waters",
            "Moraine Lake",
            "Banff Gondola & Hot Springs",
            "Icefields Parkway drive",
        ],
        "description": "Majestic Canadian Rocky Mountain wonderland famous for vibrant glacial lakes, pine forests, and alpine wildlife.",
        "tags": ["nature", "hiking", "mountains", "wildlife", "photography"],
    },
    {
        "destination_id": "oaxaca",
        "name": "Oaxaca City",
        "country": "Mexico",
        "region": "Americas",
        "budget_tier": "budget",
        "best_season": "October to March",
        "estimated_daily_cost_usd": 75,
        "highlights": [
            "Monte Albán Zapotec archaeological site",
            "Hierve el Agua petrified waterfalls",
            "Tlacolula artisan market",
            "Authentic 7-mole tasting",
        ],
        "description": "Vibrant cultural and culinary jewel of southern Mexico renowned for artisan crafts, mezcal distilleries, and indigenous traditions.",
        "tags": ["culture", "culinary", "budget-friendly", "art", "indigenous"],
    },
    {
        "destination_id": "reykjavik",
        "name": "Reykjavik & Golden Circle",
        "country": "Iceland",
        "region": "Europe",
        "budget_tier": "luxury",
        "best_season": "Winter (Northern Lights) or Summer (Midnight Sun)",
        "estimated_daily_cost_usd": 280,
        "highlights": [
            "Blue Lagoon geothermal spa",
            "Gullfoss roaring waterfall",
            "Geysir geothermal field",
            "Thingvellir National Park rift valley",
        ],
        "description": "Land of fire and ice featuring dramatic glaciers, erupting geysers, thermal baths, and cosmic aurora views.",
        "tags": ["adventure", "geothermal", "nature", "aurora", "road-trip"],
    },
]


def seed():
    print(f"Connecting to Firestore for project: {FIRESTORE_PROJECT}...")
    db = firestore.Client(project=FIRESTORE_PROJECT)
    collection_ref = db.collection("destinations")

    for dest in DESTINATIONS:
        doc_id = dest["destination_id"]
        collection_ref.document(doc_id).set(dest)
        print(f"  [OK] Seeded destination: {dest['name']} ({doc_id})")

    print("\n[SUCCESS] Successfully seeded all destinations into Firestore!")


if __name__ == "__main__":
    seed()
