import {
  SYNTH_HANDLER,
  VelocitronNet,
  handlerSpec,
  type NetbaseUnavailableError,
  type Registration,
} from "./dist/index.js";

export function prefix(): string {
  return SYNTH_HANDLER;
}

export function unavailable(): NetbaseUnavailableError {
  try {
    return new VelocitronNet() as never;
  } catch (error) {
    return error as NetbaseUnavailableError;
  }
}

export function specUnavailable(): NetbaseUnavailableError {
  try {
    handlerSpec();
  } catch (error) {
    return error as NetbaseUnavailableError;
  }
}

export type Registered = Registration;
