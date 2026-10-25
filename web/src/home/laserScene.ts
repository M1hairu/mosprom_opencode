// Hero scene of the start page: a galvo laser head engraves the LASSARD logo on a steel plate,
// the logo glows, then a laser-cleaning sweep wipes the plate and the cycle repeats. An
// illustration of LASSARD machines: the showroom itself has no beam (D-001). Only the Home
// chunk imports this module.
import * as THREE from "three";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { ShaderPass } from "three/examples/jsm/postprocessing/ShaderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import machineUrl from "./laser-machine.glb?url";
import logoSvg from "../ui/logo-lassard.svg?raw";
import { beamAt, buildToolpath, parseLogo, type Pt } from "./toolpath";
import { Trail } from "./trail";

export type LaserScene = {
  /** 0 at the top of the page, 1 when the hero has scrolled out. */
  setScroll(p: number): void;
  /** Pointer in -1..1 for parallax. */
  setPointer(x: number, y: number): void;
  /** Mouse over the canvas in NDC: over the plate the beam follows it and burns a trail. */
  setAim(x: number, y: number, active: boolean): void;
  setPaused(paused: boolean): void;
  dispose(): void;
};

export type SceneOptions = {
  /** Draw one still frame (prefers-reduced-motion). */
  still?: boolean;
  /** Cycle time of the still frame, s (wraps over the cycle); default — the glowing logo. */
  stillAt?: number;
  onFirstFrame?(): void;
  /** The WebGL context is lost: the canvas shows nothing until a reload. */
  onLost?(): void;
};

const RED = new THREE.Color("#dd191c");
// Studio colours: background (and fog), floor, pedestal.
const STUDIO = { bg: "#f7f8fa", floor: "#eff1f4", pedestal: "#ffffff" };
// Logo on the plate: width in world units and the SVG viewBox it comes from.
const LOGO_W = 1.36;
const VIEW_W = 232.95;
const VIEW_H = 56.79;
const S = LOGO_W / VIEW_W;
const toWorld = ([x, y]: Pt): [number, number] => [(x - VIEW_W / 2) * S, (y - VIEW_H / 2) * S];
// Lens exit of the head above the plate. The head rides a gantry; the beam goes straight down.
const LENS_Y = 0.3;
// Gantry: rails along z at the plate sides, a bridge along x behind the head.
const RAIL_X = 1.06;
const BRIDGE_DZ = -0.27;
const BRIDGE_Y = LENS_Y + 0.5;
// Head parks here while the logo glows, so nothing hides it.
const PARK = new THREE.Vector3(0, LENS_Y, -0.42);
// Hatch step of the fill, SVG units; the marks are this wide so the fill reads solid.
const HATCH = 2.0;
// Cycle: engrave → glow → laser cleaning → rest.
const HOLD = 3.2;
const CLEAN = 2.6;
// Long enough for the gantry to drive back to the start of the toolpath.
const REST = 1.4;
// Brightest light box of the studio environment (see the room setup).
const ENV_LIGHT_CAP = 5;
// Cube size of the environment map (the PMREMGenerator default).
const ENV_SIZE = 256;

// Private fields of three's PMREMGenerator (r186): its blur and GGX materials, made per size.
type PmremInternals = {
  _setSize?(cubeSize: number): void;
  _allocateTargets?(): THREE.WebGLRenderTarget;
  _pingPongRenderTarget?: THREE.WebGLRenderTarget | null;
  _blurMaterial?: THREE.Material | null;
  _ggxMaterial?: THREE.Material | null;
};

export function startLaserScene(canvas: HTMLCanvasElement, opts: SceneOptions = {}): LaserScene {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: "high-performance", alpha: false });
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.setClearColor("#eceef2");
  // The error check reads LINK_STATUS right after linkProgram and waits for the driver (#372).
  renderer.debug.checkShaderErrors = import.meta.env.DEV;
  // A phone (coarse pointer) starts at 1.5× and may drop to 1×: its GPU is weaker than a laptop's.
  // On a laptop the floor stays at 1.5×: below it the scene looks pixelated.
  const coarse = window.matchMedia?.("(pointer: coarse)").matches ?? false;
  let dpr = Math.min(window.devicePixelRatio || 1, coarse ? 1.5 : 2);
  const minDpr = Math.min(dpr, coarse ? 1 : 1.5);
  renderer.setPixelRatio(dpr);

  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog("#eceef2", 6, 14);
  const pmrem = new THREE.PMREMGenerator(renderer);
  const room = new RoomEnvironment();
  // Its light boxes glow at 17–100: the metal plate and head mirror them far above the bloom
  // threshold, a white wash over the left of the plate. Capped, they stay soft highlights; the
  // higher environment intensity keeps the studio as light as before.
  room.traverse((o) => {
    const m = (o as THREE.Mesh).material;
    if (m instanceof THREE.MeshLambertMaterial) m.emissiveIntensity = Math.min(m.emissiveIntensity, ENV_LIGHT_CAP);
  });
  // Made before the first frame by makeEnvironment(), once its shaders are linked.
  let envTex: THREE.Texture | null = null;
  scene.environmentIntensity = 0.9;

  const camera = new THREE.PerspectiveCamera(34, 1, 0.05, 30);
  const target = new THREE.Vector3(0, 0.3, 0);

  // ---------- lights
  const key = new THREE.DirectionalLight("#ffffff", 1.2);
  key.position.set(-2.5, 3.5, 2);
  scene.add(key);
  const rim = new THREE.DirectionalLight(RED, 0.7);
  rim.position.set(2.5, 1.5, -2.5);
  scene.add(rim);
  const fill = new THREE.PointLight("#ffffff", 0.4, 2.5, 1.5);
  fill.position.set(0.6, 1.5, 0.9);
  scene.add(fill);
  const spot = new THREE.PointLight("#ff3a22", 0, 2.6, 1.6);
  scene.add(spot);

  // ---------- plate, pedestal, floor
  const brushed = brushedTexture();
  brushed.anisotropy = renderer.capabilities.getMaxAnisotropy();
  const plateMat = new THREE.MeshPhysicalMaterial({
    color: "#b4b8c0",
    metalness: 1,
    roughness: 0.3,
    roughnessMap: brushed,
    anisotropy: 0.7,
    anisotropyRotation: 0,
    clearcoat: 0.25,
    clearcoatRoughness: 0.4,
  });
  const plate = new THREE.Mesh(new RoundedBoxGeometry(1.8, 0.05, 1.05, 3, 0.012), plateMat);
  plate.position.y = -0.025;
  scene.add(plate);
  const pedestal = new THREE.Mesh(
    new RoundedBoxGeometry(2.2, 0.5, 1.45, 3, 0.03),
    new THREE.MeshStandardMaterial({ color: "#f4f5f7", metalness: 0.05, roughness: 0.55 }),
  );
  pedestal.position.y = -0.3;
  scene.add(pedestal);
  // Red edge line of the pedestal: the brand stripe.
  const stripe = new THREE.Mesh(new THREE.BoxGeometry(2.202, 0.012, 1.452), new THREE.MeshBasicMaterial({ color: new THREE.Color(RED).multiplyScalar(2.2) }));
  stripe.position.y = -0.09;
  scene.add(stripe);
  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(30, 30),
    new THREE.MeshStandardMaterial({ color: "#e4e6ea", metalness: 0, roughness: 0.9 }),
  );
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -0.55;
  scene.add(floor);
  renderer.setClearColor(STUDIO.bg);
  (scene.fog as THREE.Fog).color.set(STUDIO.bg);
  (floor.material as THREE.MeshStandardMaterial).color.set(STUDIO.floor);
  (pedestal.material as THREE.MeshStandardMaterial).color.set(STUDIO.pedestal);

  // ---------- head: procedural until a GLB is given, then swapped in
  const head = new THREE.Group();
  head.position.copy(PARK);
  scene.add(head);
  const gantry = gantryParts();
  scene.add(gantry.root);
  head.add(proceduralHead());
  // Blender model of the whole machine (web/scripts/laser-machine.blender.py), scene units:
  // Frame stays, Bridge rides z, Head (origin at the lens exit) rides x/z. The primitives are
  // the first frame and stay if the model does not load.
  new GLTFLoader().load(
    machineUrl,
    (gltf) => {
      if (disposed) return;
      const frameNode = gltf.scene.getObjectByName("Frame");
      const bridgeNode = gltf.scene.getObjectByName("Bridge");
      const headNode = gltf.scene.getObjectByName("Head");
      if (!frameNode || !bridgeNode || !headNode) {
        console.warn("hero: в модели станка нет узлов Frame/Bridge/Head, остаётся упрощённая");
        return;
      }
      const drop = (o: THREE.Object3D) => {
        o.removeFromParent();
        o.traverse((x) => {
          const m = x as THREE.Mesh;
          m.geometry?.dispose();
          const mat = m.material as THREE.Material | THREE.Material[] | undefined;
          (Array.isArray(mat) ? mat : mat ? [mat] : []).forEach((y) => y.dispose());
        });
      };
      // Its materials compile in parallel before the swap: a first draw would link them on the spot.
      environmentReady()
        .then(() => (disposed ? undefined : precompile(gltf.scene)))
        .then(() => {
          if (disposed) return;
          drop(gantry.root);
          head.children.slice().forEach(drop);
          headNode.position.set(0, 0, 0);
          head.add(headNode);
          gantry.root = new THREE.Group();
          gantry.root.add(frameNode, bridgeNode);
          scene.add(gantry.root);
          gantry.bridge = bridgeNode;
          // The carriage is part of Head now: it follows the head with no extra motion.
          gantry.carriage = new THREE.Object3D();
          // A still frame was drawn with the primitives: draw it again.
          if (opts.still && firstFrame && !lost) {
            cancelAnimationFrame(raf);
            raf = requestAnimationFrame(frame);
          }
        });
    },
    undefined,
    (e) => console.warn("hero: модель станка не загрузилась, остаётся упрощённая", e),
  );

  // ---------- engraving marks: quads on the plate, shown by the clock in the shader
  // Speeds a gantry can show: outline, hatch and jumps in SVG units per second.
  const tp = buildToolpath(parseLogo(logoSvg), HATCH, { mark: 520, hatch: 1000, jump: 700 });
  const [startX, startZ] = toWorld(tp.moves[0].a);
  const marks = markGeometry(tp.moves);
  const markMat = new THREE.ShaderMaterial({
    uniforms: { uClock: { value: 0 }, uWipe: { value: -10 }, uGlow: { value: 0 }, uTime: { value: 0 } },
    vertexShader: /* glsl */ `
      attribute float aT;
      varying float vT; varying vec3 vW;
      void main() {
        vT = aT;
        vec4 w = modelMatrix * vec4(position, 1.0);
        vW = w.xyz;
        gl_Position = projectionMatrix * viewMatrix * w;
      }`,
    fragmentShader: /* glsl */ `
      uniform float uClock; uniform float uWipe; uniform float uGlow; uniform float uTime;
      varying float vT; varying vec3 vW;
      void main() {
        if (vT > uClock || vW.z < uWipe) discard;
        float age = uClock - vT;
        float heat = exp(-age * 2.4);
        vec3 hot = mix(vec3(1.0, 0.18, 0.05), vec3(1.0, 0.85, 0.6), heat * heat) * (0.6 + 4.0 * heat) * heat;
        vec3 burn = vec3(0.045, 0.012, 0.014);
        float shimmer = 0.85 + 0.15 * sin(uTime * 3.0 + vW.x * 6.0);
        vec3 glow = vec3(1.1, 0.08, 0.08) * uGlow * shimmer;
        // Edge of the cleaning sweep heats the mark once more before it disappears.
        float edge = smoothstep(0.08, 0.0, vW.z - uWipe) * step(-5.0, uWipe);
        gl_FragColor = vec4(burn + hot + glow + vec3(1.0, 0.3, 0.1) * edge * 2.0, 1.0);
      }`,
    side: THREE.DoubleSide,
    polygonOffset: true,
    polygonOffsetFactor: -2,
    polygonOffsetUnits: -2,
  });
  const markMesh = new THREE.Mesh(marks, markMat);
  markMesh.position.y = 0.0012;
  scene.add(markMesh);

  // ---------- beam: a thin steady core and a faint halo, straight down from the lens
  const beamCore = beamMesh(0.0032, new THREE.Color(3.2, 0.3, 0.2), 1.2);
  const beamHalo = beamMesh(0.008, new THREE.Color(1.1, 0.05, 0.04), 2.2);
  scene.add(beamCore, beamHalo);

  // Spot glow at the contact point.
  const glowTex = radialTexture();
  const spotGlow = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: new THREE.Color(1.3, 0.32, 0.18), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
  spotGlow.scale.setScalar(0.05);
  scene.add(spotGlow);
  // Lens glow.
  const lensGlow = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: new THREE.Color(2.5, 0.2, 0.15), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
  lensGlow.scale.setScalar(0.06);
  scene.add(lensGlow);

  // ---------- sparks: streaks with gravity and a bounce off the plate
  const sparks = new Sparks(900);
  scene.add(sparks.mesh);
  const trail = new Trail();
  scene.add(trail.mesh);
  // ---------- dust in the air
  const dust = dustPoints(140, glowTex);
  scene.add(dust);

  // ---------- post: bloom, then vignette + grain, then tone mapping
  // MSAA in the HDR target: the composer bypasses the canvas antialiasing. The sample count
  // comes from what the GPU supports for RGBA16F (an unsupported count gives a black frame);
  // 2 samples on 2× screens and on phones keep the memory and the GPU in check.
  const composer = new EffectComposer(renderer, new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples: msaaSamples(renderer, coarse || dpr >= 2 ? 2 : 4) }));
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.3, 0.35, 1.6);
  composer.addPass(bloom);
  const finish = new ShaderPass({
    uniforms: { tDiffuse: { value: null }, uTime: { value: 0 } },
    vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
    fragmentShader: /* glsl */ `
      uniform sampler2D tDiffuse; uniform float uTime; varying vec2 vUv;
      float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
      void main(){
        vec4 c = texture2D(tDiffuse, vUv);
        float v = smoothstep(1.15, 0.25, length(vUv - 0.5) * 1.35);
        c.rgb *= mix(0.86, 1.0, v);
        c.rgb += (hash(vUv * 900.0 + fract(uTime) * 37.0) - 0.5) * 0.006;
        gl_FragColor = c;
      }`,
  });
  composer.addPass(finish);
  composer.addPass(new OutputPass());

  // ---------- shaders: linked in parallel (KHR_parallel_shader_compile) before the first frame.
  // Linked on first use, they froze phones for 1.5–2.5 s right after the page appeared (#372).
  const flat = new THREE.OrthographicCamera();
  /**
   * Compiles the materials of obj for the target they are drawn to, with the lights and the
   * environment of `lit` (obj itself when null): the same programs as the real frame.
   */
  function compileFor(obj: THREE.Object3D, cam: THREE.Camera, target: THREE.WebGLRenderTarget | null, lit: THREE.Scene | null = null): Promise<unknown> {
    renderer.setRenderTarget(target);
    const done = renderer.compileAsync(obj, cam, lit).catch(() => undefined);
    renderer.setRenderTarget(null);
    return done;
  }
  /** Scene materials, drawn by the RenderPass into the HDR target. */
  const precompile = (obj: THREE.Object3D) => compileFor(obj, camera, composer.readBuffer, obj === scene ? null : scene);
  /**
   * Meshes for materials of full-screen passes: compile() needs objects, not materials. The
   * position attribute is part of the program key: without it the real draw links a new program.
   */
  const quads = (materials: (THREE.Material | null | undefined)[]) => {
    const group = new THREE.Scene();
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(9, 3));
    for (const m of materials) if (m) group.add(new THREE.Mesh(geometry, m));
    return group;
  };
  // PMREM links its blur and GGX shaders on first use; the GGX one alone took ~1 s. They are
  // private: made here at the size fromScene uses, fromScene then reuses them already linked.
  async function makeEnvironment(): Promise<void> {
    const p = pmrem as unknown as PmremInternals;
    if (p._setSize && p._allocateTargets) {
      p._setSize(ENV_SIZE);
      p._allocateTargets().dispose();
      const target = p._pingPongRenderTarget ?? null;
      await Promise.all([compileFor(quads([p._blurMaterial, p._ggxMaterial]), flat, target), compileFor(room, flat, target)]);
    }
    if (disposed) return;
    envTex = pmrem.fromScene(room, 0.04, 0.1, 100, { size: ENV_SIZE }).texture;
    scene.environment = envTex;
  }
  // Made once: the scene and the machine model compile with it (the program key depends on it).
  let environment: Promise<void> | null = null;
  function environmentReady(): Promise<void> {
    return (environment ??= makeEnvironment());
  }
  async function warmUp(): Promise<void> {
    await environmentReady();
    if (disposed) return;
    const passes = [bloom.materialHighPassFilter, ...bloom.separableBlurMaterials, bloom.compositeMaterial, bloom.blendMaterial, finish.material];
    await Promise.all([precompile(scene), compileFor(quads(passes), flat, composer.readBuffer)]);
  }

  // ---------- layout
  let fullW = 1;
  // Narrow screens: the camera steps back so the whole logo fits the width.
  let far = 1;
  let fullH = 1;
  const resize = () => {
    const w = canvas.clientWidth || 1;
    const h = canvas.clientHeight || 1;
    if (w === fullW && h === fullH) return;
    fullW = w;
    fullH = h;
    renderer.setSize(w, h, false);
    composer.setSize(w, h);
    composer.setPixelRatio(dpr);
    bloom.resolution.set(w, h);
    camera.aspect = w / h;
    // Wide screens: the plate sits right of the text. Narrow: below the text.
    const wide = w / h > 1.15;
    camera.fov = wide ? 34 : 60;
    far = wide ? 1 : 1.55;
    if (wide) camera.setViewOffset(w, h, -w * 0.22, -h * 0.1, w, h);
    else camera.setViewOffset(w, h, 0, -h * 0.3, w, h);
    camera.updateProjectionMatrix();
    // A resize clears the drawing buffer: a still frame must be drawn again.
    if (opts.still && firstFrame && !lost) raf = requestAnimationFrame(frame);
  };

  // ---------- animation state
  let scroll = 0;
  const pointer = new THREE.Vector2();
  const pointerSmooth = new THREE.Vector2();
  let paused = false;
  let lost = false;
  let disposed = false;
  let raf = 0;
  let last = performance.now();
  let t = 0;
  let firstFrame = false;
  // True once the shaders are linked and the first frame may run.
  let warm = false;
  let slowFrames = 0;
  const cycle = tp.duration + HOLD + CLEAN + REST;
  const spotPos = new THREE.Vector3();
  const prevSpot = new THREE.Vector3();
  const headGoal = new THREE.Vector3();
  const lensPos = new THREE.Vector3();
  const headFrom = new THREE.Vector3();
  // Manual mode: the mouse over the plate takes the beam; the cycle clock waits.
  const raycaster = new THREE.Raycaster();
  const platePlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  const aimNdc = new THREE.Vector2();
  const aimHit = new THREE.Vector3();
  let aimActive = false;
  let onPlate = false;
  let manualUntil = -1;
  let wasManual = false;
  let cycleT = 0;

  const frame = (now: number) => {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    t += dt;
    // Adaptive quality: lower the pixel ratio when frames are slow.
    if (dt > 1 / 40) slowFrames++;
    else slowFrames = Math.max(0, slowFrames - 1);
    if (slowFrames > 90 && dpr > minDpr) {
      dpr = Math.max(minDpr, dpr - 0.25);
      renderer.setPixelRatio(dpr);
      composer.setPixelRatio(dpr);
      slowFrames = 0;
    }
    onPlate = false;
    if (aimActive && !opts.still) {
      raycaster.setFromCamera(aimNdc, camera);
      if (raycaster.ray.intersectPlane(platePlane, aimHit) && Math.abs(aimHit.x) < 0.88 && Math.abs(aimHit.z) < 0.5) {
        onPlate = true;
        manualUntil = t + 1.2;
      }
    }
    const manual = t < manualUntil;
    if (!manual) cycleT += dt;
    step(opts.still ? (opts.stillAt ?? tp.duration + 1.2) % cycle : cycleT % cycle, dt, manual);
    composer.render(dt);
    if (!firstFrame) {
      firstFrame = true;
      opts.onFirstFrame?.();
    }
    if (!opts.still && !paused && !lost) raf = requestAnimationFrame(frame);
  };

  const step = (c: number, dt: number, manual = false) => {
    const time = t;
    markMat.uniforms.uTime.value = time;
    finish.uniforms.uTime.value = time;
    let beamOn = false;
    let cleaning = false;
    let exact = false;
    let wipe = -10;
    let glow = 0;
    if (c < tp.duration) {
      // Engraving: the head follows the toolpath exactly; the beam marks under it.
      const b = beamAt(tp, c);
      const [x, z] = toWorld(b.p);
      headGoal.set(x, LENS_Y, z);
      exact = true;
      beamOn = b.on;
      markMat.uniforms.uClock.value = c;
    } else if (c < tp.duration + HOLD) {
      const k = (c - tp.duration) / HOLD;
      markMat.uniforms.uClock.value = c;
      glow = Math.min(1, k * 3) * (1.6 + 0.4 * Math.sin(time * 4));
      headGoal.copy(PARK);
    } else if (c < tp.duration + HOLD + CLEAN) {
      // Laser cleaning: the head zigzags along x and moves to the front; the logo goes behind it.
      const k = (c - tp.duration - HOLD) / CLEAN;
      const tri = 2 * Math.abs(((k * 6) % 2) - 1) - 1;
      headGoal.set(tri * 0.76, LENS_Y, -0.24 + k * 0.48);
      // From the raster, not the head: the mouse may take the head during cleaning.
      wipe = -0.24 + k * 0.48 - 0.04;
      glow = 1.6 * (1 - k * 0.5);
      beamOn = k > 0.04;
      cleaning = true;
      markMat.uniforms.uClock.value = c;
    } else {
      markMat.uniforms.uClock.value = -1; // plate is clean
      headGoal.set(startX, LENS_Y, startZ);
    }
    if (manual) {
      // The mouse takes the gantry: the head follows with a little inertia and burns a trail.
      if (onPlate) headGoal.set(aimHit.x, LENS_Y, aimHit.z);
      exact = false;
      cleaning = false;
    }
    headFrom.copy(head.position);
    if (exact || opts.still) head.position.copy(headGoal);
    else head.position.lerp(headGoal, 1 - Math.exp(-dt * (manual ? 10 : cleaning ? 16 : 5)));
    // Manual: the beam fires only once the head has reached the mouse, so no line is burnt
    // from the logo to the pointer.
    if (manual) beamOn = onPlate && (wasManual || head.position.distanceTo(headGoal) < 0.02);
    if (manual && beamOn) trail.add(headFrom.x, headFrom.z, head.position.x, head.position.z, time);
    wasManual = manual && beamOn;
    gantry.bridge.position.z = head.position.z + BRIDGE_DZ;
    gantry.carriage.position.x = head.position.x;
    spotPos.set(head.position.x, 0.002, head.position.z);
    trail.setClock(time);
    markMat.uniforms.uWipe.value = wipe;
    markMat.uniforms.uGlow.value = glow;

    const shimmer = 0.96 + 0.04 * Math.sin(time * 47);
    lensPos.set(head.position.x, LENS_Y, head.position.z);
    placeBeam(beamCore, lensPos, spotPos, beamOn ? shimmer : 0);
    placeBeam(beamHalo, lensPos, spotPos, beamOn ? 0.5 * shimmer : 0);
    spotGlow.position.copy(spotPos);
    spotGlow.material.opacity = beamOn ? 1 : 0;
    lensGlow.position.set(head.position.x, LENS_Y - 0.004, head.position.z);
    lensGlow.material.opacity = beamOn ? 0.8 : 0.15;
    spot.position.copy(spotPos);
    spot.position.y += 0.06;
    spot.intensity = beamOn ? 0.1 : glow * 0.08;
    if (!beamOn && glow > 0) spot.position.set(0, 0.12, 0);

    // Sparks fly from the spot while the beam works.
    if (beamOn && !opts.still) {
      for (let k = 0; k < (cleaning ? 8 : 6); k++) sparks.spawn(spotPos, prevSpot, cleaning ? 0.6 : 1);
    }
    prevSpot.copy(spotPos);
    sparks.update(opts.still ? 0 : dt);
    (dust.material as THREE.ShaderMaterial).uniforms.uTime.value = time;

    // Camera: slow drift, pointer parallax, scroll pushes in and down.
    pointerSmooth.lerp(pointer, 1 - Math.exp(-dt * 3));
    const drift = Math.sin(time * 0.12) * 0.12;
    camera.position.set(
      drift + pointerSmooth.x * 0.28,
      (1.9 + pointerSmooth.y * 0.1 - scroll * 0.4) * far,
      (3.3 - scroll * 0.8) * far,
    );
    target.set(pointerSmooth.x * 0.05, 0.26 - scroll * 0.15, -0.05);
    camera.lookAt(target);
  };

  const ro = new ResizeObserver(resize);
  ro.observe(canvas);
  resize();
  // No restore: the page falls back to the CSS backdrop until a reload.
  const onLost = () => {
    cancelAnimationFrame(raf);
    lost = true;
    opts.onLost?.();
  };
  canvas.addEventListener("webglcontextlost", onLost);
  warmUp()
    .catch((e) => console.warn("hero: шейдеры не прогрелись заранее", e))
    .then(() => {
      warm = true;
      if (disposed || lost || paused) return;
      last = performance.now();
      raf = requestAnimationFrame(frame);
    });

  return {
    setScroll(p) {
      scroll = Math.min(1, Math.max(0, p));
    },
    setPointer(x, y) {
      pointer.set(x, y);
    },
    setAim(x, y, active) {
      aimNdc.set(x, y);
      aimActive = active;
    },
    setPaused(p) {
      if (p === paused || lost) return;
      paused = p;
      // Before the warm-up ends the loop is not running: the warm-up starts it.
      if (!warm) return;
      if (!p && !opts.still) {
        last = performance.now();
        raf = requestAnimationFrame(frame);
      } else cancelAnimationFrame(raf);
    },
    dispose() {
      disposed = true;
      cancelAnimationFrame(raf);
      ro.disconnect();
      canvas.removeEventListener("webglcontextlost", onLost);
      scene.traverse((o) => {
        const m = o as THREE.Mesh;
        m.geometry?.dispose();
        const mat = m.material as THREE.Material | THREE.Material[] | undefined;
        (Array.isArray(mat) ? mat : mat ? [mat] : []).forEach((x) => x.dispose());
      });
      brushed.dispose();
      glowTex.dispose();
      envTex?.dispose();
      pmrem.dispose();
      room.traverse((o) => {
        const m = o as THREE.Mesh;
        m.geometry?.dispose();
        (m.material as THREE.Material | undefined)?.dispose?.();
      });
      // composer.dispose() frees only its own targets: the passes free theirs.
      for (const pass of composer.passes) pass.dispose();
      composer.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
    },
  };
}

// ---------------------------------------------------------------- helpers

/** Largest MSAA sample count ≤ want that the GPU renders for RGBA16F; 0 — no MSAA. */
function msaaSamples(renderer: THREE.WebGLRenderer, want: number): number {
  try {
    const gl = renderer.getContext() as WebGL2RenderingContext;
    if (!gl.getExtension("EXT_color_buffer_float")) return 0;
    const counts = gl.getInternalformatParameter(gl.RENDERBUFFER, gl.RGBA16F, gl.SAMPLES) as Int32Array | null;
    return Math.max(0, ...Array.from(counts ?? []).filter((n) => n <= want));
  } catch {
    return 0;
  }
}

/** Quads along each marking move; aT = the time the beam passes each vertex. */
function markGeometry(moves: ReturnType<typeof buildToolpath>["moves"]): THREE.BufferGeometry {
  const pos: number[] = [];
  const at: number[] = [];
  const idx: number[] = [];
  for (const m of moves) {
    if (!m.on) continue;
    const [ax, az] = toWorld(m.a);
    const [bx, bz] = toWorld(m.b);
    const len = Math.hypot(bx - ax, bz - az);
    if (len < 1e-6) continue;
    // Hatch lines overlap a little to read as a solid fill; outlines are a thin crisp line.
    const w = (m.hatch ? HATCH * 1.2 : 0.7) * S * 0.5;
    const nx = (-(bz - az) / len) * w;
    const nz = ((bx - ax) / len) * w;
    // Extend a bit along the move so joints have no gaps.
    const ex = ((bx - ax) / len) * w * 0.6;
    const ez = ((bz - az) / len) * w * 0.6;
    const base = pos.length / 3;
    pos.push(ax - ex + nx, 0, az - ez + nz, ax - ex - nx, 0, az - ez - nz, bx + ex - nx, 0, bz + ez - nz, bx + ex + nx, 0, bz + ez + nz);
    at.push(m.t0, m.t0, m.t1, m.t1);
    idx.push(base, base + 1, base + 2, base, base + 2, base + 3);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("aT", new THREE.Float32BufferAttribute(at, 1));
  g.setIndex(idx);
  return g;
}

function beamMesh(radius: number, color: THREE.Color, sharp: number): THREE.Mesh {
  const geo = new THREE.CylinderGeometry(1, 1, 1, 20, 1, true);
  geo.translate(0, 0.5, 0);
  const mat = new THREE.ShaderMaterial({
    uniforms: { uColor: { value: color }, uI: { value: 0 }, uSharp: { value: sharp } },
    vertexShader: /* glsl */ `
      varying vec3 vN; varying vec3 vV; varying float vY;
      void main(){
        vY = position.y;
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        vN = normalize(normalMatrix * normal);
        vV = normalize(-mv.xyz);
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: /* glsl */ `
      uniform vec3 uColor; uniform float uI; uniform float uSharp;
      varying vec3 vN; varying vec3 vV; varying float vY;
      void main(){
        float f = pow(abs(dot(normalize(vN), normalize(vV))), uSharp);
        float ends = smoothstep(0.0, 0.04, vY) * smoothstep(1.0, 0.97, vY);
        // Normal blending: on the light studio an additive red would burn out to white.
        gl_FragColor = vec4(uColor, clamp(f * uI * ends, 0.0, 1.0));
      }`,
    blending: THREE.NormalBlending,
    depthWrite: false,
    transparent: true,
  });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.userData.radius = radius;
  mesh.frustumCulled = false;
  return mesh;
}

const UP = new THREE.Vector3(0, 1, 0);
const tmpDir = new THREE.Vector3();
function placeBeam(mesh: THREE.Mesh, from: THREE.Vector3, to: THREE.Vector3, intensity: number) {
  // The cylinder grows from the spot up to the lens.
  tmpDir.subVectors(from, to);
  const len = tmpDir.length();
  mesh.position.copy(to);
  mesh.quaternion.setFromUnitVectors(UP, tmpDir.normalize());
  const r = mesh.userData.radius as number;
  mesh.scale.set(r, len, r);
  (mesh.material as THREE.ShaderMaterial).uniforms.uI.value = intensity;
  mesh.visible = intensity > 0;
}

class Sparks {
  mesh: THREE.LineSegments;
  private pos: Float32Array;
  private vel: Float32Array;
  private life: Float32Array;
  private max: Float32Array;
  private heat: Float32Array;
  private next = 0;
  constructor(private n: number) {
    this.pos = new Float32Array(n * 3);
    this.vel = new Float32Array(n * 3);
    this.life = new Float32Array(n);
    this.max = new Float32Array(n).fill(1);
    this.heat = new Float32Array(n * 2);
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(n * 6), 3).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute("aHeat", new THREE.BufferAttribute(this.heat, 1).setUsage(THREE.DynamicDrawUsage));
    const mat = new THREE.ShaderMaterial({
      vertexShader: `attribute float aHeat; varying float vH; void main(){ vH = aHeat; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
      fragmentShader: /* glsl */ `
        varying float vH;
        void main(){
          if (vH <= 0.0) discard;
          vec3 c = mix(vec3(1.2, 0.08, 0.03), vec3(4.0, 2.2, 1.2), vH * vH);
          gl_FragColor = vec4(c * vH * 2.2, 1.0);
        }`,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      transparent: true,
    });
    this.mesh = new THREE.LineSegments(g, mat);
    this.mesh.frustumCulled = false;
  }
  spawn(at: THREE.Vector3, prev: THREE.Vector3, power: number) {
    const i = this.next;
    this.next = (this.next + 1) % this.n;
    // Start somewhere between the last and the current spot so fast moves leave no gaps.
    const k = Math.random();
    this.pos[i * 3] = prev.x + (at.x - prev.x) * k;
    this.pos[i * 3 + 1] = 0.004;
    this.pos[i * 3 + 2] = prev.z + (at.z - prev.z) * k;
    const a = Math.random() * Math.PI * 2;
    const up = 0.35 + Math.random() * 0.9;
    const sp = (0.4 + Math.random() * 1.8) * power;
    this.vel[i * 3] = Math.cos(a) * sp * 0.7;
    this.vel[i * 3 + 1] = up * sp + 0.2;
    this.vel[i * 3 + 2] = Math.sin(a) * sp * 0.7;
    this.max[i] = 0.25 + Math.random() * 0.6;
    this.life[i] = this.max[i];
  }
  update(dt: number) {
    const p = this.mesh.geometry.attributes.position as THREE.BufferAttribute;
    const arr = p.array as Float32Array;
    for (let i = 0; i < this.n; i++) {
      if (this.life[i] <= 0) {
        this.heat[i * 2] = this.heat[i * 2 + 1] = 0;
        continue;
      }
      this.life[i] -= dt;
      const j = i * 3;
      this.vel[j + 1] -= 3.6 * dt;
      this.vel[j] *= 1 - 0.6 * dt;
      this.vel[j + 2] *= 1 - 0.6 * dt;
      this.pos[j] += this.vel[j] * dt;
      this.pos[j + 1] += this.vel[j + 1] * dt;
      this.pos[j + 2] += this.vel[j + 2] * dt;
      if (this.pos[j + 1] < 0.002 && Math.abs(this.pos[j]) < 0.9 && Math.abs(this.pos[j + 2]) < 0.52) {
        this.pos[j + 1] = 0.002;
        this.vel[j + 1] *= -0.38;
        this.vel[j] *= 0.7;
        this.vel[j + 2] *= 0.7;
      }
      const h = Math.max(0, this.life[i] / this.max[i]);
      // Streak: from the spark back along its velocity.
      const tail = 0.018;
      arr[i * 6] = this.pos[j];
      arr[i * 6 + 1] = this.pos[j + 1];
      arr[i * 6 + 2] = this.pos[j + 2];
      arr[i * 6 + 3] = this.pos[j] - this.vel[j] * tail;
      arr[i * 6 + 4] = this.pos[j + 1] - this.vel[j + 1] * tail;
      arr[i * 6 + 5] = this.pos[j + 2] - this.vel[j + 2] * tail;
      this.heat[i * 2] = h;
      this.heat[i * 2 + 1] = h * 0.4;
    }
    p.needsUpdate = true;
    this.mesh.geometry.attributes.aHeat.needsUpdate = true;
  }
}

function dustPoints(n: number, tex: THREE.Texture): THREE.Points {
  const pos = new Float32Array(n * 3);
  const seed = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    pos[i * 3] = (Math.random() - 0.5) * 4.5;
    pos[i * 3 + 1] = Math.random() * 2.2 - 0.3;
    pos[i * 3 + 2] = (Math.random() - 0.5) * 3.5;
    seed[i] = Math.random() * 100;
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setAttribute("aSeed", new THREE.BufferAttribute(seed, 1));
  const mat = new THREE.ShaderMaterial({
    uniforms: { uTime: { value: 0 }, uTex: { value: tex } },
    vertexShader: /* glsl */ `
      uniform float uTime; attribute float aSeed; varying float vA;
      void main(){
        vec3 p = position;
        p.x += sin(uTime * 0.15 + aSeed) * 0.15;
        p.y += mod(uTime * 0.03 + aSeed * 0.1, 2.2) - 1.1 + 0.6;
        p.z += cos(uTime * 0.11 + aSeed * 1.3) * 0.12;
        vec4 mv = modelViewMatrix * vec4(p, 1.0);
        gl_PointSize = (1.5 + fract(aSeed) * 3.5) * (2.4 / -mv.z);
        vA = 0.25 + 0.75 * fract(aSeed * 7.13);
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: /* glsl */ `
      uniform sampler2D uTex; varying float vA;
      void main(){ vec4 t = texture2D(uTex, gl_PointCoord); gl_FragColor = vec4(vec3(0.9, 0.45, 0.42) * t.a * vA * 0.5, 1.0); }`,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    transparent: true,
  });
  const pts = new THREE.Points(g, mat);
  pts.frustumCulled = false;
  return pts;
}

function radialTexture(): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const g = c.getContext("2d")!;
  const grd = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  grd.addColorStop(0, "rgba(255,255,255,1)");
  grd.addColorStop(0.15, "rgba(255,255,255,0.6)");
  grd.addColorStop(0.45, "rgba(255,255,255,0.12)");
  grd.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grd;
  g.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(c);
}

/** Roughness map of brushed steel: fine horizontal streaks. */
function brushedTexture(): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 1024;
  c.height = 512;
  const g = c.getContext("2d")!;
  g.fillStyle = "rgb(150,150,150)";
  g.fillRect(0, 0, c.width, c.height);
  for (let i = 0; i < 2600; i++) {
    const y = Math.random() * c.height;
    const v = 110 + Math.random() * 90;
    g.strokeStyle = `rgba(${v},${v},${v},${0.15 + Math.random() * 0.35})`;
    g.lineWidth = Math.random() * 1.4 + 0.3;
    g.beginPath();
    const x = Math.random() * c.width;
    g.moveTo(x - 400, y);
    g.lineTo(x + 400, y + (Math.random() - 0.5) * 2);
    g.stroke();
  }
  const t = new THREE.CanvasTexture(c);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return t;
}

/** Gantry: two rails on the pedestal, a bridge on two uprights, a carriage that holds the head. */
function gantryParts(): { root: THREE.Group; bridge: THREE.Object3D; carriage: THREE.Object3D } {
  const dark = new THREE.MeshStandardMaterial({ color: "#1d1d24", metalness: 0.85, roughness: 0.38 });
  const steel = new THREE.MeshStandardMaterial({ color: "#9a9ea6", metalness: 1, roughness: 0.3 });
  const red = new THREE.MeshBasicMaterial({ color: new THREE.Color(RED).multiplyScalar(1.6) });
  const root = new THREE.Group();
  for (const side of [-1, 1]) {
    const rail = new THREE.Mesh(new RoundedBoxGeometry(0.06, 0.05, 1.5, 2, 0.008), steel);
    rail.position.set(side * RAIL_X, -0.025, -0.2);
    root.add(rail);
  }
  const bridge = new THREE.Group();
  root.add(bridge);
  const beam = new THREE.Mesh(new RoundedBoxGeometry(2.26, 0.11, 0.13, 3, 0.012), dark);
  beam.position.y = BRIDGE_Y;
  bridge.add(beam);
  const stripe = new THREE.Mesh(new THREE.BoxGeometry(2.1, 0.012, 0.004), red);
  stripe.position.set(0, BRIDGE_Y - 0.025, 0.067);
  bridge.add(stripe);
  for (const side of [-1, 1]) {
    const post = new THREE.Mesh(new RoundedBoxGeometry(0.08, BRIDGE_Y + 0.06, 0.12, 2, 0.01), dark);
    post.position.set(side * RAIL_X, (BRIDGE_Y - 0.06) / 2, 0);
    bridge.add(post);
    const foot = new THREE.Mesh(new RoundedBoxGeometry(0.11, 0.05, 0.18, 2, 0.008), steel);
    foot.position.set(side * RAIL_X, 0.02, 0);
    bridge.add(foot);
  }
  // The carriage rides the front of the bridge and reaches down to the head bracket.
  const carriage = new THREE.Mesh(new RoundedBoxGeometry(0.22, 0.34, 0.05, 2, 0.008), dark);
  carriage.position.set(0, BRIDGE_Y - 0.06, -BRIDGE_DZ - 0.19);
  bridge.add(carriage);
  return { root, bridge, carriage };
}

/** Galvo head from primitives: scanner box, F-theta lens, red ring, fibre tube, column. */
function proceduralHead(): THREE.Object3D {
  const g = new THREE.Group();
  const body = new THREE.MeshStandardMaterial({ color: "#2a2a33", metalness: 1, roughness: 0.32 });
  const alu = new THREE.MeshStandardMaterial({ color: "#c9ccd2", metalness: 1, roughness: 0.22 });
  const red = new THREE.MeshStandardMaterial({ color: RED, metalness: 0.3, roughness: 0.25, emissive: RED, emissiveIntensity: 0.6 });
  const glass = new THREE.MeshPhysicalMaterial({ color: "#100608", metalness: 0, roughness: 0.05, clearcoat: 1 });
  const box = new THREE.Mesh(new RoundedBoxGeometry(0.36, 0.2, 0.28, 4, 0.025), body);
  box.position.y = 0.205;
  g.add(box);
  // Seam line on the box.
  const seam = new THREE.Mesh(new THREE.BoxGeometry(0.362, 0.004, 0.282), new THREE.MeshStandardMaterial({ color: "#0d0d11", metalness: 0.5, roughness: 0.6 }));
  seam.position.y = 0.24;
  g.add(seam);
  const barrel = new THREE.Mesh(new THREE.CylinderGeometry(0.068, 0.072, 0.1, 48), alu);
  barrel.position.y = 0.055;
  g.add(barrel);
  // Knurled grip: thin rings.
  for (let k = 0; k < 6; k++) {
    const r = new THREE.Mesh(new THREE.TorusGeometry(0.073, 0.0032, 6, 48), alu);
    r.rotation.x = Math.PI / 2;
    r.position.y = 0.025 + k * 0.009;
    g.add(r);
  }
  const ring = new THREE.Mesh(new THREE.CylinderGeometry(0.075, 0.075, 0.012, 48), red);
  ring.position.y = 0.1;
  g.add(ring);
  const lens = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.055, 0.004, 48), glass);
  lens.position.y = 0.001;
  g.add(lens);
  const tube = new THREE.Mesh(new THREE.CylinderGeometry(0.032, 0.032, 0.32, 24), body);
  tube.rotation.x = Math.PI / 2;
  tube.position.set(0.08, 0.23, -0.27);
  g.add(tube);
  const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.038, 0.038, 0.03, 24), alu);
  cap.rotation.x = Math.PI / 2;
  cap.position.set(0.08, 0.23, -0.14);
  g.add(cap);
  // Status LED.
  const led = new THREE.Mesh(new THREE.SphereGeometry(0.008, 12, 12), new THREE.MeshBasicMaterial({ color: new THREE.Color(4, 0.3, 0.2) }));
  led.position.set(0.13, 0.27, 0.142);
  g.add(led);
  // Vent slots on the front face.
  for (let k = 0; k < 5; k++) {
    const v = new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.006, 0.004), new THREE.MeshStandardMaterial({ color: "#0b0b0e", roughness: 0.8 }));
    v.position.set(-0.09, 0.17 + k * 0.016, 0.141);
    g.add(v);
  }
  return g;
}
