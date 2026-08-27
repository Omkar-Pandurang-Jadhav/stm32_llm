from fastapi import FastAPI
from pydantic import BaseModel
import sys
from pathlib import Path

# 🔥 Add root project to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

# 🔥 Import your actual system
from json_builder.json_builder import build_json

from json_builder.json_builder import PORT_VALID_PINS  # 👈 adjust if needed

from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],   # for dev
    allow_credentials=True,
    allow_methods=["*"],   # THIS FIXES OPTIONS
    allow_headers=["*"],
)





# ===============================
# REQUEST MODEL
# ===============================
class RequestModel(BaseModel):
    intent: str
    entities: dict

# ===============================
# HEALTH CHECK
# ===============================
@app.get("/health")
def health():
    return {"status": "ok"}

# ===============================
# HARDWARE (FROM YOUR SYSTEM)
# ===============================
@app.get("/hardware")
def hardware():
    """
    🔥 IMPORTANT:
    If you already have hardware rules in your project,
    import them here instead of hardcoding.
    """

    from json_builder.json_builder.constants import PORT_VALID_PINS  # 👈 adjust if needed

    return {
        "ports": list(PORT_VALID_PINS.keys()),
        "pins": PORT_VALID_PINS,
    }

# ===============================
# MAIN API
# ===============================
from inference import predict_prompt

@app.post("/generate-json")
def generate(data: RequestModel):

    try:

        intent = data.intent
        entities = data.entities

        prompt = ""

        # =========================================
        # GPIO OUTPUT
        # =========================================
        if intent == "GPIO_OUTPUT":

            prompt = (
                f"configure P{entities['port']}{entities['pin']} "
                f"as output {entities['mode']} {entities['speed']}"
            )

        # =========================================
        # GPIO INPUT
        # =========================================
        elif intent == "GPIO_INPUT":

            prompt = (
                f"set P{entities['port']}{entities['pin']} "
                f"as input {entities['mode']}"
            )

        # =========================================
        # GPIO TOGGLE
        # =========================================
        elif intent == "GPIO_TOGGLE":

            prompt = (
                f"toggle P{entities['port']}{entities['pin']}"
            )

        # =========================================
        # GPIO READ
        # =========================================
        elif intent == "GPIO_READ":

            prompt = (
                f"read P{entities['port']}{entities['pin']}"
            )

        # =========================================
        # UART INIT
        # =========================================
        elif intent == "UART_INIT":

            prompt = (
                f"initialize {entities['usart']} "
                f"at {entities['baudrate']} baud"
            )

        # =========================================
        # UART RECEIVE
        # =========================================
        elif intent == "UART_RECEIVE":

            prompt = (
                f"receive using {entities['usart']}"
            )

        # =========================================
        # TIMER DELAY
        # =========================================
        elif intent == "TIMER_DELAY":

            prompt = (
                f"generate {entities['delay']}ms delay "
                f"using {entities['timer']}"
            )

        # =========================================
        # RCC ENABLE
        # =========================================
        elif intent == "RCC_ENABLE":

            prompt = (
                f"enable {entities['peripheral']} clock"
            )

        else:
            return {
                "error": f"Unsupported intent: {intent}"
            }

        # =========================================
        # RUN FULL PIPELINE
        # =========================================

        result = predict_prompt(prompt)

        return result

    except Exception as e:

        return {
            "error": str(e)
        }