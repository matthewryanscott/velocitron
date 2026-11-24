import {
  COMMANDS,
  VIZ_PROGRAM,
  main,
  vizMain,
  type CliUnavailableError,
  type Command,
} from "./dist/index.js";

export function commands(): readonly Command[] {
  return COMMANDS;
}

export function vizProgram(): string {
  return VIZ_PROGRAM;
}

export function unavailable(): CliUnavailableError {
  try {
    main();
  } catch (error) {
    return error as CliUnavailableError;
  }
}

export function vizUnavailable(): CliUnavailableError {
  try {
    vizMain();
  } catch (error) {
    return error as CliUnavailableError;
  }
}
