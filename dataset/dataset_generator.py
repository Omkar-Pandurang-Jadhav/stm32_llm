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
    "output_push_pull" : "push pull",
    "output_open_drain": "open drain",
    "input_floating"   : "floating",
    "input_pull_up"    : "pull up",
    "input_pull_down"  : "pull down",
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


def standardize_assumed_flags(cfg, intent):
    """
    Enforces standard format for all assumed flags.

    ALWAYS uses nested format:
      "tx_pin": {"port":"A","pin":9,"assumed":true}

    NEVER uses flat format:
      "tx_pin_assumed": true   ← remove this
    """

    # ── TX pin ────────────────────────────────────────
    if "tx_pin_assumed" in cfg:
        tx = cfg.get("tx_pin", {})
        if isinstance(tx, dict):
            tx["assumed"] = True
            cfg["tx_pin"] = tx
        del cfg["tx_pin_assumed"]

    # ── RX pin ────────────────────────────────────────
    if "rx_pin_assumed" in cfg:
        rx = cfg.get("rx_pin", {})
        if isinstance(rx, dict):
            rx["assumed"] = True
            cfg["rx_pin"] = rx
        del cfg["rx_pin_assumed"]

    # ── PWM pin ───────────────────────────────────────
    if "pwm_pin_assumed" in cfg:
        pwm = cfg.get("pwm_pin", {})
        if isinstance(pwm, dict):
            pwm["assumed"] = True
            cfg["pwm_pin"] = pwm
        del cfg["pwm_pin_assumed"]

    # ── Ensure tx/rx pins always have assumed:true ────
    # These are hardware-fixed, always assumed
    if intent in ["UART_INIT","UART_TRANSMIT"]:
        tx = cfg.get("tx_pin", {})
        if isinstance(tx, dict) and tx:
            tx["assumed"] = True
            cfg["tx_pin"] = tx

    if intent in ["UART_INIT","UART_RECEIVE"]:
        rx = cfg.get("rx_pin", {})
        if isinstance(rx, dict) and rx:
            rx["assumed"] = True
            cfg["rx_pin"] = rx

    if intent == "TIMER_PWM":
        pwm = cfg.get("pwm_pin", {})
        if isinstance(pwm, dict) and pwm:
            pwm["assumed"] = True
            cfg["pwm_pin"] = pwm

    return cfg

# ══════════════════════════════════════════════════════
# CORE VALIDATION + FINALIZATION LAYER
# Issue 2, 3, 5: validate → inject flags → classify
# Call this on EVERY example before appending
# ══════════════════════════════════════════════════════

def validate_and_finalize(example_json):
    """
    Input:  raw list of JSON blocks from any builder
    Output: (finalized_blocks, data_class, error_block)

    Steps:
      1. Validate each block against hardware tables
      2. Inject deterministic defaults where missing
      3. Add assumption flags consistently
      4. Sort blocks by INTENT_ORDER
      5. Determine data_class:
           VALID_COMPLETE → no assumptions
           VALID_PARTIAL  → some assumptions
           INVALID        → hardware violation found
    """
    finalized   = []
    assumptions = []   # track which fields were assumed
    errors      = []   # track hardware violations

    for block in example_json:
        intent = block.get("intent","")

        # Skip already-error blocks — pass through
        if intent in ["ERROR","AMBIGUOUS","INVALID"]:
            finalized.append(block)
            continue

        block, assumed, error = _validate_block(
            block, intent)

        if error:
            errors.append(error)
        else:
            assumptions.extend(assumed)
            finalized.append(block)

    # If any hardware violation found → INVALID
    if errors:
        error_block = {
            "intent": "INVALID",
            "error_details": {
                "error":         "INVALID_HARDWARE",
                "message":       errors[0]["message"],
                "invalid_field": errors[0]["field"],
                "suggestion":    errors[0]["suggestion"],
            }
        }
        return [error_block], "INVALID", error_block

    # Sort by intent order (Issue 6)
    finalized.sort(
        key=lambda b: INTENT_ORDER.get(
            b.get("intent",""), 99))

    # Determine data class (Issue 3)
    if assumptions:
        data_class = "VALID_PARTIAL"
    else:
        data_class = "VALID_COMPLETE"

    return finalized, data_class, None


def _validate_block(block, intent):
    """
    Validates and finalizes a single JSON block.
    Returns (block, assumed_fields, error_or_None)
    """
    assumed = []
    cfg     = block.get("config", {})

    # ── GPIO blocks ───────────────────────────────────
    if intent in ["GPIO_OUTPUT","GPIO_TOGGLE",
                  "GPIO_INPUT","GPIO_READ"]:

        port = cfg.get("port")
        pin  = cfg.get("pin")

        # Validate port exists
        if port not in PORT_VALID_PINS:
            return block, assumed, {
                "field":      "port",
                "message":    f"Port {port} does not "
                              f"exist on STM32F103VB",
                "suggestion": "Use port A, B, C, or D",
            }

        # Validate pin exists for this port
        if pin not in PORT_VALID_PINS[port]:
            valid = PORT_VALID_PINS[port]
            return block, assumed, {
                "field":   "pin",
                "message": (f"P{port}{pin} is invalid. "
                            f"Port {port} supports: "
                            f"{valid}"),
                "suggestion": (f"Use pins "
                               f"{valid[0]}-{valid[-1]} "
                               f"for port {port}"),
            }

        # Validate not reserved
        if (port, pin) in RESERVED_PINS:
            return block, assumed, {
                "field":   "pin",
                "message": (f"P{port}{pin} is reserved "
                            f"for JTAG/SWD debugger"),
                "suggestion": ("Use a non-reserved pin. "
                               "Avoid PA13,PA14,PA15,"
                               "PB3,PB4"),
            }

        # Fix missing speed for output
        if intent in ["GPIO_OUTPUT","GPIO_TOGGLE"]:
            if not cfg.get("speed"):
                cfg["speed"]        = DEFAULTS["GPIO"]["speed"]
                cfg["speed_assumed"] = True
                assumed.append("speed")

        # Fix missing mode
        if intent in ["GPIO_OUTPUT","GPIO_TOGGLE"]:
            if not cfg.get("mode"):
                cfg["mode"]        = DEFAULTS["GPIO"]["mode_output"]
                cfg["mode_assumed"] = True
                assumed.append("mode")

        if intent == "GPIO_INPUT":
            if not cfg.get("mode"):
                cfg["mode"]        = DEFAULTS["GPIO"]["mode_input"]
                cfg["mode_assumed"] = True
                assumed.append("mode")

        # Issue 6: standardize action flag
        action = block.get("action", {})
        if intent in ["GPIO_OUTPUT","GPIO_TOGGLE"]:
            if not action.get("type"):
                action["type"]    = "set_high"
                action["assumed"] = True
                assumed.append("action")

        block["config"] = cfg
        block["action"] = action

    # ── UART blocks ───────────────────────────────────
    elif intent in ["UART_INIT","UART_TRANSMIT",
                    "UART_RECEIVE"]:

        uart = block.get("peripheral","")
        if uart not in USART_MAP:
            return block, assumed, {
                "field":      "peripheral",
                "message":    f"{uart} is not a valid "
                              f"USART on STM32F103VB",
                "suggestion": "Use USART1, USART2, "
                              "or USART3",
            }

        info = USART_MAP[uart]

        # Validate baudrate
        baud = cfg.get("baudrate")
        if baud is None:
            cfg["baudrate"]          = DEFAULTS["UART"]["baudrate"]
            cfg["brr_value"]         = brr_value(
                DEFAULTS["UART"]["baudrate"])
            cfg["baudrate_assumed"]  = True
            assumed.append("baudrate")
        elif baud not in VALID_BAUDRATES:
            return block, assumed, {
                "field":   "baudrate",
                "message": (f"{baud} is not a supported "
                            f"baudrate for STM32F103VB "
                            f"at 72MHz"),
                "suggestion": ("Use one of: " +
                               ", ".join(
                                   map(str,
                                       VALID_BAUDRATES))),
            }
        else:
            # Ensure brr_value always correct
            cfg["brr_value"] = brr_value(baud)

        # Issue 5: standardize TX/RX pin flags
        if intent in ["UART_INIT","UART_TRANSMIT"]:
            tx = cfg.get("tx_pin", {})
            if not tx:
                cfg["tx_pin"] = {
                    **info["tx"],
                    "tx_pin_assumed": True,
                }
                assumed.append("tx_pin")
            else:
                # Validate TX pin
                if (tx.get("port") != info["tx"]["port"] or
                        tx.get("pin") != info["tx"]["pin"]):
                    return block, assumed, {
                        "field":   "tx_pin",
                        "message": (
                            f"{uart} TX must be "
                            f"P{info['tx']['port']}"
                            f"{info['tx']['pin']}, "
                            f"not P{tx.get('port')}"
                            f"{tx.get('pin')}"),
                        "suggestion": (
                            f"Use P{info['tx']['port']}"
                            f"{info['tx']['pin']} "
                            f"for {uart} TX"),
                    }
                # Mark as assumed (hardware fixed)
                cfg["tx_pin"] = {
                    **info["tx"],
                    "tx_pin_assumed": True,
                }
                assumed.append("tx_pin")

        if intent in ["UART_INIT","UART_RECEIVE"]:
            rx = cfg.get("rx_pin", {})
            if not rx:
                cfg["rx_pin"] = {
                    **info["rx"],
                    "rx_pin_assumed": True,
                }
                assumed.append("rx_pin")
            else:
                cfg["rx_pin"] = {
                    **info["rx"],
                    "rx_pin_assumed": True,
                }
                assumed.append("rx_pin")

        # Fill UART defaults
        if intent == "UART_INIT":
            if not cfg.get("word_length"):
                cfg["word_length"]         = DEFAULTS["UART"]["word_length"]
                cfg["word_length_assumed"] = True
                assumed.append("word_length")
            if not cfg.get("stop_bits"):
                cfg["stop_bits"]         = DEFAULTS["UART"]["stop_bits"]
                cfg["stop_bits_assumed"] = True
                assumed.append("stop_bits")
            if not cfg.get("parity"):
                cfg["parity"]         = DEFAULTS["UART"]["parity"]
                cfg["parity_assumed"] = True
                assumed.append("parity")

        block["config"] = cfg

    # ── TIMER blocks ──────────────────────────────────
    elif intent in ["TIMER_DELAY","TIMER_PWM"]:

        timer = block.get("peripheral","")
        if timer not in TIMER_MAP:
            return block, assumed, {
                "field":      "peripheral",
                "message":    f"{timer} is not available "
                              f"on STM32F103VB",
                "suggestion": "Use TIM2, TIM3, or TIM4",
            }

        info = TIMER_MAP[timer]



        if intent == "TIMER_DELAY":
            delay = cfg.get("delay_ms")
            if delay is None:
                delay = DEFAULTS["TIMER"]["delay_ms"]
                p, per = psc_period(delay)
                cfg["delay_ms"]      = delay
                cfg["prescaler"]     = p
                cfg["period"]        = per
                cfg["delay_assumed"] = True
                assumed.append("delay_ms")


            cfg["timer_assumed"] = True
            assumed.append("timer")
            block["config"] = cfg

        elif intent == "TIMER_PWM":
            channel = cfg.get("channel")
            if channel is None:
                channel = DEFAULTS["TIMER"]["channel"]
                cfg["channel"]          = channel
                cfg["channel_assumed"]  = True
                assumed.append("channel")

            # Validate channel exists for this timer
            if channel not in info["channels"]:
                return block, assumed, {
                    "field":   "channel",
                    "message": (f"{timer} does not have "
                                f"channel {channel}. "
                                f"Valid: "
                                f"{list(info['channels'].keys())}"),
                    "suggestion": (f"Use channels 1-4 "
                                   f"for {timer}"),
                }

            duty = cfg.get("duty_cycle_percent")
            if duty is None:
                duty = DEFAULTS["TIMER"]["duty"]
                cfg["duty_cycle_percent"] = duty
                cfg["ccr_value"]          = int(
                    (duty/100) * cfg.get("period",999))
                cfg["duty_assumed"]       = True
                assumed.append("duty")

            # Always update pwm_pin from hardware table
            cfg["pwm_pin"] = {
                **info["channels"][channel],
                "pwm_pin_assumed": True,
            }
            assumed.append("pwm_pin")

        block["config"] = cfg

# Standardize all assumed flags before returning
    block["config"] = standardize_assumed_flags(
        block.get("config", {}), intent)
    return block, assumed, None


# ══════════════════════════════════════════════════════
# WRAP YOUR EXISTING add() FUNCTION
# Replace the add() inside generate_dataset() with this
# ══════════════════════════════════════════════════════

def finalized_add(examples, stats, ex_id,
                  clean_p, raw_jout, complexity,
                  noise_level=None):
    """
    Correct pipeline:
    1. validate_and_finalize  (defaults + validation)
    2. detect_data_class      (WITH clean prompt)
    3. apply_noise            (prompt only, never JSON)
    4. append
    """
    # Step 1: validate + inject defaults
    final_jout, _, _ = validate_and_finalize(raw_jout)

    # Step 2: classify WITH prompt (not without)
    data_class = detect_data_class(final_jout, clean_p)

    # Step 3: noise on prompt only
    if noise_level is None:
        noise_level = random.choice(
            ["clean","light","heavy"])
    noisy_p = apply_noise(clean_p, noise_level)

    # Step 4: append
    examples.append({
        "id":           f"ex_{ex_id:05d}",
        "prompt":       noisy_p,
        "clean_prompt": clean_p,
        "complexity":   complexity,
        "data_class":   data_class,
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
    "configure {P}{N} as {MT} output at {SP}",
    "set {P}{N} as {MT} output running at {SP}",
    "initialize pin {N} of port {P} as {MT} at {SP}",
    "setup {P}{N} as {MT} output at {SP}",
    "make port {P} pin {N} a {MT} output at {SP}",
    "configure port {P} pin {N} output {MT} {SP}",
    "set pin {N} on port {P} as {MT} at {SP}",
    "initialize {P}{N} for {MT} digital output at {SP}",
    "assign {MT} output to {P}{N} with speed {SP}",
    "configure {P}{N} for {MT} output operation at {SP}",
    "i want {P}{N} as {MT} output at {SP}",
    "turn {P}{N} into a {MT} output running at {SP}",
    "{P}{N} should work as {MT} output at {SP}",
    "set up {P}{N} as a {SP} {MT} output pin",
    "prepare {P}{N} for {MT} output at {SP} speed",
    "gpio {P}{N} {MT} output {SP}",
    "{P}{N} output {MT} {SP}",
    "make {P}{N} drive load as {MT} at {SP}",
    "configure {P}{N} push pull output {SP}",
    "set {P}{N} to output mode {MT} at {SP}",
],

"GPIO_TOGGLE": [
    "blink LED on {P}{N} every {D}ms",
    "toggle {P}{N} every {D} milliseconds",
    "flip {P}{N} state every {D}ms",
    "make {P}{N} blink at {D}ms interval",
    "set {P}{N} high then low every {D}ms",
    "blink LED at port {P} pin {N} with {D}ms period",
    "toggle pin {N} of port {P} every {D}ms",
    "periodically toggle {P}{N} with {D}ms delay",
    "switch {P}{N} on and off every {D}ms",
    "create {D}ms blink on {P}{N}",
    "i want {P}{N} to blink every {D}ms",
    "make the LED on {P}{N} flash every {D}ms",
    "drive {P}{N} with {D}ms on-off cycle",
    "{P}{N} needs to toggle every {D}ms",
    "repeatedly switch {P}{N} every {D} milliseconds",
    "{P}{N} blink {D}ms",
    "led blink on {P}{N} {D}ms period",
    "toggle {P}{N} with {D} ms cycle",
    "{D}ms blink cycle on port {P} pin {N}",
    "make {P}{N} oscillate every {D}ms",
],

"GPIO_INPUT": [
    "configure {P}{N} as {MT} input",
    "set {P}{N} as input with {MT}",
    "initialize pin {N} port {P} as {MT} input",
    "setup {P}{N} as digital input {MT}",
    "make {P}{N} a {MT} input pin",
    "configure port {P} pin {N} for {MT} input",
    "set pin {N} on port {P} as {MT} input",
    "initialize {P}{N} for {MT} digital input",
    "prepare {P}{N} as {MT} input pin",
    "configure {P}{N} input mode as {MT}",
    "i need {P}{N} as {MT} input",
    "assign {MT} input to {P}{N}",
    "{P}{N} should be {MT} input",
    "turn {P}{N} into a {MT} input pin",
    "set up {P}{N} to sense signals as {MT}",
    "{P}{N} input {MT}",
    "gpio {P}{N} {MT} input mode",
    "configure {P}{N} for reading as {MT}",
    "pin {N} port {P} as {MT} input",
    "make {P}{N} detect signals in {MT} mode",
],

"GPIO_READ": [
    "read the state of {P}{N}",
    "get current value of {P}{N}",
    "check if {P}{N} is high or low",
    "read digital value from {P}{N}",
    "sample input on pin {N} of port {P}",
    "get logic level of {P}{N}",
    "read pin {N} on port {P}",
    "check logic level at {P}{N}",
    "get state of port {P} pin {N}",
    "read input data register for {P}{N}",
    "what is state of {P}{N}",
    "is {P}{N} driven high or low",
    "detect logic state at {P}{N}",
    "capture digital value of {P}{N}",
    "sample voltage level on {P}{N}",
    "{P}{N} read",
    "read {P}{N} value",
    "check {P}{N}",
    "get {P}{N} level",
    "sense {P}{N} state",
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
    "configure {P}{N} as output",
    "set {P}{N} as output pin",
    "make {P}{N} output",
    "{P}{N} output",
    "setup {P}{N} for output",
    "initialize {P}{N} output pin",
    "configure pin {N} of port {P} as output",
    "set port {P} pin {N} to output",
    "{P}{N} as output",
    "output on {P}{N}",
],

"GPIO_TOGGLE": [
    "blink {P}{N}",
    "toggle {P}{N}",
    "make {P}{N} blink",
    "led blink {P}{N}",
    "{P}{N} toggle",
    "blink led on {P}{N}",
    "flip {P}{N}",
    "{P}{N} blink",
    "make {P}{N} flash",
    "oscillate {P}{N}",
],

"GPIO_INPUT": [
    "configure {P}{N} as input",
    "set {P}{N} as input",
    "make {P}{N} input",
    "{P}{N} input",
    "setup {P}{N} for input",
    "initialize {P}{N} input",
    "{P}{N} as input pin",
    "input on {P}{N}",
    "set {P}{N} to read mode",
    "{P}{N} read mode",
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
    return {
        "intent":     "GPIO_OUTPUT",
        "peripheral": "GPIO",
        "rcc":        build_rcc(f"GPIO{port}"),
        "config": {
            "port":  port,
            "pin":   pin,
            "mode":  mode,
            "speed": speed,
            **({"mode_assumed": True}
               if mode_assumed else {}),
            **({"speed_assumed": True}
               if speed_assumed else {}),
        },
        "action": {
            "type":    "set_high",
            **({"assumed": True}
               if action_assumed else {}),
        },
    }


def build_gpio_toggle(port, pin, delay_ms,
                      delay_assumed=False):
    ok, err = validate_hardware(port, pin)
    if not ok:
        raise ValueError(err)
    return {
        "intent":     "GPIO_TOGGLE",
        "peripheral": "GPIO",
        "rcc":        build_rcc(f"GPIO{port}"),
        "config": {
            "port":  port,
            "pin":   pin,
            "mode":  "output_push_pull",
            "speed": "50MHz",
        },
        "action": {"type": "toggle"},
        "timing": {
            "delay_ms": delay_ms,
            **({"assumed": True}
               if delay_assumed else {}),
        },
    }


def build_gpio_input(port, pin, mode,
                     mode_assumed=False):
    ok, err = validate_hardware(port, pin)
    if not ok:
        raise ValueError(err)
    return {
        "intent":     "GPIO_INPUT",
        "peripheral": "GPIO",
        "rcc":        build_rcc(f"GPIO{port}"),
        "config": {
            "port":  port,
            "pin":   pin,
            "mode":  mode,
            "speed": None,
            **({"mode_assumed": True}
               if mode_assumed else {}),
        },
        "action": {"type": "read"},
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
            "port":  port,
            "pin":   pin,
            "mode":  "input_floating",
            "speed": None,
        },
        "action": {"type": "read_idr"},
    }


def build_uart_init(uart, baud, bits, stop,
                    baud_assumed=False,
                    bits_assumed=False,
                    stop_assumed=False):
    info = USART_MAP[uart]
    return {
        "intent":       "UART_INIT",
        "peripheral":   uart,
        "base_address": info["base"],
        "rcc":          build_rcc(uart),
        "config": {
            "baudrate":    baud,
            "brr_value":   brr_value(baud),
            "word_length": bits,
            "parity":      "none",
            "stop_bits":   stop,
            "tx_pin": {
                **info["tx"],
                **({"assumed": True}
                   if True else {}),  # always assumed
            },
            "rx_pin": {
                **info["rx"],
                "assumed": True,
            },
            **({"baudrate_assumed": True}
               if baud_assumed else {}),
            **({"word_length_assumed": True}
               if bits_assumed else {}),
            **({"stop_bits_assumed": True}
               if stop_assumed else {}),
        },
        "action": {"type": "init"},
    }


def build_uart_tx(uart, baud, baud_assumed=False):
    info = USART_MAP[uart]
    return {
        "intent":       "UART_TRANSMIT",
        "peripheral":   uart,
        "base_address": info["base"],
        "rcc":          build_rcc(uart),
        "config": {
            "baudrate": baud,
            "tx_pin": {**info["tx"], "assumed": True},
            **({"baudrate_assumed": True}
               if baud_assumed else {}),
        },
        "action": {"type": "transmit"},
    }


def build_uart_rx(uart, baud, baud_assumed=False):
    info = USART_MAP[uart]
    return {
        "intent":       "UART_RECEIVE",
        "peripheral":   uart,
        "base_address": info["base"],
        "rcc":          build_rcc(uart),
        "config": {
            "baudrate": baud,
            "rx_pin": {**info["rx"], "assumed": True},
            **({"baudrate_assumed": True}
               if baud_assumed else {}),
        },
        "action": {"type": "receive"},
    }


def build_timer_delay(timer, delay_ms,
                      delay_assumed=False):
    p, per = psc_period(delay_ms)
    info   = TIMER_MAP[timer]
    return {
        "intent":       "TIMER_DELAY",
        "peripheral":   timer,
        "base_address": info["base"],
        "rcc":          build_rcc(timer),
        "config": {
            "prescaler": p,
            "period":    per,
            "delay_ms":  delay_ms,
            "unit":      "ms",
            **({"delay_assumed": True}
               if delay_assumed else {}),
        },
        "action": {"type": "delay"},
    }


def build_timer_pwm(timer, channel, duty,
                    duty_assumed=False,
                    channel_assumed=False):
    info    = TIMER_MAP[timer]
    pwm_pin = info["channels"][channel]
    period  = 999
    ccr     = int((duty / 100) * period)
    return {
        "intent":       "TIMER_PWM",
        "peripheral":   timer,
        "base_address": info["base"],
        "rcc":          build_rcc(timer),
        "config": {
            "channel":            channel,
            "prescaler":          719,
            "period":             period,
            "duty_cycle_percent": duty,
            "ccr_value":          ccr,
            "pwm_pin":            {**pwm_pin,
                                   "assumed": True},
            **({"duty_assumed": True}
               if duty_assumed else {}),
            **({"channel_assumed": True}
               if channel_assumed else {}),
        },
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
    port, pin = random.choice(SAFE_GPIO_PINS)
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
    port, pin = random.choice(SAFE_GPIO_PINS)
    speed     = "50MHz"    # default, not in prompt
    mode      = "output_push_pull"  # default
    tmpl      = random.choice(
        PARTIAL_TEMPLATES["GPIO_OUTPUT"])
    prompt = tmpl.format(P=port, N=pin)
    j = build_gpio_output(port, pin, speed, mode,
                          speed_assumed=True,
                          mode_assumed=True,
                          action_assumed=True)
    return prompt, [j], "VALID_PARTIAL"


def make_complete_gpio_toggle():
    port, pin = random.choice(SAFE_GPIO_PINS)
    delay     = random.choice([100,200,500,1000,2000])
    tmpl      = random.choice(
        COMPLETE_TEMPLATES["GPIO_TOGGLE"])
    prompt = tmpl.format(P=port, N=pin, D=delay)
    j = build_gpio_toggle(port, pin, delay)
    return prompt, [j], "VALID_COMPLETE"


def make_partial_gpio_toggle():
    port, pin = random.choice(SAFE_GPIO_PINS)
    delay     = 500   # default
    tmpl      = random.choice(
        PARTIAL_TEMPLATES["GPIO_TOGGLE"])
    prompt = tmpl.format(P=port, N=pin)
    j = build_gpio_toggle(port, pin, delay,
                          delay_assumed=True)
    return prompt, [j], "VALID_PARTIAL"


def make_complete_gpio_input():
    port, pin = random.choice(SAFE_GPIO_PINS)
    mode      = random.choice(GPIO_MODES_INPUT)
    mt        = MODE_TEXT[mode]
    tmpl      = random.choice(
        COMPLETE_TEMPLATES["GPIO_INPUT"])
    prompt = tmpl.format(P=port, N=pin,
                         MT=mt, mode=mode)
    j = build_gpio_input(port, pin, mode)
    return prompt, [j], "VALID_COMPLETE"


def make_partial_gpio_input():
    port, pin = random.choice(SAFE_GPIO_PINS)
    mode      = "input_floating"  # default
    tmpl      = random.choice(
        PARTIAL_TEMPLATES["GPIO_INPUT"])
    prompt = tmpl.format(P=port, N=pin)
    j = build_gpio_input(port, pin, mode,
                         mode_assumed=True)
    return prompt, [j], "VALID_PARTIAL"


def make_gpio_read():
    port, pin = random.choice(SAFE_GPIO_PINS)
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
    baud = 115200   # default
    bits = 8        # default
    stop = 1        # default
    tmpl = random.choice(
        PARTIAL_TEMPLATES["UART_INIT"])
    prompt = tmpl.format(U=uart, B=baud)
    j = build_uart_init(uart, baud, bits, stop,
                        baud_assumed=True,
                        bits_assumed=True,
                        stop_assumed=True)
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
    baud = 115200
    tmpl = random.choice(PARTIAL_TEMPLATES["UART_TX"])
    prompt = tmpl.format(U=uart, B=baud)
    j = build_uart_tx(uart, baud, baud_assumed=True)
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
    baud = 115200
    tmpl = random.choice(PARTIAL_TEMPLATES["UART_RX"])
    prompt = tmpl.format(U=uart, B=baud)
    j = build_uart_rx(uart, baud, baud_assumed=True)
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
    timer = DEFAULTS["TIMER"]["instance"]
    delay = random.choice([100,200,500,1000,2000])
    tmpl  = random.choice(
        PARTIAL_TEMPLATES["TIMER_DELAY"])
    prompt = tmpl.format(T=timer, D=delay)
    # delay is in prompt but timer assumed
    j = build_timer_delay(timer, delay)
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
    timer   = random.choice(["TIM2","TIM3","TIM4"])
    channel = 1      # default
    duty    = 50     # default
    tmpl    = random.choice(
        PARTIAL_TEMPLATES["TIMER_PWM"])
    prompt = tmpl.format(T=timer, C=channel, DT=duty)
    j = build_timer_pwm(timer, channel, duty,
                        duty_assumed=True,
                        channel_assumed=True)
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
            if cfg.get("tx_pin") or cfg.get("rx_pin"):
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
        noise = random.choice(noise_levels)
        noisy = apply_noise(clean_p, noise)
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
                            baud = block["config"]["baudrate"]
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

        examples.append({
            "id":           f"ex_{ex_id:05d}",
            "prompt":       noisy,
            "clean_prompt": clean,
            "complexity":   "complex",
            "data_class":   "VALID_COMPLETE",
            "noise_level":  noise,
            "output":       jout,
        })
        stats["VALID_COMPLETE"] += 1
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
                




