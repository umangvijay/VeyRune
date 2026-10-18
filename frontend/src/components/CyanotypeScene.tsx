"use client";

/**
 * CyanotypeScene — the Drafting Works (Sandtable home backdrop).
 *
 * A dark drafting hall rendered with React Three Fiber:
 *  - giant blueprint sheets hover and unfold in the air (planned DAGs)
 *  - thin light streams trace lines onto them (the planner at work)
 *  - finished sheets fold into wireframe structures (execution)
 *  - drafting primitives (icosahedron, cone) stand in the hall
 *  - a grid floor with graphite dust — no cosmos, no stars
 *
 * Theme-aware: "tungsten" (dark, near-black #04060B + klein blue #3E6BFF)
 * and "north light" (pale drafting paper + prussian ink).
 */

import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

export type CyanotypeMode = "dark" | "light";

const PALETTE = {
  dark: {
    bg: "#04060b",
    fog: "#04060b",
    sheet: "#12325e",
    sheetEdge: "#5b8cff",
    line: "#3e6bff",
    lineBright: "#9fc0ff",
    wire: "#3e6bff",
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

/** A blueprint sheet: grid-textured plane + wireframe rim, slow drift. */
function Sheet({
  position, rotation, size = [4.2, 3], seed = 0, mode,
}: {
  position: [number, number, number];
  rotation: [number, number, number];
  size?: [number, number];
  seed?: number;
  mode: CyanotypeMode;
}) {
  const c = PALETTE[mode];
  const group = useRef<THREE.Group>(null);

  const texture = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 512; canvas.height = 384;
    const ctx = canvas.getContext("2d")!;
    const base = mode === "dark" ? "#0d2247" : "#c6d5ee";
    const ink = mode === "dark" ? "rgba(120,160,255,0.55)" : "rgba(29,63,143,0.5)";
    ctx.fillStyle = base;
    ctx.fillRect(0, 0, 512, 384);
    ctx.strokeStyle = ink;
    ctx.lineWidth = 1;
    for (let x = 0; x <= 512; x += 32) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 384); ctx.stroke(); }
    for (let y = 0; y <= 384; y += 32) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(512, y); ctx.stroke(); }
    // title block + a schematic circle, like a real sheet
    ctx.lineWidth = 2;
    ctx.strokeRect(16, 16, 480, 352);
    ctx.beginPath(); ctx.arc(384, 288, 42, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.arc(384, 288, 24, 0, Math.PI * 2); ctx.stroke();
    ctx.strokeRect(360, 100, 120, 60);
    ctx.font = "14px monospace";
    ctx.fillStyle = mode === "dark" ? "rgba(159,192,255,0.8)" : "rgba(29,63,143,0.85)";
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
    <group ref={group} position={position} rotation={rotation}>
      <mesh>
        <planeGeometry args={[size[0], size[1]]} />
        <meshBasicMaterial map={texture} transparent opacity={mode === "dark" ? 0.92 : 0.85} side={THREE.DoubleSide} />
      </mesh>
      <lineSegments>
        <edgesGeometry args={[new THREE.PlaneGeometry(size[0], size[1])]} />
        <lineBasicMaterial color={c.sheetEdge} transparent opacity={0.9} />
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

/** Wireframe drafting primitives — half-built structures assembling. */
function Structure({ mode, position, kind }: { mode: CyanotypeMode; position: [number, number, number]; kind: "icosa" | "cone" | "torus" }) {
  const c = PALETTE[mode];
  const ref = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (ref.current) {
      const t = clock.getElapsedTime();
      ref.current.rotation.y = t * 0.12;
      ref.current.rotation.x = Math.sin(t * 0.2) * 0.14;
    }
  });
  return (
    <mesh ref={ref} position={position}>
      {kind === "icosa" && <icosahedronGeometry args={[1.15, 1]} />}
      {kind === "cone" && <coneGeometry args={[0.9, 2.1, 6, 3, true]} />}
      {kind === "torus" && <torusGeometry args={[1, 0.28, 8, 20]} />}
      <meshBasicMaterial color={c.wire} wireframe transparent opacity={mode === "dark" ? 0.5 : 0.4} />
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
  return (
    <gridHelper args={[40, 40, c.grid, c.grid]} position={[0, -1.6, 0]} />
  );
}

function Scene({ mode }: { mode: CyanotypeMode }) {
  const c = PALETTE[mode];
  return (
    <>
      <color attach="background" args={[c.bg]} />
      <fog attach="fog" args={[c.fog, 9, 26]} />
      {/* Hall */}
      <GridFloor mode={mode} />
      <Dust mode={mode} />
      {/* Blueprint sheets, hovering and unfolding */}
      <Sheet mode={mode} position={[-4.4, 1.7, -4]} rotation={[0.06, 0.5, 0.03]} seed={0} />
      <Sheet mode={mode} position={[3.9, 2.1, -5.2]} rotation={[-0.04, -0.42, -0.05]} size={[4.8, 3.4]} seed={1} />
      <Sheet mode={mode} position={[0.6, 3.1, -8.5]} rotation={[0.1, 0.12, 0.04]} size={[3.6, 2.6]} seed={2} />
      {/* Planner light streams */}
      <TracingLine mode={mode} offset={0} points={[[-6.5, 0.4, -2.2], [-4.2, 1.6, -3.4], [-1.2, 2.6, -5.6], [1.8, 1.4, -4.1], [4.4, 2.4, -6.2]]} />
      <TracingLine mode={mode} offset={0.5} speed={0.09} points={[[5.8, 0.8, -1.6], [3.4, 2.4, -4.6], [0.4, 3.2, -7.4], [-3.2, 1.8, -5.2]]} />
      {/* Half-built structures */}
      <Structure mode={mode} position={[-7.4, 0.4, -3]} kind="icosa" />
      <Structure mode={mode} position={[7.6, 0.2, -4.5]} kind="cone" />
      <Structure mode={mode} position={[6.4, 2.6, -9]} kind="torus" />
    </>
  );
}

export default function CyanotypeScene({ mode = "dark" }: { mode?: CyanotypeMode }) {
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
      >
        <Scene mode={mode} />
      </Canvas>
    </div>
  );
}
