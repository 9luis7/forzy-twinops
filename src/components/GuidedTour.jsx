// GuidedTour.jsx — MODO APRESENTAÇÃO (tour guiado da demo).
//
// Conduz o espectador pela história do gêmeo digital: planta -> motor sob suspeita ->
// rolamento -> telemetria ao vivo -> auditoria. A cada passo o tour NAVEGA a aplicação
// (via nav) e destaca o elemento marcado com data-tour="<target>".
//
// Exporta:
//   - TourProvider({ nav, children }) — contexto com {active, stepIndex} que dirige a navegação.
//   - useTour() — acesso ao estado e às ações (start/next/prev/stop).
//   - TourLauncher() — botão flutuante "▶ Apresentar".
//   - TourOverlay() — escurece a tela, anela o alvo (.tour-spotlight) e mostra a barra do apresentador.

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { TOUR_STEPS } from "../tour.js";

// ---- Contexto -------------------------------------------------------------------------
const TourContext = createContext(null);

export function useTour() {
  const ctx = useContext(TourContext);
  if (!ctx) {
    // Falha graciosa: se algum componente usar useTour fora do provider,
    // devolve um stub inerte para não quebrar a renderização.
    return {
      active: false,
      stepIndex: 0,
      step: null,
      steps: TOUR_STEPS,
      start: () => {},
      next: () => {},
      prev: () => {},
      stop: () => {},
    };
  }
  return ctx;
}

// ---- Provider -------------------------------------------------------------------------
// Mantém {active, stepIndex} e, a cada mudança de passo, dirige a navegação da app.
export function TourProvider({ nav, children }) {
  const [active, setActive] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);

  const steps = TOUR_STEPS;
  const step = active ? steps[stepIndex] ?? null : null;

  // nav pode mudar de identidade entre renders; guardamos a referência mais recente.
  const navRef = useRef(nav);
  navRef.current = nav;

  // Aplica a navegação correspondente a um passo do tour.
  const driveTo = useCallback((s) => {
    const n = navRef.current;
    if (!n || !s) return;
    if (s.asset) {
      n.goAsset(s.asset, s.view || "ativos");
    } else if (s.view) {
      n.goView(s.view);
    }
  }, []);

  const start = useCallback(() => {
    setStepIndex(0);
    setActive(true);
    driveTo(steps[0]);
  }, [driveTo, steps]);

  const stop = useCallback(() => {
    setActive(false);
  }, []);

  const goToIndex = useCallback(
    (idx) => {
      if (idx < 0) return;
      if (idx >= steps.length) {
        // Passar do último passo encerra o tour.
        setActive(false);
        return;
      }
      setStepIndex(idx);
      driveTo(steps[idx]);
    },
    [driveTo, steps]
  );

  const next = useCallback(() => goToIndex(stepIndex + 1), [goToIndex, stepIndex]);
  const prev = useCallback(() => goToIndex(stepIndex - 1), [goToIndex, stepIndex]);

  const value = useMemo(
    () => ({ active, stepIndex, step, steps, start, next, prev, stop }),
    [active, stepIndex, step, steps, start, next, prev, stop]
  );

  return <TourContext.Provider value={value}>{children}</TourContext.Provider>;
}

// ---- Botão flutuante ------------------------------------------------------------------
export function TourLauncher() {
  const { active, start } = useTour();
  if (active) return null; // esconde o lançador enquanto a apresentação roda
  return (
    <button
      type="button"
      className="tour-launcher"
      onClick={start}
      aria-label="Iniciar apresentação guiada"
      title="Iniciar apresentação guiada"
    >
      ▶ Apresentar
    </button>
  );
}

// ---- Overlay (escurecimento + anel de destaque + barra do apresentador) ---------------
export function TourOverlay() {
  const { active, step, stepIndex, steps, next, prev, stop } = useTour();
  const [rect, setRect] = useState(null);

  const target = step?.target || null;

  // Mede o elemento-alvo. A view precisa renderizar/scrollar antes — medimos após
  // requestAnimationFrame + um pequeno timeout. Recalculamos em resize/scroll.
  useLayoutEffect(() => {
    if (!active || !target) {
      setRect(null);
      return;
    }

    let raf1 = 0;
    let timer = 0;
    let cancelled = false;

    const measure = () => {
      if (cancelled) return;
      const el = document.querySelector(`[data-tour="${target}"]`);
      if (!el) {
        setRect(null); // alvo ausente: pula o anel, mas a barra continua
        return;
      }
      const r = el.getBoundingClientRect();
      setRect({ top: r.top, left: r.left, width: r.width, height: r.height });
    };

    const schedule = () => {
      raf1 = requestAnimationFrame(() => {
        // dá tempo da troca de view montar o DOM e do scrollTo iniciar
        timer = window.setTimeout(() => {
          // rola o alvo para a área visível, depois mede
          const el = document.querySelector(`[data-tour="${target}"]`);
          if (el) {
            el.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
          }
          // mede já e novamente após o scroll suave assentar
          measure();
          window.setTimeout(measure, 360);
        }, 120);
      });
    };

    schedule();

    const onChange = () => measure();
    window.addEventListener("resize", onChange);
    window.addEventListener("scroll", onChange, true);

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf1);
      window.clearTimeout(timer);
      window.removeEventListener("resize", onChange);
      window.removeEventListener("scroll", onChange, true);
    };
  }, [active, target, stepIndex]);

  // Esc encerra a apresentação.
  useEffect(() => {
    if (!active) return;
    const onKey = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        stop();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, stop]);

  if (!active || !step) return null;

  const total = steps.length;
  const isFirst = stepIndex === 0;
  const PAD = 8; // folga do anel ao redor do alvo

  return (
    <div className="tour-overlay" role="dialog" aria-modal="true" aria-label="Apresentação guiada">
      {/* Anel de destaque ao redor do alvo (omitido se o alvo não foi encontrado). */}
      {rect && (
        <div
          className="tour-spotlight"
          style={{
            position: "fixed",
            top: rect.top - PAD,
            left: rect.left - PAD,
            width: rect.width + PAD * 2,
            height: rect.height + PAD * 2,
          }}
        />
      )}

      {/* Barra do apresentador, ancorada na base. */}
      <div className="presenter-bar" onClick={(e) => e.stopPropagation()}>
        <div className="presenter-title">{step.title}</div>
        <div className="presenter-text">{step.text}</div>

        <div className="presenter-progress" aria-hidden="true">
          {steps.map((s, i) => (
            <span
              key={s.id}
              className={"dot" + (i === stepIndex ? " is-active" : "")}
            />
          ))}
        </div>

        <div className="presenter-ctrls">
          <span className="presenter-count">
            {stepIndex + 1} de {total}
          </span>
          <button
            type="button"
            className="btn"
            onClick={prev}
            disabled={isFirst}
            aria-label="Passo anterior"
          >
            ◀ Anterior
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={next}
            aria-label="Próximo passo"
          >
            Próximo ▶
          </button>
          <button
            type="button"
            className="btn"
            onClick={stop}
            aria-label="Sair da apresentação"
          >
            Sair
          </button>
        </div>
      </div>
    </div>
  );
}

export default TourProvider;
