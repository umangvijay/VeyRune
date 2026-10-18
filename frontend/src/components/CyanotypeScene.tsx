"use client";

/**
 * CyanotypeScene — the Drafting Works (Sandtable home backdrop).
 *
 * INTERACTIVE: the scene is the navigation.
 *  - click a blueprint sheet or a structure → the camera dollies in (focus)
 *  - click the hall / press Esc → pull back
 *  - hover targets highlight + the cursor becomes a lens
 *  - the camera drifts with the pointer (observatory parallax)
 *
 * A dark drafting hall rendered with React Three Fiber:
 *  - giant blueprint sheets hover and unfold (planned DAGs)
 *  - thin light streams trace lines onto them (the planner)
 *  - wireframe structures assemble (execution); drafting primitives stand
 *    in the hall — no cosmos, no stars: graphite dust and ruler light
 *
 * Theme-aware: "tungsten" (near-black #04060B + klein blue) and
 * "north light" (pale drafting paper + prussian ink).
 */

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

export type CyanotypeMode = "dark" | "light";

const PALETTE = {
  dark: {
    bg: "#04060b",
    fog: "#04060b",
    sheet: "#12325e",
    sheetEdge: "#8ab4ff",
    line: "#3e6bff",
    lineBright: "#a9c6ff",
    wire: "#5b8cff",
    grid: "#0d1730",
    dust: "#41598f",
  },
  light: {
    bg: "#dfe7f3",
    fog: "#dfe7f3",
    sheet: "#b7c9ea",
    sheetEdge: "#1d3f8f",
    line: "#2e56c4",
    lineBright: "#1d3f8f",
    wire: "#5a74c9",
    grid: "#c3d0e6",
    dust: "#8fa6cc",
  },
};

export type FocusTarget = {
  id: string;
  lookAt: [number, number, number];
  camPos: [number, number, number];
};

/** Camera rig: pointer parallax + click-to-zoom dolly with smooth lerp. */
function CameraRig({ focus, pointer }: { focus: FocusTarget | null; pointer: React.MutableRefObject<{ x: number; y: number }> }) {
  const { camera } = useThree();
  const target = useRef(new THREE.Vector3(0, 1.6, 8.5));
  const lookAt = useRef(new THREE.Vector3(0, 1.4, -3));

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    if (focus) {
      target.current.set(...focus.camPos);
      lookAt.current.set(...focus.lookAt);
    } else {
      // parked orbit + observatory parallax: the hall drifts with the pointer
      target.current.set(
        Math.sin(t * 0.05) * 0.6 + pointer.current.x * 0.7,
        1.6 + pointer.current.y * 0.4,
        8.5 + Math.cos(t * 0.04) * 0.4,
      );
      lookAt.current.set(pointer.current.x * 1.2, 1.4 + pointer.current.y * 0.6, -3);
    }
    camera.position.lerp(target.current, 0.045);
    camera.lookAt(lookAt.current);
  });
  return null;
}

/** A blueprint sheet: grid-textured plane + wireframe rim, slow drift, clickable. */
function Sheet({
  position, rotation, size = [4.2, 3], seed = 0, mode, focused, onFocus,
}: {
  position: [number, number, number];
  rotation: [number, number, number];
  size?: [number, number];
  seed?: number;
  mode: CyanotypeMode;
  focused: boolean;
  onFocus: (t: FocusTarget | null) => void;
}) {
  const c = PALETTE[mode];
  const group = useRef<THREE.Group>(null);
  const [hovered, setHovered] = useState(false);

  const texture = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 512; canvas.height = 384;
    const ctx = canvas.getContext("2d")!;
    const base = mode === "dark" ? "#0d2247" : "#c6d5ee";
    const ink = mode === "dark" ? "rgba(138,180,255,0.6)" : "rgba(29,63,143,0.5)";
    ctx.fillStyle = base;
    ctx.fillRect(0, 0, 512, 384);
    ctx.strokeStyle = ink;
    ctx.lineWidth = 1;
    for (let x = 0; x <= 512; x += 32) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 384); ctx.stroke(); }
    for (let y = 0; y <= 384; y += 32) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(512, y); ctx.stroke(); }
    ctx.lineWidth = 2;
    ctx.strokeRect(16, 16, 480, 352);
    ctx.beginPath(); ctx.arc(384, 288, 42, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.arc(384, 288, 24, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeRect(360, 100, 120, 60);
    ctx.font = "14px monospace";
    ctx.fillStyle = mode === "dark" ? "rgba(169,198,255,0.85)" : "rgba(29,63,143,0.85)";
    ctx.fillText(`SANDTABLE // SHEET-${(seed + 1).toString().padStart(3, "0")}`, 28, 44);
    const tex = new THREE.CanvasTexture(canvas);
    tex.anisotropy = 4;
    return tex;
  }, [mode, seed]);

  useFrame(({ clock }) => {
    if (group.current) {
      const t = clock.getElapsedTime();
      group.current.position.y = position[1] + Math.sin(t * 0.35 + seed) * 0.14;
      group.current.rotation.z = rotation[2] + Math.sin(t * 0.22 + seed * 2) * 0.02;
    }
  });

  return (
    <group
      ref={group}
      position={position}
      rotation={rotation}
      onClick={(e) => {
        e.stopPropagation();
        if (focused) { onFocus(null); return; }
        // dolly to a position slightly in front of the sheet, facing it
        const n = new THREE.Vector3(0, 0, 1).applyEuler(new THREE.Euler(...rotation));
        onFocus({
          id: `sheet-${seed}`,
          lookAt: position,
          camPos: [position[0] + n.x * 3.4, position[1] + n.y * 3.4 + 0.5, position[2] + n.z * 3.4],
        });
      }}
      onPointerOver={(e) => { e.stopPropagation(); setHovered(true); document.body.style.cursor = "zoom-in"; }}
      onPointerOut={() => { setHovered(false); document.body.style.cursor = "auto"; }}
    >
      <mesh>
        <planeGeometry args={[size[0], size[1]]} />
        <meshBasicMaterial
          map={texture}
          transparent
          opacity={focused || hovered ? (mode === "dark" ? 1 : 0.95) : mode === "dark" ? 0.8 : 0.75}
          side={THREE.DoubleSide}
        />
      </mesh>
      <lineSegments>
        <edgesGeometry args={[new THREE.PlaneGeometry(size[0], size[1])]} />
        <lineBasicMaterial color={hovered || focused ? c.lineBright : c.sheetEdge} transparent opacity={hovered || focused ? 1 : 0.85} />
      </lineSegments>
    </group>
  );
}

/** The planner: a light stream tracing a path across the hall.
 *  Built imperatively — R3F's JSX <line> collides with the SVG intrinsic. */
function TracingLine({ mode, points, speed = 0.12, offset = 0 }: { mode: CyanotypeMode; points: [number, number, number][]; speed?: number; offset?: number }) {
  const c = PALETTE[mode];
  const full = useMemo(() => points.map(p => new THREE.Vector3(...p)), [points]);
  const { line, material } = useMemo(() => {
    const geometry = new THREE.BufferGeometry().setFromPoints(full.slice(0, 2));
    const mat = new THREE.LineBasicMaterial({ color: c.lineBright, transparent: true, opacity: 0.8 });
    return { line: new THREE.Line(geometry, mat), material: mat };
  }, [full, c.lineBright]);
  const total = points.length - 1;

  useFrame(({ clock }) => {
    const t = (clock.getElapsedTime() * speed + offset) % 1;
    const head = Math.max(1, Math.ceil(t * total));
    line.geometry.setFromPoints(full.slice(0, head + 1));
    material.opacity = 0.3 + 0.6 * Math.sin(t * Math.PI);
  });

  return <primitive object={line} />;
}

/** Wireframe drafting primitives — half-built structures, clickable. */
function Structure({
  mode, position, kind, focused, onFocus,
}: {
  mode: CyanotypeMode;
  position: [number, number, number];
  kind: "icosa" | "cone" | "torus";
  focused: boolean;
  onFocus: (t: FocusTarget | null) => void;
}) {
  const c = PALETTE[mode];
  const ref = useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);
  useFrame(({ clock }) => {
    if (ref.current) {
      const t = clock.getElapsedTime();
      ref.current.rotation.y = t * 0.12;
      ref.current.rotation.x = Math.sin(t * 0.2) * 0.14;
    }
  });
  return (
    <mesh
      ref={ref}
      position={position}
      onClick={(e) => {
        e.stopPropagation();
        if (focused) { onFocus(null); return; }
        onFocus({
          id: `${kind}-${position.join(",")}`,
          lookAt: position,
          camPos: [position[0] + 1.6, position[1] + 1.2, position[2] + 3.2],
        });
      }}
      onPointerOver={(e) => { e.stopPropagation(); setHovered(true); document.body.style.cursor = "zoom-in"; }}
      onPointerOut={() => { setHovered(false); document.body.style.cursor = "auto"; }}
    >
      {kind === "icosa" && <icosahedronGeometry args={[1.15, 1]} />}
      {kind === "cone" && <coneGeometry args={[0.9, 2.1, 6, 3, true]} />}
      {kind === "torus" && <torusGeometry args={[1, 0.28, 8, 20]} />}
      <meshBasicMaterial
        color={hovered || focused ? c.lineBright : c.wire}
        wireframe
        transparent
        opacity={hovered || focused ? 0.9 : mode === "dark" ? 0.5 : 0.4}
      />
    </mesh>
  );
}

/** Graphite dust: a sparse, slow-drifting point field (not a starfield). */
function Dust({ mode, count = 160 }: { mode: CyanotypeMode; count?: number }) {
  const c = PALETTE[mode];
  const ref = useRef<THREE.Points>(null);
  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      arr[i * 3] = (Math.random() - 0.5) * 24;
      arr[i * 3 + 1] = Math.random() * 8 - 1;
      arr[i * 3 + 2] = (Math.random() - 0.5) * 16 - 2;
    }
    return arr;
  }, [count]);
  useFrame(({ clock }) => {
    if (ref.current) ref.current.position.y = Math.sin(clock.getElapsedTime() * 0.08) * 0.3;
  });
  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial color={c.dust} size={0.035} transparent opacity={mode === "dark" ? 0.7 : 0.5} sizeAttenuation />
    </points>
  );
}

function GridFloor({ mode }: { mode: CyanotypeMode }) {
  const c = PALETTE[mode];
  return <gridHelper args={[40, 40, c.grid, c.grid]} position={[0, -1.6, 0]} />;
}

function Scene({ mode, onFocusChange }: { mode: CyanotypeMode; onFocusChange: (id: string | null) => void }) {
  const c = PALETTE[mode];
  const [focus, setFocus] = useState<FocusTarget | null>(null);
  const pointer = useRef({ x: 0, y: 0 });

  useEffect(() => {
    const onPointer = (e: PointerEvent) => {
      pointer.current.x = (e.clientX / window.innerWidth - 0.5) * 2;
      pointer.current.y = -(e.clientY / window.innerHeight - 0.5) * 2;
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && focus) { setFocus(null); onFocusChange(null); }
    };
    window.addEventListener("pointermove", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointermove", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [focus, onFocusChange]);

  return (
    <>
      <color attach="background" args={[c.bg]} />
      <fog attach="fog" args={[c.fog, 9, 26]} />
      <CameraRig focus={focus} pointer={pointer} />
      <GridFloor mode={mode} />
      <Dust mode={mode} />
      <Sheet mode={mode} position={[-4.4, 1.7, -4]} rotation={[0.06, 0.5, 0.03]} seed={0}
        focused={focus?.id === "sheet-0"}
        onFocus={(t) => { setFocus(t); onFocusChange(t ? "sheet-0" : null); }} />
      <Sheet mode={mode} position={[3.9, 2.1, -5.2]} rotation={[-0.04, -0.42, -0.05]} size={[4.8, 3.4]} seed={1}
        focused={focus?.id === "sheet-1"}
        onFocus={(t) => { setFocus(t); onFocusChange(t ? "sheet-1" : null); }} />
      <Sheet mode={mode} position={[0.6, 3.1, -8.5]} rotation={[0.1, 0.12, 0.04]} size={[3.6, 2.6]} seed={2}
        focused={focus?.id === "sheet-2"}
        onFocus={(t) => { setFocus(t); onFocusChange(t ? "sheet-2" : null); }} />
      <TracingLine mode={mode} offset={0} points={[[-6.5, 0.4, -2.2], [-4.2, 1.6, -3.4], [-1.2, 2.6, -5.6], [1.8, 1.4, -4.1], [4.4, 2.4, -6.2]]} />
      <TracingLine mode={mode} offset={0.5} speed={0.09} points={[[5.8, 0.8, -1.6], [3.4, 2.4, -4.6], [0.4, 3.2, -7.4], [-3.2, 1.8, -5.2]]} />
      <Structure mode={mode} position={[-7.4, 0.4, -3]} kind="icosa"
        focused={focus?.id.startsWith("icosa")}
        onFocus={(t) => { setFocus(t); onFocusChange(t ? "icosa" : null); }} />
      <Structure mode={mode} position={[7.6, 0.2, -4.5]} kind="cone"
        focused={focus?.id.startsWith("cone")}
        onFocus={(t) => { setFocus(t); onFocusChange(t ? "cone" : null); }} />
      <Structure mode={mode} position={[6.4, 2.6, -9]} kind="torus"
        focused={focus?.id.startsWith("torus")}
        onFocus={(t) => { setFocus(t); onFocusChange(t ? "torus" : null); }} />
    </>
  );
}

export default function CyanotypeScene({
  mode = "dark",
  onFocusChange,
}: {
  mode?: CyanotypeMode;
  onFocusChange?: (id: string | null) => void;
}) {
  return (
    <div
      style={{ position: "absolute", inset: 0, zIndex: 0 }}
      aria-hidden="true"
    >
      <Canvas
        camera={{ position: [0, 1.6, 8.5], fov: 55 }}
        dpr={[1, 1.75]}
        gl={{ antialias: true, powerPreference: "low-power" }}
        style={{ position: "absolute", inset: 0 }}
        onPointerMissed={() => onFocusChange?.(null)}
      >
        <Scene mode={mode} onFocusChange={onFocusChange ?? (() => {})} />
      </Canvas>
    </div>
  );
}
