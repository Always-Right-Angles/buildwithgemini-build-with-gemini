# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import json
import os
import re
from typing import Any
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors.agent_engine_sandbox_code_executor import AgentEngineSandboxCodeExecutor
from google.adk.models import Gemini
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.adk.tools.tool_context import ToolContext
from google.cloud import firestore, storage
from google.genai import types

from app.a2ui_utils import a2ui_callback


MODEL = "gemini-3.8-flash"

# Hardcode project ID as a string to avoid project number resolution on Agent Platform
FIRESTORE_PROJECT = "qwiklabs-gcp-01-310a79347b6d"

# Hardcode public Cloud Storage bucket for destination assets
TRAVEL_ASSETS_BUCKET = "wanderlust-travel-assets-310a79347b6d"

# Vertex AI Memory Bank instance (Agent Engine ID)
MEMORY_BANK_ID = "9123051496424865792"

# Agent Platform Code Execution Sandbox on Agent Engine
SANDBOX_RESOURCE_NAME = (
    "projects/724735868902/locations/us-east1/reasoningEngines/9123051496424865792/sandboxEnvironments/1912873155400040448"
)

# Lazy-loaded Firestore client
_db_client = None


def get_db() -> firestore.Client:
    global _db_client
    if _db_client is None:
        _db_client = firestore.Client(project=FIRESTORE_PROJECT)
    return _db_client


# ---------------------------------------------------------
# Firestore Tools (Read & Write)
# ---------------------------------------------------------


def search_destinations(
    query: str = "",
    budget_tier: str = "",
    region: str = "",
) -> list[dict[str, Any]]:
    """Search and filter destinations from the Firestore catalog.

    Args:
        query: Optional search keyword to match destination name, country, tags, or description.
        budget_tier: Optional budget filter: 'budget', 'moderate', or 'luxury'.
        region: Optional geographic region filter: 'Asia', 'Europe', 'North America', 'Americas', etc.

    Returns:
        A list of matching destination summaries from the database.
    """
    db = get_db()
    destinations_ref = db.collection("destinations")
    results = []

    # Stream all destinations and filter in memory for rich multi-field matching
    for doc in destinations_ref.stream():
        data = doc.to_dict()
        data["destination_id"] = doc.id

        # Apply budget filter
        if budget_tier and data.get("budget_tier", "").lower() != budget_tier.lower():
            continue

        # Apply region filter
        if region and data.get("region", "").lower() != region.lower():
            continue

        # Apply keyword query search
        if query:
            q = query.lower()
            text_corpus = (
                f"{data.get('name', '')} {data.get('country', '')} {data.get('region', '')} "
                f"{data.get('description', '')} {' '.join(data.get('tags', []))} "
                f"{' '.join(data.get('highlights', []))}"
            ).lower()
            if q not in text_corpus:
                continue

        results.append(data)

    return results


def get_destination_details(destination_id: str) -> dict[str, Any]:
    """Retrieve full details for a specific destination by its ID.

    Args:
        destination_id: The unique identifier of the destination (e.g. 'kyoto', 'amalfi-coast', 'banff', 'oaxaca', 'reykjavik').

    Returns:
        The destination record dictionary or an error message if not found.
    """
    db = get_db()
    doc_ref = db.collection("destinations").document(destination_id.strip().lower())
    doc = doc_ref.get()

    if not doc.exists:
        return {"error": f"Destination with ID '{destination_id}' was not found in the catalog."}

    data = doc.to_dict()
    data["destination_id"] = doc.id
    return data


def add_destination(
    destination_id: str,
    name: str,
    country: str,
    region: str,
    budget_tier: str,
    estimated_daily_cost_usd: float,
    highlights: list[str],
    description: str,
    best_season: str,
) -> str:
    """Add a new destination or update an existing one in the Firestore database.

    Args:
        destination_id: Unique slug for the destination (e.g. 'tokyo', 'paris', 'cusco').
        name: Common display name (e.g. 'Tokyo', 'Paris').
        country: Country name (e.g. 'Japan', 'France').
        region: Geographic region (e.g. 'Asia', 'Europe', 'South America').
        budget_tier: Expected cost tier: 'budget', 'moderate', or 'luxury'.
        estimated_daily_cost_usd: Estimated average daily cost per person in USD.
        highlights: Key attractions and must-do activities.
        description: A short overview of the destination appeal.
        best_season: Best times of year to visit.

    Returns:
        A confirmation message indicating the destination was saved.
    """
    db = get_db()
    slug = destination_id.strip().lower().replace(" ", "-")

    dest_data = {
        "destination_id": slug,
        "name": name,
        "country": country,
        "region": region,
        "budget_tier": budget_tier.lower(),
        "estimated_daily_cost_usd": float(estimated_daily_cost_usd),
        "highlights": highlights,
        "description": description,
        "best_season": best_season,
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    db.collection("destinations").document(slug).set(dest_data, merge=True)
    return f"Successfully saved destination '{name}' ({slug}) to Firestore!"


def save_itinerary(
    trip_title: str,
    destination_name: str,
    total_days: int,
    estimated_cost_usd: float,
    daily_plan: list[str],
) -> str:
    """Save a personalized travel itinerary to the Firestore database.

    Args:
        trip_title: A title for this travel plan (e.g. '4-Day Cultural Highlights in Kyoto').
        destination_name: The destination name.
        total_days: Number of days in the itinerary.
        estimated_cost_usd: Estimated total cost in USD.
        daily_plan: A list of descriptions or summaries for each day's plan.

    Returns:
        Confirmation message with the generated itinerary ID.
    """
    db = get_db()
    now = datetime.datetime.now(datetime.timezone.utc)
    itinerary_id = f"trip_{now.strftime('%Y%m%d_%H%M%S')}"

    itinerary_data = {
        "itinerary_id": itinerary_id,
        "trip_title": trip_title,
        "destination_name": destination_name,
        "total_days": total_days,
        "estimated_cost_usd": float(estimated_cost_usd),
        "daily_plan": daily_plan,
        "created_at": now.isoformat(),
    }

    db.collection("itineraries").document(itinerary_id).set(itinerary_data)
    return f"Itinerary '{trip_title}' saved successfully with ID: {itinerary_id}."


# ---------------------------------------------------------
# Utility Tools
# ---------------------------------------------------------


def get_weather(query: str) -> str:
    """Simulates a weather check for a destination.

    Args:
        query: The location or city to check weather for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    q = query.lower()
    if "kyoto" in q or "japan" in q:
        return "It's 68°F (20°C) with pleasant, clear skies."
    elif "amalfi" in q or "italy" in q:
        return "It's 75°F (24°C) with warm Mediterranean sunshine."
    elif "banff" in q or "canada" in q:
        return "It's 55°F (13°C) with crisp mountain air and sunshine."
    elif "oaxaca" in q or "mexico" in q:
        return "It's 82°F (28°C) and sunny."
    elif "reykjavik" in q or "iceland" in q:
        return "It's 42°F (6°C) with a brisk breeze and clear night skies for aurora viewing."
    return f"Simulated weather for {query}: 72°F (22°C) and partly cloudy."


def convert_currency(
    amount: float,
    from_currency: str = "USD",
    to_currency: str = "EUR",
) -> dict[str, Any]:
    """Convert an amount from one currency to another using real-time foreign exchange rates.

    Args:
        amount: The monetary amount to convert.
        from_currency: 3-letter currency code to convert from (e.g. 'USD', 'EUR', 'JPY', 'GBP', 'CAD', 'MXN').
        to_currency: 3-letter currency code to convert to (e.g. 'JPY', 'EUR', 'CAD', 'MXN', 'USD').

    Returns:
        A dictionary containing the converted amount, exchange rate, and target currency.
    """
    base = from_currency.strip().upper()
    target = to_currency.strip().upper()
    url = f"https://open.er-api.com/v6/latest/{base}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Wanderlust-Agent/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        rates = data.get("rates", {})
        rate = rates.get(target)
        if rate is None:
            return {"error": f"Currency code '{target}' not found."}
        converted = round(amount * rate, 2)
        return {
            "original_amount": amount,
            "from_currency": base,
            "converted_amount": converted,
            "to_currency": target,
            "exchange_rate": rate,
        }
    except Exception as e:
        return {"error": f"Failed to fetch exchange rates: {str(e)}"}


def get_maps_api_key() -> str:
    key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        from dotenv import load_dotenv
        load_dotenv()
        key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    return key


def geocode_address(address: str) -> dict[str, Any]:
    """Turn a street address, city, or landmark into coordinates using the Google Maps Geocoding API.

    Args:
        address: The address or place to geocode (e.g. 'Kyoto, Japan' or 'Eiffel Tower, Paris').

    Returns:
        A dictionary with the formatted address and location coordinates (latitude, longitude).
    """
    api_key = get_maps_api_key()
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY is not configured in .env."}

    encoded_address = urllib.parse.quote(address)
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_address}&key={api_key}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Wanderlust-Agent/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        if data.get("status") != "OK" or not data.get("results"):
            return {
                "error": f"Geocoding failed for '{address}': {data.get('status')} - {data.get('error_message', 'No results found')}"
            }

        first_result = data["results"][0]
        geometry_loc = first_result.get("geometry", {}).get("location", {})
        return {
            "query": address,
            "formatted_address": first_result.get("formatted_address"),
            "location": {
                "latitude": geometry_loc.get("lat"),
                "longitude": geometry_loc.get("lng"),
            },
        }
    except Exception as e:
        return {"error": f"Failed to call Geocoding API: {str(e)}"}


def search_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "tourist_attraction",
    radius_meters: float = 2000.0,
    max_results: int = 5,
) -> list[dict[str, Any]]:
    """Find nearby places of a given type around a coordinate using Google Maps Places API (New).

    Args:
        latitude: Center latitude coordinate.
        longitude: Center longitude coordinate.
        place_type: Place type to search for (e.g. 'tourist_attraction', 'restaurant', 'museum', 'park', 'cafe').
        radius_meters: Search radius in meters (default 2000 meters).
        max_results: Maximum number of results to return (up to 20).

    Returns:
        A list of place dictionaries with name, address, and location coordinates.
    """
    api_key = get_maps_api_key()
    if not api_key:
        return [{"error": "GOOGLE_MAPS_API_KEY is not configured in .env."}]

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
    }
    body = {
        "includedTypes": [place_type],
        "maxResultCount": min(max(int(max_results), 1), 20),
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                },
                "radius": float(radius_meters),
            }
        },
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        places = []
        for p in data.get("places", []):
            places.append({
                "name": p.get("displayName", {}).get("text", "Unknown"),
                "address": p.get("formattedAddress", "N/A"),
                "location": p.get("location", {}),
            })
        return places
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        return [{"error": f"Places API HTTP error {e.code}: {error_body}"}]
    except Exception as e:
        return [{"error": f"Failed to call Places API: {str(e)}"}]



async def generate_destination_image(
    prompt: str,
    destination_name: str = "",
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """Generate an image for a travel destination or attraction using Gemini and upload it to Cloud Storage.

    Args:
        prompt: Detailed description of the image to generate (e.g. 'A scenic postcard view of Kyoto in autumn with vibrant red maples and traditional wooden pagoda').
        destination_name: Name of the destination or attraction (e.g. 'Kyoto', 'Amalfi Coast').
        tool_context: ToolContext injected by the agent runtime for saving artifacts.

    Returns:
        A dictionary with the generated image filename, destination, and public Cloud Storage URL.
    """
    try:
        genai_client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT, location="global")
        response = genai_client.models.generate_content(
            model="gemini-3.1-flash-image",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )

        image_bytes = None
        mime_type = "image/png"
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if getattr(part, "inline_data", None) and part.inline_data.data:
                    image_bytes = part.inline_data.data
                    if part.inline_data.mime_type:
                        mime_type = part.inline_data.mime_type
                    break

        if not image_bytes:
            return {"error": "Failed to generate image bytes from model response."}

        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", destination_name.strip().lower()) if destination_name else "destination"
        extension = "png" if "png" in mime_type else "jpg"
        filename = f"{slug}_{timestamp}.{extension}"

        # 1. Save artifact in the Playground's Artifacts panel via ToolContext
        if tool_context is not None:
            try:
                artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                await tool_context.save_artifact(filename=filename, artifact=artifact_part)
            except Exception as e:
                print(f"Warning: Failed to save artifact in tool_context: {e}")

        # 2. Upload the same image bytes in-memory to public Cloud Storage bucket
        storage_client = storage.Client(project=FIRESTORE_PROJECT)
        bucket = storage_client.bucket(TRAVEL_ASSETS_BUCKET)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{TRAVEL_ASSETS_BUCKET}/{filename}"
        return {
            "status": "success",
            "destination": destination_name,
            "filename": filename,
            "public_url": public_url,
        }
    except Exception as e:
        return {"error": f"Failed to generate destination image: {str(e)}"}


# ---------------------------------------------------------
# A2UI Schema Manager, Callbacks & Root Agent Configuration
# ---------------------------------------------------------


# WRITE: after each turn, send the session to Memory Bank for extraction.
async def generate_memories_callback(callback_context: CallbackContext) -> None:
    await callback_context.add_session_to_memory()
    return None


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are Wanderlust AI, an expert global travel concierge. "
        "You help travelers discover vacation spots, explore destination highlights, compare costs, "
        "and craft personalized day-by-day itineraries. "
        "You remember the traveler's stated preferences, travel styles, dietary restrictions, and past trip facts "
        "from previous conversations and use them to personalize your recommendations. "
        "Always use your Firestore tools (search_destinations, get_destination_details) to fetch factual "
        "catalog data, convert_currency to compute real-time foreign exchange amounts, and use geocode_address "
        "and search_nearby_places to look up real-world coordinates and local attractions, restaurants, or museums. "
        "Use generate_destination_image to generate scenic travel photos, postcards, or visuals for destinations. "
        "You have Python code execution enabled via a secure Agent Engine sandbox. You can write and execute Python code "
        "to calculate complex multi-destination travel budgets, compare costs, or analyze data. "
        "Use save_itinerary or add_destination when the traveler wants to create or record plans."
    ),
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    # Keep in sync with create_params.root_agent_name in agents-cli-manifest.yaml
    name="starter_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=a2ui_instruction,
    code_executor=AgentEngineSandboxCodeExecutor(
        sandbox_resource_name=SANDBOX_RESOURCE_NAME,
    ),
    tools=[
        PreloadMemoryTool(),
        search_destinations,
        get_destination_details,
        add_destination,
        save_itinerary,
        convert_currency,
        geocode_address,
        search_nearby_places,
        generate_destination_image,
        get_weather,
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
