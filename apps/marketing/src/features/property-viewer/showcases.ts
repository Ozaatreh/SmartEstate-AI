/** Camera framing for a model, in the model's own units (metres) with Y up. */
export interface ViewerCamera {
  /** Home camera position; on narrow screens it is pushed back along the same direction to fit `fitRadius`. */
  position: [number, number, number];
  /** Orbit target: the building's centre at mid-height. */
  target: [number, number, number];
  fov: number;
  /** Half-width (m) of the site that must fit horizontally in the home view (the 30 × 24 m platform's half-diagonal). */
  fitRadius: number;
  minDistance: number;
  maxDistance: number;
  minPolarAngle: number;
  /** Just under the horizon, so the camera never goes below the ground. */
  maxPolarAngle: number;
}

export interface Showcase {
  /** Static file under `public/` (served by Vite / the web server, never inlined as Base64). */
  modelUrl: string;
  /** Still image of the same model: shown while loading and when WebGL isn't available. */
  posterUrl: string;
  /** Always shown with the viewer: what the model is, and what it is not (English and Arabic). */
  notice: { en: string; ar: string };
  camera: ViewerCamera;
}

/** The SmartEstate modern villa (assets/3d/smartestate-villa): framing from its README. */
export const VILLA_CAMERA: ViewerCamera = {
  position: [-27, 10.5, 33],
  target: [0, 3.2, 0],
  fov: 32,
  fitRadius: 19,
  minDistance: 16,
  maxDistance: 65,
  minPolarAngle: 0.15 * Math.PI,
  maxPolarAngle: Math.PI / 2 - 0.1,
};

/**
 * Projects that show the interactive showcase, by public project code. The villa is an original illustrative model:
 * it is not NOVA's actual design (NOVA is fictional demo data), and the notice says so wherever it is shown.
 */
export const SHOWCASES: Record<string, Showcase> = {
  NOVA: {
    modelUrl: "/models/smartestate_modern_villa.glb",
    posterUrl: "/models/smartestate_modern_villa_poster.webp",
    notice: {
      en: "Illustrative concept model — not the actual design of NOVA Residences, which is a fictional demo project.",
      ar: "نموذج تصوّري توضيحي — ليس التصميم الفعلي لمشروع NOVA Residences، وهو مشروع تجريبي وهمي.",
    },
    camera: VILLA_CAMERA,
  },
};
