import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// h2_renders/ holds the URDFs + meshes; serve it as the static folder, so
// h2_renders/h2_description/H2.urdf is fetched as /h2_description/H2.urdf.
export default defineConfig({
  plugins: [react()],
  publicDir: "h2_renders",
});
