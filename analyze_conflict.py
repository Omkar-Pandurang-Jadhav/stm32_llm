import json
import hashlib
from pathlib import Path
from collections import Counter


BASE_DIR = Path(__file__).resolve().parent

DATASET = (
    BASE_DIR /
    "stm32_instruction_code_v3_code_only.jsonl"
)

OUTPUT = (
    BASE_DIR /
    "qwen_dataset" /
    "conflict_analysis.txt"
)


def normalize(text):
    return " ".join(
        text.lower().split()
    )


def code_hash(code):
    return hashlib.sha256(
        code.strip().encode("utf-8")
    ).hexdigest()[:12]


# ============================================================
# LOAD
# ============================================================

groups = {}

with open(
    DATASET,
    encoding="utf-8"
) as f:

    for line in f:

        if not line.strip():
            continue

        record = json.loads(line)

        prompt = normalize(
            record["instruction"]
        )

        groups.setdefault(
            prompt,
            []
        ).append(
            record
        )


# ============================================================
# FIND CONFLICTS
# ============================================================

conflicts = {}

for prompt, records in groups.items():

    code_hashes = {
        code_hash(r["response"])
        for r in records
    }

    if len(code_hashes) > 1:

        conflicts[prompt] = records


# ============================================================
# REPORT
# ============================================================

with open(
    OUTPUT,
    "w",
    encoding="utf-8"
) as out:

    out.write(
        f"TOTAL CONFLICTING PROMPTS: "
        f"{len(conflicts)}\n"
    )

    out.write(
        "=" * 90
        + "\n\n"
    )

    for index, (
        prompt,
        records
    ) in enumerate(
        conflicts.items(),
        start=1
    ):

        out.write(
            f"[{index}] PROMPT\n"
        )

        out.write(
            f"{prompt}\n\n"
        )

        out.write(
            f"RECORD COUNT: "
            f"{len(records)}\n\n"
        )

        for j, record in enumerate(
            records,
            start=1
        ):

            out.write(
                f"--- RECORD {j} ---\n"
            )

            out.write(
                f"ID: {record.get('id')}\n"
            )

            out.write(
                f"Intent: "
                f"{record.get('input_json', [{}])[0].get('intent')}\n"
            )

            out.write(
                "INPUT JSON:\n"
            )

            out.write(
                json.dumps(
                    record.get(
                        "input_json",
                        []
                    ),
                    indent=2,
                    ensure_ascii=False
                )
            )

            out.write(
                "\n\n"
            )

            out.write(
                f"CODE HASH: "
                f"{code_hash(record['response'])}\n"
            )

            out.write(
                "CODE:\n"
            )

            out.write(
                record["response"]
            )

            out.write(
                "\n\n"
            )

        out.write(
            "=" * 90
            + "\n\n"
        )


print(
    f"Found {len(conflicts)} conflicting prompts."
)

print(
    f"Full analysis written to:\n{OUTPUT}"
)