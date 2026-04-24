/**
 * DynamicForm - Renders fields based on selected intent
 * All hardware constraints are fetched from backend via props
 */
import PortSelector from './fields/PortSelector.jsx';
import PinSelector from './fields/PinSelector.jsx';
import ModeSelector from './fields/ModeSelector.jsx';
import SpeedSelector from './fields/SpeedSelector.jsx';
import BaudrateSelector from './fields/BaudrateSelector.jsx';
import TimerSelector from './fields/TimerSelector.jsx';

const RCC_PERIPHERALS = [
  'GPIOA', 'GPIOB', 'GPIOC', 'GPIOD',
  'USART1', 'USART2', 'USART3',
  'TIM1', 'TIM2', 'TIM3', 'TIM4',
  'SPI1', 'SPI2', 'I2C1', 'I2C2',
  'ADC1', 'ADC2', 'DMA1',
];

const USART_INSTANCES = ['USART1', 'USART2', 'USART3'];

export default function DynamicForm({ intent, entities, onChange, hardware }) {
  const { ports = [], pins = {}, baudrates = [], timers = [], speeds = [] } = hardware || {};

  const set = (key, val) => onChange({ ...entities, [key]: val });

  if (!intent) {
    return (
      <div className="flex flex-col items-center justify-center py-10 gap-3">
        <div style={{ color: '#00ff9d22', fontSize: '3rem' }}>⚙</div>
        <p className="text-center" style={{ color: '#406070', fontFamily: 'JetBrains Mono', fontSize: '0.8rem' }}>
          Select an intent to configure
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fadeIn">
      {/* ── GPIO_OUTPUT ─────────────────────────────────────── */}
      {intent === 'GPIO_OUTPUT' && (
        <>
          <PortSelector value={entities.port || ''} onChange={(v) => set('port', v)} ports={ports} />
          <PinSelector value={entities.pin ?? ''} onChange={(v) => set('pin', v)} port={entities.port} pins={pins} />
          <ModeSelector value={entities.mode || ''} onChange={(v) => set('mode', v)} type="output" />
          <SpeedSelector value={entities.speed || ''} onChange={(v) => set('speed', v)} speeds={speeds} />
        </>
      )}

      {/* ── GPIO_INPUT ──────────────────────────────────────── */}
      {intent === 'GPIO_INPUT' && (
        <>
          <PortSelector value={entities.port || ''} onChange={(v) => set('port', v)} ports={ports} />
          <PinSelector value={entities.pin ?? ''} onChange={(v) => set('pin', v)} port={entities.port} pins={pins} />
          <ModeSelector value={entities.mode || ''} onChange={(v) => set('mode', v)} type="input" />
        </>
      )}

      {/* ── GPIO_TOGGLE / GPIO_READ ──────────────────────────── */}
      {(intent === 'GPIO_TOGGLE' || intent === 'GPIO_READ') && (
        <>
          <PortSelector value={entities.port || ''} onChange={(v) => set('port', v)} ports={ports} />
          <PinSelector value={entities.pin ?? ''} onChange={(v) => set('pin', v)} port={entities.port} pins={pins} />
        </>
      )}

      {/* ── UART_INIT ────────────────────────────────────────── */}
      {intent === 'UART_INIT' && (
        <>
          <div className="animate-fadeIn">
            <label className="label-field">USART Instance</label>
            <select
              className="select-field"
              value={entities.usart || ''}
              onChange={(e) => set('usart', e.target.value)}
            >
              <option value="">— Select USART —</option>
              {USART_INSTANCES.map((u) => (
                <option key={u} value={u}>{u}</option>
              ))}
            </select>
          </div>
          <BaudrateSelector
            value={entities.baudrate || ''}
            onChange={(v) => set('baudrate', v)}
            baudrates={baudrates}
          />
        </>
      )}

      {/* ── UART_RECEIVE ─────────────────────────────────────── */}
      {intent === 'UART_RECEIVE' && (
        <div className="animate-fadeIn">
          <label className="label-field">USART Instance</label>
          <select
            className="select-field"
            value={entities.usart || ''}
            onChange={(e) => set('usart', e.target.value)}
          >
            <option value="">— Select USART —</option>
            {USART_INSTANCES.map((u) => (
              <option key={u} value={u}>{u}</option>
            ))}
          </select>
          {entities.usart && (
            <p className="mt-1 text-xs" style={{ color: '#406070', fontFamily: 'JetBrains Mono' }}>
              Reads {entities.usart}_DR until RXNE flag is set
            </p>
          )}
        </div>
      )}

      {/* ── TIMER_DELAY ──────────────────────────────────────── */}
      {intent === 'TIMER_DELAY' && (
        <TimerSelector
          timerValue={entities.timer || ''}
          delayValue={entities.delay || ''}
          onTimerChange={(v) => set('timer', v)}
          onDelayChange={(v) => set('delay', v)}
          timers={timers}
        />
      )}

      {/* ── RCC_ENABLE ───────────────────────────────────────── */}
      {intent === 'RCC_ENABLE' && (
        <div className="animate-fadeIn">
          <label className="label-field">Peripheral Clock</label>
          <select
            className="select-field"
            value={entities.peripheral || ''}
            onChange={(e) => set('peripheral', e.target.value)}
          >
            <option value="">— Select Peripheral —</option>
            <optgroup label="── GPIO ──">
              {['GPIOA', 'GPIOB', 'GPIOC', 'GPIOD'].map((p) => (
                <option key={p} value={p}>{p} — APB2ENR</option>
              ))}
            </optgroup>
            <optgroup label="── USART ──">
              {['USART1', 'USART2', 'USART3'].map((p) => (
                <option key={p} value={p}>{p} — {p === 'USART1' ? 'APB2' : 'APB1'}ENR</option>
              ))}
            </optgroup>
            <optgroup label="── TIMER ──">
              {['TIM1', 'TIM2', 'TIM3', 'TIM4'].map((p) => (
                <option key={p} value={p}>{p} — {p === 'TIM1' ? 'APB2' : 'APB1'}ENR</option>
              ))}
            </optgroup>
            <optgroup label="── Other ──">
              {['SPI1', 'SPI2', 'I2C1', 'I2C2', 'ADC1', 'ADC2', 'DMA1'].map((p) => (
                <option key={p} value={p}>{p}</option>
              ))}
            </optgroup>
          </select>
          {entities.peripheral && (
            <p className="mt-1 text-xs" style={{ color: '#406070', fontFamily: 'JetBrains Mono' }}>
              RCC-&gt;{getRCCRegister(entities.peripheral)} |= RCC_{entities.peripheral}EN;
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function getRCCRegister(peripheral) {
  const apb2 = ['GPIOA', 'GPIOB', 'GPIOC', 'GPIOD', 'USART1', 'TIM1', 'SPI1', 'ADC1', 'ADC2'];
  return apb2.includes(peripheral) ? 'APB2ENR' : 'APB1ENR';
}
