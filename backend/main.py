from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
import json

app = FastAPI(title="STM32 Config API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ══════════════════════════════════════════════════════
# HARDWARE TABLES
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
    "USART1":{"base":"0x40013800","tx":{"port":"A","pin":9},"rx":{"port":"A","pin":10}},
    "USART2":{"base":"0x40004000","tx":{"port":"A","pin":2},"rx":{"port":"A","pin":3}},
    "USART3":{"base":"0x40004400","tx":{"port":"B","pin":10},"rx":{"port":"B","pin":11}},
}

TIMER_MAP = {
    "TIM2":{"base":"0x40000000","channels":{1:{"port":"A","pin":0},2:{"port":"A","pin":1},3:{"port":"A","pin":2},4:{"port":"A","pin":3}}},
    "TIM3":{"base":"0x40000400","channels":{1:{"port":"A","pin":6},2:{"port":"A","pin":7},3:{"port":"B","pin":0},4:{"port":"B","pin":1}}},
    "TIM4":{"base":"0x40000800","channels":{1:{"port":"B","pin":6},2:{"port":"B","pin":7},3:{"port":"B","pin":8},4:{"port":"B","pin":9}}},
}

PORT_VALID_PINS = {
    "A": list(range(0, 13)),  # PA0-PA12 (PA13,14,15 reserved)
    "B": [0,1,2,5,6,7,8,9,10,11,12,13,14,15],  # PB3,PB4 reserved
    "C": [13, 14, 15],
    "D": [0, 1],
}

VALID_BAUDRATES = [9600, 19200, 38400, 57600, 115200]

# ══════════════════════════════════════════════════════
# MODELS
# ══════════════════════════════════════════════════════

class GenerateRequest(BaseModel):
    intent: str
    entities: Dict[str, Any]

# ══════════════════════════════════════════════════════
# RCC BUILDER
# ══════════════════════════════════════════════════════

def build_rcc(peripheral_name: str) -> dict:
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
# INTENT BUILDERS
# ══════════════════════════════════════════════════════

def build_gpio_output(e: dict) -> dict:
    port  = e.get("port", "A")
    pin   = int(e.get("pin", 0))
    mode  = e.get("mode", "output_push_pull")
    speed = e.get("speed", "50MHz")
    return {
        "intent":     "GPIO_OUTPUT",
        "peripheral": "GPIO",
        "rcc":        build_rcc(f"GPIO{port}"),
        "config":     {"port": port, "pin": pin, "mode": mode, "speed": speed},
        "action":     {"type": "set_high"},
    }

def build_gpio_input(e: dict) -> dict:
    port = e.get("port", "A")
    pin  = int(e.get("pin", 0))
    mode = e.get("mode", "input_floating")
    return {
        "intent":     "GPIO_INPUT",
        "peripheral": "GPIO",
        "rcc":        build_rcc(f"GPIO{port}"),
        "config":     {"port": port, "pin": pin, "mode": mode},
        "action":     {"type": "read"},
    }

def build_gpio_toggle(e: dict) -> dict:
    port     = e.get("port", "A")
    pin      = int(e.get("pin", 0))
    delay_ms = int(e.get("delay_ms", 500))
    return {
        "intent":     "GPIO_TOGGLE",
        "peripheral": "GPIO",
        "rcc":        build_rcc(f"GPIO{port}"),
        "config":     {"port": port, "pin": pin, "mode": "output_push_pull", "speed": "50MHz"},
        "action":     {"type": "toggle"},
        "timing":     {"delay_ms": delay_ms},
    }

def build_gpio_read(e: dict) -> dict:
    port = e.get("port", "A")
    pin  = int(e.get("pin", 0))
    return {
        "intent":     "GPIO_READ",
        "peripheral": "GPIO",
        "rcc":        build_rcc(f"GPIO{port}"),
        "config":     {"port": port, "pin": pin},
        "action":     {"type": "read_idr"},
    }

def build_uart_init(e: dict) -> dict:
    uart = e.get("uart", "USART1")
    baud = int(e.get("baudrate", 115200))
    bits = int(e.get("word_length", 8))
    stop = int(e.get("stop_bits", 1))
    if uart not in USART_MAP:
        raise ValueError(f"Invalid UART: {uart}")
    info = USART_MAP[uart]
    return {
        "intent":       "UART_INIT",
        "peripheral":   uart,
        "base_address": info["base"],
        "rcc":          build_rcc(uart),
        "config": {
            "baudrate":    baud,
            "brr_value":   SYSTEM_CLOCK // baud,
            "word_length": bits,
            "parity":      "none",
            "stop_bits":   stop,
            "tx_pin":      info["tx"],
            "rx_pin":      info["rx"],
        },
        "action": {"type": "init"},
    }

def build_uart_receive(e: dict) -> dict:
    uart = e.get("uart", "USART1")
    baud = int(e.get("baudrate", 115200))
    if uart not in USART_MAP:
        raise ValueError(f"Invalid UART: {uart}")
    info = USART_MAP[uart]
    return {
        "intent":       "UART_RECEIVE",
        "peripheral":   uart,
        "base_address": info["base"],
        "rcc":          build_rcc(uart),
        "config":       {"baudrate": baud, "rx_pin": info["rx"]},
        "action":       {"type": "receive"},
    }

def build_timer_delay(e: dict) -> dict:
    timer    = e.get("timer", "TIM2")
    delay_ms = int(e.get("delay_ms", 500))
    if timer not in TIMER_MAP:
        raise ValueError(f"Invalid timer: {timer}")
    info = TIMER_MAP[timer]
    return {
        "intent":       "TIMER_DELAY",
        "peripheral":   timer,
        "base_address": info["base"],
        "rcc":          build_rcc(timer),
        "config": {
            "prescaler": 7199,
            "period":    delay_ms * 10,
            "delay_ms":  delay_ms,
            "unit":      "ms",
        },
        "action": {"type": "delay"},
    }

INTENT_BUILDERS = {
    "GPIO_OUTPUT":  build_gpio_output,
    "GPIO_INPUT":   build_gpio_input,
    "GPIO_TOGGLE":  build_gpio_toggle,
    "GPIO_READ":    build_gpio_read,
    "UART_INIT":    build_uart_init,
    "UART_RECEIVE": build_uart_receive,
    "TIMER_DELAY":  build_timer_delay,
}

# ══════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════

@app.get("/")
def root():
    return {"status": "STM32 Config API running", "version": "1.0.0"}

@app.get("/hardware-constraints")
def get_hardware_constraints():
    return {
        "ports": PORT_VALID_PINS,
        "baudrates": VALID_BAUDRATES,
        "timers": list(TIMER_MAP.keys()),
        "uart_instances": list(USART_MAP.keys()),
        "gpio_modes_output": ["output_push_pull", "output_open_drain"],
        "gpio_modes_input": ["input_floating", "input_pull_up", "input_pull_down"],
        "gpio_speeds": ["2MHz", "10MHz", "50MHz"],
        "intents": list(INTENT_BUILDERS.keys()),
    }

@app.post("/generate-json")
def generate_json(req: GenerateRequest):
    builder = INTENT_BUILDERS.get(req.intent)
    if not builder:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown intent: {req.intent}. Valid: {list(INTENT_BUILDERS.keys())}"
        )
    try:
        result = builder(req.entities)
        return {"success": True, "intent": req.intent, "output": [result]}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Build error: {str(e)}")

@app.get("/valid-pins/{port}")
def get_valid_pins(port: str):
    port = port.upper()
    if port not in PORT_VALID_PINS:
        raise HTTPException(status_code=404, detail=f"Port {port} not found")
    return {"port": port, "pins": PORT_VALID_PINS[port]}
