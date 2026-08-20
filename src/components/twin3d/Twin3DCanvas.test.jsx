import "@testing-library/jest-dom/vitest";
import React, { Component } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import Twin3DCanvas from "./Twin3DCanvas.jsx";
import { normalSnapshot, realManifestFixture } from "./testFixtures.js";


vi.mock("@react-three/fiber", () => ({
  Canvas: ({ children, dpr }) => {
    const renderableChildren = React.Children.toArray(children).filter(
      (child) => !["ambientLight", "directionalLight"].includes(child.type),
    );
    return (
      <div data-testid="r3f-canvas" data-dpr={JSON.stringify(dpr)}>
        {renderableChildren}
      </div>
    );
  },
}));

vi.mock("@react-three/drei", () => ({
  Bounds: ({ children, fit, clip, observe, margin }) => (
    <div
      data-testid="model-bounds"
      data-fit={String(fit)}
      data-clip={String(clip)}
      data-observe={String(observe)}
      data-margin={String(margin)}
    >
      {children}
    </div>
  ),
  OrbitControls: ({ enablePan, makeDefault }) => (
    <div
      aria-label="Controles orbitais do modelo"
      data-enable-pan={String(enablePan)}
      data-make-default={String(makeDefault)}
    />
  ),
  useGLTF: vi.fn(),
}));

class TestErrorBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? <div data-testid="error-fallback">Falha 3D</div> : this.props.children;
  }
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("renders the supplied GLB without sensor markers", async () => {
  const ModelStub = vi.fn(({ modelUrl }) => <div data-testid="loaded-model" data-model-url={modelUrl} />);

  render(
    <Twin3DCanvas
      snapshot={normalSnapshot}
      loadManifest={() => Promise.resolve(realManifestFixture)}
      Model={ModelStub}
    />,
  );

  expect(await screen.findByLabelText("Modelo 3D do conjunto motor-bomba")).toBeInTheDocument();
  expect(screen.getByTestId("loaded-model")).toHaveAttribute(
    "data-model-url",
    "/models/conjunto-motor-bomba.glb",
  );
  expect(screen.getByTestId("r3f-canvas")).toHaveAttribute("data-dpr", "[1,1.5]");
  expect(screen.getByTestId("model-bounds")).toHaveAttribute("data-fit", "true");
  expect(screen.getByTestId("model-bounds")).toHaveAttribute("data-clip", "true");
  expect(screen.getByTestId("model-bounds")).toHaveAttribute("data-observe", "true");
  expect(screen.getByTestId("model-bounds")).toHaveAttribute("data-margin", "1.2");
  expect(screen.getByLabelText("Controles orbitais do modelo")).toHaveAttribute("data-enable-pan", "false");
  expect(screen.queryByLabelText(/Sensor S1/i)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/Sensor S2/i)).not.toBeInTheDocument();
});

it("surfaces manifest loading failures to the outer fallback boundary", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {});

  render(
    <TestErrorBoundary>
      <Twin3DCanvas
        snapshot={normalSnapshot}
        loadManifest={() => Promise.reject(new Error("manifest unavailable"))}
      />
    </TestErrorBoundary>,
  );

  expect(await screen.findByTestId("error-fallback")).toBeVisible();
});

it("surfaces GLB rendering failures to the outer fallback boundary", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  const RejectingModel = () => {
    throw new Error("glb unavailable");
  };

  render(
    <TestErrorBoundary>
      <Twin3DCanvas
        snapshot={normalSnapshot}
        loadManifest={() => Promise.resolve(realManifestFixture)}
        Model={RejectingModel}
      />
    </TestErrorBoundary>,
  );

  expect(await screen.findByTestId("error-fallback")).toBeVisible();
});
