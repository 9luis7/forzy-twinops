import React, { Component, Suspense, lazy } from "react";
import LoadingState from "./LoadingState.jsx";

export function canUseWebGL() {
  if (typeof document === "undefined") return false;
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

const TWIN_LOADING_MESSAGES = [
  "Preparando a geometria do conjunto…",
  "Validando o manifesto do modelo…",
  "Sincronizando o gêmeo digital…",
  "Preparando rotação e zoom…",
];

export function Twin3DStaticFallback({ snapshot }) {
  return (
    <figure className="card" aria-label="Prévia estática do conjunto motor-bomba">
      <img
        src="/models/conjunto-motor-bomba-preview.png"
        alt="Prévia estática do conjunto motor-bomba derivada do STEP fornecido"
        loading="lazy"
        style={{ display: "block", width: "100%", height: "auto" }}
      />
      <figcaption className="muted small">
        Visualização 3D indisponível; exibindo a prévia estática do mesmo conjunto.
      </figcaption>
      {snapshot?.mode === "replay" && <div className="demo-static-sensors" aria-label="Sensores na prévia estática">{["s1", "s2"].map((id) => <span key={id}>{id.toUpperCase()} · {id === "s1" ? "Motor" : "Bomba"}<br />{snapshot.sensors[id].latest?.measurements.vibrationVelocityRms?.value ?? "—"} mm/s · {snapshot.sensors[id].assessment?.assessment.status ?? "indisponível"}</span>)}</div>}
    </figure>
  );
}

class Twin3DErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error) {
    console.warn("Twin3D fallback", error);
  }

  componentDidUpdate(previousProps) {
    if (this.state.error && previousProps.resetSignal !== this.props.resetSignal) {
      this.setState({ error: null });
    }
  }

  render() {
    return this.state.error ? this.props.fallback : this.props.children;
  }
}

export function createTwin3DComponent(loadCanvas) {
  const LazyTwin3DCanvas = lazy(loadCanvas);

  return function Twin3D({ snapshot, fallback, selectedSensor, onSelectSensor }) {
    const fallbackView = fallback ?? <Twin3DStaticFallback snapshot={snapshot} />;
    if (!snapshot || snapshot.capabilities?.twin3d !== true || !canUseWebGL()) {
      return fallbackView;
    }

    const loadingView = (
      <LoadingState
        label="Carregando o gêmeo 3D real…"
        messages={TWIN_LOADING_MESSAGES}
        variant="twin"
      />
    );

    return (
      <Twin3DErrorBoundary fallback={fallbackView} resetSignal={snapshot}>
        <Suspense fallback={loadingView}>
          <LazyTwin3DCanvas snapshot={snapshot} {...(selectedSensor !== undefined ? { selectedSensor } : {})} {...(onSelectSensor !== undefined ? { onSelectSensor } : {})} />
        </Suspense>
      </Twin3DErrorBoundary>
    );
  };
}

const Twin3D = createTwin3DComponent(() => import("./twin3d/Twin3DCanvas.jsx"));

export default Twin3D;
