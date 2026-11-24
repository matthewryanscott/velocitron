import {existsSync} from "node:fs";
import {fileURLToPath} from "node:url";

// Parity tests import the installed leaf packages, so they need the
// integration-project venv: prefer it over whatever python3 is on PATH.
const VENV_PYTHON = fileURLToPath(new URL("../../../python/.venv/bin/python", import.meta.url));

export const PYTHON = existsSync(VENV_PYTHON) ? VENV_PYTHON : "python3";
