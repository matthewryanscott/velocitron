import {
  capacityProperties,
  checkMarking,
  checkReplay,
  type PropertiesUnavailableError,
} from "./dist/index.js";

export function markingUnavailable(): PropertiesUnavailableError {
  try {
    checkMarking();
  } catch (error) {
    return error as PropertiesUnavailableError;
  }
}

export function replayUnavailable(): PropertiesUnavailableError {
  try {
    checkReplay();
  } catch (error) {
    return error as PropertiesUnavailableError;
  }
}

export function capacityUnavailable(): PropertiesUnavailableError {
  try {
    capacityProperties();
  } catch (error) {
    return error as PropertiesUnavailableError;
  }
}
