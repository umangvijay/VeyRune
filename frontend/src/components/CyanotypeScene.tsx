"use client";

/**
 * CyanotypeScene — the Drafting Works (Sandtable home backdrop).
 *
 * MOTION CONTRACT (audit the user's note): the camera never rotates.
 * It holds a fixed drafting angle and GLIDES laterally — all life comes
 * from the hall itself: the planner's tracer light running its path,
 * sheets breathing and unfolding, beams sweeping, dust drifting,
 * wireframes assembling. A tempo control scales the whole hall's clock.
 *
 * Theme-aware: "tungsten" (near-black #04060B + klein blue #3E6BFF) and
 * "north light" (pale drafting paper + prussian ink).
 */

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

export type CyanotypeMode = "dark" | "light";

/** Central reprint scheduler: sheets redraw at random intervals. */
const reprintWatchers: Array<(t: number) => void> = [];
function watchSheetReprints(fn: (t: number) => void) {
  reprintWatchers.push(fn);
  return () => {
    const i = reprintWatchers.indexOf(fn);
    if (i >= 0) reprintWatchers.splice(i, 1);
  };
}

/* ── Shared hall clock: one tempo drives every animation ── */
const hall = { t: 0, tempo: 1, stepQueued: 0 };

export function setHallTempo(multiplier: number) {
  hall.tempo = multiplier;
}

export function hallStep() {
  hall.stepQueued += 0.35; // manual frame advance for the STEP button
}

function useHallTime() {
  const ref = useRef(0);
  useFrame((_, delta) => {
    hall.t += delta * hall.tempo;
    if (hall.stepQueued > 0) {
      hall.t += hall.stepQueued;
      hall.stepQueued = 0;
    }
    ref.current = hall.t;
  });
  return ref;
}

const PALETTE = {
  dark: {
    bg: "#04060b",
    fog: "#04060b",
    sheetBase: "#0d3a8f",
    sheetBase2: "#1a55c4",
    ink: "rgba(220,235,255,0.92)",
    inkSoft: "rgba(150,185,255,0.55)",
    edge: "#9fc2ff",
    line: "#6f9dff",
    lineBright: "#cfe2ff",
    icosa: "#39d9c0",
    cone: "#3e6bff",
    grid: "#0e1c3f",
    dust: "#7d9bff",
    beam: "#2a52c8",
  },
  light: {
    bg: "#dfe7f3",
    fog: "#dfe7f3",
    sheetBase: "#7ea3e8",
    sheetBase2: "#9dbdf2",
    ink: "rgba(10,30,80,0.85)",
    inkSoft: "rgba(10,30,80,0.5)",
    edge: "#1d3f8f",
    line: "#2e56c4",
    lineBright: "#1d3f8f",
    icosa: "#1f9e8e",
    cone: "#2e56c4",
    grid: "#c3d0e6",
    dust: "#8fa6cc",
    beam: "#b8ccf0",
  },
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

type SheetSpec = {
  position: [number, number, number];
  rotation: [number, number, number];
  size: [number, number];
  seed: number;
  withStamp: boolean;
  unfold?: boolean;
};

/** Blueprint sheet — HOLDS its drawn angle (no rotation drift), only breathes.
 *  At random intervals the pattern REPRINTS: the sheet flashes and the
 *  drafting blocks change — plans being redrawn in front of you. */
function Sheet({ spec, mode, hallTime }: { spec: SheetSpec; mode: CyanotypeMode; hallTime: React.MutableRefObject<number> }) {
  const c = PALETTE[mode];
  const group = useRef<THREE.Group>(null);
  const { position, rotation, size, seed, withStamp, unfold } = spec;

  const [variant, setVariant] = useState(seed);
  const materialRef = useRef<THREE.MeshBasicMaterial>(null);
  const reprint = useRef({ active: false, startedAt: 0, nextAt: 5 + Math.random() * 5 });

  useEffect(() => {
    return watchSheetReprints((t) => {
      if (t >= reprint.current.nextAt && !reprint.current.active) {
        reprint.current.active = true;
        reprint.current.startedAt = t;
        setVariant(Math.floor(Math.random() * 100000));
      }
      if (reprint.current.active && t - reprint.current.startedAt > 0.9) {
        reprint.current.active = false;
        reprint.current.nextAt = t + 6 + Math.random() * 7;
      }
    });
  }, []);

  const texture = useMemo(() => makeSheetTexture(mode, variant, withStamp), [mode, variant, withStamp]);

  useFrame(() => {
    if (!group.current) return;
    const t = hallTime.current;
    // breathing bob only — orientation stays exactly as drawn
    group.current.position.y = position[1] + Math.sin(t * 0.3 + seed) * 0.1;
    if (unfold) {
      // the back sheets unfold like a drawing being spread open
      group.current.rotation.x = rotation[0] + Math.sin(t * 0.12 + seed) * 0.055;
    }
    // reprint flash: the sheet brightens while the reprint sweep runs
    if (materialRef.current) {
      const r = reprint.current;
      const phase = r.active ? Math.min(1, (t - r.startedAt) / 0.9) : -1;
      const flash = phase >= 0 ? Math.sin(phase * Math.PI) * 0.4 : 0;
      materialRef.current.opacity = (mode === "dark" ? 0.97 : 0.94) + flash * (mode === "dark" ? 0.03 : -0.12);
    }
  });

  return (
    <group ref={group} position={position} rotation={rotation}>
      <mesh>
        <planeGeometry args={[size[0], size[1]]} />
        <meshBasicMaterial ref={materialRef} map={texture} transparent opacity={mode === "dark" ? 0.97 : 0.94} side={THREE.DoubleSide} />
      </mesh>
      <lineSegments>
        <edgesGeometry args={[new THREE.PlaneGeometry(size[0], size[1])]} />
        <lineBasicMaterial color={c.edge} transparent opacity={0.9} />
      </lineSegments>
    </group>
  );
}

/** The planner's draughtsman: a light stream tracing its path. */
function TracingLine({ mode, points, speed = 0.1, offset = 0, hallTime }: { mode: CyanotypeMode; points: [number, number, number][]; speed?: number; offset?: number; hallTime: React.MutableRefObject<number> }) {
  const c = PALETTE[mode];
  const full = useMemo(() => points.map(p => new THREE.Vector3(...p)), [points]);
  const { line, material } = useMemo(() => {
    const geometry = new THREE.BufferGeometry().setFromPoints(full.slice(0, 2));
    const mat = new THREE.LineBasicMaterial({ color: c.lineBright, transparent: true, opacity: 0.85 });
    return { line: new THREE.Line(geometry, mat), material: mat };
  }, [full, c.lineBright]);
  const total = points.length - 1;

  useFrame(() => {
    const t = (hallTime.current * speed + offset) % 1;
    const head = Math.max(1, Math.ceil(t * total));
    line.geometry.setFromPoints(full.slice(0, head + 1));
    material.opacity = 0.35 + 0.6 * Math.sin(t * Math.PI);
  });

  return <primitive object={line} />;
}

/** Diagonal light beams — ruler-straight, sweeping slowly. */
function LightBeams({ mode, hallTime }: { mode: CyanotypeMode; hallTime: React.MutableRefObject<number> }) {
  const c = PALETTE[mode];
  const group = useRef<THREE.Group>(null);
  useFrame(() => {
    if (!group.current) return;
    const t = hallTime.current;
    group.current.children.forEach((child, i) => {
      const mat = (child as THREE.Mesh).material as THREE.MeshBasicMaterial;
      mat.opacity = 0.05 + 0.035 * Math.sin(t * 0.4 + i * 1.7);
    });
  });
  return (
    <group ref={group}>
      {[[-5.5, 4.5, -6], [-1.5, 5, -7], [2.5, 4.8, -6.4], [6.5, 4.6, -7.5]].map(([x, y, z], i) => (
        <mesh key={i} position={[x, y, z]} rotation={[0, 0, 0.6 + i * 0.07]}>
          <planeGeometry args={[0.34, 14]} />
          <meshBasicMaterial
            color={c.beam}
            transparent
            opacity={0.06}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
            side={THREE.DoubleSide}
          />
        </mesh>
      ))}
    </group>
  );
}

/** Wireframe structures assembling — piece by piece, minimal drift. */
function Structure({ mode, position, kind, scale = 1, hallTime }: { mode: CyanotypeMode; position: [number, number, number]; kind: "icosa" | "cone" | "knot" | "dodeca"; scale?: number; hallTime: React.MutableRefObject<number> }) {
  const c = PALETTE[mode];
  const ref = useRef<THREE.Mesh>(null);
  useFrame(() => {
    if (ref.current) {
      const t = hallTime.current;
      ref.current.rotation.y = t * 0.03;      // barely turning
      ref.current.rotation.x = Math.sin(t * 0.1) * 0.05;
    }
  });
  return (
    <mesh ref={ref} position={position} scale={scale}>
      {kind === "icosa" && <icosahedronGeometry args={[1.5, 1]} />}
      {kind === "cone" && <coneGeometry args={[1, 2.6, 7, 4, true]} />}
      {kind === "knot" && <torusKnotGeometry args={[0.8, 0.26, 90, 10]} />}
      {kind === "dodeca" && <dodecahedronGeometry args={[1.1, 0]} />}
      <meshBasicMaterial
        color={kind === "icosa" ? c.icosa : kind === "knot" ? c.lineBright : c.cone}
        wireframe
        transparent
        opacity={mode === "dark" ? 0.6 : 0.45}
      />
    </mesh>
  );
}

/** The Planet: a drafting globe — prussian seas, blueprint meridians.
 *  It turns slowly, weaving the threads that draw every sheet. */
function Planet({ mode, hallTime, position, scale = 1, withHalo = false }: { mode: CyanotypeMode; hallTime: React.MutableRefObject<number>; position: [number, number, number]; scale?: number; withHalo?: boolean }) {
  const c = PALETTE[mode];
  const globe = useRef<THREE.Mesh>(null);
  const graticule = useRef<THREE.LineSegments>(null);

  // graticule: meridians + parallels as line segments (the drafting globe)
  const graticuleGeometry = useMemo(() => {
    const pts: THREE.Vector3[] = [];
    const R = 1.25;
    for (let i = 0; i < 10; i++) {
      const lon = (i / 10) * Math.PI * 2;
      for (let a = 0; a < 24; a++) {
        const t1 = (a / 24) * Math.PI * 2;
        const t2 = ((a + 1) / 24) * Math.PI * 2;
        pts.push(new THREE.Vector3(
          R * Math.sin(t1) * Math.cos(lon), R * Math.cos(t1), R * Math.sin(t1) * Math.sin(lon),
        ), new THREE.Vector3(
          R * Math.sin(t2) * Math.cos(lon), R * Math.cos(t2), R * Math.sin(t2) * Math.sin(lon),
        ));
      }
    }
    for (let i = 1; i < 6; i++) {
      const lat = -Math.PI / 2 + (i / 6) * Math.PI;
      const r = R * Math.cos(lat);
      const y = R * Math.sin(lat);
      for (let a = 0; a < 36; a++) {
        const t1 = (a / 36) * Math.PI * 2;
        const t2 = ((a + 1) / 36) * Math.PI * 2;
        pts.push(new THREE.Vector3(r * Math.cos(t1), y, r * Math.sin(t1)),
                 new THREE.Vector3(r * Math.cos(t2), y, r * Math.sin(t2)));
      }
    }
    return new THREE.BufferGeometry().setFromPoints(pts);
  }, []);

  useFrame(() => {
    const t = hallTime.current;
    if (globe.current) globe.current.rotation.y = t * 0.05;
    if (graticule.current) graticule.current.rotation.y = t * 0.05;
  });

  const halo = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 128; canvas.height = 128;
    const ctx = canvas.getContext("2d")!;
    const g = ctx.createRadialGradient(64, 64, 30, 64, 64, 64);
    g.addColorStop(0, "rgba(90,140,255,0.4)");
    g.addColorStop(0.7, "rgba(62,107,255,0.12)");
    g.addColorStop(1, "rgba(62,107,255,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, 128, 128);
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
      map: new THREE.CanvasTexture(canvas),
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }));
    sprite.scale.setScalar(4.6 * scale);
    return sprite;
  }, []);

  return (
    <group position={position} scale={scale}>
      <primitive object={halo} />
      <mesh ref={globe}>
        <sphereGeometry args={[1.22, 32, 24]} />
        <meshBasicMaterial color={mode === "dark" ? "#0a1e4d" : "#a8bfe8"} />
      </mesh>
      <lineSegments ref={graticule}>
        <primitive object={graticuleGeometry} attach="geometry" />
        <lineBasicMaterial color={c.edge} transparent opacity={mode === "dark" ? 0.95 : 0.8} />
      </lineSegments>
    </group>
  );
}

/** A thread of the planet: a THICK glowing tube arcing to a sheet, woven
 *  stitch by stitch by a knitting head — with a wireframe patch that
 *  materializes on the sheet where the thread lands. */
function Thread({
  mode, from, to, landAt, hallTime, speed = 0.14, offset = 0,
}: {
  mode: CyanotypeMode;
  from: [number, number, number];
  to: [number, number, number];
  landAt?: [number, number, number];
  hallTime: React.MutableRefObject<number>;
  speed?: number;
  offset?: number;
}) {
  const c = PALETTE[mode];
  const curve = useMemo(() => {
    const a = new THREE.Vector3(...from);
    const b = new THREE.Vector3(...to);
    const mid = a.clone().add(b).multiplyScalar(0.5);
    mid.y += 1.9;
    return new THREE.QuadraticBezierCurve3(a, mid, b);
  }, [from, to]);

  const tube = useMemo(
    () => new THREE.TubeGeometry(curve, 48, 0.035, 8, false),
    [curve],
  );
  const tubeMat = useMemo(
    () => new THREE.MeshBasicMaterial({
      color: c.lineBright, transparent: true, opacity: 0.85,
      blending: THREE.AdditiveBlending, depthWrite: false,
    }),
    [c.lineBright],
  );
  const tubeMesh = useMemo(() => new THREE.Mesh(tube, tubeMat), [tube, tubeMat]);

  // the knitting head: a bright glow sprite riding the weave point
  const headSprite = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 64; canvas.height = 64;
    const ctx = canvas.getContext("2d")!;
    const g = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
    g.addColorStop(0, "rgba(210,228,255,1)");
    g.addColorStop(0.3, "rgba(130,170,255,0.95)");
    g.addColorStop(1, "rgba(62,107,255,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, 64, 64);
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
      map: new THREE.CanvasTexture(canvas),
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }));
    sprite.scale.setScalar(0.6);
    return sprite;
  }, []);

  // the patch: a small wireframe lattice that GROWS on the sheet where the
  // thread lands — the blueprint being knitted into existence
  const patch = useRef<THREE.Group>(null);
  const patchEdges = useMemo(() => {
    const g = new THREE.Group();
    const land = new THREE.Vector3(...(landAt || to));
    const cell = 0.34;
    for (let i = -1; i <= 1; i++) {
      for (let j = -1; j <= 1; j++) {
        const quad = new THREE.PlaneGeometry(cell, cell);
        const edges = new THREE.EdgesGeometry(quad);
        const mesh = new THREE.LineSegments(
          edges,
          new THREE.LineBasicMaterial({ color: c.lineBright, transparent: true, opacity: 0 }),
        );
        mesh.position.set(land.x + i * cell, land.y + j * cell, land.z + 0.02);
        g.add(mesh);
      }
    }
    return g;
  }, [landAt, to, c.lineBright]);

  useFrame(() => {
    const t = (hallTime.current * speed + offset) % 1.5; // weave, hold, restart
    const head = Math.min(1, t);

    // draw the tube progressively (rebuild geometry is cheap at 48 segments)
    const drawn = curve.getPoints(Math.max(2, Math.ceil(head * 48)));
    const sub = new THREE.TubeGeometry(
      new THREE.CatmullRomCurve3(drawn), Math.max(4, Math.ceil(head * 48)), 0.035, 8, false,
    );
    tubeMesh.geometry.dispose();
    tubeMesh.geometry = sub;

    // knitting head rides the weave point
    const weavePoint = curve.getPoint(head);
    headSprite.position.copy(weavePoint);
    headSprite.visible = t <= 1.05;

    // patch cells materialize one by one once the thread lands
    if (patch.current) {
      patch.current.children.forEach((cellMesh, idx) => {
        const mat = (cellMesh as THREE.LineSegments).material as THREE.LineBasicMaterial;
        const appear = Math.min(1, Math.max(0, (head - 0.9) * 10 - idx * 0.09));
        mat.opacity = appear * 0.9;
      });
      patch.current.visible = head > 0.88;
    }
  });

  return (
    <>
      <primitive object={tubeMesh} />
      <primitive object={headSprite} />
      <group ref={patch}>{patchEdges.children.map((child, i) => (
        <primitive object={child} key={i} />
      ))}</group>
    </>
  );
}

/** Small drafting cubes orbiting the planet — satellites of the workshop. */
function OrbitingCubes({ mode, hallTime }: { mode: CyanotypeMode; hallTime: React.MutableRefObject<number> }) {
  const c = PALETTE[mode];
  const group = useRef<THREE.Group>(null);
  useFrame(() => {
    if (group.current) group.current.rotation.y = hallTime.current * 0.18;
  });
  const cubes = useMemo(() => [0, 1, 2, 3].map(i => {
    const angle = (i / 4) * Math.PI * 2;
    return { position: [Math.cos(angle) * 2.3, 0.4 + (i % 2) * 0.5, Math.sin(angle) * 2.3] as [number, number, number], rotation: [i * 0.4, i * 0.7, 0] as [number, number, number] };
  }), []);
  return (
    <group ref={group} position={[0.3, 2.6, -7.3]}>
      {cubes.map((cube, i) => (
        <mesh key={i} position={cube.position} rotation={cube.rotation}>
          <boxGeometry args={[0.26, 0.26, 0.26]} />
          <meshBasicMaterial color={c.edge} wireframe transparent opacity={mode === "dark" ? 0.7 : 0.5} />
        </mesh>
      ))}
    </group>
  );
}

/** Graphite dust — sparse drifting points (not a starfield). */
function Dust({ mode, count = 220, hallTime }: { mode: CyanotypeMode; count?: number; hallTime: React.MutableRefObject<number> }) {
  const c = PALETTE[mode];
  const ref = useRef<THREE.Points>(null);
  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      arr[i * 3] = (Math.random() - 0.5) * 26;
      arr[i * 3 + 1] = Math.random() * 9 - 1;
      arr[i * 3 + 2] = (Math.random() - 0.5) * 18 - 2;
    }
    return arr;
  }, [count]);
  useFrame(() => {
    if (ref.current) ref.current.position.y = Math.sin(hallTime.current * 0.07) * 0.3;
  });
  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial color={c.dust} size={0.05} transparent opacity={mode === "dark" ? 0.8 : 0.55} sizeAttenuation />
    </points>
  );
}

function GridFloor({ mode }: { mode: CyanotypeMode }) {
  const c = PALETTE[mode];
  return (
    <>
      <gridHelper args={[46, 46, c.grid, c.grid]} position={[0, -1.7, 0]} />
      <gridHelper args={[46, 8, c.line, c.line]} position={[0, -1.69, 0]} />
    </>
  );
}

/** Fixed drafting angle — the camera GLIDES laterally, never rotates. */
function CameraGlide({ hallTime }: { hallTime: React.MutableRefObject<number> }) {
  const { camera } = useThree();
  useFrame(() => {
    const t = hallTime.current;
    const x = Math.sin(t * 0.1) * 0.5;      // slow lateral glide
    const y = 0.9 + Math.sin(t * 0.13) * 0.12; // gentle bob
    camera.position.x += (x - camera.position.x) * 0.05;
    camera.position.y += (y - camera.position.y) * 0.05;
    camera.lookAt(0.4, 2.1, -4);            // same bearing, always
  });
  return null;
}

function Scene({ mode }: { mode: CyanotypeMode }) {
  const c = PALETTE[mode];
  const hallTime = useHallTime();

  useFrame(() => {
    for (const fn of reprintWatchers) fn(hall.t);
  });

  return (
    <>
      <color attach="background" args={[c.bg]} />
      <fog attach="fog" args={[c.fog, 10, 30]} />
      <CameraGlide hallTime={hallTime} />
      <GridFloor mode={mode} />
      <Dust mode={mode} hallTime={hallTime} />
      <LightBeams mode={mode} hallTime={hallTime} />
      <Sheet mode={mode} hallTime={hallTime} spec={{ position: [3.6, 2.3, -4.2], rotation: [-0.03, -0.55, -0.04], size: [6.2, 4.6], seed: 0, withStamp: true }} />
      <Sheet mode={mode} hallTime={hallTime} spec={{ position: [-4.9, 2.0, -5.4], rotation: [0.05, 0.52, 0.03], size: [5.4, 4], seed: 1, withStamp: false, unfold: true }} />
      <Sheet mode={mode} hallTime={hallTime} spec={{ position: [1.2, 3.4, -9.5], rotation: [0.08, 0.1, 0.05], size: [5, 3.8], seed: 2, withStamp: false, unfold: true }} />
      <TracingLine mode={mode} hallTime={hallTime} offset={0} points={[[-6.5, 0.5, -2], [-4.6, 1.8, -3.6], [-1.4, 2.8, -5.8], [1.6, 1.6, -4.3], [4.6, 2.6, -6.4]]} />
      <TracingLine mode={mode} hallTime={hallTime} offset={0.45} speed={0.085} points={[[6.2, 0.9, -1.4], [3.8, 2.6, -4.4], [0.6, 3.4, -7.6], [-3.4, 2, -5.4]]} />
      <TracingLine mode={mode} hallTime={hallTime} offset={0.75} speed={0.11} points={[[0.2, 1.2, -2.6], [2.2, 2.2, -4.8], [5.4, 1.4, -6.8], [7.4, 2.4, -8.2]]} />
      <Structure mode={mode} hallTime={hallTime} position={[-7.2, 0.6, -4.2]} kind="icosa" />
      <Structure mode={mode} hallTime={hallTime} position={[7.8, 0.3, -5.6]} kind="cone" />
      <Structure mode={mode} hallTime={hallTime} position={[6.2, 4.4, -10.5]} kind="knot" />
      <Structure mode={mode} hallTime={hallTime} position={[-6.8, 4.2, -9.8]} kind="dodeca" />
      <OrbitingCubes mode={mode} hallTime={hallTime} />
      {/* The Planet — knitting every blueprint into existence */}
      <Planet mode={mode} hallTime={hallTime} position={[-2.6, 4.3, -7.2]} scale={1.45} withHalo />
      {/* Three strands woven to the big stamped sheet */}
      <Thread mode={mode} hallTime={hallTime} offset={0} speed={0.15}
        from={[-1.7, 3.8, -7.2]} to={[2.6, 2.6, -4.1]} landAt={[2.3, 2.5, -4.05]} />
      <Thread mode={mode} hallTime={hallTime} offset={0.18} speed={0.15}
        from={[-1.9, 3.6, -7.3]} to={[3.6, 2.2, -4.2]} landAt={[3.3, 2.0, -4.15]} />
      <Thread mode={mode} hallTime={hallTime} offset={0.36} speed={0.15}
        from={[-2.1, 3.4, -7.4]} to={[4.2, 2.6, -4.3]} landAt={[3.9, 2.4, -4.25]} />
      {/* Two strands to the left sheet */}
      <Thread mode={mode} hallTime={hallTime} offset={0.55} speed={0.13}
        from={[-2.0, 3.5, -7.3]} to={[-4.6, 2.2, -5.4]} landAt={[-4.3, 2.1, -5.3]} />
      <Thread mode={mode} hallTime={hallTime} offset={0.7} speed={0.13}
        from={[-2.3, 3.3, -7.4]} to={[-5.2, 2.6, -5.5]} landAt={[-4.9, 2.5, -5.4]} />
      {/* One strand to the back sheet */}
      <Thread mode={mode} hallTime={hallTime} offset={0.9} speed={0.11}
        from={[-1.4, 3.9, -7.5]} to={[1.0, 3.3, -9.6]} landAt={[0.9, 3.2, -9.5]} />
    </>
  );
}

export default function CyanotypeScene({ mode = "dark", tempo = 1 }: { mode?: CyanotypeMode; tempo?: number }) {
  useEffect(() => {
    setHallTempo(tempo);
  }, [tempo]);

  return (
    <div style={{ position: "absolute", inset: 0, zIndex: 0 }} aria-hidden="true">
      <Canvas
        camera={{ position: [0, 0.9, 8.2], fov: 58 }}
        dpr={[1, 1.75]}
        gl={{ antialias: true, powerPreference: "high-performance" }}
        style={{ position: "absolute", inset: 0 }}
      >
        <Scene mode={mode} />
      </Canvas>
    </div>
  );
}
