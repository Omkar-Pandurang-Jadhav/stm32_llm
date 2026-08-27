#!/usr/bin/env python3

"""
============================================================
STM32F103VB Dataset Codegen JSON Repair
============================================================

Purpose
-------
Repair incomplete JSON records in:

    dataset/dataset_full_codegen.json

without modifying the original dataset.

The repair uses the existing:
    json_builder.py

for:
    - STM32 defaults
    - USART mappings
    - TIMER mappings
    - RCC mappings
    - BRR calculation

The goal is to make every VALID hardware JSON block
self-contained before running json_to_c.py.

Pipeline:

    dataset_full.json
          |
          v
    complete_json_for_codegen.py
          |
          v
    dataset_full_codegen.json
          |
          v
    THIS SCRIPT
          |
          v
    dataset_full_codegen_fixed.json
          |
          v
    json_to_c.py
          |
          v
    instruction -> C dataset

IMPORTANT
---------
This script does NOT invent a hardware mapping.

If a default is explicitly defined in json_builder.py,
that default may be materialized.

If the builder does not provide enough information,
the record remains incomplete and is reported.
"""


import json
import sys
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = (
    BASE_DIR
    / "dataset"
    / "dataset_full_codegen.json"
)

OUTPUT_FILE = (
    BASE_DIR
    / "dataset"
    / "dataset_full_codegen_fixed.json"
)


# ============================================================
# IMPORT EXISTING BUILDER KNOWLEDGE
# ============================================================

try:

    from json_builder.json_builder import (
        DEFAULTS,
        USART_MAP,
        TIMER_MAP,
        RCC_MAP,
        compute_brr,
    )

except ImportError as exc:

    print()
    print("ERROR: Could not import json_builder.py")
    print()
    print(
        "Make sure your project has:"
    )
    print()
    print(
        "json_builder/"
    )
    print(
        "    json_builder.py"
    )
    print()
    print(
        "Original error:"
    )
    print(exc)

    sys.exit(1)


# ============================================================
# SUPPORTED HARDWARE INTENTS
# ============================================================

CODEGEN_INTENTS = {
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


NON_CODEGEN_INTENTS = {
    "ERROR",
    "INVALID",
    "UNKNOWN",
    "AMBIGUOUS",
}


# ============================================================
# HELPERS
# ============================================================

def deep_copy(value):
    return json.loads(
        json.dumps(value)
    )


def ensure_config(block):
    config = block.get("config")

    if not isinstance(config, dict):
        config = {}
        block["config"] = config

    return config


def add_assumed(config, field):
    """
    Record that the field was supplied by the
    dataset repair/default mechanism.
    """

    assumed = config.setdefault(
        "assumed_fields",
        []
    )

    if field not in assumed:
        assumed.append(field)


def remove_assumed(config, field):
    assumed = config.get(
        "assumed_fields",
        []
    )

    if field in assumed:
        assumed.remove(field)

    if not assumed:
        config.pop(
            "assumed_fields",
            None
        )


def peripheral(block):
    value = block.get(
        "peripheral"
    )

    if value is None:
        return None

    return str(value).upper()


def int_value(value):
    if value is None:
        return None

    try:
        return int(value)

    except (
        TypeError,
        ValueError
    ):
        return None


def copy_pin(pin):
    if not isinstance(pin, dict):
        return None

    return {
        "port": pin.get("port"),
        "pin": pin.get("pin"),
    }


# ============================================================
# RCC REPAIR
# ============================================================

def repair_rcc(block):
    """
    If a peripheral is known and RCC information is absent,
    reconstruct RCC information from the project's RCC_MAP.

    Existing RCC information is NEVER overwritten.
    """

    if block.get("rcc"):
        return

    periph = peripheral(
        block
    )

    if not periph:
        return

    if periph not in RCC_MAP:
        return

    rcc_info = RCC_MAP[
        periph
    ]

    block["rcc"] = deep_copy(
        rcc_info
    )


# ============================================================
# GPIO REPAIR
# ============================================================

def repair_gpio_output(block):

    config = ensure_config(
        block
    )

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


def repair_gpio_input(block):

    config = ensure_config(
        block
    )

    if "mode" not in config:

        config["mode"] = (
            DEFAULTS["GPIO"]["mode_input"]
        )

        add_assumed(
            config,
            "mode"
        )


def repair_gpio_toggle(block):

    config = ensure_config(
        block
    )

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

    timing = block.get(
        "timing"
    )

    if not isinstance(
        timing,
        dict
    ):
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


def repair_gpio_read(block):

    config = ensure_config(
        block
    )

    if "mode" not in config:

        config["mode"] = (
            DEFAULTS["GPIO"]["mode_input"]
        )

        add_assumed(
            config,
            "mode"
        )


# ============================================================
# UART REPAIR
# ============================================================

def repair_uart_common(block):

    config = ensure_config(
        block
    )

    uart = peripheral(
        block
    )

    if uart not in USART_MAP:
        return

    info = USART_MAP[
        uart
    ]

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
    # TX PIN
    # --------------------------------------------------------

    if "tx_pin" not in config:

        tx = info.get(
            "tx"
        )

        if tx:

            config["tx_pin"] = (
                copy_pin(tx)
            )

            add_assumed(
                config,
                "tx_pin"
            )

    # --------------------------------------------------------
    # RX PIN
    # --------------------------------------------------------

    if "rx_pin" not in config:

        rx = info.get(
            "rx"
        )

        if rx:

            config["rx_pin"] = (
                copy_pin(rx)
            )

            add_assumed(
                config,
                "rx_pin"
            )


def repair_uart_init(block):

    repair_uart_common(
        block
    )

    config = ensure_config(
        block
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
    # BRR
    # --------------------------------------------------------

    if "brr_value" not in config:

        baudrate = int_value(
            config.get(
                "baudrate"
            )
        )

        if baudrate:

            # IMPORTANT:
            # Use the project's existing BRR function.
            brr = compute_brr(
                8_000_000,
                baudrate
            )

            config["brr_value"] = hex(
                brr
            )

            add_assumed(
                config,
                "brr_value"
            )


def repair_uart_transmit(block):

    repair_uart_common(
        block
    )

    config = ensure_config(
        block
    )

    # TX operation only needs TX.
    remove_assumed(
        config,
        "rx_pin"
    )

    remove_assumed(
        config,
        "word_length"
    )

    remove_assumed(
        config,
        "parity"
    )

    remove_assumed(
        config,
        "stop_bits"
    )


def repair_uart_receive(block):

    repair_uart_common(
        block
    )

    config = ensure_config(
        block
    )

    # RX operation only needs RX.
    remove_assumed(
        config,
        "tx_pin"
    )

    remove_assumed(
        config,
        "word_length"
    )

    remove_assumed(
        config,
        "parity"
    )

    remove_assumed(
        config,
        "stop_bits"
    )


# ============================================================
# TIMER DELAY REPAIR
# ============================================================

def repair_timer_delay(block):

    config = ensure_config(
        block
    )

    timer = peripheral(
        block
    )

    # --------------------------------------------------------
    # DEFAULT TIMER INSTANCE
    # --------------------------------------------------------

    if not timer:

        timer = (
            DEFAULTS["TIMER"]["instance"]
        )

        block["peripheral"] = timer

        add_assumed(
            config,
            "peripheral"
        )

    if timer not in TIMER_MAP:

        return

    # --------------------------------------------------------
    # DELAY
    # --------------------------------------------------------

    if "delay_ms" not in config:

        # First try action.delay_ms if it exists.
        action = block.get(
            "action",
            {}
        )

        delay = (
            action.get("delay_ms")
            if isinstance(action, dict)
            else None
        )

        if delay is None:

            delay = (
                DEFAULTS["TIMER"]["delay_ms"]
            )

        config["delay_ms"] = int(
            delay
        )

        add_assumed(
            config,
            "delay_ms"
        )

    # --------------------------------------------------------
    # PRESCALER
    # --------------------------------------------------------

    if "prescaler" not in config:

        # This is the timer setup used by the
        # existing STM32 dataset builder:
        #
        # 72 MHz / (7199 + 1)
        # = 10 kHz timer frequency.
        #
        # Therefore one count = 0.1 ms.
        #
        # period = delay_ms * 10

        config["prescaler"] = 7199

        add_assumed(
            config,
            "prescaler"
        )

    # --------------------------------------------------------
    # PERIOD
    # --------------------------------------------------------

    if "period" not in config:

        delay_ms = int(
            config["delay_ms"]
        )

        config["period"] = (
            delay_ms * 10
        )

        add_assumed(
            config,
            "period"
        )

    # --------------------------------------------------------
    # UNIT
    # --------------------------------------------------------

    if "unit" not in config:

        config["unit"] = "ms"


# ============================================================
# TIMER PWM REPAIR
# ============================================================

def repair_timer_pwm(block):

    config = ensure_config(
        block
    )

    timer = peripheral(
        block
    )

    # --------------------------------------------------------
    # TIMER INSTANCE
    # --------------------------------------------------------

    if not timer:

        timer = (
            DEFAULTS["TIMER"]["instance"]
        )

        block["peripheral"] = timer

        add_assumed(
            config,
            "peripheral"
        )

    if timer not in TIMER_MAP:

        return

    timer_info = TIMER_MAP[
        timer
    ]

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

    channel = int_value(
        config.get(
            "channel"
        )
    )

    if channel is None:
        return

    if channel not in timer_info["channels"]:
        return

    # --------------------------------------------------------
    # DUTY
    # --------------------------------------------------------

    if "duty_cycle_percent" not in config:

        config["duty_cycle_percent"] = (
            DEFAULTS["TIMER"]["duty"]
        )

        add_assumed(
            config,
            "duty_cycle_percent"
        )

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
            config[
                "duty_cycle_percent"
            ]
        )

        period = int(
            config[
                "period"
            ]
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

        pwm_pin = (
            timer_info[
                "channels"
            ][channel]
        )

        config["pwm_pin"] = (
            copy_pin(
                pwm_pin
            )
        )

        add_assumed(
            config,
            "pwm_pin"
        )


# ============================================================
# RCC ENABLE
# ============================================================

def repair_rcc_enable(block):

    repair_rcc(
        block
    )


# ============================================================
# BLOCK REPAIR
# ============================================================

def repair_block(block):

    if not isinstance(
        block,
        dict
    ):
        return block

    intent = block.get(
        "intent"
    )

    # Don't touch error/ambiguous records.
    if intent in NON_CODEGEN_INTENTS:
        return block

    # --------------------------------------------------------
    # RCC
    # --------------------------------------------------------

    repair_rcc(
        block
    )

    # --------------------------------------------------------
    # GPIO
    # --------------------------------------------------------

    if intent == "GPIO_OUTPUT":
        repair_gpio_output(
            block
        )

    elif intent == "GPIO_INPUT":
        repair_gpio_input(
            block
        )

    elif intent == "GPIO_TOGGLE":
        repair_gpio_toggle(
            block
        )

    elif intent == "GPIO_READ":
        repair_gpio_read(
            block
        )

    # --------------------------------------------------------
    # UART
    # --------------------------------------------------------

    elif intent == "UART_INIT":
        repair_uart_init(
            block
        )

    elif intent == "UART_TRANSMIT":
        repair_uart_transmit(
            block
        )

    elif intent == "UART_RECEIVE":
        repair_uart_receive(
            block
        )

    # --------------------------------------------------------
    # TIMER
    # --------------------------------------------------------

    elif intent == "TIMER_DELAY":
        repair_timer_delay(
            block
        )

    elif intent == "TIMER_PWM":
        repair_timer_pwm(
            block
        )

    # --------------------------------------------------------
    # RCC ENABLE
    # --------------------------------------------------------

    elif intent == "RCC_ENABLE":
        repair_rcc_enable(
            block
        )

    return block


# ============================================================
# VALIDATION
# ============================================================

def validate_block(block):

    if not isinstance(
        block,
        dict
    ):
        return False, "not_object"

    intent = block.get(
        "intent"
    )

    if intent in NON_CODEGEN_INTENTS:
        return True, "non_codegen"

    config = block.get(
        "config",
        {}
    )

    if not isinstance(
        config,
        dict
    ):
        return False, "config_not_object"

    # --------------------------------------------------------
    # GPIO
    # --------------------------------------------------------

    if intent in {
        "GPIO_OUTPUT",
        "GPIO_INPUT",
        "GPIO_TOGGLE",
        "GPIO_READ",
    }:

        if config.get("port") is None:
            return False, "missing_gpio_port"

        if config.get("pin") is None:
            return False, "missing_gpio_pin"

    # --------------------------------------------------------
    # UART
    # --------------------------------------------------------

    if intent == "UART_INIT":

        required = [
            "baudrate",
            "brr_value",
            "tx_pin",
            "rx_pin",
        ]

        for field in required:

            if config.get(field) is None:

                return False, (
                    f"missing_uart_{field}"
                )

    if intent == "UART_TRANSMIT":

        required = [
            "baudrate",
            "tx_pin",
        ]

        for field in required:

            if config.get(field) is None:

                return False, (
                    f"missing_uart_{field}"
                )

    if intent == "UART_RECEIVE":

        required = [
            "baudrate",
            "rx_pin",
        ]

        for field in required:

            if config.get(field) is None:

                return False, (
                    f"missing_uart_{field}"
                )

    # --------------------------------------------------------
    # TIMER DELAY
    # --------------------------------------------------------

    if intent == "TIMER_DELAY":

        if block.get("peripheral") is None:
            return False, "missing_timer_instance"

        required = [
            "delay_ms",
            "prescaler",
            "period",
        ]

        for field in required:

            if config.get(field) is None:

                return False, (
                    f"missing_timer_{field}"
                )

    # --------------------------------------------------------
    # TIMER PWM
    # --------------------------------------------------------

    if intent == "TIMER_PWM":

        if block.get("peripheral") is None:
            return False, "missing_timer_instance"

        required = [
            "channel",
            "prescaler",
            "period",
            "duty_cycle_percent",
            "ccr_value",
            "pwm_pin",
        ]

        for field in required:

            if config.get(field) is None:

                return False, (
                    f"missing_pwm_{field}"
                )

    return True, "valid"


# ============================================================
# PROCESS DATASET
# ============================================================

def process_dataset(data):

    fixed = []

    stats = {
        "total": 0,
        "blocks": 0,
        "repaired": 0,
        "valid_after_repair": 0,
        "still_incomplete": 0,
        "errors": 0,
    }

    incomplete_examples = []

    for example in data:

        stats["total"] += 1

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

            fixed.append(
                item
            )

            continue

        new_blocks = []

        for block in blocks:

            stats["blocks"] += 1

            original = deep_copy(
                block
            )

            try:

                repaired = repair_block(
                    block
                )

            except Exception as exc:

                stats["errors"] += 1

                repaired = original

                print(
                    f"[REPAIR ERROR] "
                    f"{item.get('id')} "
                    f"{exc}"
                )

            if repaired != original:
                stats["repaired"] += 1

            valid, reason = (
                validate_block(
                    repaired
                )
            )

            if valid:

                stats[
                    "valid_after_repair"
                ] += 1

            else:

                stats[
                    "still_incomplete"
                ] += 1

                incomplete_examples.append(
                    {
                        "id": item.get("id"),
                        "prompt": item.get("prompt"),
                        "intent": repaired.get(
                            "intent"
                        ),
                        "reason": reason,
                        "block": repaired,
                    }
                )

            new_blocks.append(
                repaired
            )

        item["output"] = new_blocks

        fixed.append(
            item
        )

    return fixed, stats, incomplete_examples


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print(
        "STM32F103VB DATASET JSON REPAIR"
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
            "ERROR: Input file does not exist."
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

    fixed, stats, incomplete = (
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
            fixed,
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
        f"Examples                 : "
        f"{stats['total']:,}"
    )

    print(
        f"JSON blocks              : "
        f"{stats['blocks']:,}"
    )

    print(
        f"Blocks repaired          : "
        f"{stats['repaired']:,}"
    )

    print(
        f"Valid after repair       : "
        f"{stats['valid_after_repair']:,}"
    )

    print(
        f"Still incomplete         : "
        f"{stats['still_incomplete']:,}"
    )

    print(
        f"Repair exceptions        : "
        f"{stats['errors']:,}"
    )

    print()

    # --------------------------------------------------------
    # INCOMPLETE DETAILS
    # --------------------------------------------------------

    if incomplete:

        print(
            "Examples still incomplete:"
        )

        for item in incomplete[:20]:

            print()
            print(
                f"ID      : {item['id']}"
            )

            print(
                f"Prompt  : {item['prompt']}"
            )

            print(
                f"Intent  : {item['intent']}"
            )

            print(
                f"Reason  : {item['reason']}"
            )

    else:

        print(
            "SUCCESS: No valid hardware block "
            "remains incomplete."
        )

    print()

    print(
        f"Saved fixed dataset to:"
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