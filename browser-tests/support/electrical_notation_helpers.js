// DEC-117: shared visual check for the electrical-symbol formatter.
//
// Browser assertions on the DOM alone are not enough: the owner-UAT
// defect had a real <sub> in the DOM while CSS painted it ABOVE the
// baseline (a generic `span { display: flex }` rule blockified it and its
// zero line-height box let the ink overflow upwards). This measures the
// rendered GLYPHS (text ranges), never element boxes.

const { expect } = require("@playwright/test");

// Every `.ww-electrical-symbol` matched by `locator` -> ink geometry of the
// subscript relative to its V/I glyph.
async function electricalSymbolGeometry(locator) {
  return locator.evaluateAll((els) => els.map((el) => {
    const sub = el.querySelector(".ww-electrical-sub");
    const glyph = (node, a, b) => { const r = document.createRange(); r.setStart(node, a); r.setEnd(node, b); return r.getBoundingClientRect(); };
    const v = glyph(el.firstChild, 0, 1);
    const s = glyph(sub.firstChild, 0, sub.firstChild.nodeValue.length);
    return {
      text: el.textContent,
      centreBelowRatio: ((s.top + s.bottom) / 2 - (v.top + v.bottom) / 2) / v.height,
      bottomBelow: s.bottom - v.bottom,
    };
  }));
}

// A true subscript: ink centre clearly below the V's (measured +0.25 for
// the shared rule; the pre-fix superscript defect measured -0.38) and ink
// bottom at/below the V's.
async function expectTrueSubscripts(locator, expectedCount) {
  const geometry = await electricalSymbolGeometry(locator);
  if (expectedCount !== undefined) expect(geometry).toHaveLength(expectedCount);
  expect(geometry.length).toBeGreaterThan(0);
  for (const g of geometry) {
    expect(g.centreBelowRatio, `${g.text}: subscript centre below the V centre`).toBeGreaterThan(0.15);
    expect(g.bottomBelow, `${g.text}: subscript ink bottom at/below the V`).toBeGreaterThan(0);
  }
  return geometry;
}

module.exports = { electricalSymbolGeometry, expectTrueSubscripts };
