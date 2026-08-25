import "@testing-library/jest-dom/vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import React, { useState } from "react";
import { cleanup, createEvent, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import ViewModeSwitch from "./ViewModeSwitch.jsx";

const styles = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");

afterEach(cleanup);

function ViewModeHarness() {
  const [viewMode, setViewMode] = useState("now");
  return (
    <ViewModeSwitch
      onShowHistory={() => setViewMode("historical")}
      onShowNow={() => setViewMode("now")}
      viewMode={viewMode}
    />
  );
}

function ruleBody(selector) {
  const start = styles.indexOf(`${selector} {`);
  if (start === -1) return "";
  const bodyStart = start + selector.length + 2;
  return styles.slice(bodyStart, styles.indexOf("}", bodyStart));
}

function hexProperty(rule, property) {
  return rule.match(new RegExp(`${property}:\\s*[^;]*?(#[0-9a-f]{6})`, "i"))?.[1] ?? null;
}

function relativeLuminance(hex) {
  const channels = hex.slice(1).match(/.{2}/g).map((channel) => Number.parseInt(channel, 16) / 255);
  const linear = channels.map((channel) => (
    channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
  ));
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function contrastRatio(left, right) {
  const lighter = Math.max(relativeLuminance(left), relativeLuminance(right));
  const darker = Math.min(relativeLuminance(left), relativeLuminance(right));
  return (lighter + 0.05) / (darker + 0.05);
}

it("keeps native Tab and Arrow navigation for the temporal radio group", () => {
  render(<ViewModeHarness />);
  const now = screen.getByRole("radio", { name: "Agora" });
  const history = screen.getByRole("radio", { name: "Histórico" });

  now.focus();
  expect(now).toHaveFocus();
  const tabEvent = createEvent.keyDown(now, { key: "Tab" });
  fireEvent(now, tabEvent);
  expect(tabEvent.defaultPrevented).toBe(false);

  const arrowEvent = createEvent.keyDown(now, { key: "ArrowRight" });
  fireEvent(now, arrowEvent);
  expect(arrowEvent.defaultPrevented).toBe(false);

  // jsdom does not execute the browser's native radio-group default action.
  history.focus();
  fireEvent.click(history);
  expect(history).toHaveFocus();
  expect(history).toBeChecked();
});

it("keeps the selected radio focus indicator above 3:1 against its adjacent fill", () => {
  const selectedRule = ruleBody(".view-mode-switch input:checked + span");
  const selectedFocusRule = ruleBody(
    ".view-mode-switch input:checked:focus-visible + span",
  );

  expect(selectedFocusRule).not.toBe("");
  const selectedFill = hexProperty(selectedRule, "background");
  const selectedFocus = hexProperty(selectedFocusRule, "outline");
  expect(selectedFill).not.toBeNull();
  expect(selectedFocus).not.toBeNull();
  expect(contrastRatio(selectedFill, selectedFocus)).toBeGreaterThanOrEqual(3);
});
