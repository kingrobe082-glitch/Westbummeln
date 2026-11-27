'use strict';
// Funkmeldeempfänger (FME) im Alarm-Panel: Anzeige und Alarmton.
// Ablauf wie am echten Melder: Bereit → Alarm (Glocke, Ton) → Blinken und Vibration →
// Einsatztext → Quittiert. Welcher Einsatz alarmiert wird, entscheidet game.js (updateFme).
// Ton: static/sounds/Westbummeln_FME_ZVEI.wav (eigene ZVEI-Fünftonfolge mit Weckton), über den
// AudioContext aus app.js, damit „Ton an/aus“ und der Lautstärkeregler auch hier gelten.
const WBFme = (() => {
  const $ = id => document.getElementById(id);
  const SOUND = document.querySelector('meta[name="fme-sound"]')?.content || '/static/sounds/Westbummeln_FME_ZVEI.wav';
  // So lange zeigt der Melder nur „Alarm“, bevor der Einsatztext erscheint (ms).
  const ALARM_PHASE = 2200;
  // Der Ton läuft höchstens so oft hintereinander, wenn niemand quittiert.
  const MAX_PLAYS = 3;

  let buffer = null, loading = null, source = null, gain = null, textTimer = 0;

  function load() {
    if (buffer || loading || typeof audioCtx === 'undefined' || !audioCtx) return loading;
    loading = fetch(SOUND)
      .then(response => response.ok ? response.arrayBuffer() : Promise.reject(response.status))
      .then(data => audioCtx.decodeAudioData(data))
      .then(decoded => { buffer = decoded; return decoded; })
      .catch(() => { loading = null; return null; });
    return loading;
  }

  function stopSound() {
    if (source) {
      try { source.stop(); } catch (e) { /* schon beendet */ }
      source = null;
    }
  }

  // Spielt den Alarmton (bis zu MAX_PLAYS-mal). Ohne Ton oder ohne Datei: kurze Ersatz-Piepser.
  async function playSound() {
    stopSound();
    if (typeof soundOn === 'undefined' || !soundOn || !audioCtx) return;
    const decoded = buffer || await load();
    if (!decoded) {
      beep(1060, .16, 0, 'sine', .18);
      beep(1400, .16, .20, 'sine', .18);
      beep(1060, .16, .40, 'sine', .18);
      beep(1400, .30, .60, 'sine', .18);
      return;
    }
    const vol = Number($('volume')?.value ?? 70) / 100;
    gain = audioCtx.createGain();
    gain.gain.value = 0.9 * vol;
    gain.connect(audioCtx.destination);
    source = audioCtx.createBufferSource();
    source.buffer = decoded;
    source.loop = true;
    source.connect(gain);
    const playing = source;
    source.start();
    source.stop(audioCtx.currentTime + decoded.duration * MAX_PLAYS);
    playing.onended = () => { if (source === playing) source = null; };
  }

  function setState(state) {
    const device = $('fmeDevice');
    if (device) device.dataset.state = state;
  }

  function clock() {
    const now = new Date();
    return now.toLocaleTimeString('de-DE', {hour: '2-digit', minute: '2-digit'});
  }

  function render(lines) {
    $('fmeClock').textContent = clock();
    $('fmeMessage').replaceChildren(...lines.map((text, i) => {
      const line = document.createElement('span');
      line.className = i === 0 ? 'fme-line fme-head' : 'fme-line';
      line.textContent = text;
      return line;
    }));
  }

  // Neuer Alarm: lines = Zeilen des Einsatztextes, z. B. ['Einsatzalarm', 'WB 2-LF', 'B3 – …', 'Hauptstr. 12'].
  function alarm(lines) {
    clearTimeout(textTimer);
    setState('alarm');
    render(['Alarm']);
    playSound();
    textTimer = setTimeout(() => {
      setState('text');
      render(lines);
    }, ALARM_PHASE);
    return lines;
  }

  function acknowledge(lines) {
    clearTimeout(textTimer);
    stopSound();
    setState('quittiert');
    render(['✓ Quittiert', ...lines.slice(1)]);
  }

  function clear() {
    clearTimeout(textTimer);
    stopSound();
    setState('bereit');
    render(['Bereit']);
  }

  // Ton schon beim ersten Einschalten laden, damit der erste Alarm ohne Verzögerung klingt.
  document.addEventListener('click', () => load(), {once: true, capture: true});

  return {alarm, acknowledge, clear, stopSound};
})();
