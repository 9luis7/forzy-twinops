import "@testing-library/jest-dom/vitest";
import React, { useEffect, useState } from "react";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CopilotDock from "./CopilotDock.jsx";

let media;
let mediaListener;

beforeEach(() => {
  mediaListener = null;
  media = {
    matches: false,
    addEventListener: vi.fn((_, listener) => { mediaListener = listener; }),
    removeEventListener: vi.fn(),
  };
  vi.stubGlobal("matchMedia", vi.fn(() => media));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("CopilotDock", () => {
  it("keeps draft state and the same child mounted while closing and reopening", () => {
    const mount = vi.fn();
    const unmount = vi.fn();
    function Draft() {
      const [value, setValue] = useState("");
      useEffect(() => { mount(); return unmount; }, []);
      return <label>Pergunta<textarea value={value} onChange={(event) => setValue(event.target.value)} /></label>;
    }
    render(<CopilotDock contextLabel="Últimos dados disponíveis"><Draft /></CopilotDock>);

    const launcher = screen.getByRole("button", { name: "Copiloto" });
    expect(launcher).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(mount).toHaveBeenCalledTimes(1);

    fireEvent.click(launcher);
    expect(screen.getByRole("complementary", { name: "Copiloto" })).not.toHaveAttribute("aria-modal");
    expect(screen.getByRole("button", { name: "Fechar copiloto" })).toHaveFocus();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Como verificar a vibração?" } });
    fireEvent.click(screen.getByRole("button", { name: "Fechar copiloto" }));

    expect(launcher).toHaveFocus();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(unmount).not.toHaveBeenCalled();
    fireEvent.click(launcher);
    expect(screen.getByRole("textbox")).toHaveValue("Como verificar a vibração?");
    expect(mount).toHaveBeenCalledTimes(1);
  });

  it("keeps desktop content interactive without trapping keyboard focus", () => {
    const clicked = vi.fn();
    const { container } = render(
      <><button onClick={clicked}>Selecionar período</button><CopilotDock><button>Enviar pergunta</button></CopilotDock></>
    );
    fireEvent.click(screen.getByRole("button", { name: "Copiloto" }));
    const chartControl = screen.getByRole("button", { name: "Selecionar período" });
    chartControl.focus();
    fireEvent.click(chartControl);
    expect(clicked).toHaveBeenCalledTimes(1);
    expect(chartControl).toHaveFocus();
    expect(container).not.toHaveAttribute("inert");
    const event = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
    document.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });

  it("requests controlled changes and closes with Escape without opening on notifications", () => {
    const onOpenChange = vi.fn();
    const view = render(<CopilotDock open={false} onOpenChange={onOpenChange} notificationCount={1}><p>Orientação existente</p></CopilotDock>);
    fireEvent.click(screen.getByRole("button", { name: "Copiloto" }));
    expect(onOpenChange).toHaveBeenLastCalledWith(true);
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
    view.rerender(<CopilotDock open={false} onOpenChange={onOpenChange} notificationCount={2}><p>Orientação existente</p></CopilotDock>);
    expect(screen.getByRole("button", { name: "Copiloto" })).toHaveAccessibleDescription("2 orientações disponíveis.");
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();

    view.rerender(<CopilotDock open onOpenChange={onOpenChange} notificationCount={2}><p>Orientação existente</p></CopilotDock>);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onOpenChange).toHaveBeenLastCalledWith(false);
    expect(screen.getByRole("complementary")).toBeInTheDocument();
    view.rerender(<CopilotDock open={false} onOpenChange={onOpenChange}><p>Orientação existente</p></CopilotDock>);
    expect(screen.getByRole("button", { name: "Copiloto" })).toHaveFocus();
  });

  it("uses a mobile dialog, traps focus and restores the background on close", () => {
    media.matches = true;
    const { container } = render(
      <><button>Gráfico</button><CopilotDock><textarea aria-label="Pergunta" /><button>Enviar pergunta</button></CopilotDock></>
    );
    const launcher = screen.getByRole("button", { name: "Copiloto" });
    expect(container).not.toHaveAttribute("inert");
    fireEvent.click(launcher);
    const dialog = screen.getByRole("dialog", { name: "Copiloto" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(container).toHaveAttribute("inert");
    expect(document.body.style.overflow).toBe("hidden");
    expect(screen.queryByRole("button", { name: "Copiloto" })).not.toBeInTheDocument();
    const close = within(dialog).getByRole("button", { name: "Fechar copiloto" });
    const send = within(dialog).getByRole("button", { name: "Enviar pergunta" });
    expect(close).toHaveFocus();
    fireEvent.keyDown(close, { key: "Tab", shiftKey: true });
    expect(send).toHaveFocus();
    fireEvent.keyDown(send, { key: "Tab" });
    expect(close).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(container).not.toHaveAttribute("inert");
    expect(document.body.style.overflow).toBe("");
    expect(launcher).toHaveFocus();
  });

  it("skips controls inside collapsed sources in the mobile focus loop", () => {
    media.matches = true;
    render(<CopilotDock><textarea aria-label="Pergunta" /><details><summary>Fonte</summary><a href="#manual">Abrir manual</a></details></CopilotDock>);
    fireEvent.click(screen.getByRole("button", { name: "Copiloto" }));
    const close = screen.getByRole("button", { name: "Fechar copiloto" });
    fireEvent.keyDown(close, { key: "Tab", shiftKey: true });
    expect(screen.getByText("Fonte")).toHaveFocus();
    fireEvent.keyDown(document.activeElement, { key: "Tab" });
    expect(close).toHaveFocus();
  });

  it("restores existing inert and scroll values after switching out of mobile and unmounting", () => {
    const background = document.createElement("section");
    background.setAttribute("inert", "existing");
    document.body.appendChild(background);
    document.body.style.overflow = "clip";
    media.matches = true;
    const { container, unmount } = render(<CopilotDock open><p>Consulta</p></CopilotDock>);
    expect(container).toHaveAttribute("inert");
    act(() => { media.matches = false; mediaListener(); });
    expect(screen.getByRole("complementary")).not.toHaveAttribute("aria-modal");
    expect(container).not.toHaveAttribute("inert");
    expect(background).toHaveAttribute("inert", "existing");
    expect(document.body.style.overflow).toBe("clip");
    act(() => { media.matches = true; mediaListener(); });
    expect(container).toHaveAttribute("inert");
    unmount();
    expect(container).not.toHaveAttribute("inert");
    expect(background).toHaveAttribute("inert", "existing");
    expect(document.body.style.overflow).toBe("clip");
    background.remove();
    document.body.style.overflow = "";
  });

  it("can explain unavailability without dropping saved content", () => {
    render(<CopilotDock available={false}><p>Orientação anterior</p></CopilotDock>);
    const launcher = screen.getByRole("button", { name: "Copiloto" });
    expect(launcher).toBeEnabled();
    expect(launcher).toHaveAccessibleDescription("Consultas temporariamente indisponíveis.");
    fireEvent.click(launcher);
    expect(screen.getByRole("status")).toHaveTextContent("Consultas temporariamente indisponíveis");
    expect(screen.getByText("Orientação anterior")).toBeVisible();
  });
});
