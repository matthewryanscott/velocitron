import {Equivalence, compare, type EquivUnavailableError} from "./dist/index.js";

export function compareUnavailable(): EquivUnavailableError {
  try {
    compare();
  } catch (error) {
    return error as EquivUnavailableError;
  }
}

export function resultUnavailable(): EquivUnavailableError {
  try {
    return new Equivalence() as never;
  } catch (error) {
    return error as EquivUnavailableError;
  }
}
