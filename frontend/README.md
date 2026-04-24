# STM32F103VB Peripheral Configurator — Frontend

A modern, modular React frontend for configuring STM32F103VB microcontroller peripherals visually.

## Stack
- **React 18** (Vite)
- **Tailwind CSS**
- **JetBrains Mono** · **Orbitron** · **Share Tech** fonts
- Dark theme · Neon green/cyan embedded-system aesthetic

## Project Structure

```
src/
├── App.jsx                        # Main shell: layout, state, API calls
├── main.jsx                       # React root
├── index.css                      # Global styles, design tokens
├── services/
│   └── api.js                     # GET /hardware · POST /generate-json · checkHealth()
└── components/
    ├── IntentSelector.jsx          # Intent dropdown (grouped by peripheral)
    ├── DynamicForm.jsx             # Intent-driven field renderer
    ├── JsonOutput.jsx              # Syntax-highlighted JSON output + copy
    ├── LearningPanel.jsx           # Static MCU info + dynamic register reference
    └── fields/
        ├── PortSelector.jsx        # GPIO port A/B/C/D with base address hint
        ├── PinSelector.jsx         # Pin 0–15 (port-aware) with CRL/CRH indicator
        ├── ModeSelector.jsx        # CNF bits for output/input modes
        ├── SpeedSelector.jsx       # MODE bits: 2/10/50 MHz
        ├── BaudrateSelector.jsx    # USART baudrates with BRR formula preview
        └── TimerSelector.jsx       # TIMx instance + delay ms input
```

## Supported Intents

| Intent | Fields |
|---|---|
| `GPIO_OUTPUT` | Port · Pin · Mode (output) · Speed |
| `GPIO_INPUT` | Port · Pin · Mode (input) |
| `GPIO_TOGGLE` | Port · Pin |
| `GPIO_READ` | Port · Pin |
| `UART_INIT` | USART · Baudrate |
| `UART_RECEIVE` | USART |
| `TIMER_DELAY` | Timer · Delay (ms) |
| `RCC_ENABLE` | Peripheral |

## Backend API Contract

### `GET /health`
Returns `200 OK` if backend is running.

### `GET /hardware`
Returns hardware constraints:
```json
{
  "ports": ["A", "B", "C", "D"],
  "pins": { "A": [0,1,...,15], "B": [...], "C": [13,14,15], "D": [0,1] },
  "baudrates": [9600, 19200, 38400, 57600, 115200],
  "timers": ["TIM1", "TIM2", "TIM3", "TIM4"],
  "speeds": ["2MHz", "10MHz", "50MHz"],
  "intents": [...]
}
```

### `POST /generate-json`
Request:
```json
{ "intent": "GPIO_OUTPUT", "entities": { "port": "A", "pin": 5, "mode": "output_push_pull", "speed": "50MHz" } }
```

Response: Any JSON object (displayed in the output panel).

## Setup

```bash
# Install dependencies
npm install

# Configure backend URL
cp .env.example .env
# Edit VITE_API_BASE_URL in .env

# Start dev server
npm run dev

# Build for production
npm run build
```

## Hardware Reference (STM32F103VB)
- **Datasheet**: STM32F103xB · Medium-density · LQFP100
- **Reference Manual**: RM0008 Rev 21
- **Core**: ARM Cortex-M3 · 72 MHz · Thumb-2 ISA
- **GPIO**: PA0–PA15, PB0–PB15, PC13–PC15, PD0–PD1
- **USART**: USART1 (APB2/72MHz), USART2/3 (APB1/36MHz)
- **Timers**: TIM1 (advanced/APB2), TIM2–TIM4 (general/APB1)
- **RCC**: APB2ENR (GPIO/USART1/TIM1), APB1ENR (TIM2-4/USART2-3)
