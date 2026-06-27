// Globaler reaktiver Store für KI-Modell-Downloads.
// Überlebt Modal-Schließen — Dashboard und Settings lesen denselben State.

let _state = {
  pulling: false,
  model: null,
  status: null,
  percent: null,
  done: false,
  error: null,
};

const _listeners = new Set();
const notify = () => _listeners.forEach(fn => fn({ ..._state }));

export const aiDownloadStore = {
  getState: () => ({ ..._state }),
  set: (patch) => { _state = { ..._state, ...patch }; notify(); },
  subscribe: (fn) => { _listeners.add(fn); return () => _listeners.delete(fn); },
};
