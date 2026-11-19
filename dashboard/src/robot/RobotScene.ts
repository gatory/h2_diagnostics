/**
 * RobotScene: the three.js side of the 3D view. Owns the renderer, camera, lights
 * and the loaded URDF robot, and runs its own animation loop.
 *
 * It *pulls* data: each frame it asks getSnapshot() for the newest snapshot and,
 * if it changed, applies poseFromSnapshot() and jointColors(). React never
 * re-renders the scene (same "keep newest, use it on our own tick" pattern as
 * LiveSource). Clicks go the other way, through the `onSelect` callback.
 *
 * Frames: the URDF is ROS-style Z-up; three.js is Y-up. The robot sits inside a
 * `world` group rotated -90° about X, so everything inside stays in URDF frames.
 * What stays still (pose.ts resolveFrame): on the "ground" the lowest foot is put on
 * the grid every update; on the "gantry" the pelvis stays at standing height.
 *
 * Hands: two sets, each shown or hidden with setHandsVisible():
 *  - "h2":   H2.urdf's own static hand on each `*_hand_link` (no finger joints; it takes
 *            the wrist_yaw colour, as part of that link);
 *  - "dex5": the two Dex5 URDFs, mounted on the same links (DEX5_MOUNT), fingers posed
 *            from hand q and coloured per finger motor.
 * Both can be on at once (to compare the fit). A Dex5 that fails to load is reported
 * in handErrors and the rest still works.
 */
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import URDFLoader, { type URDFJoint, type URDFRobot } from "urdf-loader";
import type { Snapshot } from "../contract/snapshot";
import type { Side } from "../panels/hands";
import { DEX5_URDF, drawable, handAngles, handColors } from "./handPose";
import { jointColors } from "./heat";
import { poseFromSnapshot, resolveFrame, type FrameChoice } from "./pose";

export const H2_URDF_URL = "/renders/h2_description/H2.urdf";

/**
 * Where each Dex5 base sits in its `*_hand_link` frame (hand_link X runs along the
 * forearm, out of the wrist). Dex5 frame: fingers point +Y; the palm's wrist end is at
 * y = -0.040. Fitted by eye against H2.urdf's placeholder hand; NOT a Unitree number.
 * `axes` gives where Dex5's own x, y, z axes point in hand_link's frame.
 */
const DEX5_MOUNT: Record<Side, { xyz: [number, number, number]; axes: [Vec3, Vec3, Vec3] }> = {
  left: { xyz: [0.0546, -0.0126, 0.0269], axes: [[0, 0, 1], [1, 0, 0], [0, 1, 0]] },
  right: { xyz: [0.0533, 0.012, 0.0261], axes: [[0, 0, 1], [1, 0, 0], [0, 1, 0]] },
};
type Vec3 = [number, number, number];

/** One mounted Dex5: its moving joints and meshes, both keyed by the joint's child link. */
interface HandModel {
  root: THREE.Object3D;
  joints: Map<string, URDFJoint>;
  meshes: Map<string, THREE.Mesh[]>;
}

export type HandSet = "h2" | "dex5";

const SELECTED_GLOW = 0x1d3f66; // emissive tint on the selected link
const CLICK_SLOP_PX = 5; // a pointer that moved further was an orbit drag, not a click

export class RobotScene {
  /** Called with the clicked URDF joint name, or null when clicking empty space. */
  onSelect: ((urdfJoint: string | null) => void) | null = null;

  private readonly container: HTMLElement;
  private readonly getSnapshot: () => Snapshot | null;
  private readonly renderer: THREE.WebGLRenderer;
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.PerspectiveCamera(35, 1, 0.05, 50);
  private readonly controls: OrbitControls;
  private readonly world = new THREE.Group(); // Z-up -> Y-up
  private readonly resize: ResizeObserver;
  private robot: URDFRobot | null = null;
  private lastSnap: Snapshot | null = null;
  private frame = 0;

  /** URDF joint name -> the meshes that joint's motor moves (its link, plus fixed children). */
  private readonly linkMeshes = new Map<string, THREE.Mesh[]>();
  /** Mesh -> URDF joint name, for picking (null: clickable but not a body joint, e.g. fingers). */
  private readonly meshJoint = new Map<THREE.Object3D, string | null>();
  private readonly hands = new Map<Side, HandModel>();
  /** H2.urdf's own hand visuals (one per side). */
  private readonly h2Hands: THREE.Object3D[] = [];
  private readonly handsVisible: Record<HandSet, boolean> = { h2: false, dex5: true };
  private frameChoice: FrameChoice = "auto";
  /** world.position.y that puts the feet on the grid at the zero pose (= pelvis at standing height). */
  private standY = 0;
  /** Foot meshes (both ankle links of both legs): what touches the floor. */
  private feet: THREE.Mesh[] = [];
  /** Why a Dex5 hand is missing, e.g. "left: could not load mesh …" (empty when fine). */
  readonly handErrors: string[] = [];
  private selected: string | null = null;
  private downAt: { x: number; y: number } | null = null;

  constructor(container: HTMLElement, getSnapshot: () => Snapshot | null) {
    this.container = container;
    this.getSnapshot = getSnapshot;

    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(this.renderer.domElement);

    this.scene.background = new THREE.Color(0x101418);
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x404050, 2.0));
    const sun = new THREE.DirectionalLight(0xffffff, 2.0);
    sun.position.set(2, 4, 3);
    this.scene.add(sun);

    this.world.rotation.x = -Math.PI / 2;
    this.scene.add(this.world);

    this.camera.position.set(2.2, 1.4, 2.6);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.target.set(0, 0.9, 0);
    this.controls.enableDamping = true;

    const canvas = this.renderer.domElement;
    canvas.addEventListener("pointerdown", this.onPointerDown);
    canvas.addEventListener("pointerup", this.onPointerUp);

    this.resize = new ResizeObserver(() => this.fit());
    this.resize.observe(container);
    this.fit();
  }

  /**
   * Loads the body, then the two Dex5 hands. Resolves once everything is in; a Dex5
   * that fails is recorded in handErrors, the body failing rejects.
   */
  async load(url = H2_URDF_URL): Promise<void> {
    const robot = await loadUrdf(url);
    this.robot = robot;
    this.world.add(robot);
    this.indexLinks(robot);
    this.placeOnFloor(robot); // before the hands: measured at the zero pose, hands don't change the height
    for (const side of ["left", "right"] as const) {
      // Its visual is a direct child of the link.
      const link = robot.links[`${side}_hand_link`];
      for (const child of link?.children ?? []) if ((child as { isURDFVisual?: boolean }).isURDFVisual) this.h2Hands.push(child);
    }
    this.applyHandVisibility();
    await Promise.all(
      (["left", "right"] as const).map((side) =>
        this.mountHand(robot, side).catch((e: unknown) => {
          this.handErrors.push(`${side}: ${e instanceof Error ? e.message : String(e)}`);
        }),
      ),
    );
    this.applyHandVisibility();
    this.lastSnap = null; // re-apply pose + colours to the finished model
  }

  /** What stays still: the floor, the pelvis, or whatever the bridge's estimate says. */
  setFrame(choice: FrameChoice): void {
    this.frameChoice = choice;
    this.lastSnap = null; // re-place on the next frame, even without a new snapshot
  }

  /** Show or hide one set of hands. Works before the hands have loaded too. */
  setHandsVisible(set: HandSet, visible: boolean): void {
    this.handsVisible[set] = visible;
    this.applyHandVisibility();
  }

  start(): this {
    const loop = () => {
      this.frame = requestAnimationFrame(loop);
      this.update();
      this.controls.update();
      this.renderer.render(this.scene, this.camera);
    };
    loop();
    return this;
  }

  /** Highlight a joint's link (null clears). Does not call onSelect. */
  select(urdfJoint: string | null): void {
    for (const mesh of this.linkMeshes.get(this.selected ?? "") ?? []) material(mesh).emissive.setHex(0);
    this.selected = urdfJoint && this.linkMeshes.has(urdfJoint) ? urdfJoint : null;
    for (const mesh of this.linkMeshes.get(this.selected ?? "") ?? []) material(mesh).emissive.setHex(SELECTED_GLOW);
  }

  dispose(): void {
    cancelAnimationFrame(this.frame);
    const canvas = this.renderer.domElement;
    canvas.removeEventListener("pointerdown", this.onPointerDown);
    canvas.removeEventListener("pointerup", this.onPointerUp);
    this.resize.disconnect();
    this.controls.dispose();
    this.renderer.dispose();
    canvas.remove();
  }

  // ---- internals ------------------------------------------------------------------

  private update(): void {
    const snap = this.getSnapshot();
    if (!this.robot || !snap || snap === this.lastSnap) return;
    this.lastSnap = snap;
    const pose = poseFromSnapshot(snap);
    // Frozen: keep the last good joint angles on screen rather than guessing.
    if (!pose.frozen) this.robot.setJointValues(pose.joints);
    if (pose.tilt) this.robot.rotation.set(pose.tilt[0], pose.tilt[1], 0, "ZYX");
    this.placeWorld(resolveFrame(snap, this.frameChoice));
    // Temperatures are valid even when the pose is frozen.
    for (const [joint, color] of jointColors(snap)) {
      for (const mesh of this.linkMeshes.get(joint) ?? []) material(mesh).color.setHex(color);
    }
    for (const [side, model] of this.hands) {
      const hand = snap.hands[side];
      if (!hand) continue; // no data: keep the last picture
      for (const [link, q] of handAngles(hand, side)) {
        const joint = model.joints.get(link);
        if (joint && drawable(q, joint.limit.lower, joint.limit.upper)) joint.setJointValue(q);
      }
      for (const [link, color] of handColors(hand, side, snap.warnings)) {
        for (const mesh of model.meshes.get(link) ?? []) material(mesh).color.setHex(color);
      }
    }
  }

  /** Load one Dex5 and mount it on the body's hand link. */
  private async mountHand(body: URDFRobot, side: Side): Promise<void> {
    const handLink = body.links[`${side}_hand_link`];
    if (!handLink) throw new Error(`H2.urdf has no ${side}_hand_link`);
    const dex5 = await loadUrdf(DEX5_URDF[side]);
    const { xyz, axes } = DEX5_MOUNT[side];
    const [ax, ay, az] = axes.map((a) => new THREE.Vector3(...a));
    dex5.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(ax, ay, az));
    dex5.position.set(...xyz);

    const model: HandModel = { root: dex5, joints: new Map(), meshes: new Map() };
    dex5.traverse((obj) => {
      if (!isMovingJoint(obj)) return;
      const link = obj.children.find((c) => (c as { isURDFLink?: boolean }).isURDFLink);
      if (!link) return;
      const meshes: THREE.Mesh[] = []; // this link's own visual, not the next finger segment's
      for (const c of link.children) {
        if (!isMovingJoint(c)) c.traverse((m) => void ((m as THREE.Mesh).isMesh && meshes.push(m as THREE.Mesh)));
      }
      model.joints.set(link.name, obj);
      model.meshes.set(link.name, meshes);
    });
    dex5.traverse((obj) => {
      if (!(obj as THREE.Mesh).isMesh) return;
      const mesh = obj as THREE.Mesh;
      const mat = material(mesh).clone();
      mat.transparent = false; // the vendor URDF makes the palm 70% opaque; draw it solid like the body
      mat.opacity = 1;
      mesh.material = mat;
      this.meshJoint.set(mesh, null); // clicking a finger selects nothing (hand panel has the detail)
    });
    handLink.add(dex5);
    this.hands.set(side, model);
  }

  private applyHandVisibility(): void {
    for (const obj of this.h2Hands) obj.visible = this.handsVisible.h2;
    for (const model of this.hands.values()) model.root.visible = this.handsVisible.dex5;
  }

  /**
   * For each moving joint, collect the meshes its motor carries: its child link plus
   * anything attached by fixed joints (hand placeholder, camera), stopping at the next
   * moving joint. Each mesh gets its own material: the URDF shares one "white"
   * material between many links, and colouring a shared one would colour them all.
   */
  private indexLinks(robot: URDFRobot): void {
    const collect = (obj: THREE.Object3D, out: THREE.Mesh[]) => {
      for (const child of obj.children) {
        if (isMovingJoint(child)) continue;
        if ((child as THREE.Mesh).isMesh) out.push(child as THREE.Mesh);
        collect(child, out);
      }
    };
    robot.traverse((obj) => {
      if (!isMovingJoint(obj)) return;
      const meshes: THREE.Mesh[] = [];
      collect(obj, meshes);
      for (const mesh of meshes) {
        mesh.material = material(mesh).clone();
        this.meshJoint.set(mesh, obj.name);
      }
      this.linkMeshes.set(obj.name, meshes);
    });
  }

  private readonly onPointerDown = (e: PointerEvent) => {
    this.downAt = { x: e.clientX, y: e.clientY };
  };

  private readonly onPointerUp = (e: PointerEvent) => {
    const down = this.downAt;
    this.downAt = null;
    if (!down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > CLICK_SLOP_PX) return;
    const rect = this.renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1,
    );
    const ray = new THREE.Raycaster();
    ray.setFromCamera(ndc, this.camera);
    // Raycasting ignores `visible`, so skip hits on hidden hands ourselves.
    const hit = ray.intersectObjects([...this.meshJoint.keys()], false).find((h) => shown(h.object));
    const joint = hit ? (this.meshJoint.get(hit.object) ?? null) : null;
    this.select(joint);
    this.onSelect?.(joint);
  };

  /**
   * The URDF root is the pelvis, so the feet start ~1 m below y=0. Measured once at
   * the zero pose: lift the robot so the feet stand on the grid at y=0, and aim the
   * camera at the chest.
   */
  private placeOnFloor(robot: URDFRobot): void {
    const box = new THREE.Box3().setFromObject(robot);
    this.standY = -box.min.y;
    this.world.position.y = this.standY;
    this.feet = ["left", "right"].flatMap((side) =>
      ["ankle_roll", "ankle_pitch"].flatMap((j) => this.linkMeshes.get(`${side}_${j}_joint`) ?? []),
    );
    this.scene.add(new THREE.GridHelper(4, 16, 0x3a4450, 0x242b33));
    const height = box.max.y - box.min.y;
    this.controls.target.set(0, height * 0.5, 0);
    this.camera.position.set(2.3, height * 0.7, 2.9);
  }

  /**
   * Gantry: pelvis at standing height, legs hang. Ground: shift the robot up/down so the
   * lowest point of either foot touches y = 0 (after the joints and tilt are applied).
   * Only height changes; there's no odometry, so the robot never walks across the grid.
   */
  private placeWorld(frame: "ground" | "gantry"): void {
    this.world.position.y = this.standY;
    if (frame !== "ground" || !this.feet.length) return;
    this.world.updateMatrixWorld(true);
    const box = new THREE.Box3();
    for (const mesh of this.feet) box.expandByObject(mesh);
    this.world.position.y -= box.min.y;
  }

  private fit(): void {
    const { clientWidth: w, clientHeight: h } = this.container;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }
}

/**
 * Loads a URDF and its meshes; resolves once every mesh has arrived.
 *
 * We count the mesh loads ourselves instead of using LoadingManager.onLoad, which
 * is unreliable here: it fires once right after the .urdf (before any mesh, giving
 * an empty bounding box and a NaN camera), and three.js merges duplicate requests
 * for the same URL without telling the second manager (React StrictMode mounts
 * twice in dev, so two scenes load the same meshes at once), so it may never fire.
 */
function loadUrdf(url: string): Promise<URDFRobot> {
  return new Promise((resolve, reject) => {
    const loader = new URDFLoader();
    loader.parseCollision = false; // visuals only
    let pending = 0;
    let robot: URDFRobot | null = null;
    const finishIfDone = () => {
      if (robot && pending === 0) resolve(robot);
    };
    // urdf-loader calls this once per <mesh> while parsing, before load()'s callback.
    const loadMesh = loader.defaultMeshLoader.bind(loader);
    loader.loadMeshCb = (path, manager, material, done) => {
      pending++;
      loadMesh(path, manager, material, (obj, err) => {
        done(obj, err);
        if (err) reject(new Error(`could not load mesh ${path}`));
        pending--;
        finishIfDone();
      });
    };
    loader.load(
      url,
      (r) => {
        robot = r;
        finishIfDone(); // in case there were no meshes at all
      },
      undefined,
      (err) => reject(err instanceof Error ? err : new Error(String(err))),
    );
  });
}

/** Visible itself and through all its parents. */
function shown(obj: THREE.Object3D | null): boolean {
  for (; obj; obj = obj.parent) if (!obj.visible) return false;
  return true;
}

function isMovingJoint(obj: THREE.Object3D): obj is URDFJoint {
  return (obj as URDFJoint).isURDFJoint === true && (obj as URDFJoint).jointType !== "fixed";
}

/** urdf-loader always builds MeshPhongMaterial (colour + emissive). */
function material(mesh: THREE.Mesh): THREE.MeshPhongMaterial {
  return mesh.material as THREE.MeshPhongMaterial;
}
