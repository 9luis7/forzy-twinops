import React, { Component, Suspense, lazy } from "react";

export function canUseWebGL() {
  if (typeof document === "undefined") return false;
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

export function prefersReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

export function Twin3DStaticFallback() {
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

  render() {
    return this.state.error ? this.props.fallback : this.props.children;
  }
}

export function createTwin3DComponent(loadCanvas) {
  const LazyTwin3DCanvas = lazy(loadCanvas);

  return function Twin3D({ snapshot, fallback }) {
    const fallbackView = fallback ?? <Twin3DStaticFallback />;
    if (!snapshot || snapshot.capabilities?.twin3d !== true || !canUseWebGL() || prefersReducedMotion()) {
      return fallbackView;
    }

    return (
      <Twin3DErrorBoundary fallback={fallbackView}>
        <Suspense fallback={fallbackView}>
          <LazyTwin3DCanvas snapshot={snapshot} />
        </Suspense>
      </Twin3DErrorBoundary>
    );
  };
}

const Twin3D = createTwin3DComponent(() => import("./twin3d/Twin3DCanvas.jsx"));

export default Twin3D;
