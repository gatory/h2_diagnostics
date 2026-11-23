/**
 * RobotScene: the three.js side of the hero view. Owns renderer, camera, lights and the
 * URDF model, and runs its own animation loop that PULLS the newest snapshot each frame
 * (React never re-renders it).
 *
 * Frames: the URDF is ROS-style Z-up (X forward, Y left); three.js is Y-up. The robot
 * sits in a `world` group rotated -90° about X, so everything inside keeps URDF frames.
 * The robot then faces +X in three.js; the camera looks at it from the front-right.
 *
 * Joint angles come from derive.jointAngles (frozen while mode_pr says the slots aren't
 * angles); pelvis roll/pitch from the pelvis IMU (yaw dropped: it drifts, and the robot
 * should keep facing the viewer); colours from derive.jointColors.
 *
 * The FLOOR is the fixed reference, not the pelvis: after posing, the whole model is
 * moved up/down so the lower foot touches the floor (knees bend -> pelvis drops).
 * Only height is corrected; there's no odometry, so the robot never walks off the disc.
 */
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import URDFLoader, { type URDFJoint, type URDFRobot } from "urdf-loader";
import { jointAngles, jointColors } from "../derive";
import type { Snapshot } from "../types";

export const H2_URDF = "/h2_description/H2.urdf"; // dashboard/h2_renders/ is Vite's static folder

const FOOT_LINKS = ["left_ankle_roll_link", "right_ankle_roll_link"];
const BACKGROUND = 0xffffff; // tesla.design.md canvas
const FLOOR = 0xf4f4f4; // surface-soft

export class RobotScene {
  private readonly renderer: THREE.WebGLRenderer;
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.PerspectiveCamera(28, 1, 0.05, 50);
  private readonly controls: OrbitControls;
  private readonly world = new THREE.Group();
  private readonly resize: ResizeObserver;
  private robot: URDFRobot | null = null;
  /** URDF joint name -> materials of the link(s) that joint's motor moves. */
  private readonly linkMaterials = new Map<string, THREE.MeshPhongMaterial[]>();
  private lastSnap: Snapshot | null = null;
  private frame = 0;
  private size = new THREE.Vector3(1, 1.8, 1); // robot bounding box at the zero pose
  /** The links that touch the ground (the foot soles hang off the ankle roll joints). */
  private feet: THREE.Object3D[] = [];

  private readonly container: HTMLElement;
  private readonly getSnapshot: () => Snapshot | null;

  constructor(container: HTMLElement, getSnapshot: () => Snapshot | null) {
    this.container = container;
    this.getSnapshot = getSnapshot;
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(this.renderer.domElement);

    this.scene.background = new THREE.Color(BACKGROUND);
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0xb8bcc4, 2.2));
    const key = new THREE.DirectionalLight(0xffffff, 1.6);
    key.position.set(3, 5, 4);
    this.scene.add(key);

    this.world.rotation.x = -Math.PI / 2;
    this.scene.add(this.world);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.enablePan = false;

    this.resize = new ResizeObserver(() => this.fit());
    this.resize.observe(container);
    this.fit();
  }

  async load(url = H2_URDF): Promise<void> {
    const robot = await loadUrdf(url);
    this.robot = robot;
    this.world.add(robot);
    this.indexLinks(robot);

    this.feet = FOOT_LINKS.map((name) => robot.links[name]).filter((l): l is NonNullable<typeof l> => !!l);
    new THREE.Box3().setFromObject(robot).getSize(this.size);
    this.ground(); // the URDF root is the pelvis, ~1 m above the feet

    const floor = new THREE.Mesh(
      new THREE.CircleGeometry(this.size.y * 0.24, 96), // a pale disc just under the feet
      new THREE.MeshBasicMaterial({ color: FLOOR }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -0.001;
    this.scene.add(floor);

    this.frameCamera();
    this.lastSnap = null; // apply the current snapshot to the finished model
  }

  start(): void {
    const loop = () => {
      this.frame = requestAnimationFrame(loop);
      this.update();
      this.controls.update();
      this.renderer.render(this.scene, this.camera);
    };
    loop();
  }

  dispose(): void {
    cancelAnimationFrame(this.frame);
    this.resize.disconnect();
    this.controls.dispose();
    this.scene.traverse((obj) => {
      const mesh = obj as THREE.Mesh;
      if (!mesh.isMesh) return;
      mesh.geometry.dispose();
      for (const m of [mesh.material].flat()) m.dispose();
    });
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }

  // ---- internals ------------------------------------------------------------------

  private update(): void {
    const snap = this.getSnapshot();
    if (!this.robot || !snap || snap === this.lastSnap) return;
    this.lastSnap = snap;

    const angles = jointAngles(snap.body);
    if (angles) this.robot.setJointValues(angles); // null: keep the last good pose
    const rpy = snap.imu.pelvis?.rpy;
    if (rpy) this.robot.rotation.set(rpy[0], rpy[1], 0, "ZYX");
    this.ground();

    for (const [joint, color] of jointColors(snap)) {
      for (const mat of this.linkMaterials.get(joint) ?? []) mat.color.setHex(color);
    }
  }

  /** Move the model vertically so its lowest foot point sits on the floor (y = 0). */
  private ground(): void {
    const parts = this.feet.length ? this.feet : this.robot ? [this.robot] : [];
    if (!parts.length) return;
    this.world.updateMatrixWorld(true);
    const box = new THREE.Box3();
    for (const p of parts) box.expandByObject(p);
    if (!box.isEmpty()) this.world.position.y -= box.min.y;
  }

  /**
   * For each moving joint, the meshes its motor carries: its child link plus anything
   * fixed to it, up to the next moving joint. Each gets its own material, because the
   * URDF shares one "white" material between links and we colour them separately.
   */
  private indexLinks(robot: URDFRobot): void {
    const collect = (obj: THREE.Object3D, out: THREE.MeshPhongMaterial[]) => {
      for (const child of obj.children) {
        if (isMovingJoint(child)) continue;
        const mesh = child as THREE.Mesh;
        if (mesh.isMesh) {
          const mat = (mesh.material as THREE.MeshPhongMaterial).clone();
          mat.shininess = 12; // satin, not glossy plastic
          mesh.material = mat;
          out.push(mat);
        }
        collect(child, out);
      }
    };
    robot.traverse((obj) => {
      if (!isMovingJoint(obj)) return;
      const mats: THREE.MeshPhongMaterial[] = [];
      collect(obj, mats);
      this.linkMaterials.set(obj.name, mats);
    });
  }

  /** Front-right three-quarter view that fits the whole robot, whatever the aspect. */
  private frameCamera(): void {
    const h = this.size.y;
    const target = new THREE.Vector3(0, h * 0.5, 0);
    const vFov = THREE.MathUtils.degToRad(this.camera.fov);
    const fitH = (h * 0.62) / Math.tan(vFov / 2);
    const fitW = (h * 0.62) / Math.tan(vFov / 2) / Math.min(1, this.camera.aspect * 1.6);
    const dist = Math.max(fitH, fitW);
    const dir = new THREE.Vector3(1, 0.18, 0.62).normalize();
    this.camera.position.copy(target).addScaledVector(dir, dist);
    this.controls.target.copy(target);
    this.controls.minDistance = dist * 0.4;
    this.controls.maxDistance = dist * 2;
    this.controls.update();
  }

  private fit(): void {
    const { clientWidth: w, clientHeight: h } = this.container;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    if (this.robot) this.frameCamera();
  }
}

/**
 * Load a URDF and resolve once every mesh has arrived. We count mesh loads ourselves:
 * LoadingManager.onLoad fires right after the .urdf (before the meshes), and may never
 * fire when React StrictMode mounts twice and three.js merges the duplicate requests.
 */
function loadUrdf(url: string): Promise<URDFRobot> {
  return new Promise((resolve, reject) => {
    const loader = new URDFLoader();
    loader.parseCollision = false;
    let pending = 0;
    let robot: URDFRobot | null = null;
    const done = () => robot && pending === 0 && resolve(robot);
    const loadMesh = loader.defaultMeshLoader.bind(loader);
    loader.loadMeshCb = (path, manager, material, onLoad) => {
      pending++;
      loadMesh(path, manager, material, (obj, err) => {
        onLoad(obj, err);
        if (err) reject(new Error(`could not load mesh ${path}`));
        pending--;
        done();
      });
    };
    loader.load(
      url,
      (r) => {
        robot = r;
        done();
      },
      undefined,
      (err) => reject(err instanceof Error ? err : new Error(String(err))),
    );
  });
}

function isMovingJoint(obj: THREE.Object3D): obj is URDFJoint {
  return (obj as URDFJoint).isURDFJoint === true && (obj as URDFJoint).jointType !== "fixed";
}
