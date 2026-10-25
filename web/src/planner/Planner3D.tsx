// 3D view of the plan (pochta src/features/view3d/View3DCanvas.tsx, cut to what /planner
// needs). A separate chunk: Three.js loads only when the user opens the 3D tab.
// Axes go straight into the world: X right, Y up on the plan, Z is height.
import { useEffect, useRef, useState } from "react";
import {
  BoxGeometry,
  Box3,
  Color,
  DirectionalLight,
  EdgesGeometry,
  ExtrudeGeometry,
  Group,
  HemisphereLight,
  LineBasicMaterial,
  LineSegments,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  type Object3D,
  PerspectiveCamera,
  PlaneGeometry,
  CanvasTexture,
  SRGBColorSpace,
  Scene as ThreeScene,
  Shape,
  Sprite,
  SpriteMaterial,
  type Texture,
  TextureLoader,
  Vector2,
  Vector3,
  WebGLRenderer,
} from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { refKey } from "./findings";
import type { Finding } from "./model";
import { modelFit, screenRect, type ModelPlace } from "./models";
import type { Prism, Scene, WallLine } from "./scene";
import { SEVERITY_COLOR } from "./colors";
import styles from "./planner.module.css";

type Props = { scene: Scene; highlight: Map<string, Finding["severity"]> };

const ORBIT_FOV = 50;

const BACKGROUND = "#F4F6F8";
const EDGE_COLOR = "#343A40";
/** A wall in front of the camera is a hint of glass, not a screen. */
const FADED_WALL_OPACITY = 0.12;

function wallLine(polygon: Prism["polygon"]): WallLine {
  let best = { dx: 1, dy: 0, length: 0 };
  polygon.forEach(([x, y], i) => {
    const [nx, ny] = polygon[(i + 1) % polygon.length]!;
    const length = Math.hypot(nx - x, ny - y);
    if (length > best.length) best = { dx: nx - x, dy: ny - y, length };
  });
  const cx = polygon.reduce((sum, [x]) => sum + x, 0) / polygon.length;
  const cy = polygon.reduce((sum, [, y]) => sum + y, 0) / polygon.length;
  return { cx, cy, nx: -best.dy / best.length, ny: best.dx / best.length };
}

/**
 * Dollhouse view (pochta fadeWalls): a wall between the camera and the point it
 * orbits around turns to glass, so the room is seen through it; its edges stay.
 */
function fadeWalls(group: Group, camera: Vector3, target: Vector3): void {
  for (const child of group.children) {
    const line = child.userData["wallLine"] as WallLine | undefined;
    if (!line || !(child instanceof Mesh || child instanceof LineSegments)) continue;
    const side = (x: number, y: number) => (x - line.cx) * line.nx + (y - line.cy) * line.ny;
    const across = side(camera.x, camera.y) * side(target.x, target.y) < 0;
    const material = child.material as MeshStandardMaterial | LineBasicMaterial;
    if (material.transparent === across) continue;
    material.transparent = across;
    material.opacity = across ? (child instanceof Mesh ? FADED_WALL_OPACITY : FADED_WALL_OPACITY / 2) : 1;
    material.depthWrite = !across;
    material.needsUpdate = true;
  }
}

function prismMeshes(prism: Prism, color: string): (Mesh | LineSegments)[] {
  if (prism.polygon.length < 3) return [];
  const geometry = new ExtrudeGeometry(new Shape(prism.polygon.map(([x, y]) => new Vector2(x, y))), {
    depth: Math.max(prism.height_m, 0.001),
    bevelEnabled: false,
  });
  const mesh = new Mesh(
    geometry,
    new MeshStandardMaterial({
      color,
      roughness: prism.kind === "object" ? 0.5 : 0.9,
      transparent: prism.opacity < 1,
      opacity: prism.opacity,
    }),
  );
  mesh.position.z = prism.base_m;
  mesh.name = refKey(prism.ref);
  if (prism.kind === "zone") mesh.userData["zone"] = true;
  if (prism.kind === "wall") mesh.userData["wallLine"] = prism.wallLine ?? wallLine(prism.polygon);
  if (prism.kind !== "object" || prism.plain) return [mesh];
  // Edges help read the volumes; 30° keeps a round column from 24 vertical stripes.
  const edges = new LineSegments(new EdgesGeometry(geometry, 30), new LineBasicMaterial({ color: EDGE_COLOR }));
  edges.position.z = prism.base_m;
  edges.userData["wallLine"] = mesh.userData["wallLine"];
  return [mesh, edges];
}

const models = new Map<string, Promise<Object3D>>();

function loadModel(file: string): Promise<Object3D> {
  let pending = models.get(file);
  if (!pending) {
    pending = new GLTFLoader().loadAsync(file).then((gltf) => gltf.scene);
    // A failed file may load on the next scene fill.
    pending.catch(() => models.delete(file));
    models.set(file, pending);
  }
  return pending;
}

/** A stand under a model below the top of its plan box: a showcase or a podium (#396). */
const STAND_COLOR = "#F1F3F5";

/** The model in plan axes (Z up), in the plan box, at real size or fitted into the box (#354, #396). */
async function placeModel(place: ModelPlace): Promise<Group> {
  // Clones share geometry and materials with the cached file: clearGroup must not dispose them.
  const model = (await loadModel(place.file)).clone(true);
  // Files are Y-up (glTF); the plan scene is Z-up.
  model.rotation.x = Math.PI / 2;
  const holder = new Group();
  holder.add(model);
  holder.updateMatrixWorld(true);
  const box = new Box3().setFromObject(holder);
  const size = box.getSize(new Vector3());
  const center = box.getCenter(new Vector3());
  model.position.set(-center.x, -center.y, -box.min.z);
  const { scale, lift_m } = modelFit(place, [size.x, size.y, size.z]);
  holder.scale.setScalar(scale);
  holder.position.z = lift_m;
  const placed = new Group();
  placed.add(holder);
  // Less than 2 cm is a gap of the model export, not a stand.
  if (lift_m > 0.02) {
    const stand = new Mesh(new BoxGeometry(place.size_m[0], place.size_m[1], lift_m), new MeshStandardMaterial({ color: STAND_COLOR }));
    stand.position.z = lift_m / 2;
    stand.userData["stand"] = true;
    placed.add(stand);
  }
  placed.rotation.z = (-place.rotation_deg * Math.PI) / 180;
  placed.position.set(place.center[0], place.center[1], place.base_m);
  placed.userData["model"] = true;
  return placed;
}

const pictures = new Map<string, Promise<Texture>>();

function loadPicture(file: string): Promise<Texture> {
  let pending = pictures.get(file);
  if (!pending) {
    pending = new TextureLoader().loadAsync(file).then((texture) => {
      texture.colorSpace = SRGBColorSpace;
      return texture;
    });
    pending.catch(() => pictures.delete(file));
    pictures.set(file, pending);
  }
  return pending;
}

/** A render on both long faces of a wall panel or screen (#369); the box stays as its frame. */
async function placeScreen(place: ModelPlace): Promise<Group> {
  const texture = await loadPicture(place.file);
  const image = texture.image as { width?: number; height?: number } | undefined;
  const aspect = image?.width && image.height ? image.width / image.height : 16 / 9;
  const rect = screenRect(place, aspect);
  const placed = new Group();
  for (const side of [1, -1]) {
    // Unlit: a screen glows, the side of the hall away from the sun must not darken it.
    const plane = new Mesh(new PlaneGeometry(rect.width, rect.height), new MeshBasicMaterial({ map: texture, toneMapped: false }));
    // The plane stands up (its Y becomes Z) and faces out of the long face.
    plane.rotation.set(Math.PI / 2, rect.alongX ? (side > 0 ? 0 : Math.PI) : (side > 0 ? Math.PI / 2 : -Math.PI / 2), 0, "ZXY");
    if (rect.alongX) plane.position.set(0, -side * rect.offset, rect.centerZ);
    else plane.position.set(side * rect.offset, 0, rect.centerZ);
    placed.add(plane);
  }
  placed.rotation.z = (-place.rotation_deg * Math.PI) / 180;
  placed.position.set(place.center[0], place.center[1], 0);
  placed.userData["screen"] = true;
  return placed;
}

/** Label height in metres (#444). */
const LABEL_HEIGHT_M = 0.45;
/** A label shows only when the camera is this close: the whole-hall view stays clean. */
const LABEL_RANGE_M = 20;
const LABEL_FONT_PX = 40;
const LABEL_PAD_PX = 14;
/** Over the top of the plan box, metres. */
const LABEL_GAP_M = 0.35;

/** Labels near the camera show, far ones hide. */
function showNearLabels(group: Group, camera: Vector3): void {
  for (const child of group.children) {
    if (child.userData["label"]) child.visible = child.position.distanceTo(camera) < LABEL_RANGE_M;
  }
}

/** The exhibit name over its model: dark text on a white plate (#444). */
function labelSprite(prism: Prism, text: string): Sprite | null {
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  // No 2D canvas (a test browser): the hall stays without labels.
  if (!context) return null;
  const font = `600 ${LABEL_FONT_PX}px system-ui, sans-serif`;
  context.font = font;
  const width = Math.ceil(context.measureText(text).width) + LABEL_PAD_PX * 2;
  const height = LABEL_FONT_PX + LABEL_PAD_PX * 2;
  canvas.width = width;
  canvas.height = height;
  context.fillStyle = "rgba(255, 255, 255, 0.92)";
  context.strokeStyle = "#CED4DA";
  context.lineWidth = 2;
  context.beginPath();
  context.roundRect(1, 1, width - 2, height - 2, height / 2);
  context.fill();
  context.stroke();
  context.font = font;
  context.fillStyle = "#212529";
  context.textBaseline = "middle";
  context.fillText(text, LABEL_PAD_PX, height / 2 + 2);
  const texture = new CanvasTexture(canvas);
  texture.colorSpace = SRGBColorSpace;
  const sprite = new Sprite(new SpriteMaterial({ map: texture, toneMapped: false }));
  sprite.scale.set((LABEL_HEIGHT_M * width) / height, LABEL_HEIGHT_M, 1);
  sprite.center.set(0.5, 0);
  const cx = prism.polygon.reduce((sum, [x]) => sum + x, 0) / prism.polygon.length;
  const cy = prism.polygon.reduce((sum, [, y]) => sum + y, 0) / prism.polygon.length;
  sprite.position.set(cx, cy, prism.base_m + prism.height_m + LABEL_GAP_M);
  sprite.userData["label"] = true;
  return sprite;
}

function clearGroup(group: Group): void {
  for (const child of [...group.children]) {
    if (child instanceof Sprite) {
      child.material.map?.dispose();
      child.material.dispose();
    }
    if (child instanceof Mesh || child instanceof LineSegments) {
      child.geometry.dispose();
      (child.material as MeshStandardMaterial | LineBasicMaterial).dispose();
    }
    // Picture planes are own per fill; their texture is shared through the cache and stays.
    if (child.userData["screen"] || child.userData["model"]) {
      child.traverse((part) => {
        // Model meshes are shared through the cache; only stands and pictures are own.
        if (!(part instanceof Mesh) || (child.userData["model"] && !part.userData["stand"])) return;
        part.geometry.dispose();
        (part.material as MeshBasicMaterial).dispose();
      });
    }
    group.remove(child);
  }
}

type Stage = {
  renderer: WebGLRenderer;
  camera: PerspectiveCamera;
  controls: OrbitControls;
  group: Group;
  render: () => void;
  /** Counts scene fills: a model that loads after a newer fill is dropped. */
  fill: number;
};

function createStage(host: HTMLDivElement): Stage {
  const renderer = new WebGLRenderer({ antialias: true });
  // A phone has a small screen and a weak GPU: 1.5 pixels per point keeps the view smooth.
  const coarse = window.matchMedia?.("(pointer: coarse)").matches ?? false;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, coarse ? 1.5 : 2));
  renderer.domElement.dataset["testid"] = "planner-3d-canvas";
  host.appendChild(renderer.domElement);
  const world = new ThreeScene();
  world.background = new Color(BACKGROUND);
  const camera = new PerspectiveCamera(ORBIT_FOV, 1, 0.1, 500);
  camera.up.set(0, 0, 1);
  const sun = new DirectionalLight("#FFF6E8", 1.8);
  sun.position.set(-6, -10, 14);
  world.add(new HemisphereLight("#FFFFFF", "#B0B8C0", 1.3), sun);
  const group = new Group();
  world.add(group);
  const controls = new OrbitControls(camera, renderer.domElement);
  // The camera stays above the floor: from below, the plan is a grey slab.
  controls.maxPolarAngle = Math.PI / 2 - 0.05;
  const stage: Stage = {
    renderer,
    camera,
    controls,
    group,
    fill: 0,
    render: () => {
      fadeWalls(group, camera.position, controls.target);
      showNearLabels(group, camera.position);
      renderer.render(world, camera);
    },
  };
  // Rendering is on demand: one frame per camera change, no loop.
  controls.addEventListener("change", stage.render);
  return stage;
}

function resize(stage: Stage, host: HTMLDivElement): void {
  const width = Math.max(1, host.clientWidth);
  const height = Math.max(1, host.clientHeight);
  stage.renderer.setSize(width, height, false);
  stage.camera.aspect = width / height;
  stage.camera.updateProjectionMatrix();
}

/** Three-quarter view from the south side; the whole room fits at any aspect ratio. */
function frame(stage: Stage, scene: Scene): void {
  const { minX, minY, maxX, maxY } = scene.bounds;
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  const radius = Math.hypot(maxX - minX, maxY - minY, scene.ceilingHeight_m) / 2;
  const vertical = (stage.camera.fov * Math.PI) / 180;
  const horizontal = 2 * Math.atan(Math.tan(vertical / 2) * stage.camera.aspect);
  stage.controls.target.set(cx, cy, 0);
  if (stage.camera.aspect < 1) {
    frameUpright(stage, scene, cx, cy);
    return;
  }
  const distance = (radius / Math.sin(Math.min(vertical, horizontal) / 2)) * 1.05;
  stage.camera.position.set(cx, cy - distance * 0.8, distance * 0.6);
  stage.controls.update();
}

/** Above the horizon on an upright screen, degrees: the long side of the hall runs up the screen. */
const UPRIGHT_ELEVATION_DEG = 58;

/**
 * Upright phone (#369): from the south the hall was a 150 px band in a 650 px canvas. The camera
 * looks from the east and high, so the long side of the hall runs up the screen, and comes as
 * close as the corners of the hall allow.
 */
function frameUpright(stage: Stage, scene: Scene, cx: number, cy: number): void {
  const { minX, minY, maxX, maxY } = scene.bounds;
  const corners = [minX, maxX].flatMap((x) =>
    [minY, maxY].flatMap((y) => [0, scene.ceilingHeight_m].map((z) => new Vector3(x, y, z))),
  );
  const e = (UPRIGHT_ELEVATION_DEG * Math.PI) / 180;
  const place = (distance: number) => {
    stage.camera.position.set(cx + distance * Math.cos(e), cy, distance * Math.sin(e));
    stage.camera.lookAt(cx, cy, 0);
    stage.camera.updateMatrixWorld(true);
  };
  const fits = (distance: number) => {
    place(distance);
    return corners.every((c) => {
      const p = c.clone().project(stage.camera);
      return p.z < 1 && Math.abs(p.x) <= 0.96 && Math.abs(p.y) <= 0.96;
    });
  };
  let near = 1;
  let far = 400;
  for (let i = 0; i < 30; i++) {
    const mid = (near + far) / 2;
    if (fits(mid)) far = mid;
    else near = mid;
  }
  place(far);
  stage.controls.update();
}

export default function Planner3D({ scene, highlight }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const stage = useRef<Stage | null>(null);
  const framed = useRef(false);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let created: Stage;
    try {
      created = createStage(element);
    } catch (e) {
      setFailure(`3D недоступен: браузер не дал WebGL (${String(e)})`);
      return;
    }
    stage.current = created;
    const observer = new ResizeObserver(() => {
      resize(created, element);
      if (!framed.current && created.group.children.length > 0) {
        frame(created, scene);
        framed.current = true;
      }
      created.render();
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
      created.controls.dispose();
      clearGroup(created.group);
      created.renderer.dispose();
      created.renderer.domElement.remove();
      stage.current = null;
      framed.current = false;
    };
    // The stage lives as long as the tab; scene changes refill it below.
  }, []);

  useEffect(() => {
    const current = stage.current;
    if (!current) return;
    clearGroup(current.group);
    const fill = ++current.fill;
    const canvas = current.renderer.domElement;
    // How many models replaced their boxes: e2e reads it, the visitor does not see it.
    canvas.dataset["models"] = "0";
    canvas.dataset["screens"] = "0";
    for (const prism of scene.prisms) {
      const severity = highlight.get(refKey(prism.ref));
      const color = prism.kind !== "floor" && severity ? SEVERITY_COLOR[severity] : prism.color;
      const box = prismMeshes(prism, color);
      current.group.add(...box);
      const label = prism.label ? labelSprite(prism, prism.label) : null;
      if (label) current.group.add(label);
      if (prism.screen) {
        const screen = prism.screen;
        placeScreen(screen).then(
          (group) => {
            if (stage.current !== current || current.fill !== fill) return;
            current.group.add(group);
            canvas.dataset["screens"] = String(Number(canvas.dataset["screens"] ?? 0) + 1);
            current.render();
          },
          (e: unknown) => console.warn(`Картинка ${screen.file} не загрузилась, панель остаётся без неё`, e),
        );
      }
      // An object with a finding stays a coloured box: the model would hide the finding.
      if (!prism.model || severity) continue;
      placeModel(prism.model).then(
        (model) => {
          // A newer fill or a closed page: this model belongs to nothing.
          if (stage.current !== current || current.fill !== fill) return;
          // A fenced model keeps its glass box as the fence (#444).
          if (!prism.model?.fenced) for (const part of box) part.visible = false;
          current.group.add(model);
          canvas.dataset["models"] = String(Number(canvas.dataset["models"] ?? 0) + 1);
          current.render();
        },
        (e: unknown) => console.warn(`3D-модель ${prism.model?.file} не загрузилась, остаётся коробка`, e),
      );
    }
    // A moved partition must not yank the camera the user has just placed.
    if (!framed.current && host.current && host.current.clientWidth > 0) {
      resize(current, host.current);
      frame(current, scene);
      framed.current = true;
    }
    current.render();
  }, [scene, highlight]);

  return (
    <div
      className={styles.view3d}
      ref={host}
      aria-label="План в 3D: перетаскивание вращает, колесо приближает"
    >
      {failure && (
        <p className={styles.notice} role="alert">
          {failure}
        </p>
      )}
    </div>
  );
}
