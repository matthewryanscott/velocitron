import {
  Divergence,
  ReplayBase,
  ReplayCursor,
  ReplayNetMismatch,
  ReplayOrderError,
  ReplayResult,
  replayRun,
  type ReplayUnavailableError,
} from "./dist/index.js";

export function unavailable(): ReplayUnavailableError {
  try {
    return new ReplayCursor() as never;
  } catch (error) {
    return error as ReplayUnavailableError;
  }
}

export function baseUnavailable(): ReplayUnavailableError {
  try {
    return new ReplayBase() as never;
  } catch (error) {
    return error as ReplayUnavailableError;
  }
}

export function runUnavailable(): ReplayUnavailableError {
  try {
    replayRun();
  } catch (error) {
    return error as ReplayUnavailableError;
  }
}

export type Order = ReplayOrderError;
export type Mismatch = ReplayNetMismatch;
export type FirstDivergence = Divergence;
export type Result = ReplayResult;
