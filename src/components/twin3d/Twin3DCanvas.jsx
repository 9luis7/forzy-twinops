import React, { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { Bounds, Html, OrbitControls, useGLTF } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import LoadingState from "../LoadingState.jsx";
import { parseModelManifest } from "./modelManifest.js";
import { buildTwinViewModel } from "./twinViewModel.js";


const MANIFEST_URL = "/models/conjunto-motor-bomba.manifest.json";
const MANIFEST_LOADING_MESSAGES = [
  "Lendo o manifesto do conjunto…",
  "Validando a geometria fornecida…",
  "Preparando materiais e iluminação…",
];
const GLB_LOADING_MESSAGES = [
  "Carregando a malha do conjunto…",
  "Preparando materiais do modelo…",
  "Ajustando a visualização interativa…",
];

export async function loadModelManifest({ signal } = {}) {
  const response = await fetch(MANIFEST_URL, { signal });
  if (!response.ok) throw new Error(`Twin 3D manifest request failed: ${response.status}`);
  return response.json();
}

export function cloneSceneWithIndependentMaterials(scene) {
  const clone = scene.clone(true);
  clone.traverse((node) => {
    if (!node.isMesh) return;
    node.material = Array.isArray(node.material)
      ? node.material.map((material) => material.clone())
      : node.material.clone();
    node.castShadow = true;
    node.receiveShadow = true;
  });
  return clone;
}

function visitMaterials(scene, visitor) {
  scene.traverse((node) => {
    if (!node.isMesh) return;
    const materials = Array.isArray(node.material) ? node.material : [node.material];
    materials.forEach(visitor);
  });
}

export function applyViewModelToSceneMaterials(scene, viewModel) {
  visitMaterials(scene, (material) => {
    material.color?.set(viewModel.materialColor);
    material.emissive?.set(viewModel.emissiveColor);
    if ("emissiveIntensity" in material) {
      material.emissiveIntensity = viewModel.emissiveIntensity;
    }
    if ("metalness" in material) material.metalness = 0.18;
    if ("roughness" in material) material.roughness = 0.72;
    material.needsUpdate = true;
  });
}

export function disposeSceneMaterials(scene) {
  visitMaterials(scene, (material) => material.dispose());
}

export function TwinModel({ modelUrl, viewModel }) {
  const gltf = useGLTF(modelUrl);
  const model = useMemo(() => cloneSceneWithIndependentMaterials(gltf.scene), [gltf.scene]);

  useEffect(() => {
    applyViewModelToSceneMaterials(model, viewModel);
  }, [model, viewModel.emissiveColor, viewModel.emissiveIntensity, viewModel.materialColor]);

  useEffect(
    () => () => {
      disposeSceneMaterials(model);
    },
    [model],
  );

  return <primitive object={model} />;
}

function ModelLoadingOverlay() {
  return (
    <Html fullscreen>
      <LoadingState
        label="Carregando a malha 3D real…"
        messages={GLB_LOADING_MESSAGES}
        variant="canvas"
      />
    </Html>
  );
}

function ModelReadySignal({ children, onReady }) {
  useEffect(() => {
    onReady();
  }, [onReady]);

  return children;
}

export default function Twin3DCanvas({
  snapshot,
  loadManifest = loadModelManifest,
  Model = TwinModel,
}) {
  const [manifest, setManifest] = useState(null);
  const [error, setError] = useState(null);
  const [modelReady, setModelReady] = useState(false);
  const markModelReady = useCallback(() => setModelReady(true), []);

  useEffect(() => {
    const controller = new AbortController();
    Promise.resolve()
      .then(() => loadManifest({ signal: controller.signal }))
      .then(parseModelManifest)
      .then(setManifest)
      .catch((reason) => {
        if (reason?.name !== "AbortError") setError(reason);
      });
    return () => controller.abort();
  }, [loadManifest]);

  if (error) throw error;
  if (!manifest) {
    return (
      <LoadingState
        label="Preparando a geometria do conjunto…"
        messages={MANIFEST_LOADING_MESSAGES}
        variant="twin"
      />
    );
  }

  const viewModel = buildTwinViewModel({ snapshot });
  return (
    <section
      className="card"
      data-model-ready={String(modelReady)}
      data-testid="twin3d-canvas"
      data-status={viewModel.status}
      aria-label="Modelo 3D do conjunto motor-bomba"
    >
      <div style={{ height: "min(60vh, 32rem)", minHeight: "22rem" }}>
        <Canvas dpr={[1, 1.5]} shadows>
          <ambientLight intensity={1.4} />
          <directionalLight position={[3, 5, 4]} intensity={2.2} castShadow />
          <directionalLight position={[-4, 2, -3]} intensity={0.7} />
          <Suspense fallback={<ModelLoadingOverlay />}>
            <Bounds fit clip observe margin={1.2} maxDuration={0.01}>
              <ModelReadySignal onReady={markModelReady}>
                <Model modelUrl={manifest.modelUrl} viewModel={viewModel} />
              </ModelReadySignal>
            </Bounds>
          </Suspense>
          <OrbitControls makeDefault enableDamping={false} enablePan={false} />
        </Canvas>
      </div>
      <p className="muted small">
        Geometria derivada do STEP fornecido. Rotação e zoom são apenas controles de visualização.
      </p>
    </section>
  );
}
