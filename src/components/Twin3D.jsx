import { Component, Suspense, lazy } from "react";

const LazyTwin3DCanvas = lazy(() => import("./twin3d/Twin3DCanvas.jsx"));

export function canUseWebGL() {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

export function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
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

export default function Twin3D({ snapshot, asset, activeComponent, onSelectComponent, fallback }) {
  if (!snapshot || snapshot.capabilities?.twin3d !== true || !canUseWebGL() || prefersReducedMotion()) {
    return fallback;
  }

  return (
    <Twin3DErrorBoundary fallback={fallback}>
      <Suspense fallback={fallback}>
        <LazyTwin3DCanvas snapshot={snapshot} asset={asset} activeComponent={activeComponent} onSelectComponent={onSelectComponent} />
      </Suspense>
    </Twin3DErrorBoundary>
  );
}
