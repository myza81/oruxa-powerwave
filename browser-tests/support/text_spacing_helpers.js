// Rendered word-spacing checks for composed labels (owner UAT: "Default
// ContextV<sub>AB</sub>").
//
// textContent is not enough: the defect kept the space in the DOM
// ("Default Context VAB") while layout discarded it. When ordinary text and
// a rich symbol are separate children of a flex/grid container, each text
// run becomes its own anonymous item and its edge whitespace is trimmed.
// These helpers measure the rendered GLYPHS (per-character text ranges),
// never element boxes, and find that DOM shape directly.

const { expect } = require("@playwright/test");

// Every word boundary inside each element matched by `locator`: two
// consecutive visible glyphs on one line, whether the DOM text has
// whitespace between them, and the horizontal gap between their advance
// boxes relative to the width of a space in that font (a rendered space
// measures ~1.0; a discarded one ~0).
async function wordBoundaryGeometry(locator) {
  return locator.evaluateAll((els) => {
    const canvas = document.createElement("canvas").getContext("2d");
    const spaceWidth = (el) => {
      const cs = getComputedStyle(el);
      canvas.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
      return canvas.measureText(" ").width + (parseFloat(cs.wordSpacing) || 0) + (parseFloat(cs.letterSpacing) || 0);
    };
    return els.map((el) => {
      const glyphs = [];
      const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      let node;
      while ((node = walker.nextNode())) {
        const parent = node.parentElement;
        if (!parent || parent.getClientRects().length === 0) continue;
        const text = node.nodeValue;
        for (let i = 0; i < text.length; i += 1) {
          if (/\s/.test(text[i])) { glyphs.push({ space: true, width: spaceWidth(parent) }); continue; }
          const range = document.createRange();
          range.setStart(node, i);
          range.setEnd(node, i + 1);
          const r = range.getClientRects()[0];
          if (!r || r.width === 0) continue; // clipped by an ellipsis, or not painted
          glyphs.push({ ch: text[i], left: r.left, right: r.right, top: r.top, bottom: r.bottom });
        }
      }
      const boundaries = [];
      let prev = null;
      let space = 0;
      let before = "";
      for (const g of glyphs) {
        if (g.space) { if (prev && !space) space = g.width; before += " "; continue; }
        if (prev) {
          const sameLine = Math.min(prev.bottom, g.bottom) - Math.max(prev.top, g.top) > 0 && g.left >= prev.left - 0.5;
          if (sameLine) {
            const reference = space || spaceWidth(el);
            boundaries.push({
              context: (before.slice(-14) + "|" + g.ch).replace(/\s+/g, " "),
              spaced: space > 0,
              gapPx: g.left - prev.right,
              gapSpaces: (g.left - prev.right) / reference,
            });
          }
        }
        before += g.ch;
        prev = g;
        space = 0;
      }
      return { text: el.textContent, boundaries };
    });
  });
}

// A DOM space must render as one space: not discarded (the defect measured
// 0) and not doubled/un-collapsed. Unless `separators` is set (a label that
// deliberately uses a dot/icon/margin between runs), a boundary WITHOUT DOM
// whitespace must not suddenly render as a word gap either (e.g. "V" and
// its subscript, "RMS" and "(").
const MIN_SPACE_RATIO = 0.6;
const MAX_SPACE_RATIO = 1.6;
const MAX_JOINED_RATIO = 0.45;

async function expectWordSpacingPreserved(locator, { count, separators = false } = {}) {
  const measured = await wordBoundaryGeometry(locator);
  if (count !== undefined) expect(measured).toHaveLength(count);
  expect(measured.length).toBeGreaterThan(0);
  for (const m of measured) {
    expect(m.boundaries.length, `${m.text}: has measurable glyphs`).toBeGreaterThan(0);
    for (const b of m.boundaries) {
      if (b.spaced) {
        expect(b.gapSpaces, `${m.text}: word gap at "${b.context}"`).toBeGreaterThan(MIN_SPACE_RATIO);
        expect(b.gapSpaces, `${m.text}: word gap at "${b.context}" not oversized`).toBeLessThan(MAX_SPACE_RATIO);
      } else if (!separators) {
        expect(b.gapSpaces, `${m.text}: no stray gap at "${b.context}"`).toBeLessThan(MAX_JOINED_RATIO);
      }
    }
  }
  return measured;
}

// The exact DOM shape that loses a space: a direct text-node child of a
// flex/grid container, next to an element sibling, with whitespace on the
// shared edge ("Default Context " + <span>V<sub>AB</sub></span>), or a
// whitespace-only run between two element children. A container whose own
// column gap already separates its items (e.g. a "Voltage" summary + its
// "(3)" badge, `gap: 8px`) is reported with `gapSeparated: true` -- the
// words are visibly apart by design. Visible elements only; `rootSelector`
// defaults to the whole document.
async function findFlexWhitespaceLoss(page, rootSelector) {
  return page.evaluate((selector) => {
    const roots = selector ? Array.from(document.querySelectorAll(selector)) : [document.body];
    const found = [];
    const seen = new Set();
    for (const root of roots) {
      for (const el of [root, ...root.querySelectorAll("*")]) {
        if (seen.has(el)) continue;
        seen.add(el);
        const display = getComputedStyle(el).display;
        if (!/flex|grid/.test(display)) continue;
        if (el.getClientRects().length === 0) continue;
        const kids = Array.from(el.childNodes).filter((n) => n.nodeType === 1 ? getComputedStyle(n).display !== "none" : n.nodeType === 3);
        kids.forEach((n, i) => {
          if (n.nodeType !== 3 || !/\s/.test(n.nodeValue)) return;
          const prevEl = kids[i - 1] && kids[i - 1].nodeType === 1 && kids[i - 1].textContent.trim();
          const nextEl = kids[i + 1] && kids[i + 1].nodeType === 1 && kids[i + 1].textContent.trim();
          // Newline-indented static markup is layout whitespace by design;
          // only runtime-composed spaces (" ") are separators.
          const v = n.nodeValue;
          if (!v.trim()) {
            if (!/^[ \u00a0]+$/.test(v) || !(prevEl && nextEl)) return;
          } else if (!((/^[ ]+\S/.test(v) && prevEl) || (/\S[ ]+$/.test(v) && nextEl))) {
            return;
          }
          const cs = getComputedStyle(el);
          const gapPx = parseFloat(cs.columnGap) || 0;
          found.push({
            gapSeparated: gapPx >= 0.2 * parseFloat(cs.fontSize),
            container: el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") + (el.className && typeof el.className === "string" ? "." + el.className.trim().split(/\s+/).join(".") : ""),
            display,
            text: el.textContent.replace(/\s+/g, " ").trim().slice(0, 120),
            run: JSON.stringify(v),
          });
        });
      }
    }
    return found;
  }, rootSelector || null);
}

// No visible container anywhere under `rootSelector` drops a composed
// space: every mixed text + rich-markup label must be one inline unit
// (wwRichLabelHtml()) or rely on a real flex/grid gap.
async function expectNoFlexWhitespaceLoss(page, rootSelector) {
  const lost = (await findFlexWhitespaceLoss(page, rootSelector)).filter((f) => !f.gapSeparated);
  expect(lost, JSON.stringify(lost, null, 1)).toEqual([]);
}

module.exports = { wordBoundaryGeometry, expectWordSpacingPreserved, findFlexWhitespaceLoss, expectNoFlexWhitespaceLoss };
