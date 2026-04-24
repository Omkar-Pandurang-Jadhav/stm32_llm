import json
import re

# ══════════════════════════════════════════════════════
# HARDWARE TABLES — STM32F103VB
# ══════════════════════════════════════════════════════

SYSTEM_CLOCK   = 72_000_000
RCC_BASE       = "0x40021000"
APB2ENR_OFFSET = "0x18"
APB1ENR_OFFSET = "0x1C"

RCC_MAP = {
    "GPIOA": {"register":"RCC_APB2ENR","offset":APB2ENR_OFFSET,"bit":2, "name":"IOPAEN"},
    "GPIOB": {"register":"RCC_APB2ENR","offset":APB2ENR_OFFSET,"bit":3, "name":"IOPBEN"},
    "GPIOC": {"register":"RCC_APB2ENR","offset":APB2ENR_OFFSET,"bit":4, "name":"IOPCEN"},
    "GPIOD": {"register":"RCC_APB2ENR","offset":APB2ENR_OFFSET,"bit":5, "name":"IOPDEN"},
    "USART1":{"register":"RCC_APB2ENR","offset":APB2ENR_OFFSET,"bit":14,"name":"USART1EN"},
    "USART2":{"register":"RCC_APB1ENR","offset":APB1ENR_OFFSET,"bit":17,"name":"USART2EN"},
    "USART3":{"register":"RCC_APB1ENR","offset":APB1ENR_OFFSET,"bit":18,"name":"USART3EN"},
    "TIM2":  {"register":"RCC_APB1ENR","offset":APB1ENR_OFFSET,"bit":0, "name":"TIM2EN"},
    "TIM3":  {"register":"RCC_APB1ENR","offset":APB1ENR_OFFSET,"bit":1, "name":"TIM3EN"},
    "TIM4":  {"register":"RCC_APB1ENR","offset":APB1ENR_OFFSET,"bit":2, "name":"TIM4EN"},
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

VALID_BAUDRATES = [9600, 19200, 38400, 57600, 115200]

PORT_VALID_PINS = {
    "A": list(range(0, 16)),
    "B": list(range(0, 16)),
    "C": [13, 14, 15],
    "D": [0, 1],
}

RESERVED_PINS = {
    ("A",13),("A",14),("A",15),
    ("B",3), ("B",4),
}

# ══════════════════════════════════════════════════════
# DEFAULT VALUES
# Applied ONLY at inference — never during training
# ══════════════════════════════════════════════════════

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
        "instance":    "USART1",
    },
    "TIMER": {
        "instance":  "TIM2",
        "delay_ms":  500,
        "channel":   1,
        "duty":      50,
    },
}


# ══════════════════════════════════════════════════════
# ENTITY PARSER
# Converts BIO tag dict → clean field values
# ══════════════════════════════════════════════════════

def compute_brr(pclk,baudrate):
    usartdiv =pclk/(16*baudrate)

    mantissa=int(usartdiv)
    fraction=int((usartdiv-mantissa)*16)

    return (mantissa<<4) | fraction 
def parse_entities(entities):
    """
    Input:  dict of {token: BIO_tag}
    Example:
      {
        "PA":     "B-PORT",
        "5":      "B-PIN",
        "50MHz":  "B-SPEED",
        "USART1": "B-UART",
        "115200": "B-BAUDRATE",
        "TIM3":   "B-TIMER",
        "500ms":  "B-DELAY",
        "CH1":    "B-CHANNEL",
        "50%":    "B-DUTY",
        "output_push_pull": "B-MODE",
      }

    Output: clean field dict
      {
        "port":     "A",
        "pin":      5,
        "speed":    "50MHz",
        "uart":     "USART1",
        "baudrate": 115200,
        "timer":    "TIM3",
        "delay_ms": 500,
        "channel":  1,
        "duty":     50,
        "mode":     "output_push_pull",
      }
    """
    parsed = {}

    for token, tag in entities.items():
        token = token.strip()

        if tag == "B-PORT":
            # Normalize: "PA" → "A", "A" → "A"
            port = token.upper()
            if port.startswith("P"):
                port = port[1:]   # "PA" → "A"
            if port in PORT_VALID_PINS:
                parsed["port"] = port

        elif tag == "B-PIN":
            try:
                parsed["pin"] = int(token)
            except ValueError:
                pass

        elif tag == "B-SPEED":
            # "50MHz", "10MHz", "2MHz"
            parsed["speed"] = token

        elif tag == "B-MODE":
            parsed["mode"] = token

        elif tag == "B-UART":
            # Normalize UART1 → USART1
            u = token.upper()
            if u.startswith("UART") and \
               not u.startswith("USART"):
                u = "US" + u          # UART1 → USART1
            if u in USART_MAP:
                parsed["uart"] = u

        elif tag == "B-BAUDRATE":
            try:
                parsed["baudrate"] = int(token)
            except ValueError:
                pass

        elif tag == "B-TIMER":
            t = token.upper()
            if t in TIMER_MAP:
                parsed["timer"] = t

        elif tag == "B-DELAY":
            # "500ms" → 500,  "200ms" → 200
            m = re.match(r"(\d+)\s*ms", token,
                         re.IGNORECASE)
            if m:
                parsed["delay_ms"] = int(m.group(1))

        elif tag == "B-CHANNEL":
            # "CH1" → 1, "CH3" → 3
            m = re.match(r"CH(\d)", token,
                         re.IGNORECASE)
            if m:
                parsed["channel"] = int(m.group(1))

        elif tag == "B-DUTY":
            # "50%" → 50
            m = re.match(r"(\d+)\s*%", token)
            if m:
                parsed["duty"] = int(m.group(1))

    return parsed


# ══════════════════════════════════════════════════════
# RCC BUILDER
# ══════════════════════════════════════════════════════

def build_rcc_block(peripheral_name):
    """
    Builds RCC block from peripheral name.
    peripheral_name: "GPIOA", "USART1", "TIM3" etc.
    """
    if peripheral_name not in RCC_MAP:
        return {}
    r = RCC_MAP[peripheral_name]
    return {
        "register":        r["register"],
        "base_address":    RCC_BASE,
        "offset":          r["offset"],
        "bit":             r["bit"],
        "peripheral_name": r["name"],
    }


# ══════════════════════════════════════════════════════
# HARDWARE VALIDATOR
# ══════════════════════════════════════════════════════

def validate_pin(port, pin):
    """
    Returns (is_valid, error_message)
    """
    if port not in PORT_VALID_PINS:
        return False, f"Port {port} invalid"
    if pin not in PORT_VALID_PINS[port]:
        return False, (f"P{port}{pin} invalid for "
                       f"STM32F103VB")
    if (port, pin) in RESERVED_PINS:
        return False, (f"P{port}{pin} reserved "
                       f"for JTAG/SWD")
    return True, None


def snap_baudrate(baud):
    """
    Snap to nearest valid baudrate.
    """
    return min(VALID_BAUDRATES,
               key=lambda x: abs(x - baud))


# ══════════════════════════════════════════════════════
# INTENT-SPECIFIC BUILDERS
# Each returns complete JSON block
# ══════════════════════════════════════════════════════

def build_gpio_output(fields):
    port  = fields.get("port",
            DEFAULTS["GPIO"]["mode_output"][0])
    pin   = fields.get("pin", 0)
    mode  = fields.get("mode",
            DEFAULTS["GPIO"]["mode_output"])
    speed = fields.get("speed",
            DEFAULTS["GPIO"]["speed"])

    # Track what was assumed
    assumed = []
    if "mode"  not in fields: assumed.append("mode")
    if "speed" not in fields: assumed.append("speed")

    # Validate
    ok, err = validate_pin(port, pin)
    if not ok:
        return build_error_json(
            "INVALID_PIN", err,
            f"Use a valid pin for port {port}")

    cfg = {
        "port":  port,
        "pin":   pin,
        "mode":  mode,
        "speed": speed,
    }
    if assumed:
        cfg["assumed_fields"] = assumed

    return {
        "intent":     "GPIO_OUTPUT",
        "peripheral": "GPIO",
        "rcc":        build_rcc_block(f"GPIO{port}"),
        "config":     cfg,
        "action":     {"type": "set_high"},
    }


def build_gpio_input(fields):
    port = fields.get("port", "A")
    pin  = fields.get("pin", 0)
    mode = fields.get("mode",
           DEFAULTS["GPIO"]["mode_input"])

    assumed = []
    if "mode" not in fields:
        assumed.append("mode")

    ok, err = validate_pin(port, pin)
    if not ok:
        return build_error_json(
            "INVALID_PIN", err,
            f"Use a valid pin for port {port}")

    cfg = {
        "port": port,
        "pin":  pin,
        "mode": mode,
    }
    if assumed:
        cfg["assumed_fields"] = assumed

    return {
        "intent":     "GPIO_INPUT",
        "peripheral": "GPIO",
        "rcc":        build_rcc_block(f"GPIO{port}"),
        "config":     cfg,
        "action":     {"type": "read"},
    }


def build_gpio_toggle(fields):
    port     = fields.get("port", "A")
    pin      = fields.get("pin", 0)
    delay_ms = fields.get("delay_ms",
               DEFAULTS["TIMER"]["delay_ms"])

    assumed = []
    if "delay_ms" not in fields:
        assumed.append("delay_ms")

    ok, err = validate_pin(port, pin)
    if not ok:
        return build_error_json(
            "INVALID_PIN", err,
            f"Use a valid pin for port {port}")

    cfg = {
        "port":  port,
        "pin":   pin,
        "mode":  DEFAULTS["GPIO"]["mode_output"],
        "speed": DEFAULTS["GPIO"]["speed"],
    }

    result = {
        "intent":     "GPIO_TOGGLE",
        "peripheral": "GPIO",
        "rcc":        build_rcc_block(f"GPIO{port}"),
        "config":     cfg,
        "action":     {"type": "toggle"},
        "timing":     {"delay_ms": delay_ms},
    }
    if assumed:
        result["assumed_fields"] = assumed
    return result


def build_gpio_read(fields):
    port = fields.get("port", "A")
    pin  = fields.get("pin", 0)

    ok, err = validate_pin(port, pin)
    if not ok:
        return build_error_json(
            "INVALID_PIN", err,
            f"Use a valid pin for port {port}")

    return {
        "intent":     "GPIO_READ",
        "peripheral": "GPIO",
        "rcc":        build_rcc_block(f"GPIO{port}"),
        "config":     {"port": port, "pin": pin},
        "action":     {"type": "read_idr"},
    }


def build_uart_init(fields):
    uart = fields.get("uart",
           DEFAULTS["UART"]["instance"])
    baud = fields.get("baudrate",
           DEFAULTS["UART"]["baudrate"])
    bits = fields.get("word_length",
           DEFAULTS["UART"]["word_length"])
    stop = fields.get("stop_bits",
           DEFAULTS["UART"]["stop_bits"])

    assumed = []
    if "uart"      not in fields: assumed.append("uart")
    if "baudrate"  not in fields: assumed.append("baudrate")
    if "word_length" not in fields: assumed.append("word_length")
    if "stop_bits"   not in fields: assumed.append("stop_bits")

    if uart not in USART_MAP:
        return build_error_json(
            "INVALID_UART",
            f"{uart} not valid on STM32F103VB",
            "Use USART1, USART2, or USART3")

    # Snap to nearest valid baudrate
    baud = snap_baudrate(baud)
    info = USART_MAP[uart]

    pclk = 8000000
    cfg = {
        "baudrate":    baud,
        "brr_value":   hex(compute_brr(pclk,baud)),
        "word_length": bits,
        "parity":      "none",
        "stop_bits":   stop,
        "tx_pin":      info["tx"],
        "rx_pin":      info["rx"],
    }
    if assumed:
        cfg["assumed_fields"] = assumed

    return {
        "intent":       "UART_INIT",
        "peripheral":   uart,
        "base_address": info["base"],
        "rcc":          build_rcc_block(uart),
        "config":       cfg,
        "action":       {"type": "init"},
    }


def build_uart_transmit(fields):
    uart = fields.get("uart",
           DEFAULTS["UART"]["instance"])
    baud = fields.get("baudrate",
           DEFAULTS["UART"]["baudrate"])

    assumed = []
    if "uart"     not in fields: assumed.append("uart")
    if "baudrate" not in fields: assumed.append("baudrate")

    if uart not in USART_MAP:
        return build_error_json(
            "INVALID_UART",
            f"{uart} not valid on STM32F103VB",
            "Use USART1, USART2, or USART3")

    baud = snap_baudrate(baud)
    info = USART_MAP[uart]

    cfg = {
        "baudrate": baud,
        "tx_pin":   info["tx"],
    }
    if assumed:
        cfg["assumed_fields"] = assumed

    return {
        "intent":       "UART_TRANSMIT",
        "peripheral":   uart,
        "base_address": info["base"],
        "rcc":          build_rcc_block(uart),
        "config":       cfg,
        "action":       {"type": "transmit"},
    }


def build_uart_receive(fields):
    uart = fields.get("uart",
           DEFAULTS["UART"]["instance"])
    baud = fields.get("baudrate",
           DEFAULTS["UART"]["baudrate"])

    assumed = []
    if "uart"     not in fields: assumed.append("uart")
    if "baudrate" not in fields: assumed.append("baudrate")

    if uart not in USART_MAP:
        return build_error_json(
            "INVALID_UART",
            f"{uart} not valid on STM32F103VB",
            "Use USART1, USART2, or USART3")

    baud = snap_baudrate(baud)
    info = USART_MAP[uart]

    cfg = {
        "baudrate": baud,
        "rx_pin":   info["rx"],
    }
    if assumed:
        cfg["assumed_fields"] = assumed

    return {
        "intent":       "UART_RECEIVE",
        "peripheral":   uart,
        "base_address": info["base"],
        "rcc":          build_rcc_block(uart),
        "config":       cfg,
        "action":       {"type": "receive"},
    }


def build_timer_delay(fields):
    timer    = fields.get("timer",
               DEFAULTS["TIMER"]["instance"])
    delay_ms = fields.get("delay_ms",
               DEFAULTS["TIMER"]["delay_ms"])

    assumed = []
    if "timer"    not in fields: assumed.append("timer")
    if "delay_ms" not in fields: assumed.append("delay_ms")

    if timer not in TIMER_MAP:
        return build_error_json(
            "INVALID_TIMER",
            f"{timer} not valid on STM32F103VB",
            "Use TIM2, TIM3, or TIM4")

    info = TIMER_MAP[timer]
    psc  = 7199
    per  = delay_ms * 10

    cfg = {
        "prescaler": psc,
        "period":    per,
        "delay_ms":  delay_ms,
        "unit":      "ms",
    }
    if assumed:
        cfg["assumed_fields"] = assumed

    return {
        "intent":       "TIMER_DELAY",
        "peripheral":   timer,
        "base_address": info["base"],
        "rcc":          build_rcc_block(timer),
        "config":       cfg,
        "action":       {"type": "delay"},
    }


def build_timer_pwm(fields):
    timer   = fields.get("timer",
              DEFAULTS["TIMER"]["instance"])
    channel = fields.get("channel",
              DEFAULTS["TIMER"]["channel"])
    duty    = fields.get("duty",
              DEFAULTS["TIMER"]["duty"])

    assumed = []
    if "timer"   not in fields: assumed.append("timer")
    if "channel" not in fields: assumed.append("channel")
    if "duty"    not in fields: assumed.append("duty")

    if timer not in TIMER_MAP:
        return build_error_json(
            "INVALID_TIMER",
            f"{timer} not valid on STM32F103VB",
            "Use TIM2, TIM3, or TIM4")

    info = TIMER_MAP[timer]

    if channel not in info["channels"]:
        return build_error_json(
            "INVALID_CHANNEL",
            f"{timer} CH{channel} does not exist",
            f"Use channels 1-4 for {timer}")

    pwm_pin = info["channels"][channel]
    period  = 999
    ccr     = int((duty / 100) * period)

    cfg = {
        "channel":            channel,
        "prescaler":          719,
        "period":             period,
        "duty_cycle_percent": duty,
        "ccr_value":          ccr,
        "pwm_pin":            pwm_pin,
    }
    if assumed:
        cfg["assumed_fields"] = assumed

    return {
        "intent":       "TIMER_PWM",
        "peripheral":   timer,
        "base_address": info["base"],
        "rcc":          build_rcc_block(timer),
        "config":       cfg,
        "action":       {"type": "pwm_start"},
    }


def build_rcc_enable(fields):
    # Try to find peripheral from entities
    uart  = fields.get("uart")
    timer = fields.get("timer")
    port  = fields.get("port")

    if uart and uart in USART_MAP:
        peri = uart
    elif timer and timer in TIMER_MAP:
        peri = timer
    elif port:
        peri = f"GPIO{port}"
    else:
        peri = "GPIOA"  # safe default

    return {
        "intent":     "RCC_ENABLE",
        "peripheral": peri,
        "rcc":        build_rcc_block(peri),
        "action":     {"type": "clock_enable"},
    }


# ══════════════════════════════════════════════════════
# ERROR JSON BUILDER
# ══════════════════════════════════════════════════════

def build_error_json(error_type, message,
                     suggestion):
    return {
        "intent": "INVALID",
        "error_details": {
            "error":      error_type,
            "message":    message,
            "suggestion": suggestion,
        }
    }


def build_unknown_json(intent):
    return {
        "intent": "UNKNOWN",
        "error_details": {
            "error":      "UNKNOWN_INTENT",
            "message":    f"Intent '{intent}' "
                          f"not recognized",
            "suggestion": (
                "Valid intents: GPIO_OUTPUT, "
                "GPIO_INPUT, GPIO_TOGGLE, "
                "GPIO_READ, UART_INIT, "
                "UART_TRANSMIT, UART_RECEIVE, "
                "TIMER_DELAY, TIMER_PWM, "
                "RCC_ENABLE"),
        }
    }


# ══════════════════════════════════════════════════════
# INTENT ROUTER
# ══════════════════════════════════════════════════════

INTENT_BUILDERS = {
    "GPIO_OUTPUT":   build_gpio_output,
    "GPIO_INPUT":    build_gpio_input,
    "GPIO_TOGGLE":   build_gpio_toggle,
    "GPIO_READ":     build_gpio_read,
    "UART_INIT":     build_uart_init,
    "UART_TRANSMIT": build_uart_transmit,
    "UART_RECEIVE":  build_uart_receive,
    "TIMER_DELAY":   build_timer_delay,
    "TIMER_PWM":     build_timer_pwm,
    "RCC_ENABLE":    build_rcc_enable,
}


# ══════════════════════════════════════════════════════
# MAIN BUILD FUNCTION
# ══════════════════════════════════════════════════════

def build_json(intent, entities):
    """
    Main entry point.

    Args:
        intent:   string — predicted intent class
                  e.g. "GPIO_OUTPUT"

        entities: dict of {token: BIO_tag}
                  e.g. {
                    "PA":     "B-PORT",
                    "5":      "B-PIN",
                    "50MHz":  "B-SPEED",
                  }

    Returns:
        list of JSON blocks (always a list
        even for single intent)
    """
    # Step 1: Parse BIO entities → clean fields
    fields = parse_entities(entities)

    # Step 2: Route to correct builder
    builder = INTENT_BUILDERS.get(intent)
    if builder is None:
        return [build_unknown_json(intent)]

    # Step 3: Build JSON block
    try:
        block = builder(fields)
    except Exception as e:
        return [build_error_json(
            "BUILD_ERROR",
            f"Failed to build JSON: {str(e)}",
            "Check input entities")]

    # Step 4: Always return as list
    return [block]


# ══════════════════════════════════════════════════════
# MULTI-INTENT BUILDER
# For complex prompts with multiple intents
# ══════════════════════════════════════════════════════

def build_json_multi(intent_list, entities):
    """
    For complex prompts with multiple intents.

    Args:
        intent_list: list of intent strings
                     ["GPIO_TOGGLE", "UART_INIT"]
        entities:    dict of {token: BIO_tag}

    Returns:
        list of JSON blocks, one per intent
    """
    results = []
    fields  = parse_entities(entities)

    for intent in intent_list:
        builder = INTENT_BUILDERS.get(intent)
        if builder is None:
            results.append(
                build_unknown_json(intent))
            continue
        try:
            block = builder(fields)
            results.append(block)
        except Exception as e:
            results.append(build_error_json(
                "BUILD_ERROR",
                f"Failed for {intent}: {str(e)}",
                "Check input entities"))

    return results


# ══════════════════════════════════════════════════════
# TEST
# ══════════════════════════════════════════════════════

if __name__ == "__main__":

    print("="*55)
    print("JSON BUILDER TESTS")
    print("="*55)

    tests = [
        # Test 1: GPIO OUTPUT complete
        {
            "desc":    "GPIO OUTPUT complete",
            "intent":  "GPIO_OUTPUT",
            "entities":{
                "B":               "B-PORT",
                "5":               "B-PIN",
                "output_push_pull":"B-MODE",
                "50MHz":           "B-SPEED",
            }
        },
        # Test 2: GPIO TOGGLE partial (no delay)
        {
            "desc":    "GPIO TOGGLE partial",
            "intent":  "GPIO_TOGGLE",
            "entities":{
                "PA": "B-PORT",
                "2":  "B-PIN",
            }
        },
        # Test 3: UART INIT complete
        {
            "desc":    "UART INIT complete",
            "intent":  "UART_INIT",
            "entities":{
                "USART1": "B-UART",
                "115200": "B-BAUDRATE",
            }
        },
        # Test 4: UART TRANSMIT from dataset sample
        {
            "desc":    "UART TRANSMIT (dataset match)",
            "intent":  "UART_TRANSMIT",
            "entities":{
                "USART1": "B-UART",
                "115200": "B-BAUDRATE",
            }
        },
        # Test 5: TIMER DELAY complete
        {
            "desc":    "TIMER DELAY complete",
            "intent":  "TIMER_DELAY",
            "entities":{
                "TIM3":  "B-TIMER",
                "500ms": "B-DELAY",
            }
        },
        # Test 6: TIMER PWM complete
        {
            "desc":    "TIMER PWM complete",
            "intent":  "TIMER_PWM",
            "entities":{
                "TIM3": "B-TIMER",
                "CH1":  "B-CHANNEL",
                "50%":  "B-DUTY",
            }
        },
        # Test 7: GPIO INPUT partial
        {
            "desc":    "GPIO INPUT partial",
            "intent":  "GPIO_INPUT",
            "entities":{
                "A": "B-PORT",
                "2": "B-PIN",
            }
        },
        # Test 8: Invalid pin
        {
            "desc":    "INVALID pin (PB3 reserved)",
            "intent":  "GPIO_OUTPUT",
            "entities":{
                "B":  "B-PORT",
                "3":  "B-PIN",
            }
        },
        # Test 9: Unknown intent
        {
            "desc":    "Unknown intent",
            "intent":  "UNKNOWN_THING",
            "entities":{}
        },
        # Test 10: Multi-intent
        {
            "desc":       "MULTI-INTENT",
            "intent":     ["GPIO_TOGGLE","UART_INIT"],
            "entities":{
                "PA":     "B-PORT",
                "5":      "B-PIN",
                "500ms":  "B-DELAY",
                "USART1": "B-UART",
                "115200": "B-BAUDRATE",
            }
        },
    ]

    for i, test in enumerate(tests, 1):
        print(f"\n{'─'*55}")
        print(f"Test {i}: {test['desc']}")
        print(f"Input intent  : {test['intent']}")
        print(f"Input entities: {test['entities']}")

        intent   = test["intent"]
        entities = test["entities"]

        if isinstance(intent, list):
            result = build_json_multi(
                intent, entities)
        else:
            result = build_json(intent, entities)

        print(f"Output:")
        print(json.dumps(result, indent=2))

        # Check for assumed fields
        for block in result:
            assumed = block.get(
                "config",{}).get(
                "assumed_fields",[])
            if assumed:
                print(f"⚠ Assumed fields: {assumed}")