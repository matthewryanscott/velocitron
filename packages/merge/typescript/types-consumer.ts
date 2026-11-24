import {
  NetValidationError,
  mergeComposition,
  mergeNets,
  portFusionMap,
  type CompositionDocument,
  type Net,
} from "./dist/index.js";

export function mergeAlone(net: Net): Net {
  try {
    return mergeNets(new Map([["only", net]]), []);
  } catch (error) {
    if (error instanceof NetValidationError) {
      throw new Error(error.issues[0]?.message ?? error.message);
    }
    throw error;
  }
}

export function fuse(
  composition: CompositionDocument,
  nets: ReadonlyMap<string, Net>,
): ReadonlyMap<string, string> {
  mergeComposition(composition, nets);
  return portFusionMap(nets, composition.wires, composition.shares ?? []);
}
