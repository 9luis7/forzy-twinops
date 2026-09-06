import React, { Suspense, useEffect, useMemo, useState } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import { Bounds, Html, OrbitControls, useBounds, useGLTF } from "@react-three/drei";
import { Box3, Vector3 } from "three";
import { applyDemoMaterials, meshGroup, parseDemoModelManifest } from "./demoModel.js";
import DemoSensorMarker from "./DemoSensorMarker.jsx";

function cloneMaterials(scene) {
  const model = scene.clone(true);
  model.traverse((node) => {
    if (!node.isMesh) return;
    node.material = Array.isArray(node.material) ? node.material.map((m) => m.clone()) : node.material.clone();
  });
  return model;
}

function DemoModel({ manifest, snapshot, selected, isolate, focus, onSelect, onReady }) {
  const { scene } = useGLTF(manifest.modelUrl);
  const model = useMemo(() => cloneMaterials(scene), [scene]);
  const bounds = useBounds();
  const size = useThree((state) => state.size);
  useEffect(() => { applyDemoMaterials(model, manifest, snapshot, { selected, isolate }); }, [model, manifest, snapshot, selected, isolate]);
  useEffect(() => {
    model.updateMatrixWorld(true);
    const box = new Box3();
    const group = selected === "s1" ? "motor" : selected === "s2" ? "pump" : null;
    model.traverse((node) => {
      if (node.isMesh && (!focus.selected || !group || meshGroup(manifest, node) === group)) box.expandByObject(node);
    });
    if (!box.isEmpty()) {
      bounds.refresh(box);
      const { center, distance } = bounds.getSize();
      const position = center.clone().addScaledVector(new Vector3(1.15, 0.9, 1.2).normalize(), distance);
      bounds.moveTo(position).lookAt({ target: center }).clip();
    }
  }, [model, manifest, bounds, focus, size.width, size.height]);
  useEffect(() => { onReady(true); return () => { model.traverse((n) => { if (n.isMesh) (Array.isArray(n.material) ? n.material : [n.material]).forEach((m) => m.dispose()); }); }; }, [model, onReady]);
  return <primitive object={model} onClick={(event) => { event.stopPropagation(); const group = meshGroup(manifest, event.object); if (group === "motor" || group === "pump") onSelect(group === "motor" ? "s1" : "s2"); }} />;
}

export default function DemoTwin3DCanvas({ snapshot, selectedSensor = "all", onSelectSensor = () => {} }) {
  const [manifest, setManifest] = useState(null), [error, setError] = useState(null), [ready, setReady] = useState(false);
  const [isolate, setIsolate] = useState(false), [focus, setFocus] = useState({ selected: false, count: 0 });
  useEffect(() => {
    const controller = new AbortController();
    fetch("/models/conjunto-motor-bomba.demo.manifest.json", { signal: controller.signal })
      .then((r) => { if (!r.ok) throw new Error("Manifesto indisponível"); return r.json(); })
      .then(parseDemoModelManifest).then((m) => { if (!controller.signal.aborted) setManifest(m); })
      .catch((e) => { if (e.name !== "AbortError") setError(e); });
    return () => controller.abort();
  }, []);
  if (error) throw error;
  if (!manifest) return <p role="status">Preparando geometria e posições assumidas…</p>;
  return <section aria-label="Modelo 3D do conjunto motor-bomba" data-model-ready={String(ready)} data-revision={snapshot.revision}>
    <div className="demo-model-controls"><button className="secondary-button" aria-pressed={selectedSensor === "s1"} onClick={() => onSelectSensor("s1")}>S1 · Motor</button><button className="secondary-button" aria-pressed={selectedSensor === "s2"} onClick={() => onSelectSensor("s2")}>S2 · Bomba</button><button className="secondary-button" disabled={selectedSensor === "all"} onClick={() => setFocus({ selected: true, count: focus.count + 1 })}>Focar seleção</button><button className="secondary-button" disabled={selectedSensor === "all"} aria-pressed={isolate} onClick={() => setIsolate(!isolate)}>Isolar</button><button className="secondary-button" onClick={() => { setIsolate(false); onSelectSensor("all"); setFocus({ selected: false, count: focus.count + 1 }); }}>Restaurar visão</button></div>
    <div className="demo-canvas-viewport" style={{ height: "min(56vh, 32rem)", minHeight: "23rem" }}>
      <Canvas dpr={[1, 1.5]} camera={{ position: [73.1, 1.35, 20.1], near: 0.01, far: 300 }}>
        <ambientLight intensity={1.1} /><directionalLight position={[73, 4, 22]} intensity={2.2} /><directionalLight position={[70, 2, 16]} intensity={0.7} />
        <Suspense fallback={<Html center><span>Carregando conjunto CAD…</span></Html>}>
          <Bounds fit clip margin={1.3} maxDuration={0.3}>
            <DemoModel manifest={manifest} snapshot={snapshot} selected={selectedSensor} isolate={isolate} focus={focus} onSelect={onSelectSensor} onReady={setReady} />
          </Bounds>
          {manifest.sensors.map((sensor) => {
            const data = snapshot.sensors[sensor.sensorId];
            const hidden = isolate && selectedSensor !== "all" && selectedSensor !== sensor.sensorId;
            return <Html key={sensor.sensorId} position={sensor.position} center zIndexRange={[20, 0]} style={{ visibility: hidden ? "hidden" : "visible" }}>
              <DemoSensorMarker sensor={sensor} data={data} onSelect={onSelectSensor} />
            </Html>;
          })}
        </Suspense>
        <OrbitControls makeDefault enableDamping={false} target={[71.935, 0.4, 18.865]} />
      </Canvas>
    </div>
    <p className="small muted">Arraste para girar · role para aproximar · selecione um componente ou marcador. Motor azul, bomba verde; brilho e marcadores indicam a condição.</p>
  </section>;
}
