#!/usr/bin/env python3

"""
STM32F103VB Dataset JSON Completer

Purpose
-------
Take the existing dataset_full.json and make every VALID JSON block
self-contained for the JSON -> C code generation stage.

IMPORTANT:
    - Original dataset is NOT modified.
    - Hardware mappings come from json_builder.py.
    - Existing values are preserved.
    - Missing values are completed only where they can be determined
      from the existing JSON + project's hardware/default tables.
    - INVALID / UNKNOWN / AMBIGUOUS examples are preserved but are
      not sent to the code-generation dataset.

Output:
    dataset/dataset_full_codegen.json

This is a DATASET PREPARATION step.
It does not change inference behavior.
"""

import json
from pathlib import Path
import sys


# ============================================================
# PATH SETUP
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = BASE_DIR / "dataset" / "dataset_full.json"

OUTPUT_FILE = (
    BASE_DIR
    / "dataset"
    / "dataset_full_codegen.json"
)


# ============================================================
# IMPORT EXISTING STM32 KNOWLEDGE
# ============================================================

# Adjust this import if your json_builder.py is located elsewhere.

try:

    from json_builder.json_builder import (
        SYSTEM_CLOCK,
        USART_MAP,
        TIMER_MAP,
        DEFAULTS,
        compute_brr,
        build_rcc_block,
    )

except ImportError as e:

    print("\nERROR: Could not import json_builder.py")
    print()
    print("Expected structure:")
    print()
    print("project/")
    print("├── json_builder/")
    print("│   └── json_builder.py")
    print("├── dataset/")
    print("│   └── dataset_full.json")
    print("└── complete_json_for_codegen.py")
    print()
    print("Original error:")
    print(e)

    sys.exit(1)


# ============================================================
# HELPERS
# ============================================================

def deep_copy(obj):
    """
    Simple JSON-safe deep copy.
    """
    return json.loads(json.dumps(obj))


def get_config(block):
    """
    Safely obtain config dictionary.
    """
    config = block.get("config")

    if not isinstance(config, dict):
        config = {}
        block["config"] = config

    return config


def add_assumed(config, field):
    """
    Add a field to assumed_fields without duplicates.
    """
    assumed = config.setdefault(
        "assumed_fields",
        []
    )

    if field not in assumed:
        assumed.append(field)


def get_peripheral(block):
    """
    Get peripheral name.
    """
    peripheral = block.get("peripheral")

    if peripheral is None:
        return None

    return str(peripheral).upper()


def get_baudrate(config):
    """
    Safely get baudrate as integer.
    """
    baud = config.get("baudrate")

    if baud is None:
        return None

    try:
        return int(baud)
    except (TypeError, ValueError):
        return None


# ============================================================
# GPIO COMPLETION
# ============================================================

def complete_gpio_output(block):

    config = get_config(block)

    # --------------------------------------------------------
    # MODE
    # --------------------------------------------------------

    if "mode" not in config:

        config["mode"] = (
            DEFAULTS["GPIO"]["mode_output"]
        )

        add_assumed(
            config,
            "mode"
        )

    # --------------------------------------------------------
    # SPEED
    # --------------------------------------------------------

    if "speed" not in config:

        config["speed"] = (
            DEFAULTS["GPIO"]["speed"]
        )

        add_assumed(
            config,
            "speed"
        )

    return block


def complete_gpio_input(block):

    config = get_config(block)

    if "mode" not in config:

        config["mode"] = (
            DEFAULTS["GPIO"]["mode_input"]
        )

        add_assumed(
            config,
            "mode"
        )

    return block


def complete_gpio_toggle(block):

    config = get_config(block)

    # GPIO toggle is an output operation.

    if "mode" not in config:

        config["mode"] = (
            DEFAULTS["GPIO"]["mode_output"]
        )

        add_assumed(
            config,
            "mode"
        )

    if "speed" not in config:

        config["speed"] = (
            DEFAULTS["GPIO"]["speed"]
        )

        add_assumed(
            config,
            "speed"
        )

    timing = block.get("timing")

    if not isinstance(timing, dict):

        timing = {}
        block["timing"] = timing

    if "delay_ms" not in timing:

        timing["delay_ms"] = (
            DEFAULTS["TIMER"]["delay_ms"]
        )

        add_assumed(
            config,
            "delay_ms"
        )

    return block


def complete_gpio_read(block):

    config = get_config(block)

    if "mode" not in config:

        config["mode"] = (
            DEFAULTS["GPIO"]["mode_input"]
        )

        add_assumed(
            config,
            "mode"
        )

    return block


# ============================================================
# UART COMPLETION
# ============================================================

def complete_uart_common(block):

    config = get_config(block)

    uart = get_peripheral(block)

    if uart not in USART_MAP:

        return block

    info = USART_MAP[uart]

    # --------------------------------------------------------
    # BAUDRATE
    # --------------------------------------------------------

    if "baudrate" not in config:

        config["baudrate"] = (
            DEFAULTS["UART"]["baudrate"]
        )

        add_assumed(
            config,
            "baudrate"
        )

    # --------------------------------------------------------
    # WORD LENGTH
    # --------------------------------------------------------

    if "word_length" not in config:

        config["word_length"] = (
            DEFAULTS["UART"]["word_length"]
        )

        add_assumed(
            config,
            "word_length"
        )

    # --------------------------------------------------------
    # PARITY
    # --------------------------------------------------------

    if "parity" not in config:

        config["parity"] = (
            DEFAULTS["UART"]["parity"]
        )

        add_assumed(
            config,
            "parity"
        )

    # --------------------------------------------------------
    # STOP BITS
    # --------------------------------------------------------

    if "stop_bits" not in config:

        config["stop_bits"] = (
            DEFAULTS["UART"]["stop_bits"]
        )

        add_assumed(
            config,
            "stop_bits"
        )

    # --------------------------------------------------------
    # TX PIN
    # --------------------------------------------------------

    if "tx_pin" not in config:

        config["tx_pin"] = deep_copy(
            info["tx"]
        )

        add_assumed(
            config,
            "tx_pin"
        )

    # --------------------------------------------------------
    # RX PIN
    # --------------------------------------------------------

    if "rx_pin" not in config:

        config["rx_pin"] = deep_copy(
            info["rx"]
        )

        add_assumed(
            config,
            "rx_pin"
        )

    return block


def complete_uart_init(block):

    block = complete_uart_common(block)

    config = get_config(block)

    baud = get_baudrate(config)

    if baud is not None:

        # Preserve existing BRR if present.
        if "brr_value" not in config:

            brr = compute_brr(
                8_000_000,
                baud
            )

            config["brr_value"] = hex(brr)

            add_assumed(
                config,
                "brr_value"
            )

    return block


def complete_uart_transmit(block):

    block = complete_uart_common(block)

    config = get_config(block)

    # TRANSMIT doesn't require RX configuration.
    # We can remove RX-related assumptions because TX
    # is the only operation being requested.

    assumed = config.get(
        "assumed_fields",
        []
    )

    if "rx_pin" in assumed:
        assumed.remove("rx_pin")

    if "word_length" in assumed:
        assumed.remove("word_length")

    if "parity" in assumed:
        assumed.remove("parity")

    if "stop_bits" in assumed:
        assumed.remove("stop_bits")

    if not assumed:

        config.pop(
            "assumed_fields",
            None
        )

    return block


def complete_uart_receive(block):

    block = complete_uart_common(block)

    config = get_config(block)

    # RECEIVE doesn't require TX configuration.

    assumed = config.get(
        "assumed_fields",
        []
    )

    if "tx_pin" in assumed:
        assumed.remove("tx_pin")

    if "word_length" in assumed:
        assumed.remove("word_length")

    if "parity" in assumed:
        assumed.remove("parity")

    if "stop_bits" in assumed:
        assumed.remove("stop_bits")

    if not assumed:

        config.pop(
            "assumed_fields",
            None
        )

    return block


# ============================================================
# TIMER COMPLETION
# ============================================================

def complete_timer_delay(block):

    config = get_config(block)

    timer = get_peripheral(block)

    if timer not in TIMER_MAP:

        return block

    if "delay_ms" not in config:

        config["delay_ms"] = (
            DEFAULTS["TIMER"]["delay_ms"]
        )

        add_assumed(
            config,
            "delay_ms"
        )

    # Existing builder uses:
    #
    # prescaler = 7199
    # period = delay_ms * 10
    #
    # Preserve that exact project logic.

    if "prescaler" not in config:

        config["prescaler"] = 7199

        add_assumed(
            config,
            "prescaler"
        )

    if "period" not in config:

        config["period"] = (
            int(config["delay_ms"]) * 10
        )

        add_assumed(
            config,
            "period"
        )

    if "unit" not in config:

        config["unit"] = "ms"

    return block


def complete_timer_pwm(block):

    config = get_config(block)

    timer = get_peripheral(block)

    if timer not in TIMER_MAP:

        return block

    # --------------------------------------------------------
    # CHANNEL
    # --------------------------------------------------------

    if "channel" not in config:

        config["channel"] = (
            DEFAULTS["TIMER"]["channel"]
        )

        add_assumed(
            config,
            "channel"
        )

    # --------------------------------------------------------
    # DUTY
    # --------------------------------------------------------

    if "duty_cycle_percent" not in config:

        config["duty_cycle_percent"] = (
            DEFAULTS["TIMER"]["duty"]
        )

        add_assumed(
            config,
            "duty"
        )

    channel = int(
        config["channel"]
    )

    info = TIMER_MAP[timer]

    if channel not in info["channels"]:

        return block

    # --------------------------------------------------------
    # PRESCALER
    # --------------------------------------------------------

    if "prescaler" not in config:

        config["prescaler"] = 719

        add_assumed(
            config,
            "prescaler"
        )

    # --------------------------------------------------------
    # PERIOD
    # --------------------------------------------------------

    if "period" not in config:

        config["period"] = 999

        add_assumed(
            config,
            "period"
        )

    # --------------------------------------------------------
    # CCR
    # --------------------------------------------------------

    if "ccr_value" not in config:

        duty = float(
            config["duty_cycle_percent"]
        )

        period = int(
            config["period"]
        )

        config["ccr_value"] = int(
            (duty / 100.0) * period
        )

        add_assumed(
            config,
            "ccr_value"
        )

    # --------------------------------------------------------
    # PWM PIN
    # --------------------------------------------------------

    if "pwm_pin" not in config:

        config["pwm_pin"] = deep_copy(
            info["channels"][channel]
        )

        add_assumed(
            config,
            "pwm_pin"
        )

    return block


# ============================================================
# RCC COMPLETION
# ============================================================

def complete_rcc(block):

    peripheral = get_peripheral(block)

    if not peripheral:
        return block

    # If RCC already exists, preserve it.
    if isinstance(
        block.get("rcc"),
        dict
    ) and block["rcc"]:

        return block

    # Otherwise reconstruct it from the existing
    # peripheral name using the project's RCC_MAP.

    rcc = build_rcc_block(
        peripheral
    )

    if rcc:

        block["rcc"] = rcc

    return block


# ============================================================
# BLOCK COMPLETION ROUTER
# ============================================================

def complete_block(block):

    if not isinstance(block, dict):

        return block

    intent = block.get(
        "intent"
    )

    # --------------------------------------------------------
    # ERROR / UNKNOWN / AMBIGUOUS
    # --------------------------------------------------------

    if intent in (
        "ERROR",
        "INVALID",
        "UNKNOWN",
        "AMBIGUOUS"
    ):
        return block

    # --------------------------------------------------------
    # RCC
    # --------------------------------------------------------

    block = complete_rcc(
        block
    )

    # --------------------------------------------------------
    # GPIO
    # --------------------------------------------------------

    if intent == "GPIO_OUTPUT":

        return complete_gpio_output(
            block
        )

    if intent == "GPIO_INPUT":

        return complete_gpio_input(
            block
        )

    if intent == "GPIO_TOGGLE":

        return complete_gpio_toggle(
            block
        )

    if intent == "GPIO_READ":

        return complete_gpio_read(
            block
        )

    # --------------------------------------------------------
    # UART
    # --------------------------------------------------------

    if intent == "UART_INIT":

        return complete_uart_init(
            block
        )

    if intent == "UART_TRANSMIT":

        return complete_uart_transmit(
            block
        )

    if intent == "UART_RECEIVE":

        return complete_uart_receive(
            block
        )

    # --------------------------------------------------------
    # TIMER
    # --------------------------------------------------------

    if intent == "TIMER_DELAY":

        return complete_timer_delay(
            block
        )

    if intent == "TIMER_PWM":

        return complete_timer_pwm(
            block
        )

    return block


# ============================================================
# DATASET PROCESSING
# ============================================================

def process_dataset(data):

    if not isinstance(data, list):

        raise ValueError(
            "dataset_full.json must contain a JSON array"
        )

    output = []

    statistics = {
        "total_examples": 0,
        "valid_examples": 0,
        "invalid_examples": 0,
        "unknown_examples": 0,
        "blocks_completed": 0,
    }

    for example in data:

        statistics["total_examples"] += 1

        item = deep_copy(
            example
        )

        raw_output = item.get(
            "output"
        )

        if not isinstance(
            raw_output,
            list
        ):

            output.append(item)

            continue

        new_blocks = []

        for block in raw_output:

            intent = (
                block.get("intent")
                if isinstance(block, dict)
                else None
            )

            if intent in (
                "ERROR",
                "INVALID",
                "AMBIGUOUS",
                "UNKNOWN"
            ):

                statistics[
                    "invalid_examples"
                ] += 1

                new_blocks.append(
                    block
                )

                continue

            completed = complete_block(
                block
            )

            statistics[
                "blocks_completed"
            ] += 1

            new_blocks.append(
                completed
            )

        item["output"] = new_blocks

        # Valid if at least one block is a
        # supported generation intent.

        valid = any(
            isinstance(block, dict)
            and block.get("intent") in {
                "GPIO_OUTPUT",
                "GPIO_INPUT",
                "GPIO_TOGGLE",
                "GPIO_READ",
                "UART_INIT",
                "UART_TRANSMIT",
                "UART_RECEIVE",
                "TIMER_DELAY",
                "TIMER_PWM",
                "RCC_ENABLE",
            }
            for block in new_blocks
        )

        if valid:

            statistics[
                "valid_examples"
            ] += 1

        output.append(
            item
        )

    return output, statistics


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 65)
    print("STM32F103VB JSON DATASET COMPLETER")
    print("=" * 65)

    print()
    print(f"Input : {INPUT_FILE}")
    print(f"Output: {OUTPUT_FILE}")
    print()

    if not INPUT_FILE.exists():

        print(
            f"ERROR: Input dataset not found:\n"
            f"{INPUT_FILE}"
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

    completed_data, stats = (
        process_dataset(data)
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
            completed_data,
            f,
            indent=2,
            ensure_ascii=False
        )

    # --------------------------------------------------------
    # REPORT
    # --------------------------------------------------------

    print()
    print("-" * 65)
    print("COMPLETION FINISHED")
    print("-" * 65)

    print(
        f"Total examples       : "
        f"{stats['total_examples']:,}"
    )

    print(
        f"Valid examples       : "
        f"{stats['valid_examples']:,}"
    )

    print(
        f"Invalid/ambiguous    : "
        f"{stats['invalid_examples']:,}"
    )

    print(
        f"Completed blocks      : "
        f"{stats['blocks_completed']:,}"
    )

    print()
    print(
        f"Saved to:\n{OUTPUT_FILE}"
    )

    print()
    print(
        "Original dataset was NOT modified."
    )


if __name__ == "__main__":
    main()