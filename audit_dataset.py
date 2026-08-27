#!/usr/bin/env python3

import json
import re
from pathlib import Path
from collections import Counter, defaultdict
from pprint import pprint


# ============================================================
# CONFIG
# ============================================================

INPUT_FILE = Path("./dataset/dataset_full.json")

REPORT_JSON = Path("stm32_dataset_audit_v2.json")
REPORT_TXT = Path("stm32_dataset_audit_v2.txt")

# How many records to print when inspecting the schema
SCHEMA_SAMPLE_COUNT = 5

# Maximum number of duplicate groups to include in report
MAX_DUPLICATE_GROUPS = 100

# Maximum examples stored for each suspicious group
MAX_INDICES_PER_GROUP = 30


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_text(value):
    """
    Conservative text normalization.

    IMPORTANT:
    This is NOT semantic similarity.
    We only use it for exact/near-exact duplicate analysis.
    """

    if value is None:
        return ""

    if not isinstance(value, str):
        value = json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False
        )

    value = value.lower().strip()

    # Normalize whitespace
    value = re.sub(r"\s+", " ", value)

    # Normalize common punctuation spacing
    value = re.sub(r"\s*,\s*", ",", value)
    value = re.sub(r"\s*;\s*", ";", value)

    return value


# ============================================================
# RECURSIVE FIELD SEARCH
# ============================================================

def find_all_keys(obj, target_key, path=""):
    """
    Recursively find every occurrence of target_key.

    Returns:
        [
            {
                "path": "...",
                "value": ...
            }
        ]
    """

    results = []

    if isinstance(obj, dict):

        for key, value in obj.items():

            current_path = (
                f"{path}.{key}"
                if path
                else key
            )

            if key == target_key:
                results.append({
                    "path": current_path,
                    "value": value
                })

            results.extend(
                find_all_keys(
                    value,
                    target_key,
                    current_path
                )
            )

    elif isinstance(obj, list):

        for index, value in enumerate(obj):

            current_path = f"{path}[{index}]"

            results.extend(
                find_all_keys(
                    value,
                    target_key,
                    current_path
                )
            )

    return results


def find_keys_case_insensitive(obj, target_keys):
    """
    Find fields recursively, ignoring capitalization.
    """

    target_keys = {
        key.lower()
        for key in target_keys
    }

    results = []

    def walk(value, path=""):

        if isinstance(value, dict):

            for key, child in value.items():

                current_path = (
                    f"{path}.{key}"
                    if path
                    else key
                )

                if str(key).lower() in target_keys:

                    results.append({
                        "key": key,
                        "path": current_path,
                        "value": child
                    })

                walk(child, current_path)

        elif isinstance(value, list):

            for i, child in enumerate(value):
                walk(child, f"{path}[{i}]")

    walk(obj)

    return results


# ============================================================
# FIELD EXTRACTION
# ============================================================

PROMPT_KEYS = {
    "prompt",
    "clean_prompt",
    "instruction",
    "input",
    "query",
    "user_prompt"
}

OUTPUT_KEYS = {
    "output",
    "response",
    "answer",
    "completion",
    "target"
}

INTENT_KEYS = {
    "intent",
    "task",
    "intent_type"
}

STATUS_KEYS = {
    "status",
    "label",
    "classification",
    "result"
}

COMPLEXITY_KEYS = {
    "complexity",
    "difficulty"
}

NOISE_KEYS = {
    "noise",
    "noise_level"
}

CATEGORY_KEYS = {
    "category",
    "type"
}


def extract_first_value(record, keys):
    """
    Find the first useful occurrence of one of the keys.
    """

    results = find_keys_case_insensitive(
        record,
        keys
    )

    for result in results:

        value = result["value"]

        if value is None:
            continue

        if isinstance(value, str):

            if value.strip():
                return {
                    "key": result["key"],
                    "path": result["path"],
                    "value": value
                }

        else:

            return {
                "key": result["key"],
                "path": result["path"],
                "value": value
            }

    return None


# ============================================================
# OUTPUT SIGNATURE
# ============================================================

def canonicalize(value):
    """
    Produce a stable representation of structured JSON.

    Dictionary ordering does not affect the signature.
    """

    if isinstance(value, dict):

        return {
            key: canonicalize(value[key])
            for key in sorted(value)
        }

    if isinstance(value, list):

        return [
            canonicalize(x)
            for x in value
        ]

    return value


def output_signature(value):
    """
    Stable output signature for duplicate analysis.
    """

    if value is None:
        return ""

    if isinstance(value, str):
        return normalize_text(value)

    return json.dumps(
        canonicalize(value),
        sort_keys=True,
        ensure_ascii=False
    )


# ============================================================
# PERIPHERAL EXTRACTION
# ============================================================

KNOWN_PERIPHERALS = [
    "RCC",

    "GPIOA",
    "GPIOB",
    "GPIOC",
    "GPIOD",
    "GPIOE",

    "USART1",
    "USART2",
    "USART3",

    "TIM1",
    "TIM2",
    "TIM3",
    "TIM4"
]


def find_peripherals(record):
    """
    Search the entire record for known STM32 peripherals.

    This is for statistics only.
    It does NOT determine whether the example is correct.
    """

    text = json.dumps(
        record,
        ensure_ascii=False
    ).upper()

    found = set()

    for peripheral in KNOWN_PERIPHERALS:

        if peripheral in text:
            found.add(peripheral)

    return sorted(found)


# ============================================================
# LOAD DATASET
# ============================================================

print("=" * 80)
print("STM32F103VB DATASET AUDIT V2")
print("=" * 80)

print(f"\nInput: {INPUT_FILE}")

if not INPUT_FILE.exists():

    raise FileNotFoundError(
        f"\nCould not find:\n{INPUT_FILE}\n\n"
        "Change INPUT_FILE at the top of the script "
        "to the actual dataset path."
    )


with open(
    INPUT_FILE,
    "r",
    encoding="utf-8"
) as f:

    raw_data = json.load(f)


# ============================================================
# DETERMINE DATASET CONTAINER
# ============================================================

if isinstance(raw_data, list):

    dataset = raw_data
    container_type = "top_level_list"

elif isinstance(raw_data, dict):

    container_type = "top_level_object"

    possible_fields = [
        "data",
        "dataset",
        "examples",
        "records",
        "items"
    ]

    dataset = None

    for field in possible_fields:

        if isinstance(raw_data.get(field), list):

            dataset = raw_data[field]

            print(
                f"\nFound dataset under key: {field}"
            )

            break

    if dataset is None:

        raise ValueError(
            "Top-level JSON is an object, but "
            "no dataset list was found."
        )

else:

    raise ValueError(
        "Unsupported JSON structure."
    )


total = len(dataset)


# ============================================================
# SCHEMA INSPECTION
# ============================================================

print("\n")
print("=" * 80)
print("SCHEMA INSPECTION")
print("=" * 80)

print(
    f"\nContainer type: {container_type}"
)

print(
    f"Number of records: {total}"
)

print(
    f"\nShowing first {min(SCHEMA_SAMPLE_COUNT, total)} records:\n"
)


for i, record in enumerate(
    dataset[:SCHEMA_SAMPLE_COUNT]
):

    print("-" * 80)
    print(f"RECORD {i}")
    print("-" * 80)

    if isinstance(record, dict):

        print(
            "Top-level keys:"
        )

        print(
            list(record.keys())
        )

        print("\nRecord:")

        pprint(
            record,
            sort_dicts=False,
            width=120
        )

    else:

        print(
            f"Record type: {type(record).__name__}"
        )

        pprint(record)


# ============================================================
# COUNTERS
# ============================================================

intent_counter = Counter()
status_counter = Counter()
complexity_counter = Counter()
noise_counter = Counter()
category_counter = Counter()
peripheral_counter = Counter()

field_paths = defaultdict(Counter)

missing_fields = Counter()

invalid_records = []

error_records = []
ambiguous_records = []


# ============================================================
# DUPLICATE GROUPS
# ============================================================

prompt_groups = defaultdict(list)

prompt_output_groups = defaultdict(list)

prompt_to_outputs = defaultdict(
    lambda: defaultdict(list)
)


# ============================================================
# PROCESS RECORDS
# ============================================================

for index, record in enumerate(dataset):

    if not isinstance(record, dict):

        invalid_records.append({
            "index": index,
            "reason": "Record is not an object"
        })

        continue


    # --------------------------------------------------------
    # PROMPT
    # --------------------------------------------------------

    prompt_info = extract_first_value(
        record,
        PROMPT_KEYS
    )

    if prompt_info is None:

        missing_fields["prompt"] += 1
        prompt = ""

    else:

        prompt = prompt_info["value"]

        field_paths["prompt"][
            prompt_info["path"]
        ] += 1


    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

    output_info = extract_first_value(
        record,
        OUTPUT_KEYS
    )

    if output_info is None:

        missing_fields["output"] += 1
        output = None

    else:

        output = output_info["value"]

        field_paths["output"][
            output_info["path"]
        ] += 1


    # --------------------------------------------------------
    # INTENT
    # --------------------------------------------------------

    intent_info = extract_first_value(
        record,
        INTENT_KEYS
    )

    if intent_info is None:

        missing_fields["intent"] += 1

    else:

        field_paths["intent"][
            intent_info["path"]
        ] += 1

        intent = intent_info["value"]

        if isinstance(intent, (dict, list)):

            intent = json.dumps(
                intent,
                sort_keys=True
            )

        intent_counter[str(intent)] += 1


    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    status_info = extract_first_value(
        record,
        STATUS_KEYS
    )

    if status_info is None:

        missing_fields["status"] += 1

    else:

        field_paths["status"][
            status_info["path"]
        ] += 1

        status = status_info["value"]

        if isinstance(status, (dict, list)):

            status = json.dumps(
                status,
                sort_keys=True
            )

        status_counter[str(status)] += 1


    # --------------------------------------------------------
    # COMPLEXITY
    # --------------------------------------------------------

    complexity_info = extract_first_value(
        record,
        COMPLEXITY_KEYS
    )

    if complexity_info is None:

        missing_fields["complexity"] += 1

    else:

        field_paths["complexity"][
            complexity_info["path"]
        ] += 1

        complexity = complexity_info["value"]

        complexity_counter[
            str(complexity)
        ] += 1


    # --------------------------------------------------------
    # NOISE
    # --------------------------------------------------------

    noise_info = extract_first_value(
        record,
        NOISE_KEYS
    )

    if noise_info is None:

        missing_fields["noise"] += 1

    else:

        field_paths["noise"][
            noise_info["path"]
        ] += 1

        noise = noise_info["value"]

        noise_counter[
            str(noise)
        ] += 1


    # --------------------------------------------------------
    # CATEGORY
    # --------------------------------------------------------

    category_info = extract_first_value(
        record,
        CATEGORY_KEYS
    )

    if category_info is None:

        missing_fields["category"] += 1

    else:

        field_paths["category"][
            category_info["path"]
        ] += 1

        category = category_info["value"]

        category_counter[
            str(category)
        ] += 1


    # --------------------------------------------------------
    # PERIPHERALS
    # --------------------------------------------------------

    for peripheral in find_peripherals(record):

        peripheral_counter[
            peripheral
        ] += 1


    # --------------------------------------------------------
    # ERROR / AMBIGUOUS
    # --------------------------------------------------------

    record_text = json.dumps(
        record,
        ensure_ascii=False
    ).upper()

    # This is ONLY a preliminary indicator.
    # We are not calling these true errors yet.

    if (
        "ERROR" in record_text
        or "INVALID" in record_text
    ):

        error_records.append(index)


    if "AMBIGUOUS" in record_text:

        ambiguous_records.append(index)


    # --------------------------------------------------------
    # DUPLICATES
    # --------------------------------------------------------

    normalized_prompt = normalize_text(
        prompt
    )

    normalized_output = output_signature(
        output
    )


    if normalized_prompt:

        prompt_groups[
            normalized_prompt
        ].append(index)


    if normalized_prompt and normalized_output:

        pair_key = (
            normalized_prompt
            + " ||| "
            + normalized_output
        )

        prompt_output_groups[
            pair_key
        ].append(index)

        prompt_to_outputs[
            normalized_prompt
        ][normalized_output].append(index)


# ============================================================
# DUPLICATE ANALYSIS
# ============================================================

exact_duplicate_prompt_groups = {

    prompt: indices

    for prompt, indices
    in prompt_groups.items()

    if len(indices) > 1
}


exact_duplicate_pair_groups = {

    pair: indices

    for pair, indices
    in prompt_output_groups.items()

    if len(indices) > 1
}


# Same prompt, but multiple distinct outputs
same_prompt_multiple_outputs = {

    prompt: outputs

    for prompt, outputs
    in prompt_to_outputs.items()

    if len(outputs) > 1
}


# ============================================================
# DUPLICATE COUNTS
# ============================================================

duplicate_prompt_records = sum(
    len(indices) - 1
    for indices
    in exact_duplicate_prompt_groups.values()
)


duplicate_pair_records = sum(
    len(indices) - 1
    for indices
    in exact_duplicate_pair_groups.values()
)


# ============================================================
# POTENTIAL CONFLICTS
# ============================================================

potential_conflicts = []

for prompt, outputs in same_prompt_multiple_outputs.items():

    output_entries = []

    for output_signature_value, indices in outputs.items():

        output_entries.append({

            "output_signature":
                output_signature_value,

            "count":
                len(indices),

            "indices":
                indices[:MAX_INDICES_PER_GROUP]
        })

    potential_conflicts.append({

        "prompt":
            prompt,

        "number_of_distinct_outputs":
            len(outputs),

        "outputs":
            output_entries
    })


# Sort by number of distinct outputs
potential_conflicts.sort(
    key=lambda x: (
        x["number_of_distinct_outputs"],
        max(
            item["count"]
            for item in x["outputs"]
        )
    ),
    reverse=True
)


# ============================================================
# TOP DUPLICATE PROMPTS
# ============================================================

top_duplicate_prompts = []

sorted_duplicate_groups = sorted(
    exact_duplicate_prompt_groups.items(),
    key=lambda x: len(x[1]),
    reverse=True
)


for prompt, indices in sorted_duplicate_groups[
    :MAX_DUPLICATE_GROUPS
]:

    top_duplicate_prompts.append({

        "prompt":
            prompt,

        "count":
            len(indices),

        "indices":
            indices[:MAX_INDICES_PER_GROUP]
    })


# ============================================================
# FIELD PATH REPORT
# ============================================================

field_path_report = {}

for field, counter in field_paths.items():

    field_path_report[field] = dict(
        counter
    )


# ============================================================
# REPORT OBJECT
# ============================================================

report = {

    "dataset": {

        "input_file":
            str(INPUT_FILE),

        "total_examples":
            total,

        "container_type":
            container_type
    },

    "schema": {

        "field_paths":
            field_path_report
    },

    "intents":
        dict(intent_counter),

    "status":
        dict(status_counter),

    "complexity":
        dict(complexity_counter),

    "noise":
        dict(noise_counter),

    "categories":
        dict(category_counter),

    "peripherals":
        dict(peripheral_counter),

    "missing_fields":
        dict(missing_fields),

    "errors": {

        "preliminary_error_records":
            len(error_records),

        "preliminary_ambiguous_records":
            len(ambiguous_records)
    },

    "uniqueness": {

        "unique_normalized_prompts":
            len(prompt_groups),

        "unique_prompt_output_pairs":
            len(prompt_output_groups),

        "duplicate_prompt_groups":
            len(exact_duplicate_prompt_groups),

        "duplicate_prompt_records":
            duplicate_prompt_records,

        "duplicate_prompt_output_groups":
            len(exact_duplicate_pair_groups),

        "duplicate_prompt_output_records":
            duplicate_pair_records,

        "same_prompt_multiple_distinct_outputs":
            len(same_prompt_multiple_outputs)
    },

    "invalid_records": {

        "count":
            len(invalid_records),

        "examples":
            invalid_records[:50]
    },

    "top_duplicate_prompts":
        top_duplicate_prompts,

    "potential_conflicts":
        potential_conflicts[:MAX_DUPLICATE_GROUPS]
}


# ============================================================
# SAVE JSON REPORT
# ============================================================

with open(
    REPORT_JSON,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        report,
        f,
        indent=2,
        ensure_ascii=False
    )


# ============================================================
# HUMAN READABLE REPORT
# ============================================================

with open(
    REPORT_TXT,
    "w",
    encoding="utf-8"
) as f:

    f.write("=" * 80 + "\n")
    f.write("STM32F103VB DATASET AUDIT V2\n")
    f.write("=" * 80 + "\n\n")


    # --------------------------------------------------------
    # BASIC
    # --------------------------------------------------------

    f.write(
        f"Total examples: {total}\n"
    )

    f.write(
        f"Container type: {container_type}\n"
    )


    # --------------------------------------------------------
    # FIELD PATHS
    # --------------------------------------------------------

    f.write("\n")
    f.write("-" * 80 + "\n")
    f.write("FIELD LOCATIONS\n")
    f.write("-" * 80 + "\n")

    for field, paths in field_path_report.items():

        f.write(
            f"\n[{field}]\n"
        )

        for path, count in sorted(
            paths.items(),
            key=lambda x: x[1],
            reverse=True
        ):

            f.write(
                f"  {path:50s} {count}\n"
            )


    # --------------------------------------------------------
    # INTENTS
    # --------------------------------------------------------

    f.write("\n")
    f.write("-" * 80 + "\n")
    f.write("INTENTS\n")
    f.write("-" * 80 + "\n")

    if intent_counter:

        for key, count in intent_counter.most_common():

            percentage = (
                count / total * 100
            )

            f.write(
                f"{key:35s} "
                f"{count:6d} "
                f"({percentage:6.2f}%)\n"
            )

    else:

        f.write(
            "No intent field detected.\n"
        )


    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    f.write("\n")
    f.write("-" * 80 + "\n")
    f.write("STATUS\n")
    f.write("-" * 80 + "\n")

    if status_counter:

        for key, count in status_counter.most_common():

            percentage = (
                count / total * 100
            )

            f.write(
                f"{key:35s} "
                f"{count:6d} "
                f"({percentage:6.2f}%)\n"
            )

    else:

        f.write(
            "No status field detected.\n"
        )


    # --------------------------------------------------------
    # COMPLEXITY
    # --------------------------------------------------------

    f.write("\n")
    f.write("-" * 80 + "\n")
    f.write("COMPLEXITY\n")
    f.write("-" * 80 + "\n")

    for key, count in complexity_counter.most_common():

        percentage = (
            count / total * 100
        )

        f.write(
            f"{key:35s} "
            f"{count:6d} "
            f"({percentage:6.2f}%)\n"
        )


    # --------------------------------------------------------
    # NOISE
    # --------------------------------------------------------

    f.write("\n")
    f.write("-" * 80 + "\n")
    f.write("NOISE\n")
    f.write("-" * 80 + "\n")

    for key, count in noise_counter.most_common():

        percentage = (
            count / total * 100
        )

        f.write(
            f"{key:35s} "
            f"{count:6d} "
            f"({percentage:6.2f}%)\n"
        )


    # --------------------------------------------------------
    # CATEGORIES
    # --------------------------------------------------------

    f.write("\n")
    f.write("-" * 80 + "\n")
    f.write("CATEGORIES\n")
    f.write("-" * 80 + "\n")

    for key, count in category_counter.most_common():

        percentage = (
            count / total * 100
        )

        f.write(
            f"{key:35s} "
            f"{count:6d} "
            f"({percentage:6.2f}%)\n"
        )


    # --------------------------------------------------------
    # PERIPHERALS
    # --------------------------------------------------------

    f.write("\n")
    f.write("-" * 80 + "\n")
    f.write("PERIPHERALS\n")
    f.write("-" * 80 + "\n")

    for key, count in peripheral_counter.most_common():

        percentage = (
            count / total * 100
        )

        f.write(
            f"{key:35s} "
            f"{count:6d} "
            f"({percentage:6.2f}%)\n"
        )


    # --------------------------------------------------------
    # MISSING
    # --------------------------------------------------------

    f.write("\n")
    f.write("-" * 80 + "\n")
    f.write("MISSING FIELDS\n")
    f.write("-" * 80 + "\n")

    for key, count in missing_fields.items():

        f.write(
            f"{key:35s} {count:6d}\n"
        )


    # --------------------------------------------------------
    # DUPLICATES
    # --------------------------------------------------------

    f.write("\n")
    f.write("-" * 80 + "\n")
    f.write("DUPLICATE ANALYSIS\n")
    f.write("-" * 80 + "\n")

    f.write(
        f"Unique normalized prompts: "
        f"{len(prompt_groups)}\n"
    )

    f.write(
        f"Unique prompt/output pairs: "
        f"{len(prompt_output_groups)}\n"
    )

    f.write(
        f"Duplicate prompt groups: "
        f"{len(exact_duplicate_prompt_groups)}\n"
    )

    f.write(
        f"Duplicate prompt records: "
        f"{duplicate_prompt_records}\n"
    )

    f.write(
        f"Duplicate prompt/output groups: "
        f"{len(exact_duplicate_pair_groups)}\n"
    )

    f.write(
        f"Duplicate prompt/output records: "
        f"{duplicate_pair_records}\n"
    )

    f.write(
        f"Prompts with multiple distinct outputs: "
        f"{len(same_prompt_multiple_outputs)}\n"
    )


    # --------------------------------------------------------
    # ERROR / AMBIGUOUS
    # --------------------------------------------------------

    f.write("\n")
    f.write("-" * 80 + "\n")
    f.write("PRELIMINARY ERROR / AMBIGUITY DETECTION\n")
    f.write("-" * 80 + "\n")

    f.write(
        f"Records containing ERROR/INVALID text: "
        f"{len(error_records)}\n"
    )

    f.write(
        f"Records containing AMBIGUOUS text: "
        f"{len(ambiguous_records)}\n"
    )

    f.write(
        "\nWARNING: These are only text indicators. "
        "They are NOT final error classifications.\n"
    )


    # --------------------------------------------------------
    # TOP DUPLICATES
    # --------------------------------------------------------

    f.write("\n")
    f.write("-" * 80 + "\n")
    f.write("TOP EXACT DUPLICATE PROMPTS\n")
    f.write("-" * 80 + "\n")

    for group in top_duplicate_prompts[:30]:

        f.write(
            f"\nCount: {group['count']}\n"
        )

        f.write(
            f"Prompt: {group['prompt']}\n"
        )

        f.write(
            f"Indices: {group['indices']}\n"
        )


    # --------------------------------------------------------
    # CONFLICTS
    # --------------------------------------------------------

    f.write("\n")
    f.write("-" * 80 + "\n")
    f.write("PROMPTS WITH MULTIPLE DISTINCT OUTPUTS\n")
    f.write("-" * 80 + "\n")

    for conflict in potential_conflicts[:30]:

        f.write(
            f"\nPrompt:\n"
            f"{conflict['prompt']}\n"
        )

        f.write(
            f"Distinct outputs: "
            f"{conflict['number_of_distinct_outputs']}\n"
        )

        for output in conflict["outputs"]:

            f.write(
                f"\n  Count: {output['count']}\n"
            )

            f.write(
                f"  Indices: {output['indices']}\n"
            )

            signature = output[
                "output_signature"
            ]

            # Keep report readable
            if len(signature) > 1000:
                signature = signature[:1000] + "..."

            f.write(
                f"  Output:\n"
                f"  {signature}\n"
            )


# ============================================================
# CONSOLE SUMMARY
# ============================================================

print("\n")
print("=" * 80)
print("AUDIT V2 COMPLETE")
print("=" * 80)

print(
    f"\nTotal examples: {total}"
)

print(
    "\nField locations:"
)

for field, paths in field_path_report.items():

    print(
        f"\n  {field}:"
    )

    for path, count in paths.items():

        print(
            f"    {path}: {count}"
        )


print(
    "\nIntents:"
)

for key, count in intent_counter.most_common():

    print(
        f"  {key:30s} {count}"
    )


print(
    "\nStatus:"
)

for key, count in status_counter.most_common():

    print(
        f"  {key:30s} {count}"
    )


print(
    "\nComplexity:"
)

for key, count in complexity_counter.most_common():

    print(
        f"  {key:30s} {count}"
    )


print(
    "\nNoise:"
)

for key, count in noise_counter.most_common():

    print(
        f"  {key:30s} {count}"
    )


print(
    "\nCategories:"
)

for key, count in category_counter.most_common():

    print(
        f"  {key:30s} {count}"
    )


print(
    "\nPeripherals:"
)

for key, count in peripheral_counter.most_common():

    print(
        f"  {key:30s} {count}"
    )


print(
    "\nMissing fields:"
)

for key, count in missing_fields.items():

    print(
        f"  {key:30s} {count}"
    )


print(
    "\nDuplicate analysis:"
)

print(
    f"  Unique prompts: "
    f"{len(prompt_groups)}"
)

print(
    f"  Unique prompt/output pairs: "
    f"{len(prompt_output_groups)}"
)

print(
    f"  Duplicate prompt groups: "
    f"{len(exact_duplicate_prompt_groups)}"
)

print(
    f"  Duplicate prompt records: "
    f"{duplicate_prompt_records}"
)

print(
    f"  Duplicate prompt/output groups: "
    f"{len(exact_duplicate_pair_groups)}"
)

print(
    f"  Duplicate prompt/output records: "
    f"{duplicate_pair_records}"
)

print(
    f"  Same prompt, different outputs: "
    f"{len(same_prompt_multiple_outputs)}"
)


print(
    "\nReports:"
)

print(
    f"  {REPORT_JSON}"
)

print(
    f"  {REPORT_TXT}"
)

print("\nIMPORTANT:")
print(
    "Do NOT clean/delete records based on this report yet."
)
print(
    "First inspect the schema and conflict statistics."
)