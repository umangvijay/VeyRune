"use client";

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Component, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import * as THREE from "three";

export type SceneStatus = "loading" | "ready" | "fallback";

export type SceneFocus = "overview" | "planet" | "sheet";

export type CyanotypeMode = "dark" | "light";
const PALETTE = {
  dark: { sheetBase: "#073279", sheetBase2: "#1245a0", ink: "rgba(210,237,255,.9)", inkSoft: "rgba(130,190,255,.45)" },
  light: { sheetBase: "#b6d0f3", sheetBase2: "#dce9fb", ink: "rgba(15,56,120,.9)", inkSoft: "rgba(25,70,140,.45)" },
};

function makeSheetTexture(mode: CyanotypeMode, seed: number, withStamp: boolean): THREE.CanvasTexture {
  const c = PALETTE[mode];
  const canvas = document.createElement("canvas");
  canvas.width = 640; canvas.height = 480;
  const ctx = canvas.getContext("2d")!;

  const grad = ctx.createLinearGradient(0, 0, 640, 480);
  grad.addColorStop(0, c.sheetBase);
  grad.addColorStop(1, c.sheetBase2);
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 640, 480);

  ctx.strokeStyle = c.inkSoft;
  ctx.lineWidth = 1;
  for (let x = 0; x <= 640; x += 24) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 480); ctx.stroke(); }
  for (let y = 0; y <= 480; y += 24) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(640, y); ctx.stroke(); }

  ctx.strokeStyle = c.ink;
  ctx.lineWidth = 1.4;
  for (let x = 0; x <= 640; x += 120) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 480); ctx.stroke(); }
  for (let y = 0; y <= 480; y += 120) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(640, y); ctx.stroke(); }

  ctx.lineWidth = 3;
  ctx.strokeRect(10, 10, 620, 460);
  ctx.lineWidth = 1.5;
  ctx.strokeRect(24, 24, 592, 432);

  // drafting blocks: pseudo-random per variant — patterns change over time
  let s = (seed + 1) * 2654435761 % 4294967296;
  const rand = () => { s = (s * 1664525 + 1013904223) % 4294967296; return s / 4294967296; };
  ctx.lineWidth = 2;
  const blockCount = 5 + Math.floor(rand() * 3);
  for (let i = 0; i < blockCount; i++) {
    const x = 40 + rand() * 420;
    const y = 60 + rand() * 300;
    const w = 80 + rand() * 160;
    const h = 60 + rand() * 110;
    ctx.strokeRect(x, y, w, h);
    if (rand() > 0.5) {
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + w, y + h);
      ctx.moveTo(x + w, y); ctx.lineTo(x, y + h); ctx.stroke();
    } else if (rand() > 0.6) {
      ctx.beginPath(); ctx.arc(x + w / 2, y + h / 2, Math.min(w, h) / 2.6, 0, Math.PI * 2); ctx.stroke();
    }
  }

  ctx.lineWidth = 2.2;
  ctx.beginPath(); ctx.arc(470, 300, 52, 0, Math.PI * 2); ctx.stroke();
  ctx.beginPath(); ctx.arc(470, 300, 30, 0, Math.PI * 2); ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(470 - 68, 300); ctx.lineTo(470 + 68, 300);
  ctx.moveTo(470, 300 - 68); ctx.lineTo(470, 300 + 68);
  ctx.stroke();

  ctx.font = "13px monospace";
  ctx.fillStyle = c.ink;
  ctx.fillText("COMMUNICATION LATTICE", 408, 226);
  ctx.fillText("FIELD MODULES", 48, 232);
  ctx.fillText("TOR ANTENNAE", 52, 316);
  ctx.fillText("MOD PARAMETERIZE", 292, 348);

  if (withStamp) {
    ctx.save();
    ctx.translate(470, 400);
    ctx.rotate(-0.06);
    ctx.lineWidth = 3;
    ctx.strokeStyle = c.ink;
    ctx.strokeRect(-120, -30, 240, 60);
    ctx.font = "bold 26px monospace";
    ctx.fillStyle = c.ink;
    ctx.fillText("FOR APPROVAL", -102, 8);
    ctx.font = "11px monospace";
    ctx.fillText("VALIDATED · MCP SPEC · PROTOCOL · HOLD", -100, 26);
    ctx.restore();
  }

  ctx.font = "12px monospace";
  ctx.fillStyle = c.ink;
  ctx.fillText("SANDTABLE // DRAFTING WORKS · ALL RIGHTS RESERVED", 28, 458);

  const glowX = 300 + seed * 60;
  const glowY = 150 + seed * 40;
  const radial = ctx.createRadialGradient(glowX, glowY, 0, glowX, glowY, 26);
  radial.addColorStop(0, mode === "dark" ? "rgba(140,180,255,0.95)" : "rgba(29,63,143,0.8)");
  radial.addColorStop(0.4, mode === "dark" ? "rgba(90,140,255,0.35)" : "rgba(29,63,143,0.3)");
  radial.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = radial;
  ctx.fillRect(glowX - 30, glowY - 30, 60, 60);

  const tex = new THREE.CanvasTexture(canvas);
  tex.anisotropy = 4;
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}


// Shared coordinates keep every strand physically attached to its source.
function weaveProgress(t: number, index: number) {
  return (Math.sin(t * .32 + index * 1.7) + 1) / 2;
}

function sheetDepth(x: number, y: number, t: number, index: number) {
  const fold = (Math.sin(t * .38 + index * 1.7) + 1) / 2;
  return Math.sin(x * 1.7 + t * .7 + index) * .13 + Math.abs(x) ** 2 * fold * .2 + Math.sin(y * 2 + t) * .045;
}

const ORIGIN = new THREE.Vector3(1.65, 1.4, -2.2);
const SHEETS = [
  { position: [4.3, -.25, .1], rotation: [-.2, -.38, -.12], size: [3.5, 2.6] },
  { position: [-1.4, -.8, -1], rotation: [.12, .28, .16], size: [3.1, 2.3] },
  { position: [4.7, 3.15, -3.5], rotation: [.05, -.3, .1], size: [2.6, 1.9] },
] as const;

// Camera motion stays responsive even when the loom animation is paused.
function CameraRig({ focus, reducedMotion, zoom }: { focus: SceneFocus; reducedMotion: boolean; zoom: number }) {
  const { invalidate } = useThree();
  const aim = useRef(new THREE.Vector3(0, 1.2, 0));
  const destination = useMemo(() => {
    const target = focus === "planet" ? ORIGIN.clone() : focus === "sheet"
      ? new THREE.Vector3(...SHEETS[0].position) : new THREE.Vector3(0, 1.2, 0);
    const baseDist = focus === "overview" ? 11 : 5.8;
    const dist = baseDist / zoom;
    return { target, eye: target.clone().add(new THREE.Vector3(0, dist * .12, dist)) };
  }, [focus, zoom]);
  useEffect(() => invalidate(), [destination, invalidate, reducedMotion]);
  useFrame(({ camera, size }, delta) => {
    const eye = destination.eye.clone();
    const target = destination.target.clone();
    if (size.width < 760) {
      // Keep the selected object in the clear area above the mobile HUD.
      const offset = focus === "overview" ? new THREE.Vector3(1.65, -2, 0) : new THREE.Vector3(0, -1.5, 0);
      target.add(offset);
      eye.add(offset);
      if (focus !== "overview") eye.z += 2;
    }
    const blend = reducedMotion ? 1 : 1 - Math.exp(-5 * Math.min(delta, .1));
    camera.position.lerp(eye, blend);
    aim.current.lerp(target, blend);
    camera.lookAt(aim.current);
    if (camera.position.distanceTo(eye) > .001 || aim.current.distanceTo(target) > .001) invalidate();
  });
  return null;
}

function Loom({ mode, tempo, pointer, focus, onFocus, onWeave }: { mode: CyanotypeMode; tempo: number; pointer: React.RefObject<{ x: number; y: number }>; focus: SceneFocus; onFocus: (focus: SceneFocus) => void; onWeave: (progress: number) => void }) {
  const { gl } = useThree();
  useEffect(() => () => { gl.domElement.style.removeProperty("cursor"); }, [gl]);
  const time = useRef(0);
  const lastReport = useRef(-1);
  const world = useRef<THREE.Group>(null);
  useFrame((_, delta) => {
    time.current += Math.min(delta, .05) * tempo;
    if (lastReport.current < 0 || time.current - lastReport.current >= .25) {
      lastReport.current = time.current;
      onWeave(Math.round(weaveProgress(time.current, 0) * 100));
    }
    if (world.current) {
      world.current.rotation.y = THREE.MathUtils.damp(world.current.rotation.y, (focus === "overview" ? pointer.current.x * .065 : 0), 3, delta);
      world.current.rotation.x = THREE.MathUtils.damp(world.current.rotation.x, (focus === "overview" ? pointer.current.y * .035 : 0), 3, delta);
    }
  });
  const ink = mode === "dark" ? "#94d8ff" : "#214c9a";
  return <group ref={world}>
    <ambientLight intensity={1.5} />
    <pointLight position={[0, 5, 5]} color="#98caff" intensity={45} />
    <group onPointerOver={() => { gl.domElement.style.setProperty("cursor", "zoom-in"); }} onPointerOut={() => { gl.domElement.style.removeProperty("cursor"); }} onClick={event => { event.stopPropagation(); onFocus(focus === "planet" ? "overview" : "planet"); }}>
      <Planet time={time} ink={ink} mode={mode} />
    </group>
    {SHEETS.map((spec, index) => <group key={index} onPointerOver={index === 0 ? () => { gl.domElement.style.setProperty("cursor", "zoom-in"); } : undefined} onPointerOut={() => { gl.domElement.style.removeProperty("cursor"); }} onClick={index === 0 ? event => { event.stopPropagation(); onFocus(focus === "sheet" ? "overview" : "sheet"); } : undefined}><WovenSheet index={index} mode={mode} time={time} spec={spec} /></group>)}
    {SHEETS.flatMap((spec, index) => [0, 1, 2].map(strand =>
      <Thread key={`${index}-${strand}`} time={time} target={spec.position} index={index} strand={strand} ink={ink} />
    ))}
    <gridHelper args={[40, 60, mode === "dark" ? "#173766" : "#adc1df", mode === "dark" ? "#0b1a33" : "#ccd9ec"]} position={[0, -3, -4]} />
  </group>;
}

function Planet({ time, ink, mode }: { time: React.RefObject<number>; ink: string; mode: CyanotypeMode }) {
  const globe = useRef<THREE.Group>(null);
  useFrame(() => { if (globe.current) globe.current.rotation.y = time.current * .12; });
  return <group position={ORIGIN}>
    <group ref={globe} rotation={[.12, 0, -.28]}>
      <mesh><sphereGeometry args={[1.2, 48, 32]} /><meshStandardMaterial color={mode === "dark" ? "#071d40" : "#9fbde8"} roughness={.42} metalness={.65} /></mesh>
      <mesh scale={1.006}><sphereGeometry args={[1.2, 28, 18]} /><meshBasicMaterial color={ink} wireframe transparent opacity={.4} /></mesh>
      {[0, 1, 2].map(i => <mesh key={i} rotation={[Math.PI / 2 + i * .35, i * .6, .2]}>
        <torusGeometry args={[1.34 + i * .08, .008, 6, 100]} /><meshBasicMaterial color={ink} transparent opacity={.7} />
      </mesh>)}
    </group>
    <mesh scale={1.12}><sphereGeometry args={[1.2, 32, 24]} /><meshBasicMaterial color="#3e6bff" transparent opacity={.07} side={THREE.BackSide} depthWrite={false} /></mesh>
  </group>;
}

type SheetSpec = typeof SHEETS[number];
function WovenSheet({ spec, index, mode, time }: { spec: SheetSpec; index: number; mode: CyanotypeMode; time: React.RefObject<number> }) {
  const surface = useRef<THREE.Mesh<THREE.PlaneGeometry>>(null);
  const texture = useMemo(() => makeSheetTexture(mode, index + 2, index === 0), [mode, index]);
  const model = useRef<THREE.Mesh>(null);
  const material = useRef<THREE.ShaderMaterial>(null);
  const shader = useMemo(() => ({
    uniforms: { map: { value: texture }, progress: { value: .5 } },
    vertexShader: `varying vec2 vUv;
      void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `uniform sampler2D map; uniform float progress; varying vec2 vUv;
      void main() {
        vec4 paper = texture2D(map, vUv);
        float woven = 1.0 - smoothstep(progress - .015, progress + .015, vUv.y);
        float needle = 1.0 - smoothstep(.0, .012, abs(vUv.y - progress));
        gl_FragColor = vec4(paper.rgb + needle * .35, .12 + woven * .76);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
  }), [texture]);
  useEffect(() => () => texture.dispose(), [texture]);
  useFrame(() => {
    const t = time.current;
    if (!surface.current) return;
    const positions = surface.current.geometry.attributes.position;
    const fold = (Math.sin(t * .38 + index * 1.7) + 1) / 2;
    for (let i = 0; i < positions.count; i++) {
      const x = positions.getX(i), y = positions.getY(i);
      positions.setZ(i, sheetDepth(x, y, t, index));
    }
    positions.needsUpdate = true;
    surface.current.geometry.computeBoundingSphere();
    surface.current.geometry.computeBoundingBox();
    if (material.current) material.current.uniforms.progress.value = weaveProgress(t, index);
    if (model.current) {
      model.current.rotation.y = t * .22;
      model.current.rotation.z = Math.sin(t * .25) * .15;
      model.current.scale.setScalar(.35 + fold * .5);
      model.current.position.z = .6 + fold * .45;
    }
  });
  return <group position={[...spec.position]} rotation={[...spec.rotation]}>
    <mesh ref={surface}><planeGeometry args={[spec.size[0], spec.size[1], 32, 24]} /><shaderMaterial ref={material} args={[shader]} side={THREE.DoubleSide} transparent depthWrite={false} /></mesh>
    <mesh ref={model} position={[.3, .1, .9]}>
      {index === 0 ? <icosahedronGeometry args={[.7, 0]} /> : index === 1 ? <boxGeometry args={[1, .8, .8]} /> : <octahedronGeometry args={[.7]} />}
      <meshBasicMaterial color={mode === "dark" ? "#b5eaff" : "#1e499c"} wireframe transparent opacity={.8} />
    </mesh>
  </group>;
}

function Thread({ target, index, strand, time, ink }: { target: readonly number[]; index: number; strand: number; time: React.RefObject<number>; ink: string }) {
  const head = useRef<THREE.Mesh>(null);
  const thread = useRef<THREE.Line<THREE.BufferGeometry, THREE.LineBasicMaterial>>(null);
  const line = useMemo(() => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(81 * 3), 3));
    return new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: ink, transparent: true, opacity: .65 }));
  }, [ink]);
  useEffect(() => () => { line.geometry.dispose(); line.material.dispose(); }, [line]);
  useFrame(() => {
    const t = time.current;
    const phase = t * .7 + index * 2 + strand * .5;
    const start = ORIGIN.clone().add(new THREE.Vector3(Math.cos(phase), Math.sin(phase) * .55, Math.sin(phase) * .7).normalize().multiplyScalar(1.23));
    const x = Math.sin(t * 2.4 + strand * 2.1) * SHEETS[index].size[0] * .46;
    const y = (weaveProgress(t, index) - .5) * SHEETS[index].size[1];
    const end = new THREE.Vector3(x, y, sheetDepth(x, y, t, index) + .025)
      .applyEuler(new THREE.Euler(...SHEETS[index].rotation))
      .add(new THREE.Vector3(target[0], target[1], target[2]));
    const middle = start.clone().lerp(end, .5); middle.y += .8 + strand * .23;
    const curve = new THREE.QuadraticBezierCurve3(start, middle, end);
    if (!thread.current) return;
    const pos = thread.current.geometry.attributes.position;
    for (let i = 0; i <= 80; i++) {
      const u = i / 80, p = curve.getPoint(u);
      p.z += Math.sin(u * Math.PI * 12 - t * 3 + strand * Math.PI) * .07 * Math.sin(u * Math.PI);
      pos.setXYZ(i, p.x, p.y, p.z);
    }
    pos.needsUpdate = true;
    thread.current.geometry.computeBoundingSphere();
    if (head.current) {
      const u = (t * .3 + strand / 3) % 1;
      head.current.position.copy(curve.getPoint(u));
      head.current.position.z += Math.sin(u * Math.PI * 12 - t * 3 + strand * Math.PI) * .07 * Math.sin(u * Math.PI);
    }
  });
  return <><primitive ref={thread} object={line} /><mesh ref={head}><sphereGeometry args={[.045, 8, 8]} /><meshBasicMaterial color={ink} /></mesh></>;
}

function SceneIllustration() {
  return <svg className="scene-illustration" viewBox="0 0 1200 800" fill="none" aria-hidden="true">
    <g stroke="currentColor" strokeWidth="1">
      <circle cx="790" cy="260" r="100" />
      <ellipse cx="790" cy="260" rx="40" ry="100" />
      <ellipse cx="790" cy="260" rx="100" ry="30" />
      <ellipse cx="790" cy="260" rx="135" ry="45" transform="rotate(-25 790 260)" />
      <path d="M790 160v200M690 260h200M720 330Q640 400 720 520M830 350Q1020 400 970 490M870 290Q1000 280 1070 330" />
      <path d="m630 480 300-40 90 190-300 40zM650 520l300-40M670 560l300-40M690 600l300-40M700 470l90 190M780 460l90 190M860 450l90 190" />
      <path d="m1020 320 125 10-15 110-125-10z" />
      <circle cx="720" cy="520" r="5" /><circle cx="970" cy="490" r="5" />
    </g>
  </svg>;
}

function SceneUnavailable({ onStatus }: { onStatus: (status: SceneStatus) => void }) {
  useEffect(() => onStatus("fallback"), [onStatus]);
  return null;
}

class SceneBoundary extends Component<{ children: ReactNode; onStatus: (status: SceneStatus) => void }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { this.props.onStatus("fallback"); }
  render() { return this.state.failed ? null : this.props.children; }
}

export default function CyanotypeScene({ mode = "dark", tempo = 1, focus = "overview", onFocus, reducedMotion = false, onStatus, onWeave, status, zoom = 1, onZoom }: {
  mode?: CyanotypeMode; tempo?: number; focus?: SceneFocus; onFocus: (focus: SceneFocus) => void; reducedMotion?: boolean;
  onStatus: (status: SceneStatus) => void; onWeave: (progress: number) => void; status: SceneStatus; zoom?: number; onZoom?: (zoom: number) => void;
}) {
  const pointer = useRef({ x: 0, y: 0 });
  const [visible, setVisible] = useState(true);
  const [lost, setLost] = useState(false);
  useEffect(() => {
    const move = (e: PointerEvent) => { if (reducedMotion) return; pointer.current = { x: e.clientX / window.innerWidth * 2 - 1, y: e.clientY / window.innerHeight * 2 - 1 }; };
    const visibility = () => setVisible(!document.hidden);
    window.addEventListener("pointermove", move, { passive: true });
    document.addEventListener("visibilitychange", visibility);
    return () => { window.removeEventListener("pointermove", move); document.removeEventListener("visibilitychange", visibility); };
  }, [reducedMotion]);
  useEffect(() => {
    if (!onZoom) return;
    const el = document.querySelector(".loom-scene");
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const next = Math.max(0.4, Math.min(2.8, zoom - e.deltaY * 0.0015));
      onZoom(Number(next.toFixed(2)));
    };
    let pinchStart = 0;
    const onTouchStart = (e: TouchEvent) => {
      if (e.touches.length === 2) {
        pinchStart = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY,
        );
      }
    };
    const onTouchMove = (e: TouchEvent) => {
      if (e.touches.length === 2 && pinchStart > 0) {
        e.preventDefault();
        const dist = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY,
        );
        const next = Math.max(0.4, Math.min(2.8, zoom * (pinchStart / dist)));
        onZoom(Number(next.toFixed(2)));
      }
    };
    const onTouchEnd = () => { pinchStart = 0; };
    el.addEventListener("wheel", onWheel, { passive: false });
    el.addEventListener("touchstart", onTouchStart, { passive: true });
    el.addEventListener("touchmove", onTouchMove, { passive: false });
    el.addEventListener("touchend", onTouchEnd);
    return () => {
      el.removeEventListener("wheel", onWheel);
      el.removeEventListener("touchstart", onTouchStart);
      el.removeEventListener("touchmove", onTouchMove);
      el.removeEventListener("touchend", onTouchEnd);
    };
  }, [zoom, onZoom]);

  return <div className="loom-scene" data-state={status} aria-hidden="true">
    <div className="scene-fallback" /><SceneIllustration />
    {!lost && <SceneBoundary onStatus={onStatus}><Canvas camera={{ position: [0, 1.2, 11], fov: 48 }} dpr={[1, 1.5]} frameloop={!visible ? "never" : tempo > 0 ? "always" : "demand"}
      fallback={<SceneUnavailable onStatus={onStatus} />}
      gl={{ antialias: true, alpha: true, powerPreference: "low-power" }}
      onCreated={() => onStatus("ready")}>
      <ContextMonitor onLost={() => { setLost(true); onStatus("fallback"); }} />
      <CameraRig focus={focus} reducedMotion={reducedMotion} zoom={zoom} />
      <Loom mode={mode} tempo={tempo} pointer={pointer} focus={focus} onFocus={onFocus} onWeave={onWeave} />
    </Canvas></SceneBoundary>}
  </div>;
}

function ContextMonitor({ onLost }: { onLost: () => void }) {
  const { gl } = useThree();
  useEffect(() => {
    const lost = (event: Event) => { event.preventDefault(); onLost(); };
    gl.domElement.addEventListener("webglcontextlost", lost);
    return () => gl.domElement.removeEventListener("webglcontextlost", lost);
  }, [gl, onLost]);
  return null;
}
