import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function safeInlineScript(code) {
  return code.replace(/<\/script/gi, "<\\/script").replace(/<!--/g, "<\\!--");
}

function safeInlineStyle(code) {
  return code.replace(/<\/style/gi, "<\\/style");
}

function rebaseInlineAssetUrls(code, bundle) {
  let next = code;

  for (const [fileName, asset] of Object.entries(bundle)) {
    if (asset.type !== "asset" || !fileName.includes("/")) continue;
    const basename = fileName.split("/").pop();
    if (!basename) continue;

    const rebased = `./${fileName}`;
    next = next.replace(
      new RegExp(`(["'])${escapeRegExp(basename)}\\1\\s*,\\s*import\\.meta\\.url`, "g"),
      (_, quote) => `${quote}${rebased}${quote},import.meta.url`
    );
  }

  return next;
}

function inlineFileRuntime() {
  return {
    name: "cyberdetect-inline-file-runtime",
    apply: "build",
    enforce: "post",
    generateBundle(_, bundle) {
      const html = bundle["index.html"];
      if (!html || html.type !== "asset") return;

      let source = String(html.source);

      for (const [fileName, asset] of Object.entries(bundle)) {
        if (asset.type === "chunk" && fileName.endsWith(".js")) {
          const scriptPattern = new RegExp(
            `<script type="module" crossorigin src="\\./${escapeRegExp(fileName)}"></script>`
          );
          if (scriptPattern.test(source)) {
            const code = rebaseInlineAssetUrls(asset.code, bundle);
            source = source.replace(
              scriptPattern,
              () => `<script type="module">\n${safeInlineScript(code)}\n</script>`
            );
            delete bundle[fileName];
          }
        }

        if (asset.type === "asset" && fileName.endsWith(".css")) {
          const stylePattern = new RegExp(
            `<link rel="stylesheet" crossorigin href="\\./${escapeRegExp(fileName)}">`
          );
          if (stylePattern.test(source)) {
            source = source.replace(
              stylePattern,
              () => `<style>\n${safeInlineStyle(String(asset.source))}\n</style>`
            );
            delete bundle[fileName];
          }
        }
      }

      html.source = source;
    },
  };
}

export default defineConfig(({ command }) => ({
  plugins: [react(), inlineFileRuntime()],
  ...(command === "serve"
    ? {
        optimizeDeps: {
          disabled: "dev",
        },
      }
    : {}),
}));
