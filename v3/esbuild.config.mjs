// esbuild build for the v3 front-end.
// Bundles TypeScript entrypoints from web/static_src/js and CSS from
// web/static_src/css into web/static_dist. Entrypoints are added as the
// front-end phase lands; an empty list is a valid no-op build.
import { build, context } from "esbuild";
import { cpSync, existsSync } from "node:fs";

const entryPoints = [
  "web/static_src/js/main.ts",
  "web/static_src/js/report.ts",
  "web/static_src/js/schedules.ts",
  "web/static_src/js/settings.ts",
  "web/static_src/js/admin.ts",
  "web/static_src/js/dashboard.ts",
  "web/static_src/js/db_explorer.ts",
  "web/static_src/js/notif_diag.ts",
  "web/static_src/css/main.css",
].filter((p) => existsSync(p));

// Static passthrough assets (PWA manifest + icons) served from the static root.
// Not bundled - copied verbatim into static_dist so url_for('static', ...) resolves.
function copyPublic() {
  const src = "web/static_src/public";
  if (existsSync(src)) cpSync(src, "web/static_dist", { recursive: true });
}

const options = {
  entryPoints,
  bundle: true,
  minify: true,
  sourcemap: true,
  target: ["es2020"],
  outdir: "web/static_dist",
  logLevel: "info",
};

const watch = process.argv.includes("--watch");

copyPublic();

if (entryPoints.length === 0) {
  console.log("[esbuild] no entrypoints yet - nothing to build (front-end phase pending).");
} else if (watch) {
  const ctx = await context(options);
  await ctx.watch();
  console.log("[esbuild] watching...");
} else {
  await build(options);
}
