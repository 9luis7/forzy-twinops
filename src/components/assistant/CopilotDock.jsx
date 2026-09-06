import React, { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import "./CopilotDock.css";

export const COPILOT_MOBILE_QUERY = "(max-width: 760px)";

function useMobileDialog() {
  const [mobile, setMobile] = useState(() => (
    typeof window.matchMedia === "function" && window.matchMedia(COPILOT_MOBILE_QUERY).matches
  ));
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return undefined;
    const query = window.matchMedia(COPILOT_MOBILE_QUERY);
    const update = () => setMobile(query.matches);
    update();
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);
  return mobile;
}

// Only the mobile dialog owns background isolation. Restore prior inert/scroll
// values so opening this panel never permanently changes another UI surface.
function isolateBackground(host) {
  const previous = new Map();
  const isolate = () => {
    for (const element of document.body.children) {
      if (element === host || previous.has(element)) continue;
      previous.set(element, element.getAttribute("inert"));
      element.setAttribute("inert", "");
    }
  };
  isolate();
  const observer = new MutationObserver(isolate);
  observer.observe(document.body, { childList: true });
  const overflow = document.body.style.overflow;
  document.body.style.overflow = "hidden";
  return () => {
    observer.disconnect();
    for (const [element, value] of previous) {
      if (value === null) element.removeAttribute("inert");
      else element.setAttribute("inert", value);
    }
    document.body.style.overflow = overflow;
  };
}

function focusableElements(panel) {
  return [...panel.querySelectorAll(
    'button:not(:disabled), a[href], input:not(:disabled):not([type="hidden"]), textarea:not(:disabled), select:not(:disabled), summary, [tabindex]:not([tabindex="-1"])'
  )].filter((element) => (
    element.tabIndex >= 0
    && !element.closest('[hidden], [inert], [aria-hidden="true"]')
    && ![...panel.querySelectorAll("details:not([open])")].some((details) => (
      details.contains(element) && details.querySelector("summary") !== element
    ))
  ));
}

/**
 * `open` + `onOpenChange(nextOpen)` control layout from the owner; omitting open
 * uses internal state. Children remain mounted even when closed. Pass the same
 * open value as TechnicalAssistantPanel.isActive to suppress hidden autofocus.
 * Desktop owners reserve --copilot-panel-width + --copilot-panel-gap while open;
 * on mobile (<= 760px) the dialog owns inert background and keyboard focus.
 */
export default function CopilotDock({
  children,
  contextLabel,
  available = true,
  open,
  onOpenChange,
  notificationCount = 0,
}) {
  const [internalOpen, setInternalOpen] = useState(false);
  const isOpen = open ?? internalOpen;
  const mobile = useMobileDialog();
  const [host] = useState(() => {
    const element = document.createElement("div");
    element.className = "copilot-root";
    return element;
  });
  const id = useId();
  const launcherRef = useRef(null);
  const panelRef = useRef(null);
  const closeRef = useRef(null);
  const wasOpenRef = useRef(false);
  const changeRef = useRef(null);
  const count = Number.isFinite(notificationCount) ? Math.max(0, Math.floor(notificationCount)) : 0;

  const changeOpen = (next) => {
    if (open === undefined) setInternalOpen(next);
    onOpenChange?.(next);
  };
  changeRef.current = changeOpen;

  useEffect(() => {
    document.body.appendChild(host);
    return () => host.remove();
  }, [host]);

  useEffect(() => {
    if (!isOpen || !mobile) return undefined;
    return isolateBackground(host);
  }, [host, isOpen, mobile]);

  useEffect(() => {
    if (isOpen) closeRef.current?.focus();
    else if (wasOpenRef.current) launcherRef.current?.focus();
    wasOpenRef.current = isOpen;
  }, [isOpen, mobile]);

  useEffect(() => {
    if (!isOpen) return undefined;
    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        changeRef.current(false);
      } else if (mobile && event.key === "Tab") {
        const items = focusableElements(panelRef.current);
        const first = items[0];
        const last = items.at(-1);
        const outside = !panelRef.current.contains(document.activeElement);
        if (event.shiftKey && (document.activeElement === first || outside)) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && (document.activeElement === last || outside)) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isOpen, mobile]);

  return createPortal(
    <div className={`copilot-dock${isOpen ? " copilot-dock--open" : ""}`} data-open={isOpen}>
      <button
        type="button"
        className="copilot-launcher"
        ref={launcherRef}
        aria-label="Copiloto"
        aria-expanded={isOpen}
        aria-controls={`${id}-panel`}
        aria-haspopup={mobile ? "dialog" : undefined}
        aria-describedby={`${id}-notice`}
        hidden={isOpen && mobile}
        onClick={() => changeOpen(!isOpen)}
      >
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
          <path d="M20 11.5a8 8 0 0 1-8 8H5l-3 2v-10a9 9 0 0 1 18 0Z" />
          <path d="M7 10h9M7 14h6" />
        </svg>
        <span>Copiloto</span>
        {count > 0 ? <span className="copilot-launcher__badge" aria-hidden="true">{count > 9 ? "9+" : count}</span> : null}
      </button>
      <span id={`${id}-notice`} className="copilot-sr-only" aria-live="polite">
        {!available ? "Consultas temporariamente indisponíveis." : count > 0 ? `${count} orientações disponíveis.` : "Consultar manual e dados do equipamento."}
      </span>
      <section
        className="copilot-panel"
        id={`${id}-panel`}
        ref={panelRef}
        role={mobile ? "dialog" : "complementary"}
        aria-modal={mobile && isOpen ? true : undefined}
        aria-labelledby={`${id}-title`}
        aria-describedby={contextLabel ? `${id}-context` : undefined}
        hidden={!isOpen}
      >
        <header className="copilot-panel__header">
          <div>
            <h2 id={`${id}-title`}>Copiloto</h2>
            {contextLabel ? <p id={`${id}-context`}>{contextLabel}</p> : null}
          </div>
          <button type="button" className="copilot-panel__close button-secondary" ref={closeRef} onClick={() => changeOpen(false)} aria-label="Fechar copiloto">×</button>
        </header>
        <div className="copilot-panel__content">
          {!available ? <p className="assistant-unavailable" role="status">Consultas temporariamente indisponíveis. As informações disponíveis continuam abaixo.</p> : null}
          {children}
        </div>
      </section>
    </div>,
    host
  );
}
