import {parseNet} from "@velocitron/petrinet";
import type {Marking, Net, ReadonlyJsonObject, Token} from "@velocitron/engine";
import type {TransitionHandlerOutput} from "@velocitron/engine";

export function token(type: string, data: ReadonlyJsonObject = {}): Token {
  return {type, data};
}

export function completed(
  outputTokens: Readonly<Record<string, readonly Token[]>> = {},
  metadata: ReadonlyJsonObject = {},
): TransitionHandlerOutput {
  return {status: "completed", outputTokens, error: null, metadata};
}

export function failed(type = "Failure", message = "declared failure"): TransitionHandlerOutput {
  return {
    status: "failed",
    outputTokens: {},
    error: {type, message},
    metadata: {observed: true},
  };
}

export function parsedNet(document: unknown): Net {
  return parseNet(document);
}

export function nonempty(marking: Marking): Marking {
  return Object.fromEntries(Object.entries(marking).filter(([, tokens]) => tokens.length > 0));
}
