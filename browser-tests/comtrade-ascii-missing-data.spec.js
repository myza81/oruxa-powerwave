// The reserved COMTRADE-1999 raw code must become a real plotted gap.
// Other revisions and genuine engineering values keep their existing meaning.
const { test, expect } = require("./support/test");

async function uploadFrequency(page, revision) {
  const cfg = [
    `MISSING_SAMPLE_TEST,DEVICE,${revision}`, "2,2A,0D",
    "1,Recorded Frequency,,,Hz,0.0005,50,0,-99999,99998,1,1,P",
    "2,Valid Engineering Value,,,Hz,1000,-1,0,-99999,99998,1,1,P",
    "50", "1", "1000,7", "11/11/2026,08:00:00.000000",
    "11/11/2026,08:00:00.000000", "ASCII", "1",
  ].join("\r\n") + "\r\n";
  const raw = [0, 99999, 99999, 1000, -1000, 99999, 2000];
  const dat = raw.map((v, i) => `${i+1},${i*1000},${v},100`).join("\r\n") + "\r\n";
  await page.goto("/index.html");
  await page.locator("#wwRdUploadBtn").first().click();
  await page.locator("#uploadModalFile_0").setInputFiles({name:"event.cfg",mimeType:"application/octet-stream",buffer:Buffer.from(cfg)});
  await page.locator("#uploadModalFile_1").setInputFiles({name:"event.dat",mimeType:"application/octet-stream",buffer:Buffer.from(dat)});
  await page.locator("#uploadModalSubmitBtn").click();
  await expect(page.locator("#uploadModalOverlay")).toBeHidden();
  const source = page.locator("#wwRdRecordingList .ww-rd-recording-item").first();
  const sid = await source.getAttribute("data-source-id");
  await source.click();
  return sid;
}

async function traceFor(page, sid, name) {
  return page.evaluate(({sid,name}) => {
    const trace = [...document.querySelectorAll(".ww-chart")]
      .flatMap(chart => chart.data || []).find(t => t.meta === `${sid}::${name}`);
    return trace && {meta:trace.meta, values:Array.from(trace.y), connectgaps:trace.connectgaps === true, hover:trace.hovertemplate};
  }, {sid,name});
}

test("1999 missing codes render gaps while a genuine 99999 engineering value remains", async ({page}, info) => {
  const sid = await uploadFrequency(page,"1999");
  for (const name of ["Recorded Frequency","Valid Engineering Value"]) {
    await page.locator(`tr.channel-row--toggle[data-channel-kind="analog"][data-source-id="${sid}"][data-channel-name="${name}"]`).click();
    await expect.poll(async () => (await traceFor(page,sid,name))?.values.length).toBe(7);
  }
  const trace = await traceFor(page,sid,"Recorded Frequency");
  expect(trace.meta).toBe(`${sid}::Recorded Frequency`);
  expect(trace.values).toEqual([50,null,null,50.5,49.5,null,51]);
  expect(trace.connectgaps).toBe(false);
  expect(trace.hover).toContain("Hz");
  expect((await traceFor(page,sid,"Valid Engineering Value")).values).toEqual(Array(7).fill(99999));
  await page.screenshot({path:info.outputPath("reserved-code-gaps.png")});
});

test("2013 numeric 99999 is preserved rather than applying the 1999 null convention", async ({page}) => {
  const sid = await uploadFrequency(page,"2013");
  await page.locator(`tr.channel-row--toggle[data-channel-kind="analog"][data-source-id="${sid}"][data-channel-name="Recorded Frequency"]`).click();
  await expect.poll(async () => (await traceFor(page,sid,"Recorded Frequency"))?.values.length).toBe(7);
  expect((await traceFor(page,sid,"Recorded Frequency")).values).toEqual([50,99.9995,99.9995,50.5,49.5,99.9995,51]);
});
