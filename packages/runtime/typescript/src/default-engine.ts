import {createDefaultCelAdapter} from "@velocitron/cel";
import {
  Engine as PackageEngine,
  type HandlerRegistry,
  type EngineOptions as PackageEngineOptions,
} from "@velocitron/engine";

/** Package options with `celAdapter` optional. A missing adapter uses the default CEL backend. */
export interface EngineOptions extends Omit<PackageEngineOptions, "celAdapter"> {
  readonly celAdapter?: PackageEngineOptions["celAdapter"];
}

/** `@velocitron/engine` `Engine` with `createDefaultCelAdapter()` as the default. */
export class Engine extends PackageEngine {
  constructor(registry: HandlerRegistry, options: EngineOptions = {}) {
    super(registry, {
      ...options,
      celAdapter: options.celAdapter ?? createDefaultCelAdapter(),
    });
  }
}
