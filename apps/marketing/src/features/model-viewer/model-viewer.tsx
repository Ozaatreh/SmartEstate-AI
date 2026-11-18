/**
 * Interactive glTF viewer (three.js). Loaded lazily — three.js is only downloaded when a visitor opens a model.
 * Orbit (drag), zoom (wheel / pinch / buttons) and reset; loading progress, load errors and missing WebGL are shown.
 * Only same-origin model URLs from the public API are loaded.
 */
import { Minus, Plus, RotateCcw } from "lucide-react";
import * as React from "react";
import {
  AmbientLight, Box3, Color, DirectionalLight, HemisphereLight, type Material, type Mesh, type Object3D, PerspectiveCamera, Scene,
  SRGBColorSpace, type Texture, Vector3, WebGLRenderer,
} from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { useI18n } from "@/lib/i18n";
import { ViewerOverlay, type ViewerStatus } from "./viewer-overlay";
import { hasWebGL } from "./webgl";

function dispose(root: Object3D) {
  root.traverse((o) => {
    const mesh = o as Mesh;
    mesh.geometry?.dispose();
    const mats = (Array.isArray(mesh.material) ? mesh.material : mesh.material ? [mesh.material] : []) as Material[];
    for (const m of mats) {
      for (const v of Object.values(m)) if (v && typeof v === "object" && (v as Texture).isTexture) (v as Texture).dispose();
      m.dispose();
    }
  });
}

export default function ModelViewer({ url, title }: { url: string; title: string }) {
  const host = React.useRef<HTMLDivElement>(null);
  const { t } = useI18n();
  const label = t(`Interactive 3D model: ${title}. Drag to rotate, scroll or pinch to zoom.`, `نموذج تفاعلي ثلاثي الأبعاد: ${title}. اسحب للتدوير، ومرّر أو باعد بإصبعين للتكبير.`);
  const labelRef = React.useRef(label);
  React.useEffect(() => {
    labelRef.current = label;
    host.current?.querySelector("canvas")?.setAttribute("aria-label", label);
  }, [label]);
  const api = React.useRef<{ reset: () => void; zoom: (f: number) => void } | null>(null);
  const allowed = url.startsWith("/api/v1/public/models/");
  const [status, setStatus] = React.useState<ViewerStatus>(() => (!hasWebGL() ? "unsupported" : allowed ? "loading" : "error"));
  const [progress, setProgress] = React.useState<number | null>(null);
  const [attempt, setAttempt] = React.useState(0);

  React.useEffect(() => {
    const el = host.current;
    if (!el || !allowed || status === "unsupported") return;
    let cancelled = false;
    const renderer = new WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = SRGBColorSpace;
    renderer.domElement.setAttribute("role", "img");
    renderer.domElement.setAttribute("aria-label", labelRef.current);
    renderer.domElement.className = "block size-full touch-none";
    el.appendChild(renderer.domElement);

    const scene = new Scene();
    scene.background = new Color("#eceae4");
    scene.add(new HemisphereLight(0xffffff, 0xb8b2a6, 1.4), new AmbientLight(0xffffff, 0.35));
    const sun = new DirectionalLight(0xffffff, 1.6);
    sun.position.set(5, 10, 7);
    scene.add(sun);
    const camera = new PerspectiveCamera(45, 1, 0.01, 10_000);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.screenSpacePanning = true;
    const home = { position: new Vector3(3, 2, 3), target: new Vector3() };

    const resize = () => {
      const { width, height } = el.getBoundingClientRect();
      if (!width || !height) return;
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    resize();
    renderer.setAnimationLoop(() => {
      controls.update();
      renderer.render(scene, camera);
    });

    const reset = () => {
      camera.position.copy(home.position);
      controls.target.copy(home.target);
      controls.update();
    };
    api.current = {
      reset,
      zoom: (f) => {
        const offset = camera.position.clone().sub(controls.target).multiplyScalar(f);
        const len = Math.min(Math.max(offset.length(), controls.minDistance), controls.maxDistance);
        camera.position.copy(controls.target).add(offset.setLength(len));
        controls.update();
      },
    };

    let model: Object3D | null = null;
    new GLTFLoader().load(
      url,
      (gltf) => {
        if (cancelled) return dispose(gltf.scene);
        model = gltf.scene;
        scene.add(model);
        // Frame the model: centre it and place the camera so the whole bounding sphere is visible.
        const box = new Box3().setFromObject(model);
        const size = box.getSize(new Vector3()).length() || 1;
        const center = box.getCenter(new Vector3());
        // Fit the bounding sphere (radius size/2) in the narrower field of view, with a 20% margin.
        const vHalf = (camera.fov * Math.PI) / 360;
        const hHalf = Math.atan(Math.tan(vHalf) * camera.aspect);
        const dist = ((size / 2) / Math.sin(Math.min(vHalf, hHalf))) * 1.2;
        home.target.copy(center);
        home.position.copy(center).add(new Vector3(0.9, 0.55, 0.9).normalize().multiplyScalar(dist));
        camera.near = size / 1000;
        camera.far = size * 100;
        camera.updateProjectionMatrix();
        controls.minDistance = size * 0.05;
        controls.maxDistance = size * 10;
        reset();
        setStatus("ready");
      },
      (e) => { if (!cancelled && e.lengthComputable) setProgress(Math.round((e.loaded / e.total) * 100)); },
      () => { if (!cancelled) setStatus("error"); },
    );

    return () => {
      cancelled = true;
      api.current = null;
      ro.disconnect();
      renderer.setAnimationLoop(null);
      controls.dispose();
      if (model) dispose(model);
      renderer.dispose();
      renderer.domElement.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `status` is read once to skip setup; re-running on it would reload the model
  }, [url, title, attempt, allowed]);

  return (
    <div className="relative aspect-[4/3] w-full overflow-hidden rounded-[var(--radius-control)] border border-border bg-[#eceae4] sm:aspect-video">
      <div ref={host} className="absolute inset-0" />
      <ViewerOverlay status={status} progress={progress}
        onRetry={() => { setProgress(null); setStatus("loading"); setAttempt((n) => n + 1); }} />
      {status === "ready" && (
        <div className="absolute bottom-3 end-3 flex gap-1.5" role="toolbar" aria-label={t("3D view controls", "عناصر التحكم بالعرض ثلاثي الأبعاد")}>
          <ViewButton label={t("Zoom in", "تكبير")} onClick={() => api.current?.zoom(0.8)}><Plus /></ViewButton>
          <ViewButton label={t("Zoom out", "تصغير")} onClick={() => api.current?.zoom(1.25)}><Minus /></ViewButton>
          <ViewButton label={t("Reset view", "إعادة ضبط العرض")} onClick={() => api.current?.reset()}><RotateCcw /></ViewButton>
        </div>
      )}
    </div>
  );
}

function ViewButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} aria-label={label} title={label}
      className="grid size-10 place-items-center rounded-full border border-border bg-surface/95 text-fg shadow-sm transition-colors hover:bg-surface [&_svg]:size-4">
      {children}
    </button>
  );
}
