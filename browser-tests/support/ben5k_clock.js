function clockFixture() {
  const n = 3000, words = 40;
  const header = Buffer.alloc(0xdc);
  Buffer.from("0100040028ff03006e00ca00", "hex").copy(header);
  header.writeUInt16LE(5, 14);
  header.writeUInt16LE(1234, 12);
  header.write("CLOCK TEST", 16);
  header.writeUInt32LE(5000000, 0x54);
  header.writeUInt32LE(2500, 0x58);
  header.writeUInt32LE(n, 0x5c);
  header.writeUInt16LE(words, 0x60);
  Buffer.from("7e0a1012030e353600", "hex").copy(header, 0x64);
  header.writeUInt32LE(n - 1, 0x7a);
  const analog = Buffer.alloc(58), digital = Buffer.alloc(58);
  analog[1] = 1;
  analog.writeUInt16LE(0x528, 2);
  analog.write("CLOCK VR", 4);
  analog.writeFloatLE(0.01, 28);
  analog.writeFloatLE(-100, 36);
  analog.writeFloatLE(100, 40);
  analog[57] = 255;
  digital[0] = digital[1] = 1;
  digital[3] = digital[57] = 255;
  digital.write("CLOCK CB", 4);
  const payload = Buffer.alloc(n * words * 2);
  for (let i = 0; i < n; i++) {
    payload.writeUInt16BE(1000 + i % 100, i * words * 2);
    payload.writeUInt16BE(i % 2 ? 2 : 0, (i * words + 38) * 2);
  }
  return Buffer.concat([header, Buffer.alloc(0xaae - 0xdc + 12 * 22 + 4), analog, digital, payload]);
}

module.exports = { clockFixture };
