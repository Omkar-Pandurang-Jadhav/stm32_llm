import json
import hashlib
import random
import re
from pathlib import Path
from collections import Counter, defaultdict


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = (
    BASE_DIR /
    "stm32_instruction_code_v3_code_only.jsonl"
)

OUTPUT_DIR = (
    BASE_DIR /
    "qwen_dataset"
)

OUTPUT_DIR.mkdir(
    exist_ok=True
)

SEED = 42

TRAIN_RATIO = 0.80
VAL_RATIO = 0.10
TEST_RATIO = 0.10


# ============================================================
# QWEN SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = (
    "You generate pure bare-metal C code for the "
    "STM32F103VB microcontroller.\n\n"
    "Use direct hardware register access to configure "
    "and control peripherals.\n"
    "Do not use STM32 HAL, Standard Peripheral Library "
    "(SPL), STM32 LL drivers, Arduino libraries, or any "
    "other high-level peripheral abstraction or library.\n\n"
    "You may use the STM32F103 CMSIS device header for "
    "register and bit definitions, such as stm32f103xb.h.\n\n"
    "Generate complete compilable C code with the required "
    "headers and main(). The generated code must directly "
    "configure the STM32F103VB hardware through its "
    "peripheral registers."
)


# ============================================================
# NORMALIZE PROMPT
# ============================================================

def normalize_prompt(text):

    if not isinstance(text, str):
        return ""

    text = text.lower()

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    text = re.sub(
        r"\s+([,.!?])",
        r"\1",
        text
    )

    return text


# ============================================================
# EXTRACT INTENTS
# ============================================================

def extract_intents(input_json):

    intents = []

    if not isinstance(
        input_json,
        list
    ):
        return intents

    for block in input_json:

        if not isinstance(
            block,
            dict
        ):
            continue

        intent = block.get(
            "intent"
        )

        if intent:
            intents.append(
                intent
            )

    return intents


# ============================================================
# LOAD DATASET
# ============================================================

def load_dataset():

    records = []

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        for line_number, line in enumerate(
            f,
            start=1
        ):

            line = line.strip()

            if not line:
                continue

            try:

                record = json.loads(
                    line
                )

            except json.JSONDecodeError as e:

                print(
                    f"[ERROR] Invalid JSON "
                    f"at line {line_number}: {e}"
                )

                continue

            instruction = record.get(
                "instruction"
            )

            code = record.get(
                "response"
            )

            input_json = record.get(
                "input_json",
                []
            )

            if not instruction:
                continue

            if not code:
                continue

            records.append({

                "id": record.get(
                    "id"
                ),

                "instruction": instruction,

                "clean_instruction": record.get(
                    "clean_instruction",
                    instruction
                ),

                "input_json": input_json,

                "response": code,

                "task_type": record.get(
                    "task_type",
                    "code_generation"
                ),

                "mcu": record.get(
                    "mcu",
                    "STM32F103VB"
                ),

                "bare_metal": record.get(
                    "bare_metal",
                    True
                ),

                "uses_hal": record.get(
                    "uses_hal",
                    False
                ),

                "uses_spl": record.get(
                    "uses_spl",
                    False
                ),

                "intents": extract_intents(
                    input_json
                )
            })

    return records


# ============================================================
# EXACT DUPLICATE REMOVAL
# ============================================================

def record_hash(
    instruction,
    code
):

    content = (
        normalize_prompt(
            instruction
        )
        + "\n"
        + code.strip()
    )

    return hashlib.sha256(
        content.encode(
            "utf-8"
        )
    ).hexdigest()


def remove_exact_duplicates(
    records
):

    seen = set()

    unique = []

    duplicates = []

    for record in records:

        key = record_hash(
            record["instruction"],
            record["response"]
        )

        if key in seen:

            duplicates.append(
                record
            )

            continue

        seen.add(
            key
        )

        unique.append(
            record
        )

    return unique, duplicates


# ============================================================
# CONFLICT DETECTION
# ============================================================

def find_conflicting_prompts(
    records
):

    prompt_outputs = defaultdict(
        set
    )

    prompt_records = defaultdict(
        list
    )

    for record in records:

        prompt = normalize_prompt(
            record["instruction"]
        )

        output_hash = hashlib.sha256(
            record["response"]
            .strip()
            .encode("utf-8")
        ).hexdigest()

        prompt_outputs[
            prompt
        ].add(
            output_hash
        )

        prompt_records[
            prompt
        ].append(
            record
        )

    conflicts = set()

    for prompt, outputs in (
        prompt_outputs.items()
    ):

        if len(outputs) > 1:
            conflicts.add(
                prompt
            )

    return conflicts, prompt_records


# ============================================================
# REMOVE CONFLICTING PROMPT GROUPS
# ============================================================

def remove_conflicting_groups(
    records,
    conflicts
):

    clean = []

    removed = []

    for record in records:

        prompt = normalize_prompt(
            record["instruction"]
        )

        if prompt in conflicts:

            removed.append(
                record
            )

        else:

            clean.append(
                record
            )

    return clean, removed


# ============================================================
# GROUP BY NORMALIZED PROMPT
# ============================================================

def create_prompt_groups(
    records
):

    groups = defaultdict(
        list
    )

    for record in records:

        prompt = normalize_prompt(
            record["instruction"]
        )

        groups[
            prompt
        ].append(
            record
        )

    return groups


# ============================================================
# SPLIT BY PROMPT GROUP
# ============================================================

def split_groups(
    groups
):

    random.seed(
        SEED
    )

    group_items = list(
        groups.items()
    )

    random.shuffle(
        group_items
    )

    total_groups = len(
        group_items
    )

    train_end = int(
        total_groups *
        TRAIN_RATIO
    )

    val_end = (
        train_end
        +
        int(
            total_groups *
            VAL_RATIO
        )
    )

    train_groups = group_items[
        :train_end
    ]

    val_groups = group_items[
        train_end:val_end
    ]

    test_groups = group_items[
        val_end:
    ]

    def flatten(
        group_list
    ):

        result = []

        for _, records in group_list:

            result.extend(
                records
            )

        return result

    return (
        flatten(train_groups),
        flatten(val_groups),
        flatten(test_groups)
    )


# ============================================================
# CONVERT TO QWEN FORMAT
# ============================================================

def convert_to_qwen(
    record
):

    return {

        "messages": [

            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },

            {
                "role": "user",
                "content": record[
                    "instruction"
                ]
            },

            {
                "role": "assistant",
                "content": record[
                    "response"
                ]
            }

        ]
    }


# ============================================================
# WRITE JSONL
# ============================================================

def write_jsonl(
    path,
    records
):

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        for record in records:

            f.write(
                json.dumps(
                    record,
                    ensure_ascii=False
                )
                + "\n"
            )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print(
        "STM32F103VB FINAL QWEN DATASET PREPARATION"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # LOAD
    # --------------------------------------------------------

    original = load_dataset()

    print()
    print(
        f"Original records           : "
        f"{len(original)}"
    )

    # --------------------------------------------------------
    # EXACT DUPLICATES
    # --------------------------------------------------------

    unique, duplicates = (
        remove_exact_duplicates(
            original
        )
    )

    print(
        f"Exact duplicates removed   : "
        f"{len(duplicates)}"
    )

    print(
        f"After duplicate removal    : "
        f"{len(unique)}"
    )

    # --------------------------------------------------------
    # CONFLICTS
    # --------------------------------------------------------

    conflicts, prompt_records = (
        find_conflicting_prompts(
            unique
        )
    )

    print(
        f"Conflicting prompt groups  : "
        f"{len(conflicts)}"
    )

    # --------------------------------------------------------
    # SAVE CONFLICTS
    # --------------------------------------------------------

    conflict_records = []

    for prompt in sorted(
        conflicts
    ):

        conflict_records.append({

            "prompt": prompt,

            "records": prompt_records[
                prompt
            ]

        })

    write_jsonl(
        OUTPUT_DIR /
        "excluded_conflicts.jsonl",
        conflict_records
    )

    # --------------------------------------------------------
    # REMOVE CONFLICT GROUPS
    # --------------------------------------------------------

    clean, removed_conflicts = (
        remove_conflicting_groups(
            unique,
            conflicts
        )
    )

    print(
        f"Records removed for conflicts: "
        f"{len(removed_conflicts)}"
    )

    print(
        f"Final clean records        : "
        f"{len(clean)}"
    )

    # --------------------------------------------------------
    # PROMPT GROUPS
    # --------------------------------------------------------

    groups = create_prompt_groups(
        clean
    )

    print(
        f"Final unique prompt groups : "
        f"{len(groups)}"
    )

    # --------------------------------------------------------
    # SPLIT
    # --------------------------------------------------------

    train_records, val_records, test_records = (
        split_groups(
            groups
        )
    )

    print()
    print(
        f"Train records               : "
        f"{len(train_records)}"
    )

    print(
        f"Validation records          : "
        f"{len(val_records)}"
    )

    print(
        f"Test records                : "
        f"{len(test_records)}"
    )

    # --------------------------------------------------------
    # QWEN FORMAT
    # --------------------------------------------------------

    train_qwen = [
        convert_to_qwen(r)
        for r in train_records
    ]

    val_qwen = [
        convert_to_qwen(r)
        for r in val_records
    ]

    test_qwen = [
        convert_to_qwen(r)
        for r in test_records
    ]

    # --------------------------------------------------------
    # RAW DATA
    # --------------------------------------------------------

    write_jsonl(
        OUTPUT_DIR /
        "train_raw.jsonl",
        train_records
    )

    write_jsonl(
        OUTPUT_DIR /
        "validation_raw.jsonl",
        val_records
    )

    write_jsonl(
        OUTPUT_DIR /
        "test_raw.jsonl",
        test_records
    )

    # --------------------------------------------------------
    # QWEN DATA
    # --------------------------------------------------------

    write_jsonl(
        OUTPUT_DIR /
        "train.jsonl",
        train_qwen
    )

    write_jsonl(
        OUTPUT_DIR /
        "validation.jsonl",
        val_qwen
    )

    write_jsonl(
        OUTPUT_DIR /
        "test.jsonl",
        test_qwen
    )

    # --------------------------------------------------------
    # INTENT DISTRIBUTION
    # --------------------------------------------------------

    intent_counter = Counter()

    for record in clean:

        for intent in record[
            "intents"
        ]:

            intent_counter[
                intent
            ] += 1

    print()
    print(
        "INTENT DISTRIBUTION"
    )
    print(
        "-" * 70
    )

    for intent, count in (
        intent_counter.most_common()
    ):

        print(
            f"{intent:30s}: {count}"
        )

    # --------------------------------------------------------
    # CODE FLAGS
    # --------------------------------------------------------

    bare_metal = sum(
        r["bare_metal"] is True
        for r in clean
    )

    uses_hal = sum(
        r["uses_hal"] is True
        for r in clean
    )

    uses_spl = sum(
        r["uses_spl"] is True
        for r in clean
    )

    print()
    print(
        "CODE FLAGS"
    )
    print(
        "-" * 70
    )

    print(
        f"Bare-metal                 : "
        f"{bare_metal}"
    )

    print(
        f"Uses HAL                   : "
        f"{uses_hal}"
    )

    print(
        f"Uses SPL                   : "
        f"{uses_spl}"
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    summary = {

        "original_records": len(
            original
        ),

        "exact_duplicates_removed": len(
            duplicates
        ),

        "records_after_duplicates": len(
            unique
        ),

        "conflicting_prompt_groups": len(
            conflicts
        ),

        "records_removed_for_conflicts": len(
            removed_conflicts
        ),

        "final_clean_records": len(
            clean
        ),

        "unique_prompt_groups": len(
            groups
        ),

        "train_records": len(
            train_records
        ),

        "validation_records": len(
            val_records
        ),

        "test_records": len(
            test_records
        ),

        "seed": SEED,

        "system_prompt": SYSTEM_PROMPT,

        "intent_distribution": dict(
            intent_counter
        ),

        "bare_metal_records": bare_metal,

        "hal_records": uses_hal,

        "spl_records": uses_spl
    }

    with open(
        OUTPUT_DIR /
        "dataset_summary.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            summary,
            f,
            indent=2,
            ensure_ascii=False
        )

    # --------------------------------------------------------
    # DONE
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print(
        "FINAL DATASET READY FOR QWEN"
    )
    print("=" * 70)

    print()
    print(
        f"Output directory:"
    )

    print(
        OUTPUT_DIR
    )

    print()
    print(
        "Files:"
    )

    print(
        "  train.jsonl"
    )

    print(
        "  validation.jsonl"
    )

    print(
        "  test.jsonl"
    )

    print(
        "  train_raw.jsonl"
    )

    print(
        "  validation_raw.jsonl"
    )

    print(
        "  test_raw.jsonl"
    )

    print(
        "  excluded_conflicts.jsonl"
    )

    print(
        "  dataset_summary.json"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()