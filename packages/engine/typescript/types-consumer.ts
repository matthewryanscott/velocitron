import {
  Engine,
  HandlerRegistry,
  type CelAdapter,
  type Marking,
  type Net,
} from "./dist/index.js";

const adapter: CelAdapter = {
  compile(source: string): unknown {
    return source;
  },
  evaluate(): unknown {
    return false;
  },
};

export function quiesce(net: Net, marking: Marking): Marking {
  const engine = new Engine(new HandlerRegistry(), {celAdapter: adapter});
  return engine.run(net, marking, {maxSteps: 1});
}
