// Trail the visitor burns with the pointer: a ring buffer of quads on the plate. Each quad
// keeps its birth time; the shader cools it from white-hot to a dark mark and fades it out.
import * as THREE from "three";

const LIFE = 9;

export class Trail {
  mesh: THREE.Mesh;
  private pos: Float32Array;
  private born: Float32Array;
  private next = 0;
  private count = 0;
  private mat: THREE.ShaderMaterial;

  constructor(private max = 3000, private width = 0.006) {
    this.pos = new Float32Array(max * 4 * 3);
    this.born = new Float32Array(max * 4).fill(-1e6);
    const idx = new Uint32Array(max * 6);
    for (let i = 0; i < max; i++) idx.set([i * 4, i * 4 + 1, i * 4 + 2, i * 4, i * 4 + 2, i * 4 + 3], i * 6);
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(this.pos, 3).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute("aT", new THREE.BufferAttribute(this.born, 1).setUsage(THREE.DynamicDrawUsage));
    g.setIndex(new THREE.BufferAttribute(idx, 1));
    g.setDrawRange(0, 0);
    this.mat = new THREE.ShaderMaterial({
      uniforms: { uClock: { value: 0 } },
      vertexShader: `attribute float aT; varying float vT; void main(){ vT = aT; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
      fragmentShader: /* glsl */ `
        uniform float uClock; varying float vT;
        void main(){
          float age = uClock - vT;
          if (age > ${LIFE.toFixed(1)}) discard;
          float heat = exp(-age * 2.2);
          vec3 hot = mix(vec3(1.0, 0.18, 0.05), vec3(1.0, 0.85, 0.6), heat * heat) * (0.6 + 9.0 * heat) * heat;
          vec3 burn = vec3(0.05, 0.012, 0.014);
          float a = 1.0 - smoothstep(${(LIFE - 3).toFixed(1)}, ${LIFE.toFixed(1)}, age);
          gl_FragColor = vec4(burn + hot, a);
        }`,
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      polygonOffset: true,
      polygonOffsetFactor: -3,
      polygonOffsetUnits: -3,
    });
    this.mesh = new THREE.Mesh(g, this.mat);
    this.mesh.position.y = 0.0014;
    this.mesh.frustumCulled = false;
  }

  /** One burnt segment from a to b on the plate (x, z), born at `t`. */
  add(ax: number, az: number, bx: number, bz: number, t: number) {
    const len = Math.hypot(bx - ax, bz - az);
    if (len < 1e-5) return;
    const w = this.width;
    const nx = (-(bz - az) / len) * w;
    const nz = ((bx - ax) / len) * w;
    const ex = ((bx - ax) / len) * w * 0.6;
    const ez = ((bz - az) / len) * w * 0.6;
    const i = this.next;
    const p = this.pos;
    const o = i * 12;
    p[o] = ax - ex + nx; p[o + 2] = az - ez + nz;
    p[o + 3] = ax - ex - nx; p[o + 5] = az - ez - nz;
    p[o + 6] = bx + ex - nx; p[o + 8] = bz + ez - nz;
    p[o + 9] = bx + ex + nx; p[o + 11] = bz + ez + nz;
    this.born.fill(t, i * 4, i * 4 + 4);
    this.next = (i + 1) % this.max;
    this.count = Math.min(this.max, this.count + 1);
    const g = this.mesh.geometry;
    g.setDrawRange(0, this.count * 6);
    // Upload only the new quad, not the whole ring buffer.
    const pos = g.attributes.position as THREE.BufferAttribute;
    const born = g.attributes.aT as THREE.BufferAttribute;
    pos.addUpdateRange(o, 12);
    born.addUpdateRange(i * 4, 4);
    pos.needsUpdate = true;
    born.needsUpdate = true;
  }

  setClock(t: number) {
    this.mat.uniforms.uClock.value = t;
  }
}
