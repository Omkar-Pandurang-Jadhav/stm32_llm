/**
 * STM32 Configurator API Service
 * Communicates with the backend REST API
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000';

/**
 * Fetch hardware constraints from backend
 * GET /hardware
 * Returns: { ports, pins, baudrates, timers, intents, modes, speeds, peripherals }
 */
export async function fetchHardware() {
  const response = await fetch(`${BASE_URL}/hardware`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Network error' }));
    throw new Error(error.message || `HTTP ${response.status}`);
  }

  return response.json();
}

/**
 * Generate configuration JSON from backend
 * POST /generate-json
 * Body: { intent: string, entities: object }
 * Returns: { config: object, registers: object, code: string }
 */
export async function generateJson(intent, entities) {
  const response = await fetch(`${BASE_URL}/generate-json`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ intent, entities }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Backend error' }));
    throw new Error(error.message || `HTTP ${response.status}`);
  }

  return response.json();
}

/**
 * Check backend health / connectivity
 * GET /health
 */
export async function checkHealth() {
  try {
    const response = await fetch(`${BASE_URL}/health`, {
      method: 'GET',
      signal: AbortSignal.timeout(3000),
    });
    return response.ok;
  } catch {
    return false;
  }
}
