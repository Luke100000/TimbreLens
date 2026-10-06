import base64
import hashlib
import json
import math
import os
import sys
from html import escape
from pathlib import Path
from statistics import mean

from diskcache import Cache
from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

from timbrelens.enrichment import PROMPT, AudioDescription
from timbrelens.files import atomic_output
from timbrelens.state import load

TRACK_IDS = [
    "USUAN1100001",
    "USUAN1100003",
    "USUAN1100004",
    "USUAN1100005",
    "USUAN1100006",
]
MODELS = [
    "perceptron/perceptron-mk1.5",
    "xiaomi/mimo-v2.6-flash",
    "xiaomi/mimo-v2.6-pro",
    "qwen/qwen3.8-omni-flash",
    "google/gemini-3.8-flash",
    "mistralai/voxtral-small-24b-2507",
]
CATALOG = Path("data/catalog.json")
CACHE = Path(".cache/evaluation")
REPORT = Path("data/evaluation.md")
FIELDS = ("genres", "moods", "instruments")


def request(model: dict, audio: bytes) -> dict:
    parameters = model.get("supported_parameters", [])
    schema = AudioDescription.model_json_schema()

    body = {
        "model": model["id"],
        "temperature": 0,
        "max_tokens": 1600,
        "service_tier": "flex",
        "messages": [
            {
                "role": "system",
                "content": PROMPT + "\nReturn JSON matching this schema:\n" + json.dumps(schema),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "{}"},
                    {
                        "type": "input_audio",
                        "input_audio": {"data": base64.b64encode(audio).decode(), "format": "mp3"},
                    },
                ],
            },
        ],
        "extra_body": {},
    }

    if "structured_outputs" in parameters:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "AudioDescription", "strict": True, "schema": schema},
        }
        body["extra_body"]["provider"] = {"require_parameters": True}

    if "reasoning" in parameters:
        reasoning = model.get("reasoning") or {}
        efforts = reasoning.get("supported_efforts") or ["none", "minimal", "low"]
        choices = ("minimal", "low") if reasoning.get("mandatory") else ("none", "minimal", "low")
        effort = next((value for value in choices if value in efforts), efforts[-1])
        body["extra_body"]["reasoning"] = {"effort": effort, "exclude": True}

    return body


def cost(client: OpenAI, response: dict) -> float | None:
    value = (response.get("usage") or {}).get("cost")

    if value is None:
        try:
            value = client.get(
                "/generation", cast_to=dict[str, object], options={"params": {"id": response["id"]}}
            )["data"].get("total_cost")
        except OpenAIError as error:
            print(f"Cost unavailable: {error}", file=sys.stderr)
            return None

    if value is None:
        return None

    value = float(value)

    return value if math.isfinite(value) and value >= 0 else None


def cell(value: str) -> str:
    return escape(value, quote=False).replace("|", "\\|").replace("\n", "<br>")


def write_report(tracks: list[dict], results: list[dict]) -> None:
    lines = [
        "# Audio enrichment evaluation",
        "",
        "Audio-only predictions with empty metadata (`{}`). References describe whole tracks",
        "and may be incomplete; extra labels are not necessarily wrong.",
        "USD/1k extrapolates observed costs of completed requests, including cached results.",
        "",
        "| Model | Valid | USD/1k |",
        "| --- | ---: | ---: |",
    ]

    for model_id in MODELS:
        attempts = [result for result in results if result["model"] == model_id]
        completed = [result for result in attempts if result["completed"]]
        costs = [result["cost"] for result in completed]
        valid = sum(result["error"] is None for result in attempts)
        price = f"${mean(costs) * 1000:.3f}" if costs and None not in costs else "—"

        lines.append(f"| {cell(model_id)} | {valid}/{len(attempts)} | {price} |")

    for track in tracks:
        preview = track["preview"]
        preview_path = os.path.relpath(CATALOG.parent / preview["path"], REPORT.parent)
        lines.extend(
            [
                "",
                f"## {cell(track['title'])} — {cell(track['source_id'])}",
                "",
                f"[Listen to preview](<{preview_path}>)",
            ]
        )

        if "start" in preview and "duration" in preview:
            lines.extend(
                ["", f"Excerpt: {preview['start']:g}–{preview['start'] + preview['duration']:g} s."]
            )

        lines.extend(
            [
                "",
                "| Model | Description | Genres | Moods | Instruments | Texture | USD |",
                "| --- | --- | --- | --- | --- | --- | ---: |",
            ]
        )
        reference = (
            "Reference",
            track.get("description") or "—",
            *(", ".join(track.get(field, [])) or "—" for field in FIELDS),
            "—",
            "—",
        )
        lines.append("| " + " | ".join(cell(value) for value in reference) + " |")

        for result in results:
            if result["track_id"] != track["source_id"]:
                continue

            price = f"${result['cost']:.7f}" if result["cost"] is not None else "—"

            if result["error"]:
                description = "Failed: " + result["error"]

                if result["raw"]:
                    description += "\nResponse: " + result["raw"]

                columns = (result["model"], description, "—", "—", "—", "—", price)
            else:
                predicted = result["prediction"]
                columns = (
                    result["model"],
                    predicted["summary"],
                    *(", ".join(predicted[field]) or "—" for field in (*FIELDS, "texture")),
                    price,
                )

            lines.append("| " + " | ".join(cell(value) for value in columns) + " |")

    with atomic_output(REPORT) as temporary:
        temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")


def evaluate() -> None:
    load_dotenv(".env")
    key = os.getenv("OPENROUTER_API_KEY")

    if not key:
        raise ValueError("Set OPENROUTER_API_KEY in the environment or .env.")

    lookup = {
        track["source_id"]: track
        for track in load(CATALOG)["tracks"]
        if track["source"] == "incompetech"
    }
    tracks = []

    for track_id in TRACK_IDS:
        track = lookup[track_id]
        audio = (CATALOG.parent / track["preview"]["path"]).read_bytes()

        if hashlib.sha256(audio).hexdigest() != track["preview"]["sha256"]:
            raise ValueError(f"Preview checksum mismatch: {track_id}")

        tracks.append((track, audio))

    results = []

    with (
        OpenAI(
            api_key=key, base_url="https://openrouter.ai/api/v1", timeout=180, max_retries=0
        ) as client,
        Cache(str(CACHE)) as cache,
    ):
        models = {
            model["id"]: model for model in client.get("/models", cast_to=dict[str, object])["data"]
        }

        for model_id in MODELS:
            for track, audio in tracks:
                print(f"{model_id} / {track['source_id']}", file=sys.stderr)
                response = prediction = error_message = observed_cost = None
                raw = None

                try:
                    body = request(models[model_id], audio)
                    cache_key = hashlib.sha256(
                        json.dumps(body, sort_keys=True).encode()
                    ).hexdigest()
                    response = cache.get(cache_key)

                    if response is None:
                        response = client.chat.completions.create(**body).model_dump(mode="json")
                        cache[cache_key] = response

                    observed_cost = response.get("observed_cost")

                    if observed_cost is None:
                        observed_cost = cost(client, response)
                        response["observed_cost"] = observed_cost
                        cache[cache_key] = response

                    choice = response["choices"][0]
                    raw = choice["message"]["content"]

                    if choice["finish_reason"] != "stop":
                        raise ValueError(f"Incomplete response: {choice['finish_reason']}")

                    prediction = AudioDescription.model_validate_json(raw).model_dump()

                except (OpenAIError, ValueError, KeyError, IndexError, TypeError) as error:
                    error_message = str(error)
                    print(f"  Failed: {error}", file=sys.stderr)

                results.append(
                    {
                        "model": model_id,
                        "track_id": track["source_id"],
                        "prediction": prediction,
                        "cost": observed_cost,
                        "error": error_message,
                        "completed": response is not None,
                        "raw": raw,
                    }
                )

    write_report([track for track, _ in tracks], results)
    print(REPORT)
