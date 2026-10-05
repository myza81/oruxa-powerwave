// Synthetic COMTRADE (1999, ASCII) records for browser tests that need a
// chosen sampling rate, duration and start instant -- e.g. the Event
// Reconstruction mixed-rate scenario (5 kHz / 200 ms, 20 Hz / 60 s,
// 1 Hz / 300 s). Test data only: a sine per analog channel, no digital
// channels. Each call returns the CFG/DAT pair as Buffers for
// `setInputFiles`.
//
//   syntheticComtrade({
//     station: "STN_FAST", date: "06/03/2026", startClock: "10:00:00.000000",
//     rateHz: 5000, durationS: 0.2,
//     channels: [{ name: "VA", unit: "V", phase: "A", amplitude: 100, frequencyHz: 50 }],
//   })

function clockToSeconds(clock) {
  const [h, m, s] = clock.split(":");
  return Number(h) * 3600 + Number(m) * 60 + Number(s);
}

function secondsToClock(t) {
  const hh = String(Math.floor(t / 3600)).padStart(2, "0");
  const mm = String(Math.floor((t % 3600) / 60)).padStart(2, "0");
  const ss = (t % 60).toFixed(6).padStart(9, "0");
  return `${hh}:${mm}:${ss}`;
}

function syntheticComtrade({ station, date = "06/03/2026", startClock, rateHz, durationS, channels }) {
  const sampleCount = Math.round(rateHz * durationS) + 1;
  const scale = channels.map((c) => (c.amplitude || 1) / 30000);
  const cfgLines = [
    `${station},SYNTH_DEV,1999`,
    `${channels.length},${channels.length}A,0D`,
    ...channels.map((c, i) =>
      `${i + 1},${c.name},${c.phase || ""},,${c.unit},${scale[i]},0.0,0,-32767,32767,1.0,1.0,P`),
    "50",
    "1",
    `${rateHz},${sampleCount}`,
    `${date},${startClock}`,
    `${date},${startClock}`,
    "ASCII",
    "1.0",
  ];
  const datLines = [];
  for (let n = 0; n < sampleCount; n++) {
    const t = n / rateHz;
    const raw = channels.map((c) =>
      Math.round(Math.sin(2 * Math.PI * (c.frequencyHz || 50) * t + (c.phaseShiftRad || 0)) * 30000));
    datLines.push([n + 1, Math.round(t * 1e6), ...raw].join(","));
  }
  return {
    cfg: Buffer.from(cfgLines.join("\r\n") + "\r\n", "latin1"),
    dat: Buffer.from(datLines.join("\r\n") + "\r\n", "latin1"),
  };
}

module.exports = { syntheticComtrade, clockToSeconds, secondsToClock };
