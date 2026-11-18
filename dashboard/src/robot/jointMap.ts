/**
 * Bridge joint names (layout.JOINTS, e.g. "L_knee") -> H2.urdf joint names
 * ("left_knee_joint"). Same rule as bridge/tests/test_layout.py::urdf_joint_name.
 *
 * Always map by NAME: the URDF lists the head before the arms, so its file order
 * is not the bridge's slot order.
 */
export function urdfJointName(layoutName: string): string {
  let name = layoutName;
  if (name.startsWith("L_")) name = "left_" + name.slice(2);
  else if (name.startsWith("R_")) name = "right_" + name.slice(2);
  return name.endsWith("_joint") ? name : name + "_joint";
}
