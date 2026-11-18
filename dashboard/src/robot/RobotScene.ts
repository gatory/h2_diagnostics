/**
 * RobotScene: the three.js side of the 3D view. Owns the renderer, camera, lights
 * and the loaded URDF robot, and runs its own animation loop.
 *
 * It *pulls* data: each frame it asks getSnapshot() for the newest snapshot and
 * applies poseFromSnapshot() if it changed. React never re-renders the scene
 * (same "keep newest, use it on our own tick" pattern as LiveSource).
 *
 * Frames: the URDF is ROS-style Z-up; three.js is Y-up. The robot sits inside a
 * `world` group rotated -90° about X, so everything inside stays in URDF frames.
 */
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import URDFLoader, { type URDFRobot } from "urdf-loader";
import type { Snapshot } from "../contract/snapshot";
import { poseFromSnapshot } from "./pose";

export const H2_URDF_URL = "/renders/h2_description/H2.urdf";

export class RobotScene {
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

    this.resize = new ResizeObserver(() => this.fit());
    this.resize.observe(container);
    this.fit();
  }

  /**
   * Loads the URDF and its meshes; resolves once every mesh has arrived.
   *
   * We count the mesh loads ourselves instead of using LoadingManager.onLoad, which
   * is unreliable here: it fires once right after the .urdf (before any mesh, giving
   * an empty bounding box and a NaN camera), and three.js merges duplicate requests
   * for the same URL without telling the second manager (React StrictMode mounts
   * twice in dev, so two scenes load the same meshes at once), so it may never fire.
   */
  load(url = H2_URDF_URL): Promise<void> {
    return new Promise((resolve, reject) => {
      const loader = new URDFLoader();
      loader.parseCollision = false; // visuals only
      let pending = 0;
      let robot: URDFRobot | null = null;
      const finishIfDone = () => {
        if (robot && pending === 0) {
          this.placeOnFloor(robot);
          resolve();
        }
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
          this.robot = r;
          this.world.add(r);
          finishIfDone(); // in case there were no meshes at all
        },
        undefined,
        (err) => reject(err instanceof Error ? err : new Error(String(err))),
      );
    });
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

  dispose(): void {
    cancelAnimationFrame(this.frame);
    this.resize.disconnect();
    this.controls.dispose();
    this.renderer.dispose();
    this.renderer.domElement.remove();
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
  }

  /**
   * The URDF root is the pelvis, so the feet start ~1 m below y=0. Measured once at
   * the zero pose: lift the robot so the feet stand on the grid at y=0, and aim the
   * camera at the chest.
   */
  private placeOnFloor(robot: URDFRobot): void {
    const box = new THREE.Box3().setFromObject(robot);
    this.world.position.y = -box.min.y;
    this.scene.add(new THREE.GridHelper(4, 16, 0x3a4450, 0x242b33));
    const height = box.max.y - box.min.y;
    this.controls.target.set(0, height * 0.5, 0);
    this.camera.position.set(2.3, height * 0.7, 2.9);
  }

  private fit(): void {
    const { clientWidth: w, clientHeight: h } = this.container;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }
}
