#!/usr/bin/env python3

"""
Repair TIMER_DELAY records in the STM32F103VB dataset.

Input:
    dataset/dataset_full_codegen_fixed.json

Output:
    dataset/dataset_full_codegen_timer_fixed.json

Rules:
    1. Read the original natural-language prompt.
    2. Find the delay associated with the TIMER_DELAY operation.
    3. Preserve an explicitly specified timer instance.
    4. If no timer is specified, use the project's TIMER default.
    5. Preserve the project's timer formula:
           prescaler = 7199
           period    = delay_ms * 10
    6. Do not modify GPIO/UART/PWM/RCC records.
    7. Do not modify ERROR/AMBIGUOUS records.
"""

import json
import re
import copy
import sys
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = (
    BASE_DIR
    / "dataset"
    / "dataset_full_codegen_fixed.json"
)

OUTPUT_FILE = (
    BASE_DIR
    / "dataset"
    / "dataset_full_codegen_timer_fixed.json"
)


# ============================================================
# IMPORT EXISTING PROJECT DEFAULTS
# ============================================================

try:

    from json_builder.json_builder import (
        DEFAULTS,
        TIMER_MAP,
    )

except ImportError as exc:

    print("ERROR: Could not import json_builder.py")
    print(exc)
    sys.exit(1)


# ============================================================
# TIMER NAMES
# ============================================================

TIMER_NAMES = {
    "TIM1",
    "TIM2",
    "TIM3",
    "TIM4",
}


# ============================================================
# BASIC HELPERS
# ============================================================

def deep_copy(value):
    return copy.deepcopy(value)


def add_assumed(config, field):

    assumed = config.setdefault(
        "assumed_fields",
        []
    )

    if field not in assumed:
        assumed.append(field)


def get_prompt(example):

    """
    Return the original prompt.

    We intentionally use the original prompt rather than
    clean_prompt because the original wording may contain
    useful timing information.
    """

    prompt = example.get("prompt")

    if prompt is None:
        prompt = example.get("clean_prompt")

    if prompt is None:
        return ""

    return str(prompt)


# ============================================================
# EXPLICIT TIMER EXTRACTION
# ============================================================

def extract_timer(prompt):
    """
    Extract an explicitly mentioned timer.

    Examples:

        "delay 200ms using TIM3"
            -> TIM3

        "wait 500ms on TIM4"
            -> TIM4

        "TIM2 delay 100ms"
            -> TIM2

    Returns:
        timer name or None
    """

    upper = prompt.upper()

    for timer in TIMER_NAMES:

        if re.search(
            rf"\b{timer}\b",
            upper
        ):
            return timer

    return None


# ============================================================
# TIME EXTRACTION
# ============================================================

def extract_all_times(prompt):
    """
    Extract all explicit time durations.

    Supported forms:

        200ms
        200 ms
        2s
        2 sec
        2 seconds

    Returns a list of tuples:

        [
            {
                "value_ms": 200,
                "start": ...,
                "end": ...,
                "text": "200ms"
            }
        ]
    """

    pattern = re.compile(
        r"""
        (?P<value>\d+(?:\.\d+)?)
        \s*
        (?P<unit>
            ms
            |msec
            |milliseconds?
            |s
            |sec
            |seconds?
        )
        """,
        re.IGNORECASE |
        re.VERBOSE
    )

    results = []

    for match in pattern.finditer(prompt):

        value = float(
            match.group("value")
        )

        unit = match.group(
            "unit"
        ).lower()

        if unit.startswith("ms") or \
           unit.startswith("msec") or \
           unit.startswith("millisecond"):

            value_ms = value

        else:

            value_ms = value * 1000.0

        results.append(
            {
                "value_ms": value_ms,
                "start": match.start(),
                "end": match.end(),
                "text": match.group(0),
            }
        )

    return results


# ============================================================
# DETERMINE TIMER DELAY
# ============================================================

def extract_timer_delay(
    prompt,
    timer
):
    """
    Determine which timing value belongs to TIMER_DELAY.

    The important case is a prompt containing multiple
    operations/timing values.

    Example:

        "toggle every 200ms and wait 1000ms using TIM3"

    The TIMER_DELAY should use 1000ms, not 200ms.

    Strategy:
        1. Prefer a time expression near delay/wait/pause/block.
        2. Prefer time near the explicit timer.
        3. If exactly one time exists, use it.
        4. Otherwise return None so the example is flagged
           rather than silently assigning the wrong value.
    """

    times = extract_all_times(
        prompt
    )

    if not times:
        return None, "NO_TIME_FOUND"

    lower = prompt.lower()

    # --------------------------------------------------------
    # TIMER-OPERATION KEYWORDS
    # --------------------------------------------------------

    delay_words = [
        "delay",
        "wait",
        "pause",
        "block",
        "sleep",
    ]

    # --------------------------------------------------------
    # 1. Look for a timing expression occurring after a
    #    TIMER_DELAY keyword.
    # --------------------------------------------------------

    candidates = []

    for time_info in times:

        start = time_info["start"]

        # Look at the text immediately before the time.
        context_start = max(
            0,
            start - 60
        )

        context = lower[
            context_start:start
        ]

        if any(
            word in context
            for word in delay_words
        ):

            candidates.append(
                time_info
            )

    if len(candidates) == 1:

        return (
            candidates[0]["value_ms"],
            "DELAY_KEYWORD"
        )

    # --------------------------------------------------------
    # 2. If timer name is explicitly present, find the time
    #    closest to that timer.
    # --------------------------------------------------------

    if timer:

        timer_matches = list(
            re.finditer(
                rf"\b{timer.lower()}\b",
                lower
            )
        )

        if timer_matches:

            timer_position = (
                timer_matches[0].start()
            )

            closest = min(
                times,
                key=lambda x:
                    abs(
                        x["start"]
                        - timer_position
                    )
            )

            return (
                closest["value_ms"],
                "NEAREST_TIMER"
            )

    # --------------------------------------------------------
    # 3. Exactly one time = unambiguous.
    # --------------------------------------------------------

    if len(times) == 1:

        return (
            times[0]["value_ms"],
            "SINGLE_TIME"
        )

    # --------------------------------------------------------
    # 4. Multiple times with no safe association.
    # --------------------------------------------------------

    return (
        None,
        "MULTIPLE_UNRESOLVED"
    )


# ============================================================
# REPAIR ONE TIMER_DELAY BLOCK
# ============================================================

def repair_timer_delay_block(
    example,
    block
):

    if block.get(
        "intent"
    ) != "TIMER_DELAY":

        return (
            block,
            False,
            None
        )

    block = deep_copy(
        block
    )

    config = block.get(
        "config"
    )

    if not isinstance(
        config,
        dict
    ):
        config = {}
        block["config"] = config

    prompt = get_prompt(
        example
    )

    # --------------------------------------------------------
    # TIMER INSTANCE
    # --------------------------------------------------------

    existing_timer = block.get(
        "peripheral"
    )

    if existing_timer:

        timer = str(
            existing_timer
        ).upper()

    else:

        timer = extract_timer(
            prompt
        )

    # If the prompt doesn't specify a timer,
    # use the project's existing default.

    if not timer:

        timer = str(
            DEFAULTS["TIMER"]["instance"]
        ).upper()

        block["peripheral"] = timer

        add_assumed(
            config,
            "peripheral"
        )

    # --------------------------------------------------------
    # VALIDATE TIMER
    # --------------------------------------------------------

    if timer not in TIMER_MAP:

        return (
            block,
            False,
            "INVALID_TIMER"
        )

    # --------------------------------------------------------
    # EXTRACT CORRECT DELAY FROM PROMPT
    # --------------------------------------------------------

    delay_ms, reason = (
        extract_timer_delay(
            prompt,
            timer
        )
    )

    # --------------------------------------------------------
    # NO SAFE VALUE
    # --------------------------------------------------------

    if delay_ms is None:

        return (
            block,
            False,
            reason
        )

    # --------------------------------------------------------
    # VALIDATE INTEGER DELAY
    # --------------------------------------------------------

    if delay_ms <= 0:

        return (
            block,
            False,
            "NON_POSITIVE_DELAY"
        )

    # --------------------------------------------------------
    # WRITE CORRECT DELAY
    # --------------------------------------------------------

    old_delay = config.get(
        "delay_ms"
    )

    if (
        old_delay is None
        or int(float(old_delay))
        != int(round(delay_ms))
    ):

        config["delay_ms"] = int(
            round(delay_ms)
        )

        add_assumed(
            config,
            "delay_ms"
        )

        changed = True

    else:

        changed = False

    # --------------------------------------------------------
    # PROJECT TIMER FORMULA
    # --------------------------------------------------------

    # Preserve the formula used by the existing
    # STM32 project:
    #
    #     PSC = 7199
    #     timer frequency = 10 kHz
    #     period = delay_ms * 10
    #
    # Therefore:

    prescaler = 7199

    period = int(
        round(
            delay_ms * 10
        )
    )

    # --------------------------------------------------------
    # PRESCALER
    # --------------------------------------------------------

    if config.get(
        "prescaler"
    ) != prescaler:

        config["prescaler"] = (
            prescaler
        )

        add_assumed(
            config,
            "prescaler"
        )

        changed = True

    # --------------------------------------------------------
    # PERIOD
    # --------------------------------------------------------

    if config.get(
        "period"
    ) != period:

        config["period"] = (
            period
        )

        add_assumed(
            config,
            "period"
        )

        changed = True

    # --------------------------------------------------------
    # UNIT
    # --------------------------------------------------------

    if config.get(
        "unit"
    ) != "ms":

        config["unit"] = "ms"

        changed = True

    return (
        block,
        changed,
        reason
    )


# ============================================================
# PROCESS DATASET
# ============================================================

def process_dataset(data):

    output = []

    stats = {
        "total_examples": 0,
        "timer_blocks": 0,
        "changed_blocks": 0,
        "already_correct": 0,
        "unable_to_resolve": 0,
    }

    unresolved = []

    for example in data:

        stats[
            "total_examples"
        ] += 1

        item = deep_copy(
            example
        )

        blocks = item.get(
            "output"
        )

        if not isinstance(
            blocks,
            list
        ):

            output.append(
                item
            )

            continue

        new_blocks = []

        for block in blocks:

            if not isinstance(
                block,
                dict
            ):

                new_blocks.append(
                    block
                )

                continue

            if block.get(
                "intent"
            ) != "TIMER_DELAY":

                new_blocks.append(
                    block
                )

                continue

            stats[
                "timer_blocks"
            ] += 1

            repaired, changed, reason = (
                repair_timer_delay_block(
                    item,
                    block
                )
            )

            if changed:

                stats[
                    "changed_blocks"
                ] += 1

            else:

                if reason in {
                    "DELAY_KEYWORD",
                    "NEAREST_TIMER",
                    "SINGLE_TIME",
                }:

                    stats[
                        "already_correct"
                    ] += 1

            if reason in {
                "NO_TIME_FOUND",
                "MULTIPLE_UNRESOLVED",
                "INVALID_TIMER",
                "NON_POSITIVE_DELAY",
            }:

                stats[
                    "unable_to_resolve"
                ] += 1

                unresolved.append(
                    {
                        "id": item.get(
                            "id"
                        ),
                        "prompt": get_prompt(
                            item
                        ),
                        "reason": reason,
                        "block": repaired,
                    }
                )

            new_blocks.append(
                repaired
            )

        item["output"] = (
            new_blocks
        )

        output.append(
            item
        )

    return (
        output,
        stats,
        unresolved
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print(
        "STM32F103VB TIMER_DELAY REPAIR"
    )
    print("=" * 70)

    print()
    print(
        f"Input : {INPUT_FILE}"
    )

    print(
        f"Output: {OUTPUT_FILE}"
    )

    print()

    if not INPUT_FILE.exists():

        print(
            "ERROR: Input file not found."
        )

        print(
            INPUT_FILE
        )

        sys.exit(1)

    # --------------------------------------------------------
    # LOAD
    # --------------------------------------------------------

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        data = json.load(f)

    print(
        f"Loaded {len(data):,} examples."
    )

    # --------------------------------------------------------
    # PROCESS
    # --------------------------------------------------------

    repaired_data, stats, unresolved = (
        process_dataset(
            data
        )
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            repaired_data,
            f,
            indent=2,
            ensure_ascii=False
        )

    # --------------------------------------------------------
    # REPORT
    # --------------------------------------------------------

    print()
    print("-" * 70)
    print("REPAIR RESULT")
    print("-" * 70)

    print(
        f"Total examples          : "
        f"{stats['total_examples']:,}"
    )

    print(
        f"TIMER_DELAY blocks      : "
        f"{stats['timer_blocks']:,}"
    )

    print(
        f"Blocks changed          : "
        f"{stats['changed_blocks']:,}"
    )

    print(
        f"Already correct         : "
        f"{stats['already_correct']:,}"
    )

    print(
        f"Unable to resolve       : "
        f"{stats['unable_to_resolve']:,}"
    )

    # --------------------------------------------------------
    # SHOW UNRESOLVED
    # --------------------------------------------------------

    if unresolved:

        print()
        print(
            "-" * 70
        )

        print(
            "UNRESOLVED TIMER_DELAY EXAMPLES"
        )

        print(
            "-" * 70
        )

        for item in unresolved[:30]:

            print()
            print(
                f"ID     : {item['id']}"
            )

            print(
                f"Prompt : {item['prompt']}"
            )

            print(
                f"Reason : {item['reason']}"
            )

    else:

        print()
        print(
            "SUCCESS: All TIMER_DELAY records "
            "were resolved."
        )

    print()
    print(
        "Saved:"
    )

    print(
        OUTPUT_FILE
    )

    print()
    print(
        "Original dataset was NOT modified."
    )

    print("=" * 70)


if __name__ == "__main__":
    main()