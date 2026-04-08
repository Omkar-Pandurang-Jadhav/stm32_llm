import json
import random
import re
import os
from pathlib import Path
from collections import defaultdict

random.seed(42)

# ══════════════════════════════════════════════════════
# HARDWARE TABLES — STM32F103VB Datasheet Accurate
# ══════════════════════════════════════════════════════

SYSTEM_CLOCK    = 72_000_000
RCC_BASE        = "0x40021000"
APB2ENR_OFFSET  = "0x18"
APB1ENR_OFFSET  = "0x1C"

PORT_VALID_PINS = {
    "A": list(range(0, 16)),
    "B": list(range(0, 16)),
    "C": [13, 14, 15],
    "D": [0, 1],
}

RESERVED_PINS = {("A",13),("A",14),("A",15),
                 ("B",3), ("B",4)}

SAFE_GPIO_PINS = [
    (p, n)
    for p, pins in PORT_VALID_PINS.items()
    for n in pins
    if (p, n) not in RESERVED_PINS
]

GPIO_MODES_OUTPUT = ["output_push_pull","output_open_drain"]
GPIO_MODES_INPUT  = ["input_floating","input_pull_up","input_pull_down"]
GPIO_SPEEDS       = ["2MHz","10MHz","50MHz"]
VALID_BAUDRATES   = [9600,19200,38400,57600,115200]

MODE_TEXT = {
    "output_push_pull" : "output_push_pull",  # ✅
    "output_open_drain": "output_open_drain", # ✅
    "input_floating"   : "input_floating",    # ✅
    "input_pull_up"    : "input_pull_up",     # ✅
    "input_pull_down"  : "input_pull_down",   # ✅
}

RCC_MAP = {
    "GPIOA": {"bus":"APB2","offset":APB2ENR_OFFSET,"bit":2, "name":"IOPAEN"},
    "GPIOB": {"bus":"APB2","offset":APB2ENR_OFFSET,"bit":3, "name":"IOPBEN"},
    "GPIOC": {"bus":"APB2","offset":APB2ENR_OFFSET,"bit":4, "name":"IOPCEN"},
    "GPIOD": {"bus":"APB2","offset":APB2ENR_OFFSET,"bit":5, "name":"IOPDEN"},
    "USART1":{"bus":"APB2","offset":APB2ENR_OFFSET,"bit":14,"name":"USART1EN"},
    "USART2":{"bus":"APB1","offset":APB1ENR_OFFSET,"bit":17,"name":"USART2EN"},
    "USART3":{"bus":"APB1","offset":APB1ENR_OFFSET,"bit":18,"name":"USART3EN"},
    "TIM2":  {"bus":"APB1","offset":APB1ENR_OFFSET,"bit":0, "name":"TIM2EN"},
    "TIM3":  {"bus":"APB1","offset":APB1ENR_OFFSET,"bit":1, "name":"TIM3EN"},
    "TIM4":  {"bus":"APB1","offset":APB1ENR_OFFSET,"bit":2, "name":"TIM4EN"},
}

USART_MAP = {
    "USART1":{"base":"0x40013800",
              "tx":{"port":"A","pin":9},
              "rx":{"port":"A","pin":10}},
    "USART2":{"base":"0x40004000",
              "tx":{"port":"A","pin":2},
              "rx":{"port":"A","pin":3}},
    "USART3":{"base":"0x40004400",
              "tx":{"port":"B","pin":10},
              "rx":{"port":"B","pin":11}},
}

TIMER_MAP = {
    "TIM2":{"base":"0x40000000","channels":{
        1:{"port":"A","pin":0},2:{"port":"A","pin":1},
        3:{"port":"A","pin":2},4:{"port":"A","pin":3}}},
    "TIM3":{"base":"0x40000400","channels":{
        1:{"port":"A","pin":6},2:{"port":"A","pin":7},
        3:{"port":"B","pin":0},4:{"port":"B","pin":1}}},
    "TIM4":{"base":"0x40000800","channels":{
        1:{"port":"B","pin":6},2:{"port":"B","pin":7},
        3:{"port":"B","pin":8},4:{"port":"B","pin":9}}},
}

# ══════════════════════════════════════════════════════
# ADD THIS ENTIRE BLOCK TO YOUR EXISTING
# dataset_generator.py
# Place it AFTER all hardware tables
# and BEFORE any maker functions
# ══════════════════════════════════════════════════════

# ── DETERMINISTIC DEFAULTS ────────────────────────────
# Issue 1 + 4: Fixed defaults, no randomness

DEFAULTS = {
    "GPIO": {
        "mode_output": "output_push_pull",
        "mode_input":  "input_floating",
        "speed":       "50MHz",
    },
    "UART": {
        "baudrate":    115200,
        "word_length": 8,
        "parity":      "none",
        "stop_bits":   1,
    },
    "TIMER": {
        "instance":    "TIM2",   # always TIM2 if not specified
        "delay_ms":    500,
        "duty":        50,
        "channel":     1,
    },
}

# Issue 6: Fixed intent ordering in multi-intent
INTENT_ORDER = {
    "GPIO_OUTPUT":   0,
    "GPIO_TOGGLE":   0,
    "GPIO_INPUT":    0,
    "GPIO_READ":     0,
    "UART_INIT":     1,
    "UART_TRANSMIT": 1,
    "UART_RECEIVE":  1,
    "TIMER_DELAY":   2,
    "TIMER_PWM":     2,
    "RCC_ENABLE":    3,
    "ERROR":         4,
    "AMBIGUOUS":     4,
    "INVALID":       4,
}




# ══════════════════════════════════════════════════════
# CORE VALIDATION + FINALIZATION LAYER
# Issue 2, 3, 5: validate → inject flags → classify
# Call this on EVERY example before appending
# ══════════════════════════════════════════════════════

def validate_and_finalize(example_json):
    """
    ONLY validate.
    DO NOT add defaults.
    DO NOT add assumed flags.
    """

    finalized = []
    errors    = []
    has_missing = False

    for block in example_json:
        intent = block.get("intent", "")

        # Skip error/invalid blocks
        if intent in ["ERROR", "AMBIGUOUS", "INVALID"]:
            finalized.append(block)
            continue

        block, missing_fields, error = _validate_block(block, intent)

        if error:
            errors.append(error)
        else:
            if missing_fields:
                has_missing = True

            # ❌ DO NOT MODIFY CONFIG
            finalized.append(block)

    # ❌ If any error → INVALID
    if errors:
        error_block = {
            "intent": "INVALID",
            "error_details": {
                "error": "INVALID_HARDWARE",
                "message": errors[0]["message"],
                "invalid_field": errors[0]["field"],
                "suggestion": errors[0]["suggestion"],
            }
        }
        return [error_block], "INVALID", error_block

    # ✅ Decide class
    data_class = "VALID_PARTIAL" if has_missing else "VALID_COMPLETE"

    return finalized, data_class, None

def _validate_block(block, intent):
    """
    Validates a single JSON block.
    Only validates — does NOT inject values.
    Returns (block, assumed_fields, error_or_None)
    """
    assumed = []
    cfg     = block.get("config", {})

    # ── GPIO blocks ───────────────────────────────────
    if intent in ["GPIO_OUTPUT", "GPIO_TOGGLE",
                  "GPIO_INPUT", "GPIO_READ"]:

        port = cfg.get("port")
        pin  = cfg.get("pin")

        if port not in PORT_VALID_PINS:
            return block, assumed, {
                "field":      "port",
                "message":    f"Port {port} does not "
                              f"exist on STM32F103VB",
                "suggestion": "Use port A, B, C, or D",
            }

        if pin not in PORT_VALID_PINS[port]:
            valid = PORT_VALID_PINS[port]
            return block, assumed, {
                "field":      "pin",
                "message":    (f"P{port}{pin} is invalid. "
                               f"Port {port} supports: "
                               f"{valid}"),
                "suggestion": (f"Use pins "
                               f"{valid[0]}-{valid[-1]} "
                               f"for port {port}"),
            }

        if (port, pin) in RESERVED_PINS:
            return block, assumed, {
                "field":      "pin",
                "message":    (f"P{port}{pin} is reserved "
                               f"for JTAG/SWD debugger"),
                "suggestion": ("Use a non-reserved pin. "
                               "Avoid PA13,PA14,PA15,"
                               "PB3,PB4"),
            }

        # Track what is missing (do NOT inject)
        if intent in ["GPIO_OUTPUT", "GPIO_TOGGLE"]:
            if not cfg.get("mode"):
                assumed.append("mode")
            if not cfg.get("speed"):
                assumed.append("speed")

        if intent == "GPIO_INPUT":
            if not cfg.get("mode"):
                assumed.append("mode")

        block["config"] = cfg

    # ── UART blocks ───────────────────────────────────
    elif intent in ["UART_INIT", "UART_TRANSMIT",
                    "UART_RECEIVE"]:

        uart = block.get("peripheral", "")
        if uart not in USART_MAP:
            return block, assumed, {
                "field":      "peripheral",
                "message":    f"{uart} is not a valid "
                              f"USART on STM32F103VB",
                "suggestion": "Use USART1, USART2, "
                              "or USART3",
            }

        baud = cfg.get("baudrate")
        if baud is not None and \
                baud not in VALID_BAUDRATES:
            return block, assumed, {
                "field":      "baudrate",
                "message":    (f"{baud} is not a supported "
                               f"baudrate for STM32F103VB "
                               f"at 72MHz"),
                "suggestion": ("Use one of: " +
                               ", ".join(
                                   map(str,
                                       VALID_BAUDRATES))),
            }

        # Track missing — do NOT inject tx/rx pins
        if baud is None:
            assumed.append("baudrate")
        if intent in ["UART_INIT", "UART_TRANSMIT"]:
            assumed.append("tx_pin")
        if intent in ["UART_INIT", "UART_RECEIVE"]:
            assumed.append("rx_pin")

        block["config"] = cfg

    # ── TIMER blocks ──────────────────────────────────
    elif intent in ["TIMER_DELAY", "TIMER_PWM"]:

        timer = block.get("peripheral", "")

        # Timer may be None for partial examples
        if timer and timer not in TIMER_MAP:
            return block, assumed, {
                "field":      "peripheral",
                "message":    f"{timer} is not available "
                              f"on STM32F103VB",
                "suggestion": "Use TIM2, TIM3, or TIM4",
            }

        if intent == "TIMER_DELAY":
            if not timer:
                assumed.append("timer")
            if not cfg.get("delay_ms"):
                assumed.append("delay_ms")

        elif intent == "TIMER_PWM":
            channel = cfg.get("channel")

            # Only validate channel if it is present
            if channel is not None and timer:
                info = TIMER_MAP[timer]
                if channel not in info["channels"]:
                    return block, assumed, {
                        "field":      "channel",
                        "message":    (f"{timer} does not "
                                       f"have channel "
                                       f"{channel}. Valid: "
                                       f"{list(info['channels'].keys())}"),
                        "suggestion": (f"Use channels 1-4 "
                                       f"for {timer}"),
                    }

            # Track missing — do NOT inject pwm_pin
            if channel is None:
                assumed.append("channel")
            if not cfg.get("duty_cycle_percent"):
                assumed.append("duty")
            

        block["config"] = cfg

    return block, assumed, None


# ══════════════════════════════════════════════════════
# WRAP YOUR EXISTING add() FUNCTION
# Replace the add() inside generate_dataset() with this
# ══════════════════════════════════════════════════════

def finalized_add(examples, stats, ex_id,
                  clean_p, raw_jout, complexity,
                  noise_level=None):
    """
    FIX:
    Use data_class from validation, not detect_data_class
    """
    # Step 1: validate
    final_jout, data_class, _ = validate_and_finalize(raw_jout)

    # Step 2: noise
    if noise_level is None:
        noise_level = random.choice(["clean","light","heavy"])

    noisy_p = apply_noise(clean_p, noise_level)

    # Step 3: append
    examples.append({
        "id":           f"ex_{ex_id:05d}",
        "prompt":       noisy_p,
        "clean_prompt": clean_p,
        "complexity":   complexity,
        "data_class":   data_class,   # ✅ FIXED
        "noise_level":  noise_level,
        "output":       final_jout,
    })

    stats[data_class] = stats.get(data_class, 0) + 1
    return ex_id + 1

# ══════════════════════════════════════════════════════
# HARDWARE VALIDATOR
# Called before every example is added
# ══════════════════════════════════════════════════════

def validate_hardware(port, pin):
    """
    Returns (is_valid, error_message)
    """
    if port not in PORT_VALID_PINS:
        return False, f"Port {port} does not exist on STM32F103VB"
    if pin not in PORT_VALID_PINS[port]:
        valid = PORT_VALID_PINS[port]
        return False, (f"P{port}{pin} invalid. "
                       f"Port {port} supports pins "
                       f"{valid[0]}-{valid[-1]}")
    if (port, pin) in RESERVED_PINS:
        return False, (f"P{port}{pin} is reserved "
                       f"for JTAG/SWD debugger")
    return True, None


def validate_uart_pin(uart, pin_type, port, pin):
    """
    Validates UART TX/RX pin assignment
    """
    correct = USART_MAP[uart][pin_type]
    if port != correct["port"] or pin != correct["pin"]:
        return False, (
            f"{uart} {pin_type.upper()} must be "
            f"P{correct['port']}{correct['pin']}, "
            f"not P{port}{pin}")
    return True, None


# ══════════════════════════════════════════════════════
# RCC BUILDER
# ══════════════════════════════════════════════════════

def build_rcc(name):
    r   = RCC_MAP[name]
    reg = ("RCC_APB2ENR" if r["bus"] == "APB2"
           else "RCC_APB1ENR")
    return {
        "register":        reg,
        "base_address":    RCC_BASE,
        "offset":          r["offset"],
        "bit":             r["bit"],
        "peripheral_name": r["name"],
    }


def brr_value(baud):
    return SYSTEM_CLOCK // baud


def psc_period(ms):
    return 7199, ms * 10


# ══════════════════════════════════════════════════════
# ISSUE 6 FIX: SEMANTIC-AWARE NOISE
# Protects ALL hardware tokens from corruption
# ══════════════════════════════════════════════════════

def extract_semantic_tokens(text):
    """
    Finds all tokens in text that carry
    hardware meaning. These are NEVER corrupted.
    """
    protected = set()
    patterns  = [
        r'\b[Pp]?[AaBbCcDd]\d{1,2}\b',          # PA5, PB10, A5
        r'\b(USART|UART)[1-3]\b',                 # USART1, UART2
        r'\b(TIM)[1-4]\b',                        # TIM2, TIM4
        r'\b(GPIO)[ABCD]\b',                      # GPIOA
        r'\b(9600|19200|38400|57600|115200)\b',   # baudrates
        r'\b\d+ms\b',                             # 500ms
        r'\b\d+MHz\b',                            # 50MHz
        r'\b\d+%\b',                              # 50%
        r'\bCH[1-4]\b',                           # CH1, CH4
        r'\b(TIM2|TIM3|TIM4)\b',                  # timer names
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            protected.add(m.group())

    # Protect intent-critical keywords
    critical = {
        "output","input","toggle","blink","transmit",
        "receive","send","read","write","delay","pwm",
        "configure","initialize","init","setup","enable",
        "generate","create","start","clock","serial",
        "push","pull","floating","alternate",
    }
    for word in text.split():
        if word.lower().strip('.,!?') in critical:
            protected.add(word)

    return protected


CHAR_SWAPS = {
    'a':'s','e':'r','i':'u',
    'o':'p','n':'m','t':'r',
}

ABBREVIATIONS = {
    "initialize":"init","configure":"config",
    "transmit":"tx","receive":"rx",
    "generate":"gen","enable":"en",
    "through":"via","using":"w/",
    "milliseconds":"ms","microseconds":"us",
}

def light_noise(text):
    protected = extract_semantic_tokens(text)
    words     = text.split()
    result    = []
    changes   = 0

    for word in words:
        cl = word.lower().strip('.,!?')
        is_prot = (word in protected or
                   cl in {p.lower() for p in protected})
        if (not is_prot and changes < 2 and
                len(word) > 3 and random.random() < 0.35):
            op = random.randint(0, 2)
            if op == 0 and len(word) > 4:
                i    = random.randint(1, len(word)-2)
                word = word[:i] + word[i+1:]
            elif op == 1:
                i   = random.randint(1, len(word)-2)
                lst = list(word)
                lst[i], lst[i+1] = lst[i+1], lst[i]
                word = ''.join(lst)
            else:
                for orig, repl in CHAR_SWAPS.items():
                    if orig in word.lower():
                        word = word.lower().replace(
                            orig, repl, 1)
                        break
            changes += 1
        result.append(word)
    return ' '.join(result)


def heavy_noise(text):
    protected = extract_semantic_tokens(text)
    words     = text.split()
    result    = []
    deleted   = 0

    for word in words:
        cl      = word.lower().strip('.,!?')
        is_prot = (word in protected or
                   cl in {p.lower() for p in protected})
        if (not is_prot and deleted < 2 and
                len(word) > 3 and random.random() < 0.35):
            deleted += 1
            continue
        result.append(word)

    text = ' '.join(result)
    text = light_noise(text)

    # Abbreviate non-protected words
    words  = text.split()
    result = []
    done   = False
    for w in words:
        cl = w.lower().strip('.,!?')
        if (not done and cl in ABBREVIATIONS and
                w not in protected and
                random.random() < 0.5):
            result.append(ABBREVIATIONS[cl])
            done = True
        else:
            result.append(w)
    return ' '.join(result)


def apply_noise(prompt, level):
    if level == "clean": return prompt
    if level == "light": return light_noise(prompt)
    return heavy_noise(prompt)


# ══════════════════════════════════════════════════════
# ISSUE 1+2 FIX: THREE DATA CLASSES
#
# VALID_COMPLETE  → all params explicit in prompt
# VALID_PARTIAL   → some params assumed (marked)
# INVALID         → hardware violation + error JSON
# AMBIGUOUS       → vague prompt + missing params JSON
# ══════════════════════════════════════════════════════

# ── VALID_COMPLETE TEMPLATES ──────────────────────────
# Every placeholder must appear in prompt
# Model learns: what you see = what you get

COMPLETE_TEMPLATES = {

"GPIO_OUTPUT": [
    "configure {P} {N} as {mode} output at {SP}",
    "set {P} {N} as {mode} output running at {SP}",
    "initialize pin {N} of port {P} as {mode} at {SP}",
    "setup {P} {N} as {mode} output at {SP}",
    "make port {P} pin {N} a {mode} output at {SP}",
    "configure port {P} pin {N} output {mode} {SP}",
    "set pin {N} on port {P} as {mode} at {SP}",
    "initialize {P} {N} for {mode} digital output at {SP}",
    "assign {mode} output to {P} {N} with speed {SP}",
    "configure {P} {N} for {mode} output operation at {SP}",
    "i want {P} {N} as {mode} output at {SP}",
    "turn {P} {N} into a {mode} output running at {SP}",
    "{P} {N} should work as {mode} output at {SP}",
    "set up {P} {N} as a {SP} {mode} output pin",
    "prepare {P} {N} for {mode} output at {SP} speed",
    "gpio {P} {N} {mode} output {SP}",
    "{P} {N} output {mode} {SP}",
    "make {P} {N} drive load as {mode} at {SP}",
    "configure {P} {N} push pull output {SP}",
    "set {P} {N} to output mode {mode} at {SP}",
],

"GPIO_TOGGLE": [
    "blink LED on {P} {N} every {D}ms",
    "toggle {P} {N} every {D} milliseconds",
    "flip {P} {N} state every {D}ms",
    "make {P} {N} blink at {D}ms interval",
    "set {P} {N} high then low every {D}ms",
    "blink LED at port {P} pin {N} with {D}ms period",
    "toggle pin {N} of port {P} every {D}ms",
    "periodically toggle {P} {N} with {D}ms delay",
    "switch {P} {N} on and off every {D}ms",
    "create {D}ms blink on {P}{N}",
    "i want {P} {N} to blink every {D}ms",
    "make the LED on {P} {N} flash every {D}ms",
    "drive {P} {N} with {D}ms on-off cycle",
    "{P} {N} needs to toggle every {D}ms",
    "repeatedly switch {P} {N} every {D} milliseconds",
    "{P} {N} blink {D}ms",
    "led blink on {P} {N} {D}ms period",
    "toggle {P} {N} with {D} ms cycle",
    "{D}ms blink cycle on port {P} pin {N}",
    "make {P} {N} oscillate every {D}ms",
    "turn {P} {N} on and off every {D}ms",
    "pulse {P} {N} with period {D}ms",
    "alternate {P} {N} state every {D}ms",
    "square wave on {P} {N} period {D}ms",
    "{P} {N} on off {D}ms",
    "LED on {P} {N} blink rate {D}ms",
],

"GPIO_INPUT": [
    "configure {P} {N} as {mode} input",
    "set {P} {N} as input with {mode}",
    "initialize pin {N} port {P} as {mode} input",
    "setup {P} {N} as digital input {mode}",
    "make {P} {N} a {mode} input pin",
    "configure port {P} pin {N} for {mode} input",
    "set pin {N} on port {P} as {mode} input",
    "initialize {P} {N} for {mode} digital input",
    "prepare {P} {N} as {mode} input pin",
    "configure {P} {N} input mode as {mode}",
    "i need {P} {N} as {mode} input",
    "assign {mode} input to {P} {N}",
    "{P} {N} should be {mode} input",
    "turn {P} {N} into a {mode} input pin",
    "set up {P} {N} to sense signals as {mode}",
    "{P} {N} input {mode}",
    "gpio {P} {N} {mode} input mode",
    "configure {P} {N} for reading as {mode}",
    "pin {N} port {P} as {mode} input",
    "make {P} {N} detect signals in {mode} mode",
],

"GPIO_READ": [
    "read the state of {P} {N}",
    "get current value of {P} {N}",
    "check if {P} {N} is high or low",
    "read digital value from {P} {N}",
    "sample input on pin {N} of port {P}",
    "get logic level of {P} {N}",
    "read pin {N} on port {P}",
    "check logic level at {P} {N}",
    "get state of port {P} pin {N}",
    "read input data register for {P} {N}",
    "what is state of {P} {N}",
    "is {P} {N} driven high or low",
    "detect logic state at {P} {N}",
    "capture digital value of {P} {N}",
    "sample voltage level on {P} {N}",
    "{P} {N} read",
    "read {P} {N} value",
    "check {P} {N}",
    "get {P} {N} level",
    "sense {P} {N} state",
],

"UART_INIT": [
    "initialize {U} at {B} baud {W} bit {S} stop",
    "setup {U} with {B} baudrate {W}N{S}",
    "configure {U} for {B} baud {W} bit {S} stop",
    "init {U} at {B} baud {W}{S}",
    "setup serial {U} at {B} baud {W} bits {S} stop",
    "configure {U} {B} baud {W} bit no parity {S} stop",
    "initialize {U} serial at {B} baud {W}N{S}",
    "setup {U} at {B} baud rate {W} bits",
    "configure {U} for {B} baud {W} bit",
    "init {U} at {B} baud {W} data bits {S} stop bits",
    "i want {U} at {B} baud {W} bit {S} stop",
    "bring up {U} at {B} baud {W}N{S}",
    "set {U} to {B} baud {W} bit",
    "establish {U} at {B} baud {W} bit {S} stop",
    "open {U} at {B} baud {W}N{S}",
    "{U} {B} baud {W}N{S}",
    "{U} init {B} {W} bit",
    "serial {U} {B} baud",
    "{B} baud {W} bit on {U}",
    "configure {U} uart {B} baud {W} bits",
    "start {U} at {B} baud",
    "open {U} {B}",
    "activate {U} serial {B} baud",
    "enable {U} at {B}",
    "use {U} for serial {B} baud",
    "run {U} at {B} baud",
    "{U} start {B}",
    "serial comm {U} {B}",
    "initialize serial port {U} {B} baud",
    "begin {U} {B} baud",
],

"UART_TX": [
    "send data via {U} at {B} baud",
    "transmit byte through {U} at {B} baud",
    "send string using {U} at {B} baud",
    "write data to {U} at {B} baud",
    "output data through {U} at {B} baud",
    "transmit message via {U} at {B} baud",
    "push data through {U} at {B} baud",
    "send bytes over {U} at {B} baud",
    "write to {U} TX at {B} baud",
    "transmit buffer via {U} at {B} baud",
    "i want to send via {U} at {B} baud",
    "use {U} to transmit at {B} baud",
    "drive {U} TX at {B} baud",
    "feed data into {U} at {B} baud",
    "output serial on {U} at {B} baud",
    "{U} send {B} baud",
    "{U} tx {B}",
    "transmit {U} {B} baud",
    "send {U} {B}",
    "{U} {B} transmit",
],

"UART_RX": [
    "receive data from {U} at {B} baud",
    "read byte from {U} at {B} baud",
    "receive incoming data on {U} at {B} baud",
    "get data arriving on {U} at {B} baud",
    "wait for byte on {U} at {B} baud",
    "read incoming message from {U} at {B} baud",
    "receive serial data via {U} at {B} baud",
    "listen for data on {U} at {B} baud",
    "read from {U} RX at {B} baud",
    "capture incoming bytes on {U} at {B} baud",
    "i want to receive from {U} at {B} baud",
    "use {U} to read at {B} baud",
    "monitor {U} RX at {B} baud",
    "collect serial input from {U} at {B} baud",
    "poll {U} receive buffer at {B} baud",
    "{U} receive {B} baud",
    "{U} rx {B}",
    "receive {U} {B}",
    "{U} {B} receive",
    "get data {U} {B} baud",
],

"TIMER_DELAY": [
    "generate {D}ms delay using {T}",
    "wait {D} milliseconds using {T}",
    "create {D}ms blocking delay with {T}",
    "delay {D}ms using timer {T}",
    "use {T} to wait for {D}ms",
    "produce {D}ms pause using {T}",
    "setup {T} for {D}ms blocking delay",
    "configure {T} to generate {D}ms delay",
    "implement {D}ms wait with {T}",
    "use {T} timer to block for {D} milliseconds",
    "i need {D}ms pause using {T}",
    "halt execution for {D}ms with {T}",
    "make program wait {D}ms via {T}",
    "stall for {D}ms using {T}",
    "create software delay of {D}ms with {T}",
    "{T} delay {D}ms",
    "{D}ms wait {T}",
    "timer {T} {D}ms",
    "{T} {D} ms delay",
    "block {D}ms using {T}",
],

"TIMER_PWM": [
    "generate PWM on {T} channel {C} at {DT}% duty",
    "setup {T} CH{C} PWM with {DT}% duty cycle",
    "configure {T} channel {C} for {DT}% duty PWM",
    "enable PWM output on {T} CH{C} at {DT}% duty",
    "start PWM on {T} channel {C} with {DT}% duty",
    "setup {DT}% duty cycle PWM on {T} CH{C}",
    "configure PWM on {T} channel {C} duty {DT}%",
    "initialize {T} CH{C} for {DT}% PWM output",
    "produce {DT}% duty cycle on {T} channel {C}",
    "set {T} CH{C} to output {DT}% duty PWM",
    "i want {DT}% PWM from {T} channel {C}",
    "drive {T} CH{C} with {DT}% duty PWM",
    "use {T} channel {C} for {DT}% PWM",
    "configure {T} for {DT}% PWM on channel {C}",
    "set up {DT}% PWM on {T} CH{C}",
    "{T} pwm {C} {DT}%",
    "pwm {T} ch{C} duty {DT}",
    "{T} channel {C} {DT} percent duty",
    "pwm {DT}% {T} {C}",
    "{T} {C} pwm {DT}%",
],

"RCC_ENABLE": [
    "enable clock for {PERI}",
    "turn on {PERI} clock",
    "enable {PERI} peripheral clock via RCC",
    "activate {PERI} clock in RCC",
    "switch on {PERI} clock",
    "enable RCC clock gate for {PERI}",
    "turn on APB clock for {PERI}",
    "enable {PERI} in RCC register",
    "configure RCC to enable {PERI}",
    "set RCC enable bit for {PERI}",
    "i need {PERI} clock turned on",
    "bring up {PERI} by enabling clock",
    "ungate clock for {PERI}",
    "make {PERI} accessible by enabling clock",
    "allow {PERI} to run by setting RCC bit",
    "{PERI} clock enable",
    "rcc {PERI}",
    "enable {PERI}",
    "{PERI} on",
    "clock on {PERI}",
],
}

# ── VALID_PARTIAL TEMPLATES ───────────────────────────
# Some params missing from prompt
# JSON will mark missing ones as assumed=True

PARTIAL_TEMPLATES = {

"GPIO_OUTPUT": [
    "configure {P} {N} as output",
    "set {P} {N} as output pin",
    "make {P} {N} output",
    "{P} {N} output",
    "setup {P} {N} for output",
    "initialize {P} {N} output pin",
    "configure pin {N} of port {P} as output",
    "set port {P} pin {N} to output",
    "{P} {N} as output",
    "output on {P} {N}",
],

"GPIO_TOGGLE": [
    "blink {P} {N}",
    "toggle {P} {N}",
    "make {P} {N} blink",
    "led blink {P} {N}",
    "{P} {N} toggle",
    "blink led on {P} {N}",
    "flip {P} {N}",
    "{P} {N} blink",
    "make {P} {N} flash",
    "oscillate {P} {N}",
],

"GPIO_INPUT": [
    "configure {P} {N} as input",
    "set {P} {N} as input",
    "make {P} {N} input",
    "{P} {N} input",
    "setup {P} {N} for input",
    "initialize {P} {N} input",
    "{P} {N} as input pin",
    "input on {P} {N}",
    "set {P} {N} to read mode",
    "{P} {N} read mode",
],

"UART_INIT": [
    "initialize {U}",
    "setup {U}",
    "configure {U}",
    "init {U}",
    "{U} init",
    "setup serial {U}",
    "configure {U} uart",
    "start {U}",
    "bring up {U}",
    "enable {U}",
],

"UART_TX": [
    "send via {U}",
    "transmit on {U}",
    "{U} send",
    "send data {U}",
    "transmit {U}",
    "output via {U}",
    "{U} transmit",
    "write to {U}",
    "send through {U}",
    "{U} tx",
],

"UART_RX": [
    "receive from {U}",
    "read from {U}",
    "{U} receive",
    "get data {U}",
    "listen on {U}",
    "{U} rx",
    "receive {U}",
    "read {U}",
    "incoming {U}",
    "{U} read",
],

"TIMER_DELAY": [
    "delay {D}ms",
    "wait {D}ms",
    "{D}ms delay",
    "wait {D} milliseconds",
    "pause {D}ms",
    "block {D}ms",
    "delay {D} ms",
    "{D} ms pause",
    "create {D}ms delay",
    "hold {D}ms",
],

"TIMER_PWM": [
    "pwm on {T}",
    "generate pwm {T}",
    "{T} pwm",
    "setup pwm {T}",
    "pwm {T} channel {C}",
    "enable pwm {T}",
    "{T} ch{C} pwm",
    "configure pwm {T}",
    "start pwm on {T}",
    "{T} generate pwm",
],

"RCC_ENABLE": [
    "enable {PERI}",
    "{PERI} enable",
    "clock {PERI}",
    "{PERI} clock on",
    "turn on {PERI}",
    "activate {PERI}",
    "{PERI} on",
    "enable clock {PERI}",
    "{PERI} rcc enable",
    "start {PERI}",
],
}

# ── AMBIGUOUS TEMPLATES ───────────────────────────────
# No usable parameters — model must return error

AMBIGUOUS_PROMPTS = [
    "configure output",
    "setup pin as input",
    "initialize serial",
    "enable timer",
    "configure gpio",
    "setup uart",
    "blink led",
    "generate pwm",
    "create delay",
    "enable clock",
    "configure pin",
    "setup serial communication",
    "toggle output",
    "read input",
    "transmit data",
    "i want led blinking fast",
    "read sensor then send it",
    "make delay using timer",
    "send data via uart",
    "set output pin",
    "read digital pin",
    "configure serial port",
    "make pwm signal",
    "wait some time",
    "enable peripheral",
    "setup communication",
    "blink something",
    "read pin state",
    "send message",
    "receive data",
]

# Current problem:
# 400 UART_INIT examples / 30 templates = ~13 per template
# Too few for rare combinations

# Fix: Generate examples PER TEMPLATE not per intent
# This guarantees every template appears enough times

INTENT_DISTRIBUTION = {
    # (intent, template_list, count_per_template)
    "GPIO_OUTPUT"  : 25,   # 20 templates × 25 = 500
    "GPIO_TOGGLE"  : 25,   # 20 templates × 25 = 500
    "GPIO_INPUT"   : 25,
    "GPIO_READ"    : 25,
    "UART_INIT"    : 20,   # 20 templates × 20 = 400
    "UART_TX"      : 20,
    "UART_RX"      : 20,
    "TIMER_DELAY"  : 20,
    "TIMER_PWM"    : 15,
    "RCC_ENABLE"   : 15,
}

def generate_per_template(intent, templates,
                          count_per_template,
                          builder_fn):
    """
    Generate count_per_template examples
    for EVERY template
    Guarantees all vocabulary patterns seen
    """
    examples = []
    for tmpl in templates:
        for _ in range(count_per_template):
            try:
                ex = builder_fn(tmpl)
                if ex:
                    examples.append(ex)
            except Exception:
                pass
    return examples

# Current: PC in SAFE_GPIO_PINS only has PC13,PC14,PC15
# User may type PC5, PC7 → correctly → INVALID

# Add explicit INVALID examples for PC0-PC12:
def make_invalid_port_c():
    """
    Explicitly train model that PC0-PC12 are invalid
    """
    pin    = random.choice(range(0, 13))  # PC0-PC12
    prompt = random.choice([
        f"toggle PC{pin} every 500ms",
        f"configure PC{pin} as output",
        f"set PC{pin} as input",
        f"blink PC{pin}",
    ])
    j = build_error(
        "INVALID_PORT_C_PIN",
        f"PC{pin} does not exist on STM32F103VB. "
        f"Only PC13, PC14, PC15 are available.",
        "Use PC13, PC14, or PC15",
        invalid_pin=f"PC{pin}",
        valid_pins=["PC13","PC14","PC15"],
    )
    return prompt, [j], "INVALID"

# Add PC13-PC15 to VALID examples:
def make_complete_gpio_port_c():
    pin  = random.choice([13, 14, 15])
    port = "C"
    # Only output/input, no PWM (no TIM channels on PC)
    intent = random.choice([
        "GPIO_OUTPUT", "GPIO_INPUT",
        "GPIO_TOGGLE", "GPIO_READ"
    ])
    ...
# ══════════════════════════════════════════════════════
# JSON BUILDERS
# ══════════════════════════════════════════════════════

def make_pin(port, pin, assumed=False):
    d = {"port": port, "pin": pin}
    if assumed:
        d["assumed"] = True
    return d


def build_gpio_output(port, pin, speed, mode,
                      speed_assumed=False,
                      mode_assumed=False,
                      action_assumed=True):

    ok, err = validate_hardware(port, pin)
    if not ok:
        raise ValueError(err)

    cfg = {
        "port": port,
        "pin": pin,
        "pin_name": f"P{port} {pin}"   # ✅ ADD THIS
    }

    if mode is not None:
        cfg["mode"] = mode
    if speed is not None:
        cfg["speed"] = speed

    return {
        "intent":     "GPIO_OUTPUT",
        "peripheral": "GPIO",
        "rcc":        build_rcc(f"GPIO{port}"),
        "config":     cfg,
        "action":     {},
    }

# CURRENT: random.choice(SAFE_GPIO_PINS)
# This picks randomly → port A appears more

# FIXED: force balanced selection
# Replace random.choice(SAFE_GPIO_PINS) everywhere
# with this function:

def balanced_gpio_pin():
    """
    Force equal distribution:
    - Equal chance per port
    - Equal chance per valid pin
    - Never picks reserved or invalid pins
    """
    # Weight ports by usable pin count
    port_weights = {
        "A": 13,   # PA0-PA12 (PA13,14,15 reserved)
        "B": 13,   # PB0-PB2, PB5-PB15 (PB3,PB4 reserved)
        "C": 3,    # PC13,PC14,PC15 only
        "D": 2,    # PD0,PD1 only
    }
    port = random.choices(
        list(port_weights.keys()),
        weights=list(port_weights.values())
    )[0]

    valid = [
        pin for pin in PORT_VALID_PINS[port]
        if (port, pin) not in RESERVED_PINS
    ]
    pin = random.choice(valid)
    return port, pin
# Replace all:
#   random.choice(SAFE_GPIO_PINS)
# With:
#   balanced_gpio_pin()
def build_gpio_toggle(port, pin, delay_ms=None):
    ok, err = validate_hardware(port, pin)
    if not ok:
        raise ValueError(err)

    cfg = {
        "port": port,
        "pin": pin,
        "pin_name": f"P{port} {pin}"   # ✅ IMPORTANT FIX
    }

    block = {
        "intent":     "GPIO_TOGGLE",
        "peripheral": "GPIO",
        "rcc":        build_rcc(f"GPIO{port}"),
        "config":     cfg,
        "action":     {"type": "toggle"}
    }

    # ✅ Only include timing if explicitly present
    if delay_ms is not None:
        block["timing"] = {
            "delay_ms": delay_ms
        }

    return block


def build_gpio_input(port, pin, mode,
                     mode_assumed=False):
    ok, err = validate_hardware(port, pin)
    if not ok:
        raise ValueError(err)

    cfg = {
        "port": port,
        "pin": pin,
        "pin_name": f"P{port} {pin}"   # ✅ IMPORTANT FIX
    }

    if mode is not None:
        cfg["mode"] = mode

    return {
        "intent":     "GPIO_INPUT",
        "peripheral": "GPIO",
        "rcc":        build_rcc(f"GPIO{port}"),
        "config":     cfg,
        "action":     {"type": "read"},
    }

def build_gpio_read(port, pin):
    ok, err = validate_hardware(port, pin)
    if not ok:
        raise ValueError(err)

    return {
        "intent":     "GPIO_READ",
        "peripheral": "GPIO",
        "rcc":        build_rcc(f"GPIO{port}"),
        "config": {
            "port": port,
            "pin": pin,
            "pin_name": f"P{port} {pin}"   # ✅ IMPORTANT FIX
        },
        "action": {"type": "read_idr"},
    }


def build_uart_init(uart, baud, bits, stop,
                    baud_assumed=False,
                    bits_assumed=False,
                    stop_assumed=False):
    info = USART_MAP[uart]
    cfg={}
    if baud is not None:
        cfg["baudrate"]=baud
    if bits is not None:
        cfg["word_length"]=bits
    if stop is not None:
        cfg["stop_bits"]=stop
    return {
        "intent":       "UART_INIT",
        "peripheral":   uart,
        "base_address": info["base"],
        "rcc":          build_rcc(uart),
        "config": cfg,
        "action": {"type": "init"},
    }


def build_uart_tx(uart, baud, baud_assumed=False):
    info = USART_MAP[uart]
    cfg={}
    
    if baud is not None:
        cfg["baudrate"]=baud
    return {
        "intent":       "UART_TRANSMIT",
        "peripheral":   uart,
        "base_address": info["base"],
        "rcc":          build_rcc(uart),
        "config": cfg,
        "action": {"type": "transmit"},
    }


def build_uart_rx(uart, baud, baud_assumed=False):
    info = USART_MAP[uart]
    cfg  = {}
    if baud is not None:
        cfg["baudrate"] = baud
    return {
        "intent":       "UART_RECEIVE",
        "peripheral":   uart,
        "base_address": info["base"],
        "rcc":          build_rcc(uart),
        "config": cfg,
        "action": {"type": "receive"},
    }

def build_timer_delay(timer, delay_ms,
                      delay_assumed=False):
    cfg = {}
    if timer is None:
        return {
            "intent":  "TIMER_DELAY",
            "config":  cfg,
            "action":  {"type": "delay"},
        }
    info = TIMER_MAP[timer]
    if delay_ms is not None:
        cfg["delay_ms"] = delay_ms
    return {
        "intent":       "TIMER_DELAY",
        "peripheral":   timer,
        "base_address": info["base"],
        "rcc":          build_rcc(timer),
        "config": cfg,
        "action": {"type": "delay"},
    }

def build_timer_pwm(timer, channel, duty,
                    duty_assumed=False,
                    channel_assumed=False):
    info = TIMER_MAP[timer]
    cfg  = {}
    if channel is not None:
        cfg["channel"] = channel
    if duty is not None:
        cfg["duty_cycle_percent"] = duty
    return {
        "intent":       "TIMER_PWM",
        "peripheral":   timer,
        "base_address": info["base"],
        "rcc":          build_rcc(timer),
        "config": cfg,
        "action": {"type": "pwm_start"},
    }


def build_rcc_enable(peri):
    return {
        "intent":     "RCC_ENABLE",
        "peripheral": peri,
        "rcc":        build_rcc(peri),
        "action":     {"type": "clock_enable"},
    }


def build_error(error_type, message,
                suggestion, **extras):
    d = {
        "intent": "ERROR",
        "error_details": {
            "error":      error_type,
            "message":    message,
            "suggestion": suggestion,
        }
    }
    d["error_details"].update(extras)
    return d


def build_ambiguous(missing, suggestion):
    return {
        "intent": "AMBIGUOUS",
        "error_details": {
            "error":      "MISSING_PARAMETERS",
            "message":    ("Prompt is too vague "
                           "to generate a valid "
                           "configuration"),
            "missing":    missing,
            "suggestion": suggestion,
        }
    }


# ══════════════════════════════════════════════════════
# EXAMPLE MAKERS
# Each function returns (clean_prompt, json_output,
#                        data_class)
# ══════════════════════════════════════════════════════

def make_complete_gpio_output():
    port, pin = balanced_gpio_pin()
    speed     = random.choice(GPIO_SPEEDS)
    mode      = random.choice(GPIO_MODES_OUTPUT)
    mt        = MODE_TEXT[mode]
    tmpl      = random.choice(
        COMPLETE_TEMPLATES["GPIO_OUTPUT"])
    prompt = tmpl.format(P=port, N=pin,
                         SP=speed, MT=mt, mode=mode)
    j = build_gpio_output(port, pin, speed, mode,
                          action_assumed=False)
    return prompt, [j], "VALID_COMPLETE"


def make_partial_gpio_output():
    port, pin = balanced_gpio_pin()

    tmpl = random.choice(
        PARTIAL_TEMPLATES["GPIO_OUTPUT"]
    )

    prompt = tmpl.format(P=port, N=pin)

    # ❌ NO defaults
    j = build_gpio_output(port, pin, speed=None, mode=None)

    return prompt, [j], "VALID_PARTIAL"

def make_complete_gpio_toggle():
    port, pin = balanced_gpio_pin()
    delay     = random.choice([100,200,500,1000,2000])
    tmpl      = random.choice(
        COMPLETE_TEMPLATES["GPIO_TOGGLE"])
    prompt = tmpl.format(P=port, N=pin, D=delay)
    j = build_gpio_toggle(port, pin, delay)
    return prompt, [j], "VALID_COMPLETE"


def make_partial_gpio_toggle():
    port, pin = balanced_gpio_pin()

    tmpl = random.choice(
        PARTIAL_TEMPLATES["GPIO_TOGGLE"]
    )

    prompt = tmpl.format(P=port, N=pin)

    # ✅ FIX: use correct parameter name
    j = build_gpio_toggle(port, pin, delay_ms=None)

    return prompt, [j], "VALID_PARTIAL"


def make_complete_gpio_input():
    port, pin = balanced_gpio_pin()
    mode      = random.choice(GPIO_MODES_INPUT)
    mt        = MODE_TEXT[mode]
    tmpl      = random.choice(
        COMPLETE_TEMPLATES["GPIO_INPUT"])
    prompt = tmpl.format(P=port, N=pin,
                         MT=mt, mode=mode)
    j = build_gpio_input(port, pin, mode)
    return prompt, [j], "VALID_COMPLETE"


def make_partial_gpio_input():
    port, pin = balanced_gpio_pin()
    mode      = "input_floating"  # default
    tmpl      = random.choice(
        PARTIAL_TEMPLATES["GPIO_INPUT"])
    prompt = tmpl.format(P=port, N=pin)
    j = build_gpio_input(port, pin, mode=None)
    return prompt, [j], "VALID_PARTIAL"


def make_gpio_read():
    port, pin = balanced_gpio_pin()
    tmpl      = random.choice(
        COMPLETE_TEMPLATES["GPIO_READ"])
    prompt = tmpl.format(P=port, N=pin)
    j = build_gpio_read(port, pin)
    return prompt, [j], "VALID_COMPLETE"


def make_complete_uart_init():
    uart = random.choice(["USART1","USART2","USART3"])
    baud = random.choice(VALID_BAUDRATES)
    bits = random.choice([8, 9])
    stop = random.choice([1, 2])
    tmpl = random.choice(
        COMPLETE_TEMPLATES["UART_INIT"])
    prompt = tmpl.format(U=uart, B=baud,
                         W=bits, S=stop)
    j = build_uart_init(uart, baud, bits, stop)
    return prompt, [j], "VALID_COMPLETE"

def make_partial_uart_init():
    uart = random.choice(["USART1","USART2","USART3"])

    tmpl = random.choice(
        PARTIAL_TEMPLATES["UART_INIT"]
    )

    prompt = tmpl.format(U=uart)

    # ❌ NO defaults
    j = build_uart_init(uart, baud=None, bits=None, stop=None)

    return prompt, [j], "VALID_PARTIAL"


def make_complete_uart_tx():
    uart = random.choice(["USART1","USART2","USART3"])
    baud = random.choice(VALID_BAUDRATES)
    tmpl = random.choice(COMPLETE_TEMPLATES["UART_TX"])
    prompt = tmpl.format(U=uart, B=baud)
    j = build_uart_tx(uart, baud)
    return prompt, [j], "VALID_COMPLETE"


def make_partial_uart_tx():
    uart = random.choice(["USART1","USART2","USART3"])
    tmpl = random.choice(PARTIAL_TEMPLATES["UART_TX"])
    prompt = tmpl.format(U=uart)
    j = build_uart_tx(uart, baud=None)
    return prompt, [j], "VALID_PARTIAL"


def make_complete_uart_rx():
    uart = random.choice(["USART1","USART2","USART3"])
    baud = random.choice(VALID_BAUDRATES)
    tmpl = random.choice(COMPLETE_TEMPLATES["UART_RX"])
    prompt = tmpl.format(U=uart, B=baud)
    j = build_uart_rx(uart, baud)
    return prompt, [j], "VALID_COMPLETE"


def make_partial_uart_rx():
    uart = random.choice(["USART1","USART2","USART3"])
    tmpl = random.choice(PARTIAL_TEMPLATES["UART_RX"])
    prompt = tmpl.format(U=uart)
    j = build_uart_rx(uart, baud=None)
    return prompt, [j], "VALID_PARTIAL"


def make_complete_timer_delay():
    timer = random.choice(["TIM2","TIM3","TIM4"])
    delay = random.choice([100,200,500,1000,2000])
    tmpl  = random.choice(
        COMPLETE_TEMPLATES["TIMER_DELAY"])
    prompt = tmpl.format(T=timer, D=delay)
    j = build_timer_delay(timer, delay)
    return prompt, [j], "VALID_COMPLETE"


def make_partial_timer_delay():
    

    tmpl  = random.choice(
        PARTIAL_TEMPLATES["TIMER_DELAY"])
    
    delay = random.choice([100, 200, 500, 1000, 2000])

    prompt = tmpl.format(D=delay)

    j = build_timer_delay(timer=None, delay_ms=None)

    return prompt, [j], "VALID_PARTIAL"


def make_complete_timer_pwm():
    timer   = random.choice(["TIM2","TIM3","TIM4"])
    channel = random.choice([1,2,3,4])
    duty    = random.choice([25,50,75])
    tmpl    = random.choice(
        COMPLETE_TEMPLATES["TIMER_PWM"])
    prompt = tmpl.format(T=timer, C=channel, DT=duty)
    j = build_timer_pwm(timer, channel, duty)
    return prompt, [j], "VALID_COMPLETE"

def make_partial_timer_pwm():
    timer = random.choice(["TIM2","TIM3","TIM4"])

    tmpl = random.choice(
        PARTIAL_TEMPLATES["TIMER_PWM"]
    )

    prompt = tmpl.format(T=timer, C=1, DT=50)

    # ❌ NO defaults
    j = build_timer_pwm(timer, channel=None, duty=None)

    return prompt, [j], "VALID_PARTIAL"


def make_rcc_enable():
    peri   = random.choice(list(RCC_MAP.keys()))
    is_complete = random.random() < 0.6
    tmpl_pool   = (COMPLETE_TEMPLATES["RCC_ENABLE"]
                   if is_complete else
                   PARTIAL_TEMPLATES["RCC_ENABLE"])
    tmpl   = random.choice(tmpl_pool)
    prompt = tmpl.format(PERI=peri)
    j = build_rcc_enable(peri)
    cls = ("VALID_COMPLETE" if is_complete
           else "VALID_PARTIAL")
    return prompt, [j], cls


# ── INVALID EXAMPLES ──────────────────────────────────

def make_invalid_example():
    case = random.randint(0, 5)

    if case == 0:
        # Invalid pin number
        port = random.choice(["A","B"])
        pin  = random.choice([16,17,18,20])
        prompt = random.choice([
            f"configure {port}{pin} as output push pull 50MHz",
            f"set P{port}{pin} as output",
            f"blink LED on {port}{pin} every 500ms",
            f"toggle P{port}{pin} every 200ms",
        ])
        j = build_error(
            "INVALID_PIN",
            f"P{port}{pin} does not exist on STM32F103VB. "
            f"Port {port} supports pins 0-15 only.",
            f"Use a pin between 0-15 for port {port}",
            invalid_pin=f"P{port}{pin}",
            valid_range=f"P{port}0 to P{port}15",
        )

    elif case == 1:
        # Reserved JTAG pin
        port, pin = random.choice(list(RESERVED_PINS))
        prompt = random.choice([
            f"configure P{port}{pin} as output 50MHz",
            f"set {port}{pin} as output",
            f"blink P{port}{pin} every 500ms",
            f"toggle P{port}{pin} every 200ms",
            f"make P{port}{pin} input",
        ])
        j = build_error(
            "RESERVED_PIN",
            f"P{port}{pin} is reserved for JTAG/SWD "
            f"debugger and cannot be used as GPIO.",
            "Choose a different GPIO pin. "
            "Reserved pins: PA13, PA14, PA15, PB3, PB4",
            reserved_pin=f"P{port}{pin}",
            reserved_for="JTAG/SWD",
        )

    elif case == 2:
        # Invalid Port C pin
        pin = random.choice([0,1,2,3,4,5,6,7,8,9,10,11,12])
        prompt = random.choice([
            f"configure PC{pin} as output 50MHz",
            f"set PC{pin} as input floating",
            f"blink LED on PC{pin} every 500ms",
        ])
        j = build_error(
            "INVALID_PORT_C_PIN",
            f"PC{pin} is not available on STM32F103VB "
            f"LQFP100 package. Only PC13, PC14, PC15 exist.",
            "Use PC13, PC14, or PC15 only",
            invalid_pin=f"PC{pin}",
            valid_pins=["PC13","PC14","PC15"],
        )

    elif case == 3:
        # Invalid Port D pin
        pin = random.choice([2,3,4,5,6,7,8,9,10])
        prompt = random.choice([
            f"configure PD{pin} as output 50MHz",
            f"set PD{pin} as input",
            f"toggle PD{pin} every 200ms",
        ])
        j = build_error(
            "INVALID_PORT_D_PIN",
            f"PD{pin} is not available on STM32F103VB. "
            f"Only PD0 and PD1 exist on this package.",
            "Use PD0 or PD1 only",
            invalid_pin=f"PD{pin}",
            valid_pins=["PD0","PD1"],
        )

    elif case == 4:
        # Wrong USART TX pin
        uart    = random.choice(
            ["USART1","USART2","USART3"])
        info    = USART_MAP[uart]
        correct = info["tx"]
        wrong   = random.choice([
            p for p in SAFE_GPIO_PINS
            if p != (correct["port"], correct["pin"])
        ])
        wp, wn = wrong
        prompt = random.choice([
            f"initialize {uart} TX on P{wp}{wn} "
            f"at 115200 baud",
            f"setup {uart} with TX on {wp}{wn} "
            f"115200 baud",
            f"configure {uart} transmit on P{wp}{wn}",
        ])
        j = build_error(
            "WRONG_UART_PIN",
            f"{uart} TX must be "
            f"P{correct['port']}{correct['pin']}, "
            f"not P{wp}{wn}. "
            f"This is a hardware fixed mapping.",
            f"Use P{correct['port']}{correct['pin']} "
            f"for {uart} TX",
            wrong_pin=f"P{wp}{wn}",
            correct_pin=(f"P{correct['port']}"
                         f"{correct['pin']}"),
        )

    else:
        # Invalid baudrate
        bad_baud = random.choice([
            1200, 2400, 4800, 14400, 28800, 250000])
        uart = random.choice(
            ["USART1","USART2","USART3"])
        prompt = random.choice([
            f"initialize {uart} at {bad_baud} baud",
            f"setup {uart} {bad_baud} baud",
            f"configure {uart} baudrate {bad_baud}",
        ])
        j = build_error(
            "INVALID_BAUDRATE",
            f"{bad_baud} is not a standard baudrate "
            f"supported by STM32F103VB at 72MHz.",
            f"Use one of: "
            f"{', '.join(map(str, VALID_BAUDRATES))}",
            invalid_baudrate=bad_baud,
            valid_baudrates=VALID_BAUDRATES,
        )

    return prompt, [j], "INVALID"


# ── AMBIGUOUS EXAMPLES ────────────────────────────────

def make_ambiguous_example():
    prompt  = random.choice(AMBIGUOUS_PROMPTS)
    pl      = prompt.lower()
    missing = []

    needs_pin = any(k in pl for k in [
        "gpio","pin","output","input",
        "toggle","blink","read","led",
    ])
    needs_uart = any(k in pl for k in [
        "serial","uart","usart","send",
        "receive","transmit","communicate",
    ])
    needs_timer = any(k in pl for k in [
        "timer","delay","wait","pwm",
        "pause","block",
    ])

    if needs_pin:
        if not re.search(r'P?[ABCDabcd]\d', pl):
            missing.append(
                "port and pin "
                "(e.g. PA5, PB3, A7)")
    if needs_uart:
        if not any(u in pl for u in
                   ["usart1","usart2","usart3",
                    "uart1","uart2","uart3"]):
            missing.append(
                "USART instance "
                "(USART1, USART2, or USART3)")
        if not any(str(b) in pl
                   for b in VALID_BAUDRATES):
            missing.append(
                "baudrate "
                "(9600, 19200, 38400, "
                "57600, or 115200)")
    if needs_timer:
        if not any(t in pl
                   for t in ["tim2","tim3","tim4"]):
            missing.append(
                "timer instance "
                "(TIM2, TIM3, or TIM4)")
        if "delay" in pl or "wait" in pl:
            if not re.search(r'\d+\s*ms', pl):
                missing.append(
                    "delay duration in ms "
                    "(e.g. 500ms)")
        if "pwm" in pl:
            if not re.search(r'\d+\s*%', pl):
                missing.append(
                    "duty cycle percentage "
                    "(e.g. 50%)")

    if not missing:
        missing.append(
            "specific peripheral, pin, "
            "and configuration details")

    suggestion = "Please specify: " + ", ".join(missing)
    j = build_ambiguous(missing, suggestion)
    return prompt, [j], "AMBIGUOUS"


# ══════════════════════════════════════════════════════
# CROSS-INTENT VALIDATOR
# ══════════════════════════════════════════════════════

def validate_cross_intent(blocks):
    used_pins     = set()
    uart_instance = None
    issues        = []

    for b in blocks:
        intent = b.get("intent","")
        cfg    = b.get("config", {})

        if intent in ["GPIO_OUTPUT","GPIO_TOGGLE",
                      "GPIO_INPUT","GPIO_READ"]:
            pk = (cfg.get("port"), cfg.get("pin"))
            if pk in used_pins:
                issues.append(
                    f"Pin conflict: "
                    f"P{pk[0]}{pk[1]} used twice")
            used_pins.add(pk)

        if intent in ["UART_INIT","UART_TRANSMIT",
                      "UART_RECEIVE"]:
            inst = b.get("peripheral")
            if uart_instance and \
               inst != uart_instance:
                issues.append(
                    f"UART mismatch: "
                    f"{uart_instance} vs {inst}")
            uart_instance = inst

        if intent == "TIMER_PWM":
            pp  = cfg.get("pwm_pin", {})
            pk  = (pp.get("port"), pp.get("pin"))
            if pk in used_pins:
                issues.append(
                    f"PWM pin conflict: "
                    f"P{pk[0]}{pk[1]} used as GPIO")
            used_pins.add(pk)

    return issues


# ══════════════════════════════════════════════════════
# COMPLETE MAKER REGISTRY
# ══════════════════════════════════════════════════════

COMPLETE_MAKERS = [
    make_complete_gpio_output,
    make_complete_gpio_toggle,
    make_complete_gpio_input,
    make_gpio_read,
    make_complete_uart_init,
    make_complete_uart_tx,
    make_complete_uart_rx,
    make_complete_timer_delay,
    make_complete_timer_pwm,
    make_rcc_enable,
]

PARTIAL_MAKERS = [
    make_partial_gpio_output,
    make_partial_gpio_toggle,
    make_partial_gpio_input,
    make_partial_uart_init,
    make_partial_uart_tx,
    make_partial_uart_rx,
    make_partial_timer_delay,
    make_partial_timer_pwm,
]

COMPLEX_COMBOS = [
    (make_complete_gpio_toggle, make_complete_uart_init),
    (make_complete_gpio_output, make_complete_uart_tx),
    (make_complete_gpio_input,  make_complete_uart_rx),
    (make_complete_timer_delay, make_complete_gpio_toggle),
    (make_complete_uart_init,   make_complete_timer_delay),
    (make_complete_gpio_output, make_complete_timer_pwm),
    (make_complete_gpio_toggle, make_complete_uart_init,
     make_complete_timer_delay),
    (make_partial_gpio_output,  make_partial_uart_tx),
    (make_partial_gpio_toggle,  make_partial_timer_delay),
    (make_partial_uart_init,    make_partial_gpio_input),
]

CONNECTORS = [
    " and ", " also ", " then ",
    " additionally ", " plus ",
    " as well as ", " while ",
]

# ══════════════════════════════════════════════════════
# FIXED detect_data_class()
# NOW takes prompt as second argument
# ══════════════════════════════════════════════════════

def detect_data_class(output_blocks, clean_prompt=""):
    """
    Rules (strict priority order):
    1. ERROR/AMBIGUOUS/INVALID intent  → INVALID
    2. Any assumed flag anywhere        → VALID_PARTIAL
    3. TIMER_DELAY timer not in prompt  → VALID_PARTIAL
    4. UART TX/RX pin present           → VALID_PARTIAL
       (pins are always hardware-fixed)
    5. Otherwise                        → VALID_COMPLETE
    """
    prompt_lower = clean_prompt.lower()

    for block in output_blocks:
        intent = block.get("intent", "")

        # Rule 1
        if intent in ["ERROR","AMBIGUOUS","INVALID"]:
            return "INVALID"

        cfg    = block.get("config", {})
        action = block.get("action", {})
        timing = block.get("timing", {})

        # Rule 2a: top-level config keys
        for key, val in cfg.items():
            if "assumed" in str(key).lower():
                return "VALID_PARTIAL"
            # Rule 2b: nested dict (tx_pin, rx_pin, pwm_pin)
            if isinstance(val, dict):
                if val.get("assumed") is True:
                    return "VALID_PARTIAL"
                for nk in val.keys():
                    if "assumed" in str(nk).lower():
                        return "VALID_PARTIAL"

        # Rule 2c: action block
        if isinstance(action, dict):
            if action.get("assumed") is True:
                return "VALID_PARTIAL"

        # Rule 2d: timing block
        if isinstance(timing, dict):
            if timing.get("assumed") is True:
                return "VALID_PARTIAL"

        # Rule 3: timer not stated in prompt
        if intent == "TIMER_DELAY":
            timer = block.get("peripheral", "")
            if timer and timer.lower() not in prompt_lower:
                return "VALID_PARTIAL"

        # Rule 4: UART pins always hardware-fixed
        if intent in ["UART_INIT","UART_TRANSMIT",
                      "UART_RECEIVE"]:
            if isinstance(cfg.get("tx_pin"),dict):
                if cfg["tx_pin"].get("assumed"):
                    return "VALID_PARTIAL"

    return "VALID_COMPLETE"


# ══════════════════════════════════════════════════════
# MAIN GENERATOR
# Target: 10000-15000 high quality examples
# Distribution:
#   40% VALID_COMPLETE
#   30% VALID_PARTIAL
#   20% COMPLEX (multi-intent)
#   10% INVALID + AMBIGUOUS
# ══════════════════════════════════════════════════════

def generate_dataset(target=12000):
    examples  = []
    ex_id     = 0
    stats     = defaultdict(int)

    n_complete  = int(target * 0.40)
    n_partial   = int(target * 0.30)
    n_complex   = int(target * 0.20)
    n_invalid   = int(target * 0.07)
    n_ambiguous = int(target * 0.03)

    noise_levels = ["clean","light","heavy"]

    def add(clean_p, jout, data_class, complexity):
        nonlocal ex_id
        ex_id = finalized_add(
            examples, stats, ex_id,
            clean_p, jout, complexity)

    # VALID_COMPLETE
    print(f"Generating {n_complete} complete examples...")
    for _ in range(n_complete):
        maker = random.choice(COMPLETE_MAKERS)
        try:
            cp, jout, cls = maker()
            add(cp, jout, cls, "simple")
        except ValueError:
            pass

    # VALID_PARTIAL
    print(f"Generating {n_partial} partial examples...")
    for _ in range(n_partial):
        maker = random.choice(PARTIAL_MAKERS)
        try:
            cp, jout, cls = maker()
            add(cp, jout, cls, "simple")
        except ValueError:
            pass

    # COMPLEX (multi-intent)
    print(f"Generating {n_complex} complex examples...")
    attempts = 0
    while stats["VALID_COMPLETE"] + \
          stats["VALID_PARTIAL"] < \
          n_complete + n_partial + n_complex and \
          attempts < n_complex * 3:
        attempts += 1
        combo = random.choice(COMPLEX_COMBOS)
        parts = []
        jout  = []

        # Lock UART instance for consistency
        uart_lock = None

        for maker in combo:
            try:
                cp, j, cls = maker()
                # Fix UART consistency
                for block in j:
                    if block.get("intent") in [
                        "UART_INIT","UART_TRANSMIT",
                        "UART_RECEIVE"
                    ]:
                        if uart_lock is None:
                            uart_lock = block["peripheral"]
                        elif block["peripheral"] != uart_lock:
                            # Rebuild with locked instance
                            baud = block["config"].get("baudrate",None)
                            if block["intent"] == "UART_INIT":
                                block = build_uart_init(
                                    uart_lock, baud, 8, 1,
                                    baud_assumed=False)
                            elif block["intent"] == \
                                 "UART_TRANSMIT":
                                block = build_uart_tx(
                                    uart_lock, baud)
                            elif block["intent"] == \
                                 "UART_RECEIVE":
                                block = build_uart_rx(
                                    uart_lock, baud)
                parts.append(cp)
                jout.extend(j)
            except ValueError:
                break

        if not parts:
            continue

        issues = validate_cross_intent(jout)
        if issues:
            continue

        conn  = random.choice(CONNECTORS)
        clean = conn.join(parts)
        noise = random.choice(noise_levels)
        noisy = apply_noise(clean, noise)
        
        final_jout,data_class,_=validate_and_finalize(jout)

        examples.append({
            "id":           f"ex_{ex_id:05d}",
            "prompt":       noisy,
            "clean_prompt": clean,
            "complexity":   "complex",
            "data_class":   data_class,
            "noise_level":  noise,
            "output":       final_jout,
        })
        stats[data_class] += 1
        ex_id += 1

    # INVALID
    print(f"Generating {n_invalid} invalid examples...")
    for _ in range(n_invalid):
        cp, jout, cls = make_invalid_example()
        add(cp, jout, cls, "simple")

    # AMBIGUOUS
    print(f"Generating {n_ambiguous} ambiguous examples...")
    for _ in range(n_ambiguous):
        cp, jout, cls = make_ambiguous_example()
        add(cp, jout, cls, "simple")

    random.shuffle(examples)
    return examples, dict(stats)


# ══════════════════════════════════════════════════════
# ALIGNMENT VALIDATOR
# ══════════════════════════════════════════════════════

def validate_alignment(examples, sample=30):
    print(f"\n{'='*55}")
    print("ALIGNMENT VALIDATION")
    print(f"{'='*55}")
    passed = failed = skipped = 0
    checks = random.sample(
        examples, min(sample, len(examples)))

    for ex in checks:
        prompt  = ex["clean_prompt"].lower()
        dclass  = ex["data_class"]
        issues  = []
        ok      = True

        # Skip invalid/ambiguous
        if dclass in ["INVALID","AMBIGUOUS"]:
            skipped += 1
            continue

        for block in ex["output"]:
            intent = block.get("intent","")
            cfg    = block.get("config", {})

            if intent in ["ERROR","AMBIGUOUS"]:
                continue

            # For COMPLETE, params MUST be in prompt
            if dclass == "VALID_COMPLETE":
                if intent in ["GPIO_OUTPUT","GPIO_TOGGLE",
                              "GPIO_INPUT","GPIO_READ"]:
                    port = str(cfg.get("port","")).lower()
                    pin  = str(cfg.get("pin",""))
                    if (port not in prompt and
                            f"p{port}" not in prompt and
                            f"port {port}" not in prompt):
                        issues.append(
                            f"Port {port.upper()} missing")
                        ok = False
                    if pin not in prompt:
                        issues.append(
                            f"Pin {pin} missing")
                        ok = False

                if intent in ["UART_INIT","UART_TRANSMIT",
                              "UART_RECEIVE"]:
                    peri = block.get(
                        "peripheral","").lower()
                    alt  = peri.replace("usart","uart")
                    if (peri not in prompt and
                            alt not in prompt):
                        issues.append(
                            f"{peri.upper()} missing")
                        ok = False
                    baud = str(cfg.get("baudrate",""))
                    if (baud and
                            not cfg.get("baudrate_assumed")
                            and baud not in prompt):
                        issues.append(
                            f"Baudrate {baud} missing")
                        ok = False

                if intent in ["TIMER_DELAY","TIMER_PWM"]:
                    peri = block.get(
                        "peripheral","").lower()
                    if peri not in prompt:
                        issues.append(
                            f"{peri.upper()} missing")
                        ok = False
                    if intent == "TIMER_DELAY":
                        d = str(cfg.get("delay_ms",""))
                        if (d and
                                not cfg.get("delay_assumed")
                                and d not in prompt):
                            issues.append(
                                f"Delay {d} missing")
                            ok = False

            # For PARTIAL, assumed fields OK
            # just verify non-assumed fields present
            elif dclass == "VALID_PARTIAL":
                if intent in ["GPIO_OUTPUT","GPIO_TOGGLE",
                              "GPIO_INPUT","GPIO_READ"]:
                    port = str(cfg.get("port","")).lower()
                    pin  = str(cfg.get("pin",""))
                    if (port not in prompt and
                            f"p{port}" not in prompt):
                        issues.append(
                            f"Port {port.upper()} missing")
                        ok = False

        if ok:
            passed += 1
        else:
            failed += 1
            print(f"\n✗ [{ex['id']}] "
                  f"({dclass})")
            print(f"  Prompt : {ex['clean_prompt']}")
            for iss in issues:
                print(f"  Issue  : {iss}")

    print(f"\nPassed  : {passed}")
    print(f"Failed  : {failed}")
    print(f"Skipped : {skipped} "
          f"(INVALID/AMBIGUOUS — correct)")
    return failed == 0


# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════

if __name__ == "__main__":

    out_dir = Path(__file__).parent
    TARGET  = 12000

    print("="*55)
    print("STM32 DATASET GENERATOR v3.0")
    print(f"Target: {TARGET} examples")
    print("="*55)

    examples, stats = generate_dataset(TARGET)

    # Split simple/complex
    simple  = [x for x in examples
               if x["complexity"] == "simple"]
    complex_ = [x for x in examples
                if x["complexity"] == "complex"]

    # Validate
    validate_alignment(examples, sample=50)

    # Save
    all_path  = out_dir / "dataset_full.json"
    simp_path = out_dir / "simple_dataset.json"
    comp_path = out_dir / "complex_dataset.json"

    with open(all_path,  "w") as f:
        json.dump(examples, f, indent=2)
    with open(simp_path, "w") as f:
        json.dump(simple,   f, indent=2)
    with open(comp_path, "w") as f:
        json.dump(complex_, f, indent=2)

    # Stats
    print(f"\n{'='*55}")
    print("FINAL DATASET STATS")
    print(f"{'='*55}")
    print(f"Total    : {len(examples)}")
    print(f"Simple   : {len(simple)}")
    print(f"Complex  : {len(complex_)}")

    print("\nData class distribution:")
    for cls, cnt in sorted(stats.items()):
        pct = cnt / len(examples) * 100
        print(f"  {cls:20s}: {cnt:5d} ({pct:.1f}%)")

    print("\nNoise distribution:")
    nc = defaultdict(int)
    for x in examples:
        nc[x["noise_level"]] += 1
    for k, v in nc.items():
        print(f"  {k:5s}: {v}")

    # Sample each class
    for cls in ["VALID_COMPLETE","VALID_PARTIAL",
                "INVALID","AMBIGUOUS"]:
        pool = [x for x in examples
                if x["data_class"] == cls]
        if not pool:
            continue
        ex = random.choice(pool)
        print(f"\n--- {cls} SAMPLE ---")
        print(f"Prompt : {ex['clean_prompt']}")
        out = ex["output"][0]
        print(f"Intent : {out.get('intent')}")
        if out.get("intent") in ["ERROR","AMBIGUOUS"]:
            ed = out.get("error_details", {})
            print(f"Error  : {ed.get('error')}")
            print(f"Msg    : {ed.get('message','')[:60]}")
        else:
            cfg = out.get("config", {})
            assumed = {k: v for k, v in cfg.items()
                       if "assumed" in str(k).lower()
                       or k == "assumed"}
            if assumed:
                print(f"Assumed: {assumed}")
                




