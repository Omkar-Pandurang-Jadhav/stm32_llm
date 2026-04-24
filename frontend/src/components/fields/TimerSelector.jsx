/**
 * TimerSelector - TIM selection + delay input
 * STM32F103: TIM1 (advanced), TIM2–TIM4 (general purpose)
 * All are 16-bit countdown timers at up to 72 MHz
 */

const TIMERS = [
  { value: 'TIM1', label: 'TIM1', desc: 'Advanced · 16-bit · APB2 (72 MHz)' },
  { value: 'TIM2', label: 'TIM2', desc: 'General purpose · 16-bit · APB1 (36 MHz)' },
  { value: 'TIM3', label: 'TIM3', desc: 'General purpose · 16-bit · APB1 (36 MHz)' },
  { value: 'TIM4', label: 'TIM4', desc: 'General purpose · 16-bit · APB1 (36 MHz)' },
];

export default function TimerSelector({ timerValue, delayValue, onTimerChange, onDelayChange, timers = [] }) {
  const displayTimers = timers.length > 0 ? timers : TIMERS;

  return (
    <div className="space-y-4 animate-fadeIn">
      <div>
        <label className="label-field">Timer Instance</label>
        <select
          className="select-field"
          value={timerValue}
          onChange={(e) => onTimerChange(e.target.value)}
        >
          <option value="">— Select Timer —</option>
          {displayTimers.map((t) => (
            <option key={t.value || t} value={t.value || t}>
              {t.label || t}
            </option>
          ))}
        </select>
        {timerValue && (
          <p className="mt-1 text-xs" style={{ color: '#406070', fontFamily: 'JetBrains Mono' }}>
            {getTimerDesc(timerValue)}
          </p>
        )}
      </div>

      <div>
        <label className="label-field">Delay (milliseconds)</label>
        <input
          type="number"
          className="input-field"
          placeholder="e.g. 1000"
          min="1"
          max="65535"
          value={delayValue}
          onChange={(e) => onDelayChange(e.target.value)}
        />
        {delayValue && (
          <p className="mt-1 text-xs" style={{ color: '#406070', fontFamily: 'JetBrains Mono' }}>
            {delayValue} ms → {(delayValue / 1000).toFixed(3)} s · ARR value computed by backend
          </p>
        )}
      </div>
    </div>
  );
}

function getTimerDesc(value) {
  const found = TIMERS.find((t) => t.value === value);
  return found ? found.desc : '';
}
