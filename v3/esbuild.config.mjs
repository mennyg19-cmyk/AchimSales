// esbuild build for the v3 front-end.
// Bundles TypeScript entrypoints from web/static_src/js and CSS from
// web/static_src/css into web/static_dist. Entrypoints are added as the
// front-end phase lands; an empty list is a valid no-op build.
import { build, context } from "esbuild";
import { existsSync } from "node:fs";

const entryPoints = [
  // "web/static_src/js/main.ts",
  // "web/static_src/css/main.css",
].filter((p) => existsSync(p));

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

if (entryPoints.length === 0) {
  console.log("[esbuild] no entrypoints yet - nothing to build (front-end phase pending).");
} else if (watch) {
  const ctx = await context(options);
  await ctx.watch();
  console.log("[esbuild] watching...");
} else {
  await build(options);
}
