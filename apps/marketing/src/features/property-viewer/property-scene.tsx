/**
 * The React Three Fiber scene behind <InteractivePropertyViewer>. Loaded lazily (three.js, R3F and Drei are only
 * downloaded once the viewer is near the screen), so it is the module's default export.
 *
 * The building never moves: OrbitControls moves the camera around a fixed target. Pan is disabled so the model stays
 * centred, the polar limit keeps the camera above the ground, and the distance limits keep the building in frame.
 * Rendering is on demand (`frameloop="demand"`): nothing is drawn while the visitor isn't interacting.
 */
import { ContactShadows, Environment, Lightformer, OrbitControls, useGLTF, useProgress } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import * as React from "react";
import { AgXToneMapping, MathUtils, Vector3 } from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import type { ViewerCamera } from "./showcases";

export interface SceneHandle { reset: () => void }

export interface PropertySceneProps {
  url: string;
  label: string;
  camera: ViewerCamera;
  /** Filled with the reset function once the scene is mounted. */
  handle: React.RefObject<SceneHandle | null>;
  onProgress: (pct: number) => void;
  onLoaded: () => void;
}

const RESET_SECONDS = 0.7;
/** One gentle glide into the home view after the model loads (never repeats, never auto-rotates). */
const INTRO_SECONDS = 2.4;
const reducedMotion = () => typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function Model({ url, onLoaded }: { url: string; onLoaded: () => void }) {
  const { scene } = useGLTF(url);
  React.useEffect(onLoaded, [onLoaded]);
  // The GLB is already centred on its footprint with y = 0 at ground level, in metres; it is used as is.
  return <primitive object={scene} />;
}

function Progress({ onProgress }: { onProgress: (pct: number) => void }) {
  const { progress } = useProgress();
  React.useEffect(() => onProgress(Math.round(progress)), [progress, onProgress]);
  return null;
}

/** Camera rig: fits the home view to the canvas's aspect ratio, and eases back to it on reset. */
function Rig({ camera: cfg, handle, ready }: { camera: ViewerCamera; handle: PropertySceneProps["handle"]; ready: boolean }) {
  const get = useThree((s) => s.get);
  const width = useThree((s) => s.size.width);
  const height = useThree((s) => s.size.height);
  const hasControls = useThree((s) => !!s.controls);
  const target = React.useMemo(() => new Vector3(...cfg.target), [cfg.target]);
  const home = React.useMemo(() => {
    // A narrow (portrait) canvas needs the camera further back to keep the whole site in view horizontally.
    const dir = new Vector3(...cfg.position).sub(target);
    const vHalf = MathUtils.degToRad(cfg.fov / 2);
    const hHalf = Math.atan(Math.tan(vHalf) * (width / Math.max(1, height)));
    const fit = cfg.fitRadius / Math.sin(hHalf);
    return target.clone().add(dir.setLength(Math.max(dir.length(), fit)));
  }, [cfg, target, width, height]);
  const maxDistance = Math.max(cfg.maxDistance, home.distanceTo(target) * 1.25);
  const anim = React.useRef<{ t: number; seconds: number; fromPos: Vector3; fromTarget: Vector3 } | null>(null);
  const placed = React.useRef(false);
  const introduced = React.useRef(false);

  React.useLayoutEffect(() => {
    const { camera, controls, invalidate } = get();
    if (!controls || placed.current) return;
    // Start exactly at the home view (once the canvas has its real size).
    placed.current = true;
    camera.position.copy(home);
    (controls as OrbitControlsImpl).target.copy(target);
    (controls as OrbitControlsImpl).update();
    invalidate();
  }, [get, hasControls, home, target]);

  // Intro: start a little further round and back, then ease into the home view. A drag or zoom cancels it at once.
  React.useEffect(() => {
    if (!ready || introduced.current || reducedMotion()) return;
    const { camera, controls, invalidate } = get();
    if (!controls) return;
    introduced.current = true;
    const offset = home.clone().sub(target).applyAxisAngle(new Vector3(0, 1, 0), -0.5).multiplyScalar(1.15);
    offset.y += 2.5;
    camera.position.copy(target).add(offset);
    anim.current = { t: 0, seconds: INTRO_SECONDS, fromPos: camera.position.clone(), fromTarget: target.clone() };
    invalidate();
  }, [ready, get, home, target]);

  React.useImperativeHandle(handle, () => ({
    reset: () => {
      const { camera, controls, invalidate } = get();
      if (!controls) return;
      anim.current = { t: 0, seconds: RESET_SECONDS, fromPos: camera.position.clone(), fromTarget: (controls as OrbitControlsImpl).target.clone() };
      invalidate();
    },
  }), [get]);

  useFrame((state, dt) => {
    const a = anim.current;
    const controls = state.controls as OrbitControlsImpl | null;
    if (!a || !controls) return;
    a.t = Math.min(1, a.t + Math.min(dt, 0.05) / a.seconds);
    const k = a.seconds === RESET_SECONDS ? 1 - Math.pow(1 - a.t, 3) : 1 - Math.pow(1 - a.t, 4); // ease-out
    state.camera.position.lerpVectors(a.fromPos, home, k);
    controls.target.lerpVectors(a.fromTarget, target, k);
    controls.update();
    if (a.t >= 1) anim.current = null;
    state.invalidate();
  });

  return (
    <OrbitControls makeDefault target={cfg.target} enableDamping dampingFactor={0.08} rotateSpeed={0.6} zoomSpeed={1}
      enablePan={false} minDistance={cfg.minDistance} maxDistance={maxDistance}
      minPolarAngle={cfg.minPolarAngle} maxPolarAngle={cfg.maxPolarAngle}
      onStart={() => { anim.current = null; }} />
  );
}

export default function PropertyScene({ url, label, camera, handle, onProgress, onLoaded }: PropertySceneProps) {
  const [ready, setReady] = React.useState(false);
  const loaded = React.useCallback(() => { setReady(true); onLoaded(); }, [onLoaded]);
  return (
    <Canvas frameloop="demand" dpr={[1, 1.75]} aria-label={label} role="img"
      camera={{ position: camera.position, fov: camera.fov, near: 0.5, far: 400 }}
      gl={{ antialias: true, alpha: true, toneMapping: AgXToneMapping, powerPreference: "high-performance" }}
      className="touch-none">
      {/* Studio lighting: a soft sky/ground fill, one key light, and a local light-former environment for
          reflections on the glass and aluminium (no HDR file is downloaded). */}
      <hemisphereLight args={["#dfe6f5", "#1d1e22", 0.7]} />
      <directionalLight position={[-22, 26, 26]} intensity={2.3} color="#fff4e6" />
      <directionalLight position={[24, 14, -20]} intensity={0.6} color="#cfdcff" />
      <Environment resolution={128} environmentIntensity={0.45}>
        <Lightformer form="rect" intensity={2.5} position={[0, 12, 10]} scale={[30, 8, 1]} />
        <Lightformer form="rect" intensity={1.2} position={[-20, 6, -6]} rotation-y={Math.PI / 2} scale={[24, 6, 1]} />
        <Lightformer form="rect" intensity={0.8} position={[20, 4, -10]} rotation-y={-Math.PI / 2} scale={[20, 4, 1]} color="#bcd0ff" />
      </Environment>
      <React.Suspense fallback={<Progress onProgress={onProgress} />}>
        <Model url={url} onLoaded={loaded} />
        {/* The model is static, so the contact shadow is rendered once (frames=1) rather than every frame. */}
        <ContactShadows position={[0, 0.003, 0]} scale={48} far={12} blur={2.6} opacity={0.65} frames={1} resolution={1024} />
      </React.Suspense>
      <Rig camera={camera} handle={handle} ready={ready} />
    </Canvas>
  );
}

