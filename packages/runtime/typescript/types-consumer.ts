import {
  Runtime,
  TokenArrival,
  intendedWaits,
  type RuntimeOptions,
} from "./dist/index.js";

export function declared(transition: Parameters<typeof intendedWaits>[0]): string[] {
  return intendedWaits(transition).map((wait) => wait.reason);
}

export function open(net: RuntimeOptions["net"], handlers: RuntimeOptions["handlers"]): Runtime {
  return new Runtime({
    net,
    handlers,
    lanes: {main: 1},
    celAdapter: {
      compile: (source) => source,
      evaluate: () => false,
    },
  });
}

export function arrival(place: string): TokenArrival {
  return new TokenArrival(place, {type: "job", data: {}});
}
