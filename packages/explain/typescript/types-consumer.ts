import {explainNet, type ExplainUnavailableError} from "./dist/index.js";

export function explainUnavailable(): ExplainUnavailableError {
  try {
    explainNet();
  } catch (error) {
    return error as ExplainUnavailableError;
  }
}
