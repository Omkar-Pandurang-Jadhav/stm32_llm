import json
import re
import os

FILES = [
    "simple_dataset.json",
    "complex_dataset.json",
    "dataset_full.json"
]

OUTPUT_SUFFIX = "_clean"


def is_valid_example(example):
    if "output" not in example:
        return False

    outputs = example["output"]

    if not isinstance(outputs, list) or len(outputs) == 0:
        return False

    for intent in outputs:

        # ❌ INVALID intent
        if intent.get("intent") == "INVALID":
            return False

        peripheral = intent.get("peripheral", "")
        config     = intent.get("config", {})

        # ❌ GPIO must have port & pin
        if peripheral == "GPIO":
            if "port" not in config or "pin" not in config:
                return False

        # ❌ UART must have baudrate
        if "USART" in peripheral:
            if "baudrate" not in config:
                return False

        # ❌ TIMER delay mismatch
        if intent.get("intent") == "TIMER_DELAY":
            prompt = example.get("prompt", "")

            match = re.search(r"(\d+)\s*ms", prompt)
            if match:
                expected = int(match.group(1))
                actual   = config.get("delay_ms")

                if actual is not None and actual != expected:
                    return False

    return True


def clean_file(filename):
    if not os.path.exists(filename):
        print(f"❌ File not found: {filename}")
        return []

    with open(filename, "r") as f:
        data = json.load(f)

    clean_data = []
    dropped    = 0

    for ex in data:
        if is_valid_example(ex):
            clean_data.append(ex)
        else:
            dropped += 1

    output_file = filename.replace(".json", f"{OUTPUT_SUFFIX}.json")

    with open(output_file, "w") as f:
        json.dump(clean_data, f, indent=2)

    print(f"\n📂 {filename}")
    print(f"Total   : {len(data)}")
    print(f"Kept    : {len(clean_data)}")
    print(f"Dropped : {dropped}")
    print(f"Saved → {output_file}")

    return clean_data


# ───────────── MAIN ─────────────

all_clean_data = []

for file in FILES:
    cleaned = clean_file(file)
    all_clean_data.extend(cleaned)

# 🔥 Optional: merge all cleaned into one file
with open("merged_clean_dataset.json", "w") as f:
    json.dump(all_clean_data, f, indent=2)

print("\n✅ All files cleaned and merged saved as merged_clean_dataset.json")