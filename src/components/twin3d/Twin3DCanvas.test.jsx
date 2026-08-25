import "@testing-library/jest-dom/vitest";
import React, { Component } from "react";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { BoxGeometry, Mesh, MeshStandardMaterial, Scene } from "three";
import { afterEach, expect, it, vi } from "vitest";
import Twin3DCanvas, * as twin3dModule from "./Twin3DCanvas.jsx";
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
  Bounds: ({ children, fit, clip, observe, margin, maxDuration }) => (
    <div
      data-testid="model-bounds"
      data-fit={String(fit)}
      data-clip={String(clip)}
      data-observe={String(observe)}
      data-margin={String(margin)}
      data-max-duration={String(maxDuration)}
    >
      {children}
    </div>
  ),
  Html: ({ children, fullscreen }) => (
    <div data-fullscreen={String(fullscreen)} data-testid="canvas-html">{children}</div>
  ),
  OrbitControls: ({ enableDamping, enablePan, makeDefault }) => (
    <div
      aria-label="Controles orbitais do modelo"
      data-enable-damping={String(enableDamping)}
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
      viewMode="historical"
      displayContext={{ selectedAt: "2026-08-22T12:00:00.000Z" }}
      loadManifest={() => Promise.resolve(realManifestFixture)}
      Model={ModelStub}
    />,
  );

  expect(await screen.findByLabelText("Modelo 3D do conjunto motor-bomba")).toBeInTheDocument();
  expect(screen.getByTestId("twin3d-canvas")).toHaveAttribute("data-view-mode", "historical");
  expect(screen.getByTestId("twin3d-canvas")).toHaveAttribute(
    "data-context-at",
    "2026-08-22T12:00:00.000Z",
  );
  expect(screen.getByTestId("loaded-model")).toHaveAttribute(
    "data-model-url",
    "/models/conjunto-motor-bomba.glb",
  );
  expect(screen.getByTestId("r3f-canvas")).toHaveAttribute("data-dpr", "[1,1.5]");
  expect(screen.getByTestId("model-bounds")).toHaveAttribute("data-fit", "true");
  expect(screen.getByTestId("model-bounds")).toHaveAttribute("data-clip", "true");
  expect(screen.getByTestId("model-bounds")).toHaveAttribute("data-observe", "true");
  expect(screen.getByTestId("model-bounds")).toHaveAttribute("data-margin", "1.2");
  expect(screen.getByTestId("model-bounds")).toHaveAttribute("data-max-duration", "0.01");
  expect(screen.getByLabelText("Controles orbitais do modelo")).toHaveAttribute("data-enable-pan", "false");
  expect(screen.getByLabelText("Controles orbitais do modelo")).toHaveAttribute("data-enable-damping", "false");
  await waitFor(() => {
    expect(screen.getByTestId("twin3d-canvas")).toHaveAttribute("data-model-ready", "true");
  });
  expect(screen.queryByLabelText(/Sensor S1/i)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/Sensor S2/i)).not.toBeInTheDocument();
});

it("normalizes fully metallic CAD materials so the status color stays visible", () => {
  const scene = new Scene();
  const geometry = new BoxGeometry(1, 1, 1);
  const material = new MeshStandardMaterial({
    color: "#ffffff",
    metalness: 1,
    roughness: 1,
  });
  scene.add(new Mesh(geometry, material));

  twin3dModule.applyViewModelToSceneMaterials(scene, {
    materialColor: "#718096",
    emissiveColor: "#1f2937",
    emissiveIntensity: 0,
  });

  expect(material.color.getHexString()).toBe("718096");
  expect(material.metalness).toBe(0.18);
  expect(material.roughness).toBe(0.72);
  expect(material.version).toBeGreaterThan(0);
  geometry.dispose();
  material.dispose();
});

it("shows a dedicated loading state while the manifest is pending", () => {
  render(
    <Twin3DCanvas
      snapshot={normalSnapshot}
      loadManifest={() => new Promise(() => {})}
    />,
  );

  expect(
    screen.getByRole("status", { name: "Preparando a geometria do conjunto…" }),
  ).toHaveAttribute("aria-live", "polite");
});

it("shows a dedicated loading state while the GLB resource is pending", async () => {
  const pending = new Promise(() => {});
  const PendingModel = () => {
    throw pending;
  };

  render(
    <Twin3DCanvas
      snapshot={normalSnapshot}
      loadManifest={() => Promise.resolve(realManifestFixture)}
      Model={PendingModel}
    />,
  );

  await screen.findByLabelText("Modelo 3D do conjunto motor-bomba");
  expect(screen.getByTestId("twin3d-canvas")).toHaveAttribute("data-model-ready", "false");
  expect(screen.getByTestId("canvas-html")).toHaveAttribute("data-fullscreen", "true");
  expect(
    screen.getByRole("status", { name: "Carregando a malha 3D real…" }),
  ).toHaveAttribute("aria-live", "polite");
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

it("clones real Three materials independently and disposes only the clone", () => {
  const sourceScene = new Scene();
  const sourceGeometry = new BoxGeometry(1, 1, 1);
  const sourceMaterial = new MeshStandardMaterial({ color: "#ffffff" });
  sourceScene.add(new Mesh(sourceGeometry, sourceMaterial));
  const sourceDispose = vi.spyOn(sourceMaterial, "dispose");

  const clonedScene = twin3dModule.cloneSceneWithIndependentMaterials(sourceScene);
  const clonedMaterial = clonedScene.children[0].material;
  const clonedDispose = vi.spyOn(clonedMaterial, "dispose");

  expect(clonedScene).not.toBe(sourceScene);
  expect(clonedMaterial).not.toBe(sourceMaterial);
  twin3dModule.disposeSceneMaterials(clonedScene);
  expect(clonedDispose).toHaveBeenCalledTimes(1);
  expect(sourceDispose).not.toHaveBeenCalled();
  sourceGeometry.dispose();
  sourceMaterial.dispose();
});

it("surfaces an asynchronous GLB resource failure after Suspense settles", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  let state = "pending";
  let failure;
  let settle;
  const pending = new Promise((resolve) => {
    settle = resolve;
  });
  const AsyncRejectingModel = () => {
    if (state === "pending") throw pending;
    throw failure;
  };

  render(
    <TestErrorBoundary>
      <Twin3DCanvas
        snapshot={normalSnapshot}
        loadManifest={() => Promise.resolve(realManifestFixture)}
        Model={AsyncRejectingModel}
      />
    </TestErrorBoundary>,
  );
  await screen.findByLabelText("Modelo 3D do conjunto motor-bomba");

  await act(async () => {
    failure = new Error("asynchronous glb failure");
    state = "failed";
    settle();
    await pending;
  });

  expect(await screen.findByTestId("error-fallback")).toBeVisible();
});
