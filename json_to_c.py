


#!/usr/bin/env python3
"""
STM32F103VB JSON -> bare-metal C dataset generator.

Source:
    dataset_full(20260816-095344).json

Design goals:
- Preserve ALL 12,000 source records.
- Do not reject VALID_PARTIAL records merely because fields are absent.
- Apply the same inference defaults used by json_builder.py.
- Generate direct register-level CMSIS C only (no HAL/SPL/LL).
- Preserve ERROR/AMBIGUOUS records instead of inventing hardware code.
- Also write a code-only dataset containing only records for which executable
  C can actually be generated.

Outputs:
    stm32_instruction_code_v3_all.jsonl
        12,000 records. 1,200 ERROR/AMBIGUOUS records have a clarification
        response because executable C cannot truthfully be generated for them.

    stm32_instruction_code_v3_code_only.jsonl
        Only executable-code records.

    stm32_instruction_code_v3_clarification.jsonl
        ERROR/AMBIGUOUS records kept separately.

The source JSON is authoritative for hardware facts. Missing optional fields
are filled using the same defaults as json_builder.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE = Path(__file__).resolve().parent
INPUT = BASE / "dataset" / "dataset_full.json"
ALL_OUTPUT = BASE / "stm32_instruction_code_v3_all.jsonl"
CODE_OUTPUT = BASE / "stm32_instruction_code_v3_code_only.jsonl"
CLARIFICATION_OUTPUT = BASE / "stm32_instruction_code_v3_clarification.jsonl"

# ---------------------------------------------------------------------------
# Same defaults as json_builder.py
# ---------------------------------------------------------------------------
DEFAULT_GPIO_OUTPUT_MODE = "output_push_pull"
DEFAULT_GPIO_INPUT_MODE = "input_floating"
DEFAULT_GPIO_SPEED = "50MHz"

DEFAULT_UART = "USART1"
DEFAULT_BAUD = 115200
DEFAULT_WORD_LENGTH = 8
DEFAULT_STOP_BITS = 1
DEFAULT_PARITY = "none"

DEFAULT_TIMER = "TIM2"
DEFAULT_DELAY_MS = 500
DEFAULT_TIMER_CHANNEL = 1
DEFAULT_PWM_DUTY = 50
DEFAULT_TIMER_DELAY_PSC = 7199
DEFAULT_PWM_PSC = 719
DEFAULT_PWM_ARR = 999

# json_builder.py uses 8 MHz for USART BRR calculation.
USART_PCLK_HZ = 8_000_000

GPIO_RCC_BIT = {"A": 2, "B": 3, "C": 4, "D": 5}

USART_MAP = {
    "USART1": {
        "tx": ("A", 9), "rx": ("A", 10),
        "rcc": ("RCC->APB2ENR", 14),
    },
    "USART2": {
        "tx": ("A", 2), "rx": ("A", 3),
        "rcc": ("RCC->APB1ENR", 17),
    },
    "USART3": {
        "tx": ("B", 10), "rx": ("B", 11),
        "rcc": ("RCC->APB1ENR", 18),
    },
}

TIMER_MAP = {
    "TIM2": {
        1: ("A", 0), 2: ("A", 1), 3: ("A", 2), 4: ("A", 3),
        "rcc": ("RCC->APB1ENR", 0),
    },
    "TIM3": {
        1: ("A", 6), 2: ("A", 7), 3: ("B", 0), 4: ("B", 1),
        "rcc": ("RCC->APB1ENR", 1),
    },
    "TIM4": {
        1: ("B", 6), 2: ("B", 7), 3: ("B", 8), 4: ("B", 9),
        "rcc": ("RCC->APB1ENR", 2),
    },
}

VALID_CODE_INTENTS = {
    "GPIO_OUTPUT", "GPIO_INPUT", "GPIO_TOGGLE", "GPIO_READ",
    "RCC_ENABLE", "UART_INIT", "UART_TRANSMIT", "UART_RECEIVE",
    "TIMER_DELAY", "TIMER_PWM",
}

NON_CODE_INTENTS = {"ERROR", "AMBIGUOUS", "INVALID", "UNKNOWN"}


# ---------------------------------------------------------------------------
# Utility / defaults
# ---------------------------------------------------------------------------

def as_int(value: Any, default: int) -> int:
    try:
        if isinstance(value, str):
            return int(value, 0)
        return int(value)
    except (TypeError, ValueError):
        return default


def compute_brr(baudrate: int) -> int:
    """Exactly mirror json_builder.py."""
    usartdiv = USART_PCLK_HZ / (16 * baudrate)
    mantissa = int(usartdiv)
    fraction = int((usartdiv - mantissa) * 16)
    return (mantissa << 4) | fraction


def gpio_nibble(mode: str, speed: str) -> int:
    """STM32F1 GPIO CRL/CRH nibble: CNF[1:0] + MODE[1:0]."""
    mode_n = str(mode or "").lower().replace("-", "_").replace(" ", "_")
    speed_n = str(speed or DEFAULT_GPIO_SPEED).lower().replace(" ", "")

    if mode_n in {"input_floating", "floating", "input"}:
        return 0x4

    if mode_n in {"input_pullup", "pull_up", "pullup",
                  "input_pulldown", "pull_down", "pulldown"}:
        # CNF=10, MODE=00. ODR determines pull-up/down.
        return 0x8

    speed_code = {
        "2mhz": 0x2,
        "10mhz": 0x1,
        "50mhz": 0x3,
    }.get(speed_n, 0x3)

    if mode_n in {"output_open_drain", "open_drain"}:
        return 0x4 | speed_code

    # output_push_pull default
    return speed_code


def gpio_config_lines(port: str, pin: int, nibble: int) -> List[str]:
    reg = f"GPIO{port}->CRL" if pin < 8 else f"GPIO{port}->CRH"
    shift = (pin % 8) * 4
    return [
        f"{reg} &= ~(0xFU << {shift});",
        f"{reg} |= (0x{nibble:X}U << {shift});",
    ]


def gpio_clock_line(port: str) -> str:
    return f"RCC->APB2ENR |= (1U << {GPIO_RCC_BIT[port]});"


def source_rcc_line(item: Dict[str, Any]) -> Optional[str]:
    """Prefer the RCC register/bit stored in the source JSON."""
    rcc = item.get("rcc")
    if isinstance(rcc, dict):
        reg = rcc.get("register")
        bit = rcc.get("bit")
        if isinstance(reg, str) and isinstance(bit, int):
            target = "RCC->APB2ENR" if reg == "RCC_APB2ENR" else "RCC->APB1ENR"
            return f"{target} |= (1U << {bit});"
    return None


def dedupe(lines: List[str]) -> List[str]:
    seen = set()
    result = []
    for line in lines:
        if line not in seen:
            result.append(line)
            seen.add(line)
    return result


# ---------------------------------------------------------------------------
# GPIO
# ---------------------------------------------------------------------------

def gpio_fields(item: Dict[str, Any], intent: str) -> Tuple[str, int, str, str]:
    cfg = item.get("config") or {}

    port = str(cfg.get("port", "A")).upper()
    if port.startswith("P"):
        port = port[1:]
    if port not in GPIO_RCC_BIT:
        port = "A"

    pin = as_int(cfg.get("pin"), 0)
    if not 0 <= pin <= 15:
        pin = 0

    if intent in {"GPIO_INPUT", "GPIO_READ"}:
        mode = str(cfg.get("mode", DEFAULT_GPIO_INPUT_MODE))
    else:
        mode = str(cfg.get("mode", DEFAULT_GPIO_OUTPUT_MODE))

    speed = str(cfg.get("speed", DEFAULT_GPIO_SPEED))
    return port, pin, mode, speed


def gpio_setup(item: Dict[str, Any], intent: str) -> List[str]:
    port, pin, mode, speed = gpio_fields(item, intent)
    lines = [gpio_clock_line(port)]

    if intent in {"GPIO_INPUT", "GPIO_READ"}:
        nibble = gpio_nibble(mode, speed)
        lines += gpio_config_lines(port, pin, nibble)

        mode_n = mode.lower().replace("-", "_").replace(" ", "_")
        if mode_n in {"input_pullup", "pull_up", "pullup"}:
            lines.append(f"GPIO{port}->ODR |= (1U << {pin});")
        elif mode_n in {"input_pulldown", "pull_down", "pulldown"}:
            lines.append(f"GPIO{port}->ODR &= ~(1U << {pin});")
    else:
        lines += gpio_config_lines(port, pin, gpio_nibble(mode, speed))

    return lines


def gpio_code(item: Dict[str, Any], intent: str, index: int) -> Tuple[List[str], List[str]]:
    """Return (setup_lines, runtime_lines)."""
    port, pin, mode, speed = gpio_fields(item, intent)
    setup = gpio_setup(item, intent)
    runtime: List[str] = []

    if intent == "GPIO_OUTPUT":
        runtime.append(f"GPIO{port}->BSRR = (1U << {pin});")
    elif intent == "GPIO_TOGGLE":
        runtime.append(f"GPIO{port}->ODR ^= (1U << {pin});")
    elif intent == "GPIO_READ":
        runtime.append(
            f"volatile uint32_t pin_state_{index} = GPIO{port}->IDR & (1U << {pin});"
        )
    elif intent == "GPIO_INPUT":
        runtime.append(
            f"volatile uint32_t pin_state_{index} = GPIO{port}->IDR & (1U << {pin});"
        )

    return setup, runtime


# ---------------------------------------------------------------------------
# USART
# ---------------------------------------------------------------------------

def uart_name(item: Dict[str, Any]) -> str:
    uart = str(item.get("peripheral") or DEFAULT_UART).upper()
    return uart if uart in USART_MAP else DEFAULT_UART


def uart_config(item: Dict[str, Any]) -> Tuple[str, int, int, int]:
    cfg = item.get("config") or {}
    uart = uart_name(item)
    baud = as_int(cfg.get("baudrate"), DEFAULT_BAUD)
    word = as_int(cfg.get("word_length"), DEFAULT_WORD_LENGTH)
    stop = as_int(cfg.get("stop_bits"), DEFAULT_STOP_BITS)
    return uart, baud, word, stop


def usart_gpio_setup(uart: str) -> List[str]:
    tx_port, tx_pin = USART_MAP[uart]["tx"]
    rx_port, rx_pin = USART_MAP[uart]["rx"]

    lines = [gpio_clock_line(tx_port)]
    if rx_port != tx_port:
        lines.append(gpio_clock_line(rx_port))

    # USART TX = alternate-function push-pull, 50 MHz => 0xB
    lines += gpio_config_lines(tx_port, tx_pin, 0xB)
    # USART RX = input floating => 0x4
    lines += gpio_config_lines(rx_port, rx_pin, 0x4)
    return lines


def usart_init(item: Dict[str, Any], enable_te: bool = True,
               enable_re: bool = True) -> List[str]:
    uart, baud, word, stop = uart_config(item)
    rcc = source_rcc_line(item)
    if rcc is None:
        rcc_reg, rcc_bit = USART_MAP[uart]["rcc"]
        rcc = f"{rcc_reg} |= (1U << {rcc_bit});"

    brr = compute_brr(baud)
    lines = usart_gpio_setup(uart)
    lines += [
        rcc,
        f"{uart}->BRR = 0x{brr:X}U;",
        f"{uart}->CR1 = 0;",
    ]

    if word == 9:
        lines.append(f"{uart}->CR1 |= USART_CR1_M;")

    if stop == 2:
        lines.append(f"{uart}->CR2 = (2U << USART_CR2_STOP_Pos);")
    else:
        lines.append(f"{uart}->CR2 = 0U;")

    enable_bits = []
    if enable_te:
        enable_bits.append("USART_CR1_TE")
    if enable_re:
        enable_bits.append("USART_CR1_RE")
    enable_bits.append("USART_CR1_UE")
    lines.append(f"{uart}->CR1 |= {' | '.join(enable_bits)};")
    return lines


def uart_code(item: Dict[str, Any], intent: str) -> Tuple[List[str], List[str]]:
    setup: List[str]
    runtime: List[str] = []
    uart, _, _, _ = uart_config(item)

    if intent == "UART_INIT":
        setup = usart_init(item, enable_te=True, enable_re=True)
    elif intent == "UART_TRANSMIT":
        setup = usart_init(item, enable_te=True, enable_re=False)
        runtime += [
            "uint8_t data = 0x55U;",
            f"while (!( {uart}->SR & USART_SR_TXE )) {{ }}",
            f"{uart}->DR = data;",
        ]
    elif intent == "UART_RECEIVE":
        setup = usart_init(item, enable_te=False, enable_re=True)
        runtime += [
            f"while (!( {uart}->SR & USART_SR_RXNE )) {{ }}",
            f"volatile uint16_t received = (uint16_t){uart}->DR;",
        ]
    else:
        setup, runtime = [], []

    return setup, runtime


# ---------------------------------------------------------------------------
# Timers
# ---------------------------------------------------------------------------

def timer_name(item: Dict[str, Any]) -> str:
    timer = str(item.get("peripheral") or DEFAULT_TIMER).upper()
    return timer if timer in TIMER_MAP else DEFAULT_TIMER


def timer_rcc_line(timer: str, item: Optional[Dict[str, Any]] = None) -> str:
    if item is not None:
        line = source_rcc_line(item)
        if line:
            return line
    reg, bit = TIMER_MAP[timer]["rcc"]
    return f"{reg} |= (1U << {bit});"


def timer_delay_function(timer: str, psc: int, arr: int, name: str) -> List[str]:
    return [
        f"static void {name}(void)",
        "{",
        f"    {timer}->PSC = {psc}U;",
        f"    {timer}->ARR = {arr}U;",
        f"    {timer}->EGR = TIM_EGR_UG;",
        f"    {timer}->SR &= ~TIM_SR_UIF;",
        f"    {timer}->CR1 |= TIM_CR1_CEN;",
        f"    while (!({timer}->SR & TIM_SR_UIF)) {{ }}",
        f"    {timer}->CR1 &= ~TIM_CR1_CEN;",
        f"    {timer}->SR &= ~TIM_SR_UIF;",
        "}",
    ]


def timer_delay_code(item: Dict[str, Any], index: int) -> Tuple[List[str], List[str], List[str]]:
    """Return (setup, runtime, helper_function)."""
    cfg = item.get("config") or {}
    timer = timer_name(item)

    delay = as_int(cfg.get("delay_ms"), DEFAULT_DELAY_MS)
    psc = as_int(cfg.get("prescaler"), DEFAULT_TIMER_DELAY_PSC)
    period = as_int(cfg.get("period"), delay * 10)
    arr = max(period - 1, 0)

    setup = [timer_rcc_line(timer, item)]
    helper_name = f"timer_delay_{index}"
    helper = timer_delay_function(timer, psc, arr, helper_name)
    runtime = [f"{helper_name}();"]
    return setup, runtime, helper


def timer_pwm_code(item: Dict[str, Any], index: int) -> Tuple[List[str], List[str]]:
    cfg = item.get("config") or {}
    timer = timer_name(item)

    channel = as_int(cfg.get("channel"), DEFAULT_TIMER_CHANNEL)
    if channel not in {1, 2, 3, 4}:
        channel = DEFAULT_TIMER_CHANNEL

    duty = as_int(
        cfg.get("duty_cycle_percent", cfg.get("duty")),
        DEFAULT_PWM_DUTY,
    )
    duty = max(0, min(100, duty))

    psc = as_int(cfg.get("prescaler"), DEFAULT_PWM_PSC)
    arr = as_int(cfg.get("period"), DEFAULT_PWM_ARR)
    ccr = as_int(cfg.get("ccr_value"), int((duty / 100.0) * arr))

    port, pin = TIMER_MAP[timer][channel]
    setup = [
        gpio_clock_line(port),
        *gpio_config_lines(port, pin, 0xB),  # AF push-pull, 50 MHz
        timer_rcc_line(timer, item),
        f"{timer}->PSC = {psc}U;",
        f"{timer}->ARR = {arr}U;",
    ]

    if channel == 1:
        setup += [
            f"{timer}->CCR1 = {ccr}U;",
            f"{timer}->CCMR1 &= ~(TIM_CCMR1_OC1M | TIM_CCMR1_OC1PE);",
            f"{timer}->CCMR1 |= (6U << TIM_CCMR1_OC1M_Pos) | TIM_CCMR1_OC1PE;",
            f"{timer}->CCER |= TIM_CCER_CC1E;",
        ]
    elif channel == 2:
        setup += [
            f"{timer}->CCR2 = {ccr}U;",
            f"{timer}->CCMR1 &= ~(TIM_CCMR1_OC2M | TIM_CCMR1_OC2PE);",
            f"{timer}->CCMR1 |= (6U << TIM_CCMR1_OC2M_Pos) | TIM_CCMR1_OC2PE;",
            f"{timer}->CCER |= TIM_CCER_CC2E;",
        ]
    elif channel == 3:
        setup += [
            f"{timer}->CCR3 = {ccr}U;",
            f"{timer}->CCMR2 &= ~(TIM_CCMR2_OC3M | TIM_CCMR2_OC3PE);",
            f"{timer}->CCMR2 |= (6U << TIM_CCMR2_OC3M_Pos) | TIM_CCMR2_OC3PE;",
            f"{timer}->CCER |= TIM_CCER_CC3E;",
        ]
    else:
        setup += [
            f"{timer}->CCR4 = {ccr}U;",
            f"{timer}->CCMR2 &= ~(TIM_CCMR2_OC4M | TIM_CCMR2_OC4PE);",
            f"{timer}->CCMR2 |= (6U << TIM_CCMR2_OC4M_Pos) | TIM_CCMR2_OC4PE;",
            f"{timer}->CCER |= TIM_CCER_CC4E;",
        ]

    setup += [
        f"{timer}->EGR = TIM_EGR_UG;",
        f"{timer}->CR1 |= TIM_CR1_ARPE | TIM_CR1_CEN;",
    ]
    return setup, []


# ---------------------------------------------------------------------------
# RCC
# ---------------------------------------------------------------------------

def rcc_code(item: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    line = source_rcc_line(item)
    if line:
        return [line], []

    # Fallback only if source RCC block is absent.
    peri = str(item.get("peripheral", "GPIOA")).upper()
    if peri.startswith("GPIO") and peri[-1:] in GPIO_RCC_BIT:
        return [gpio_clock_line(peri[-1])], []
    if peri in USART_MAP:
        reg, bit = USART_MAP[peri]["rcc"]
        return [f"{reg} |= (1U << {bit});"], []
    if peri in TIMER_MAP:
        return [timer_rcc_line(peri)], []
    return [], []


# ---------------------------------------------------------------------------
# Program assembly
# ---------------------------------------------------------------------------

def build_program(outputs: List[Dict[str, Any]]) -> str:
    setup: List[str] = []
    runtime_once: List[str] = []
    runtime_loop: List[str] = []
    helpers: List[str] = []

    has_toggle = False

    for idx, item in enumerate(outputs):
        intent = item.get("intent")
        if intent not in VALID_CODE_INTENTS:
            continue

        if intent in {"GPIO_OUTPUT", "GPIO_INPUT", "GPIO_READ"}:
            s, r = gpio_code(item, intent, idx)
            setup += s
            runtime_once += r

        elif intent == "GPIO_TOGGLE":
            s, r = gpio_code(item, intent, idx)
            setup += s
            runtime_loop += r
            has_toggle = True

            timing = item.get("timing") or {}
            delay_ms = as_int(timing.get("delay_ms"), DEFAULT_DELAY_MS)
            timer = DEFAULT_TIMER
            # Match json_builder's timer-delay defaults.
            psc = DEFAULT_TIMER_DELAY_PSC
            arr = max(delay_ms * 10 - 1, 0)
            helper_name = f"gpio_toggle_delay_{idx}"
            setup.append(timer_rcc_line(timer))
            helpers += timer_delay_function(timer, psc, arr, helper_name)
            runtime_loop.append(f"{helper_name}();")

        elif intent == "RCC_ENABLE":
            s, r = rcc_code(item)
            setup += s
            runtime_once += r

        elif intent in {"UART_INIT", "UART_TRANSMIT", "UART_RECEIVE"}:
            s, r = uart_code(item, intent)
            setup += s
            runtime_once += r

        elif intent == "TIMER_DELAY":
            s, r, h = timer_delay_code(item, idx)
            setup += s
            runtime_once += r
            helpers += h

        elif intent == "TIMER_PWM":
            s, r = timer_pwm_code(item, idx)
            setup += s
            runtime_once += r

    setup = dedupe(setup)
    runtime_once = dedupe(runtime_once)
    runtime_loop = dedupe(runtime_loop)

    # If there is a toggle, its timing helper should be executed in the loop.
    # Other one-shot operations remain before the loop.
    body: List[str] = []
    body += [f"    {line}" for line in setup]
    body += [f"    {line}" for line in runtime_once]

    if has_toggle:
        body += ["", "    while (1)", "    {"]
        body += [f"        {line}" for line in runtime_loop]
        body += ["    }"]
    else:
        body += ["", "    while (1)", "    {", "    }"]

    # Helper functions must appear before main.
    helper_text: List[str] = []
    if helpers:
        helper_text += ["#include \"stm32f103xb.h\"", "#include <stdint.h>", ""]
        helper_text += helpers
        helper_text += [""]
        header = "\n".join(helper_text)
    else:
        header = "#include \"stm32f103xb.h\"\n#include <stdint.h>\n"

    return header + "\nint main(void)\n{\n" + "\n".join(body) + "\n}\n"


# ---------------------------------------------------------------------------
# Non-code responses
# ---------------------------------------------------------------------------

def clarification_response(row: Dict[str, Any]) -> str:
    out = row.get("output") or [{}]
    first = out[0] if isinstance(out[0], dict) else {}
    intent = first.get("intent", "UNKNOWN")
    details = first.get("error_details") or {}
    message = details.get("message", "The instruction cannot be converted to executable STM32 code from the supplied specification.")
    suggestion = details.get("suggestion", "Provide the missing or valid STM32 peripheral parameters.")

    return (
        "/* STM32F103VB instruction requires clarification; no hardware code "
        "was invented. */\n"
        f"/* Intent: {intent} */\n"
        f"/* Reason: {message} */\n"
        f"/* Suggestion: {suggestion} */\n"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    source = json.loads(INPUT.read_text())
    if not isinstance(source, list):
        raise ValueError("Input dataset must be a top-level JSON list")

    all_lines: List[str] = []
    code_lines: List[str] = []
    clarification_lines: List[str] = []

    code_count = 0
    clarification_count = 0
    intent_counts: Dict[str, int] = {}

    for row in source:
        outputs = row.get("output") or []
        intents = [
            o.get("intent") for o in outputs
            if isinstance(o, dict) and o.get("intent")
        ]
        for intent in intents:
            intent_counts[intent] = intent_counts.get(intent, 0) + 1

        is_code = bool(outputs) and all(
            intent in VALID_CODE_INTENTS for intent in intents
        )

        if is_code:
            response = build_program(outputs)
            task_type = "code_generation"
            code_count += 1
        else:
            response = clarification_response(row)
            task_type = "clarification_or_invalid"
            clarification_count += 1

        record = {
            "id": row.get("id"),
            "instruction": row.get("prompt", ""),
            "clean_instruction": row.get("clean_prompt", row.get("prompt", "")),
            "input_json": outputs,
            "response": response,
            "task_type": task_type,
            "mcu": "STM32F103VB",
            "bare_metal": True,
            "uses_hal": False,
            "uses_spl": False,
        }

        line = json.dumps(record, ensure_ascii=False)
        all_lines.append(line)

        if is_code:
            code_lines.append(line)
        else:
            clarification_lines.append(line)

    ALL_OUTPUT.write_text("\n".join(all_lines) + "\n")
    CODE_OUTPUT.write_text("\n".join(code_lines) + "\n")
    CLARIFICATION_OUTPUT.write_text("\n".join(clarification_lines) + "\n")

    print("=" * 70)
    print("STM32F103VB JSON -> C DATASET GENERATION")
    print("=" * 70)
    print(f"Input records          : {len(source)}")
    print(f"Executable-code records: {code_count}")
    print(f"Clarification records  : {clarification_count}")
    print(f"ALL output records     : {len(all_lines)}")
    print()
    print("Intent counts:")
    for k, v in sorted(intent_counts.items()):
        print(f"  {k:18s}: {v}")
    print()
    print(f"ALL          : {ALL_OUTPUT}")
    print(f"CODE ONLY    : {CODE_OUTPUT}")
    print(f"CLARIFICATION: {CLARIFICATION_OUTPUT}")
    print("=" * 70)

    assert len(all_lines) == len(source) == 12000
    assert len(code_lines) + len(clarification_lines) == 12000


if __name__ == "__main__":
    main()