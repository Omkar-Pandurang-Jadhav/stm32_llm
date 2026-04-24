/**
 * LearningPanel - Static STM32 info + dynamic educational content
 * Based on STM32F103VB Datasheet, RM0008 Reference Manual & ARM Cortex-M3 User Guide
 */
import { useState } from 'react';

// ─── Static content ──────────────────────────────────────────────────────────
const STATIC_INFO = [
  {
    icon: '🏛',
    title: 'STM32F103VB',
    body: 'ARM® Cortex®-M3 32-bit MCU at 72 MHz. 128 KB Flash · 20 KB SRAM · 80 GPIO. Medium-density device on AHB/APB bus matrix.',
  },
  {
    icon: '🧠',
    title: 'Cortex-M3 Core',
    body: 'Harvard architecture · Thumb-2 ISA · 3-stage pipeline · Single-cycle multiply · Hardware divide. NVIC with 16 priority levels.',
  },
  {
    icon: '⚡',
    title: 'Bus Architecture',
    body: 'AHB up to 72 MHz → APB2 (72 MHz) → APB1 (36 MHz). GPIO & USART1 on APB2. TIM2-4 & USART2-3 on APB1.',
  },
];

// ─── Dynamic content by field ─────────────────────────────────────────────────
function getDynamicContent(intent, entities) {
  const items = [];

  if (entities.port) {
    const bases = { A: '0x40010800', B: '0x40010C00', C: '0x40011000', D: '0x40011400' };
    items.push({
      title: `GPIO${entities.port} — Port Registers`,
      color: '#00ff9d',
      content: [
        `Base address: ${bases[entities.port]}`,
        `CRL (0x00): Configure pins 0–7 (MODEy + CNFy)`,
        `CRH (0x04): Configure pins 8–15`,
        `IDR (0x08): Input data register (read-only)`,
        `ODR (0x0C): Output data register`,
        `BSRR (0x10): Atomic set/reset (thread-safe)`,
        `Each pin: 4 bits → MODE[1:0] + CNF[1:0]`,
      ],
    });
  }

  if (entities.pin !== undefined && entities.pin !== '') {
    const pin = parseInt(entities.pin);
    const reg = pin >= 8 ? 'CRH' : 'CRL';
    const offset = (pin % 8) * 4;
    items.push({
      title: `Pin ${entities.pin} — Register Mapping`,
      color: '#00ff9d',
      content: [
        `Uses GPIO${entities.port || 'x'}_${reg} register`,
        `Bit offset: [${offset + 3}:${offset}] within ${reg}`,
        `Bits [1:0] = MODE: 00=input, 01=10MHz, 10=2MHz, 11=50MHz`,
        `Bits [3:2] = CNF: varies by input/output mode`,
        pin >= 8
          ? `CRH covers pins 8–15 of the port`
          : `CRL covers pins 0–7 of the port`,
      ],
    });
  }

  if (entities.mode) {
    const modeMap = {
      output_push_pull:  { bits: 'CNF=00', extra: 'Drives line HIGH (VDD) or LOW (GND). Default for LEDs, logic signals.' },
      output_open_drain: { bits: 'CNF=01', extra: 'Can only pull LOW. External pull-up needed for HIGH. Used in I²C, wired-AND.' },
      input_floating:    { bits: 'CNF=01, MODE=00', extra: 'High-impedance. Undefined if pin unconnected. Risk of floating.' },
      input_pull_up:     { bits: 'CNF=10, MODE=00, ODR=1', extra: 'Internal ~40 kΩ to VDD. Pin reads HIGH by default. Buttons, open-drain.' },
      input_pull_down:   { bits: 'CNF=10, MODE=00, ODR=0', extra: 'Internal pull-down to GND. Pin reads LOW by default.' },
    };
    const m = modeMap[entities.mode];
    if (m) {
      items.push({
        title: `Mode: ${entities.mode.replace(/_/g, ' ')}`,
        color: '#00e5ff',
        content: [
          `Register bits: ${m.bits}`,
          m.extra,
        ],
      });
    }
  }

  if (entities.usart) {
    const usartBases = { USART1: '0x40013800', USART2: '0x40004400', USART3: '0x40004800' };
    const bus = entities.usart === 'USART1' ? 'APB2 (72 MHz)' : 'APB1 (36 MHz)';
    items.push({
      title: `${entities.usart} — Universal Sync/Async Receiver-Transmitter`,
      color: '#00e5ff',
      content: [
        `Base: ${usartBases[entities.usart]} · Bus: ${bus}`,
        `SR  (0x00): Status — TXE, TC, RXNE, ORE flags`,
        `DR  (0x04): Data register — read=RX, write=TX`,
        `BRR (0x08): Baud Rate Register`,
        `CR1 (0x0C): Control — UE, TE, RE enable bits`,
        `TX pin must be configured as AF Push-Pull output`,
        `RX pin must be configured as Input Floating`,
      ],
    });
  }

  if (entities.baudrate) {
    const pclk = entities.usart === 'USART1' ? 72000000 : 36000000;
    const baud = parseInt(entities.baudrate);
    const div = pclk / (16 * baud);
    const mantissa = Math.floor(div);
    const fraction = Math.round((div - mantissa) * 16);
    const brr = (mantissa << 4) | fraction;
    items.push({
      title: 'Baudrate — BRR Register',
      color: '#00e5ff',
      content: [
        `USARTDIV = PCLK / (16 × Baudrate)`,
        `         = ${(pclk / 1000000).toFixed(0)}MHz / (16 × ${baud.toLocaleString()})`,
        `         = ${div.toFixed(6)}`,
        `Mantissa = ${mantissa} (0x${mantissa.toString(16).toUpperCase()})`,
        `Fraction = ${fraction} (0x${fraction.toString(16).toUpperCase()})`,
        `BRR      = 0x${brr.toString(16).toUpperCase().padStart(4, '0')} [computed by backend]`,
      ],
    });
  }

  if (entities.timer) {
    const timerBases = { TIM1: '0x40012C00', TIM2: '0x40000000', TIM3: '0x40000400', TIM4: '0x40000800' };
    items.push({
      title: `${entities.timer} — General Purpose Timer`,
      color: '#ffcc00',
      content: [
        `Base: ${timerBases[entities.timer]}`,
        `CR1  (0x00): Control — CEN (counter enable), DIR`,
        `PSC  (0x28): Prescaler — divides input clock`,
        `ARR  (0x2C): Auto-reload — period value`,
        `CNT  (0x24): Current counter value`,
        `SR   (0x10): Status — UIF (update interrupt flag)`,
        `Delay formula: ARR = (PCLK / PSC) × delay_ms / 1000`,
      ],
    });
  }

  if (intent === 'RCC_ENABLE' && entities.peripheral) {
    const apb2list = ['GPIOA', 'GPIOB', 'GPIOC', 'GPIOD', 'USART1', 'TIM1', 'SPI1', 'ADC1', 'ADC2'];
    const isAPB2 = apb2list.includes(entities.peripheral);
    items.push({
      title: `RCC — Reset & Clock Control`,
      color: '#ff6b35',
      content: [
        `${entities.peripheral} clock: ${isAPB2 ? 'APB2' : 'APB1'}ENR register`,
        `RCC base: 0x40021000`,
        `APB2ENR (0x18): GPIO A-E, USART1, TIM1, SPI1, ADC1/2`,
        `APB1ENR (0x1C): TIM2-7, USART2-3, SPI2, I2C1-2`,
        `Must enable clock BEFORE accessing peripheral registers!`,
        `Failure to enable RCC → HardFault on peripheral access`,
      ],
    });
  }

  return items;
}

function InfoCard({ icon, title, body }) {
  return (
    <div className="p-3 rounded" style={{ background: '#0a152088', border: '1px solid #00ff9d11' }}>
      <div className="flex items-start gap-2">
        <span style={{ fontSize: '1rem' }}>{icon}</span>
        <div>
          <p className="section-header" style={{ color: '#00ff9d88', fontSize: '0.6rem', marginBottom: '0.25rem' }}>
            {title}
          </p>
          <p style={{ color: '#7090a0', fontFamily: 'JetBrains Mono', fontSize: '0.7rem', lineHeight: 1.6 }}>
            {body}
          </p>
        </div>
      </div>
    </div>
  );
}

function DynamicCard({ title, color, content }) {
  return (
    <div
      className="p-3 rounded animate-fadeIn"
      style={{ background: `${color}08`, border: `1px solid ${color}22` }}
    >
      <p
        className="section-header mb-2"
        style={{ color, fontSize: '0.6rem' }}
      >
        ◈ {title}
      </p>
      <ul className="space-y-1">
        {content.map((line, i) => (
          <li
            key={i}
            style={{ color: '#7090a0', fontFamily: 'JetBrains Mono', fontSize: '0.68rem', lineHeight: 1.5 }}
          >
            <span style={{ color: `${color}66` }}>›</span> {line}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function LearningPanel({ intent, entities }) {
  const [collapsed, setCollapsed] = useState(false);
  const dynamicItems = getDynamicContent(intent, entities);

  return (
    <div className="card-glow rounded-lg overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 cursor-pointer"
        style={{ borderBottom: '1px solid #00ff9d18' }}
        onClick={() => setCollapsed(!collapsed)}
      >
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full" style={{ background: '#00e5ff', boxShadow: '0 0 6px #00e5ff' }} />
          <span className="section-header" style={{ color: '#00e5ff', fontSize: '0.65rem' }}>
            LEARNING PANEL
          </span>
        </div>
        <span style={{ color: '#00e5ff66', fontSize: '0.7rem', fontFamily: 'JetBrains Mono' }}>
          {collapsed ? '[+]' : '[−]'}
        </span>
      </div>

      {!collapsed && (
        <div className="p-4 space-y-4">
          {/* Static section */}
          <div>
            <p className="text-xs mb-2" style={{ color: '#2a4050', fontFamily: 'Orbitron', letterSpacing: '0.1em', fontSize: '0.55rem' }}>
              ── MICROCONTROLLER OVERVIEW ──
            </p>
            <div className="space-y-2">
              {STATIC_INFO.map((info, i) => (
                <InfoCard key={i} {...info} />
              ))}
            </div>
          </div>

          {/* Dynamic section */}
          {dynamicItems.length > 0 && (
            <div>
              <p className="text-xs mb-2" style={{ color: '#2a4050', fontFamily: 'Orbitron', letterSpacing: '0.1em', fontSize: '0.55rem' }}>
                ── CONTEXTUAL REFERENCE ──
              </p>
              <div className="space-y-2">
                {dynamicItems.map((item, i) => (
                  <DynamicCard key={i} {...item} />
                ))}
              </div>
            </div>
          )}

          {dynamicItems.length === 0 && (
            <div className="text-center py-4">
              <p style={{ color: '#2a4050', fontFamily: 'JetBrains Mono', fontSize: '0.7rem' }}>
                Configure fields to see register details
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
