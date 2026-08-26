import "@testing-library/jest-dom/vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import React from "react";
import { act, cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import LoadingState from "./LoadingState.jsx";

const styles = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");

function motionPreference(matches = false) {
  const listeners = new Set();
  return {
    matches,
    media: "(prefers-reduced-motion: reduce)",
    addEventListener: vi.fn((event, listener) => {
      if (event === "change") listeners.add(listener);
    }),
    removeEventListener: vi.fn((event, listener) => {
      if (event === "change") listeners.delete(listener);
    }),
    setMatches(nextValue) {
      this.matches = nextValue;
      listeners.forEach((listener) => listener({ matches: nextValue }));
    },
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue(motionPreference(false)));
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it("keeps the accessible status name stable while hiding decorative copy", () => {
  render(
    <LoadingState
      label="Carregando o último snapshot real"
      messages={["Validando a telemetria recebida"]}
    />,
  );

  const status = screen.getByRole("status", { name: "Carregando o último snapshot real" });
  expect(status).toHaveClass("loading-state", "loading-state--panel");
  expect(status).toHaveAttribute("aria-busy", "true");
  expect(within(status).getByText("Validando a telemetria recebida")).toHaveAttribute(
    "aria-hidden",
    "true",
  );
  expect(within(status).getByTestId("loading-indicator")).toHaveAttribute("aria-hidden", "true");
});

it("uses visible transform and opacity motion for the loading indicator", () => {
  const ringRule = styles.match(/\.loading-state__ring\s*\{([^}]*)\}/)?.[1] ?? "";
  const pulseRule = styles.match(/\.loading-state__pulse\s*\{([^}]*)\}/)?.[1] ?? "";

  expect(ringRule).toMatch(/animation:\s*loading-ring-turn\s+[^;]*infinite/i);
  expect(pulseRule).toMatch(/animation:\s*loading-pulse\s+[^;]*infinite/i);
  expect(styles).toMatch(/@keyframes\s+loading-ring-turn\s*\{[^}]*transform:\s*rotate\(/is);
  expect(styles).toMatch(/@keyframes\s+loading-pulse\s*\{/i);
});

it.each(["panel", "twin", "canvas"])("exposes the %s visual variant", (variant) => {
  render(<LoadingState label="Carregando" variant={variant} />);

  expect(screen.getByRole("status", { name: "Carregando" })).toHaveClass(
    `loading-state--${variant}`,
  );
});

it("chooses one random starting phrase per mount and then rotates sequentially", () => {
  const random = vi.spyOn(Math, "random").mockReturnValue(0.5);
  const messages = [
    "Preparando a geometria industrial",
    "Sincronizando o contexto operacional",
    "Conferindo os canais S1 e S2",
  ];
  const { rerender } = render(<LoadingState label="Carregando modelo" messages={messages} />);

  expect(screen.getByText(messages[1])).toBeVisible();
  expect(random).toHaveBeenCalledTimes(1);

  rerender(<LoadingState label="Carregando modelo 3D" messages={messages} />);
  expect(screen.getByText(messages[1])).toBeVisible();
  expect(random).toHaveBeenCalledTimes(1);

  act(() => vi.advanceTimersByTime(2_499));
  expect(screen.getByText(messages[1])).toBeVisible();

  act(() => vi.advanceTimersByTime(1));
  expect(screen.getByText(messages[2])).toBeVisible();
  expect(screen.queryByText(messages[1])).not.toBeInTheDocument();

  act(() => vi.advanceTimersByTime(2_500));
  expect(screen.getByText(messages[0])).toBeVisible();
});

it("does not repeat identical consecutive phrases", () => {
  vi.spyOn(Math, "random").mockReturnValue(0);
  render(
    <LoadingState
      label="Carregando modelo"
      messages={["Preparando a geometria", "Preparando a geometria", "Carregando materiais"]}
    />,
  );

  expect(screen.getByText("Preparando a geometria")).toBeVisible();
  act(() => vi.advanceTimersByTime(2_500));
  expect(screen.getByText("Carregando materiais")).toBeVisible();
  expect(screen.queryByText("Preparando a geometria")).not.toBeInTheDocument();
});

it("holds one visual phrase when reduced motion is requested", () => {
  window.matchMedia.mockReturnValue(motionPreference(true));
  vi.spyOn(Math, "random").mockReturnValue(0);
  const messages = ["Preparando a geometria", "Carregando materiais"];

  render(<LoadingState label="Carregando modelo 3D" messages={messages} variant="twin" />);
  expect(screen.getByText(messages[0])).toBeVisible();

  act(() => vi.advanceTimersByTime(10_000));

  expect(screen.getByText(messages[0])).toBeVisible();
  expect(screen.queryByText(messages[1])).not.toBeInTheDocument();
});

it("stops and resumes phrase rotation when reduced motion changes live", () => {
  const preference = motionPreference(false);
  window.matchMedia.mockReturnValue(preference);
  vi.spyOn(Math, "random").mockReturnValue(0);
  const messages = ["Preparando a geometria", "Carregando materiais", "Ajustando a vista"];

  render(<LoadingState label="Carregando modelo 3D" messages={messages} />);
  act(() => vi.advanceTimersByTime(2_500));
  expect(screen.getByText(messages[1])).toBeVisible();

  act(() => preference.setMatches(true));
  act(() => vi.advanceTimersByTime(5_000));
  expect(screen.getByText(messages[1])).toBeVisible();

  act(() => preference.setMatches(false));
  act(() => vi.advanceTimersByTime(2_500));
  expect(screen.getByText(messages[2])).toBeVisible();
});
