// Test-only deterministic frame delivery. The real mounted controls and shared
// Playback Controller run unchanged; no engineering values or source clocks are mocked.
// All overrides live inside one synchronous browser evaluation and restore in finally.
async function drivePlaybackClock(mount, segments) {
  return mount.evaluate((container, segments) => {
    const nativeRaf = window.requestAnimationFrame;
    const nativeCancel = window.cancelAnimationFrame;
    const descriptor = Object.getOwnPropertyDescriptor(performance, "now");
    let now = performance.now(), next = 0;
    const pending = new Map();
    const snapshot = () => ({ time: wwPlayback.currentTime, state: wwPlayback.state,
      speed: wwPlayback.speed, generation: wwPlayback.generation, raf: wwPlayback.rafId });
    const loops = () => [...pending.values()].filter(callback => callback === wwPlaybackTick).length;
    const results = [];
    try {
      Object.defineProperty(performance, "now", { configurable: true, value: () => now });
      window.requestAnimationFrame = callback => { const id = ++next; pending.set(id, callback); return id; };
      window.cancelAnimationFrame = id => pending.delete(id);
      container.querySelector(".ww-tg-playback-play-btn").click();
      const select = container.querySelector(".ww-tg-playback-speed-select");
      for (const segment of segments) {
        const beforeSwitch = snapshot();
        select.value = String(segment.speed);
        select.dispatchEvent(new Event("change", { bubbles: true }));
        const afterSwitch = snapshot(), wallStart = now;
        const frameLoops = [];
        for (const elapsed of segment.steps) {
          now += elapsed;
          const callbacks = [...pending.values()]; pending.clear();
          for (const callback of callbacks) callback(now);
          frameLoops.push(loops());
        }
        results.push({ beforeSwitch, afterSwitch, after: snapshot(),
          wallSeconds: (now - wallStart) / 1000, frameLoops,
          selected: select.value, button: container.querySelector(".ww-tg-playback-play-btn").textContent });
      }
      return results;
    } finally {
      wwPlaybackPause();
      window.requestAnimationFrame = nativeRaf;
      window.cancelAnimationFrame = nativeCancel;
      if (descriptor) Object.defineProperty(performance, "now", descriptor);
      else delete performance.now;
    }
  }, segments);
}
module.exports = { drivePlaybackClock };
