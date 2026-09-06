import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import openapiTS, { astToString } from "openapi-typescript";

// Build the canonical app in process, without its lifespan, DB, or model requests.
const root = fileURLToPath(new URL("../../", import.meta.url));
const env = Object.fromEntries(
  Object.entries(process.env).filter(([key]) => !key.startsWith("SOT_")),
);
const schema = JSON.parse(
  execFileSync(
    "uv",
    [
      "run",
      "--project",
      "backend",
      "python",
      "-c",
      "import json; from sot.bootstrap.app import build_app; from sot.bootstrap.settings import Settings; print(json.dumps(build_app(Settings(environment='test', development_auth=False, models=('test',))).openapi(), sort_keys=True))",
    ],
    { cwd: root, env, encoding: "utf8" },
  ),
);
const output = new URL("../src/generated/", import.meta.url);
mkdirSync(output, { recursive: true });
writeFileSync(
  new URL("openapi.json", output),
  JSON.stringify(schema, null, 2) + "\n",
);
writeFileSync(
  new URL("api.d.ts", output),
  astToString(await openapiTS(schema)),
);
