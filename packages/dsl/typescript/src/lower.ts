import {
  CharStreams,
  CommonTokenStream,
  ParserRuleContext,
  Token,
} from "antlr4";
import type {
  ErrorListener,
  RecognitionException,
  Recognizer,
  TerminalNode,
} from "antlr4";

import {
  PETRINET_RESOURCE_LIMITS,
  PetrinetDslError,
  PetrinetResourceError,
} from "./diagnostics.js";
import type { Diagnostic, SourceSpan } from "./diagnostics.js";
// TODO: this lowerer vendors a second copy of the ANTLR parser that
// packages/grammar already generates. Layer lint forbids importing
// @velocitron/grammar/generated, and grammar's public parsePetrinet returns
// a tree without the token types and visitor base this module subclasses.
// Teach grammar to export that surface, then import it here.
// @velocitron/petrinet calls lowerPetrinetText and does not vendor another copy.
import VelocitronPetriNetLexer from "./generated/VelocitronPetriNetLexer.js";
import VelocitronPetriNetParser, {
  AdditionalChainContext,
  AdditionalInitialMarkingContext,
  AdditionalTemplateDefinitionContext,
  AdditionalTransitionHandlerContext,
  DomainValueContext,
} from "./generated/VelocitronPetriNetParser.js";
import type {
  ActorAssignmentContext,
  ActorDeclarationContext,
  PlaceLivesContext,
  PlaceReadsAsContext,
  PlaceKeptContext,
  ActorTargetContext,
  ArcCorrelateContext,
  ArcDataContext,
  ArcPredicateContext,
  ArcWeightContext,
  ChainContext,
  ChainOrderContext,
  ColorContext,
  CompositionHeaderContext,
  CompositionUseContext,
  CompositionWireContext,
  CompositionShareContext,
  CompositionPlaceContext,
  CompositionTransitionContext,
  CompositionRefineContext,
  CompositionFinalContext,
  DocumentContext,
  ExtensionsContext,
  InitialMarkingContext,
  JsonArrayContext,
  JsonObjectContext,
  JsonValueContext,
  ChainHandleContext,
  ChainNodeContext,
  MarkingValueContext,
  MetadataAnnotationContext,
  MetadataDescriptionContext,
  MetadataTargetContext,
  NamedMarkingContext,
  NetHeaderContext,
  PlaceAcceptsContext,
  PlaceCapacityContext,
  PlaceDeclarationContext,
  PlacePortContext,
  PositiveIntegerContext,
  PlaceContext,
  TemplateDefinitionContext,
  TemplateReferenceContext,
  TransitionDeclarationContext,
  TransitionContext,
  TransitionGuardContext,
  TransitionHandlerContext,
  TransitionOrderContext,
  TransitionPriorityContext,
  TransitionTimerBindContext,
  TransitionBindingNameContext,
  TransitionTimerContext,
  TransitionTimerMaturityContext,
  ViewPositionContext,
  ViewRouteContext,
  ViewSplinesContext,
  ViewDetailContext,
  ViewTargetContext,
  DecorationContext,
  DomainDeclarationContext,
  FinalDeclarationContext,
  InvariantDeclarationContext,
} from "./generated/VelocitronPetriNetParser.js";
import VelocitronPetriNetVisitor from "./generated/VelocitronPetriNetVisitor.js";
import { SourceMap } from "./source.js";
import type {JsonValue, ReadonlyJsonObject} from "./json-types.js";
import {
  pythonStringRepr,
  taggedPythonRepr,
  type TaggedJsonValue,
} from "./python-repr.js";

const CONTRIBUTION_FORMAT = "velocitron.petrinet/contribution-ir";
const CONTRIBUTION_VERSION = 1;
const MAX_SAFE_INTEGER = 9_007_199_254_740_991;

/** Whether `path` names a token field: non-empty keys joined by dots. */
export function validFieldPath(path: unknown): path is string {
  return typeof path === "string" && path.split(".").every((key) => key.length > 0);
}

/** UTF-8 source coordinates used by the portable Contribution IR wire format. */
export interface ContributionIrPosition {
  readonly byteOffset: number;
  readonly line: number;
  readonly column: number;
}

export interface ContributionIrSpan {
  readonly source: string;
  readonly start: ContributionIrPosition;
  readonly end: ContributionIrPosition;
}

export interface ContributionIrIdentity {
  readonly source: string;
  readonly statement: number;
  readonly part: number;
}

/**
 * Common closed contribution envelope. The generated schema validator narrows
 * each kind's target and value before the resolver examines them.
 */
export interface ContributionIrContribution {
  readonly id: ContributionIrIdentity;
  readonly ordinal: number;
  readonly span: ContributionIrSpan;
  readonly kind: string;
  readonly target: ReadonlyJsonObject;
  readonly value: ReadonlyJsonObject;
}

/**
 * The root shape of velocitron.petrinet/contribution-ir version 1.
 *
 * Portable loading of this shape lives in `@velocitron/ir`
 * (`packages/ir/typescript`). `python3 tools/dsl_package.py` copies this
 * module into `@velocitron/dsl`. Resolution, including CEL compilation,
 * stays in `@velocitron/core`. Composition merge ships in `packages/merge`;
 * the implementations keep their own copies.
 */
export interface ContributionIr {
  readonly format: "velocitron.petrinet/contribution-ir";
  readonly version: 1;
  readonly documentKind: "net" | "composition";
  readonly document: Readonly<{id: string}>;
  readonly contributions: readonly ContributionIrContribution[];
}

type IrPosition = {
  byteOffset: number;
  line: number;
  column: number;
};

type IrSpan = {
  source: string;
  start: IrPosition;
  end: IrPosition;
};

type ArcId = {
  document: string;
  statement: number;
  part: number;
};

type ArcMode = "consume" | "read" | "inhibit" | "produce";

type ArcSpec = {
  source: ReadonlyJsonObject;
  destination: ReadonlyJsonObject;
  color: ReadonlyJsonObject;
  mode: ArcMode;
  start: number;
  end: number;
  transition: TransitionContext | undefined;
};

function resourceError(
  resource: keyof typeof PETRINET_RESOURCE_LIMITS,
  actual: number,
): PetrinetResourceError {
  return new PetrinetResourceError(
    resource,
    PETRINET_RESOURCE_LIMITS[resource],
    actual,
  );
}

function zeroSpan(source: string): SourceSpan {
  const position = { offset: 0, line: 1, column: 1 };
  return { source, start: position, end: position };
}

/**
 * Validate the JavaScript representation and count its strict UTF-8 bytes
 * without first allocating an encoded copy of an attacker-controlled source.
 */
function inspectSource(text: string, sourceId: string): number {
  let byteLength = 0;
  let invalid = text.startsWith("\uFEFF");

  for (let index = 0; index < text.length; index += 1) {
    const first = text.charCodeAt(index);
    if (first === 0x0d && text.charCodeAt(index + 1) !== 0x0a) {
      invalid = true;
    }

    if (first >= 0xd800 && first <= 0xdbff) {
      const second = text.charCodeAt(index + 1);
      if (second < 0xdc00 || second > 0xdfff) {
        invalid = true;
        byteLength += 3;
        continue;
      }
      byteLength += 4;
      index += 1;
      continue;
    }
    if (first >= 0xdc00 && first <= 0xdfff) {
      invalid = true;
      byteLength += 3;
      continue;
    }
    byteLength += first <= 0x7f ? 1 : first <= 0x7ff ? 2 : 3;
  }

  if (invalid) {
    throw new PetrinetDslError({
      code: "PN100",
      message: "source must be strict UTF-8 text without a BOM or bare CR",
      span: zeroSpan(sourceId),
    });
  }
  if (byteLength > PETRINET_RESOURCE_LIMITS.sourceBytes) {
    throw resourceError("sourceBytes", byteLength);
  }
  return byteLength;
}

function containsIsolatedSurrogate(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    const first = value.charCodeAt(index);
    if (first >= 0xd800 && first <= 0xdbff) {
      const second = value.charCodeAt(index + 1);
      if (second < 0xdc00 || second > 0xdfff) {
        return true;
      }
      index += 1;
    } else if (first >= 0xdc00 && first <= 0xdfff) {
      return true;
    }
  }
  return false;
}

function decodeString(text: string): string {
  return JSON.parse(text) as string;
}

function decodeName(text: string): string {
  return text.startsWith('"') ? decodeString(text) : text;
}

/** The dotted name inside `(...)` or `[...]` of a composition fact. */
function compositionPath(
  context: CompositionPlaceContext | CompositionTransitionContext,
): string {
  return context
    .name_list()
    .map((name) => decodeName(name.getText()))
    .join(".");
}

function untag(value: TaggedJsonValue): JsonValue {
  switch (value.type) {
    case "null":
      return null;
    case "boolean":
    case "string":
      return value.value;
    case "number":
      return Number(value.lexeme);
    case "array":
      return value.items.map(untag);
    case "object": {
      const result: Record<string, JsonValue> = {};
      for (const entry of value.entries) {
        Object.defineProperty(result, entry.key, {
          configurable: true,
          enumerable: true,
          value: untag(entry.value),
          writable: true,
        });
      }
      return result;
    }
  }
}

function validCapacityKey(value: JsonValue): boolean {
  if (typeof value === "string") {
    return value.length > 0;
  }
  return (
    Array.isArray(value) &&
    value.length > 0 &&
    value.every((item) => typeof item === "string" && item.length > 0)
  );
}

/** ANTLR indexes code points; SourceMap deliberately accepts JS UTF-16 indices. */
class SourceCoordinates {
  readonly source: SourceMap;
  readonly scalarLength: number;
  readonly #scalarToUtf16: Uint32Array | undefined;

  constructor(sourceId: string, text: string) {
    this.source = new SourceMap(sourceId, text);

    let scalarLength = 0;
    let hasSupplementaryScalar = false;
    for (let index = 0; index < text.length; scalarLength += 1) {
      const width = text.codePointAt(index) as number;
      if (width > 0xffff) {
        hasSupplementaryScalar = true;
        index += 2;
      } else {
        index += 1;
      }
    }
    this.scalarLength = scalarLength;

    if (hasSupplementaryScalar) {
      const map = new Uint32Array(scalarLength + 1);
      let scalar = 0;
      for (let utf16 = 0; utf16 < text.length; scalar += 1) {
        map[scalar] = utf16;
        utf16 += (text.codePointAt(utf16) as number) > 0xffff ? 2 : 1;
      }
      map[scalarLength] = text.length;
      this.#scalarToUtf16 = map;
    }
  }

  utf16Index(scalarIndex: number): number {
    const clamped = Math.max(0, Math.min(scalarIndex, this.scalarLength));
    return this.#scalarToUtf16?.[clamped] ?? clamped;
  }

  diagnosticSpan(startScalar: number, endScalar: number): SourceSpan {
    return this.source.span(
      this.utf16Index(startScalar),
      this.utf16Index(endScalar),
    );
  }

  diagnosticSpanUtf16(start: number, end: number): SourceSpan {
    return this.source.span(start, end);
  }

  irSpan(startScalar: number, endScalar: number): IrSpan {
    const span = this.diagnosticSpan(startScalar, endScalar);
    return {
      source: span.source,
      start: {
        byteOffset: span.start.offset,
        line: span.start.line,
        column: span.start.column,
      },
      end: {
        byteOffset: span.end.offset,
        line: span.end.line,
        column: span.end.column,
      },
    };
  }
}

function isToken(value: Token | number | null | undefined): value is Token {
  return typeof value === "object" && value !== null && "type" in value;
}

// Preserve the header-only grammar probe while recognizing a complete JSON
// value semantically once the parser has established a net body.
function hasPriorNetBody(context: ParserRuleContext): boolean {
  const extensionsContext = context.parentCtx;
  const documentContext = extensionsContext?.parentCtx;
  if (
    (context as ParserRuleContext & { readonly ruleIndex: number }).ruleIndex !==
      VelocitronPetriNetParser.RULE_jsonObject ||
    extensionsContext === undefined ||
    (extensionsContext as ParserRuleContext & { readonly ruleIndex: number })
      .ruleIndex !== VelocitronPetriNetParser.RULE_extensions ||
    documentContext === undefined ||
    (documentContext as ParserRuleContext & { readonly ruleIndex: number })
      .ruleIndex !== VelocitronPetriNetParser.RULE_document
  ) {
    return false;
  }

  return (documentContext.children ?? []).some((child) => {
    if (!(child instanceof ParserRuleContext)) return false;
    const ruleIndex = (
      child as ParserRuleContext & { readonly ruleIndex: number }
    ).ruleIndex;
    return (
      ruleIndex !== VelocitronPetriNetParser.RULE_netHeader &&
      ruleIndex !== VelocitronPetriNetParser.RULE_extensions
    );
  });
}

function nonObjectExtensionsSpan(
  recognizer: Recognizer<Token | number>,
  offendingSymbol: Token,
  coordinates: SourceCoordinates,
): SourceSpan | undefined {
  if (
    !(recognizer instanceof VelocitronPetriNetParser) ||
    !hasPriorNetBody(recognizer._ctx)
  ) {
    return undefined;
  }

  const primitive =
    offendingSymbol.type === VelocitronPetriNetLexer.STRING ||
    offendingSymbol.type === VelocitronPetriNetLexer.NUMBER ||
    offendingSymbol.type === VelocitronPetriNetLexer.POSITIVE_INTEGER ||
    offendingSymbol.type === VelocitronPetriNetLexer.ZERO ||
    offendingSymbol.type === VelocitronPetriNetLexer.TRUE ||
    offendingSymbol.type === VelocitronPetriNetLexer.FALSE ||
    offendingSymbol.type === VelocitronPetriNetLexer.NULL;
  let endScalar = primitive ? offendingSymbol.stop + 1 : undefined;

  if (offendingSymbol.type === VelocitronPetriNetLexer.LBRACK) {
    const stream = recognizer._input;
    if (!(stream instanceof CommonTokenStream)) return undefined;
    stream.fill();

    let depth = 0;
    for (
      let index = offendingSymbol.tokenIndex;
      index < stream.tokens.length;
      index += 1
    ) {
      const token = stream.tokens[index] as Token;
      if (token.channel !== Token.DEFAULT_CHANNEL) continue;
      if (token.type === VelocitronPetriNetLexer.LBRACK) {
        depth += 1;
      } else if (token.type === VelocitronPetriNetLexer.RBRACK) {
        depth -= 1;
        if (depth === 0) {
          endScalar = token.stop + 1;
          break;
        }
      } else if (token.type === Token.EOF) {
        break;
      }
    }
  }

  if (endScalar === undefined) return undefined;
  const startUtf16 = coordinates.utf16Index(offendingSymbol.start);
  const endUtf16 = coordinates.utf16Index(endScalar);
  try {
    const value: unknown = JSON.parse(
      coordinates.source.text.slice(startUtf16, endUtf16),
    );
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      return undefined;
    }
  } catch {
    return undefined;
  }
  return coordinates.diagnosticSpan(offendingSymbol.start, endScalar);
}

class SyntaxListener implements ErrorListener<Token | number> {
  readonly diagnostics: Diagnostic[] = [];
  readonly #coordinates: SourceCoordinates;
  #count = 0;

  constructor(coordinates: SourceCoordinates) {
    this.#coordinates = coordinates;
  }

  syntaxError(
    recognizer: Recognizer<Token | number>,
    offendingSymbol: Token | number,
    _line: number,
    _column: number,
    rawMessage: string,
    _error: RecognitionException | undefined,
  ): void {
    this.#count += 1;
    if (this.#count > PETRINET_RESOURCE_LIMITS.diagnostics) {
      throw resourceError("diagnostics", this.#count);
    }

    let message = rawMessage;
    let help: string | undefined;
    let span: SourceSpan;
    if (!isToken(offendingSymbol)) {
      const end = this.#coordinates.source.text.length;
      span = this.#coordinates.diagnosticSpanUtf16(end, end);
    } else if (offendingSymbol.type === Token.EOF) {
      span = this.#coordinates.source.eofSpan();
    } else {
      span = this.#coordinates.diagnosticSpan(
        offendingSymbol.start,
        Math.max(offendingSymbol.start, offendingSymbol.stop + 1),
      );
    }

    const extensionsSpan = isToken(offendingSymbol)
      ? nonObjectExtensionsSpan(recognizer, offendingSymbol, this.#coordinates)
      : undefined;
    if (extensionsSpan !== undefined) {
      message = "extensions requires a JSON object";
      help = "replace the value with a JSON object";
      span = extensionsSpan;
    } else if (
      message.includes("expecting IDENT") ||
      message.startsWith("missing IDENT at ")
    ) {
      if (message.startsWith("missing IDENT at ") && isToken(offendingSymbol)) {
        message = `mismatched input ${pythonStringRepr(offendingSymbol.text ?? "")} expecting identifier`;
      } else {
        message = message.replace("expecting IDENT", "expecting identifier");
      }
      help = "add a mandatory identifier alias after as";
    }

    this.diagnostics.push({
      code: "PN101",
      message,
      span,
      ...(help === undefined ? {} : { help }),
    });
  }

  // The runtime calls these on every listener when prediction falls back to
  // full context; they report no error.
  reportAmbiguity(): void {}

  reportAttemptingFullContext(): void {}

  reportContextSensitivity(): void {}
}

function installLexerLimits(lexer: VelocitronPetriNetLexer): void {
  const nextToken = lexer.nextToken.bind(lexer);
  let tokenCount = 0;
  let nestingDepth = 0;

  lexer.nextToken = (): Token => {
    const token = nextToken();
    if (token.type === Token.EOF) {
      return token;
    }

    tokenCount += 1;
    if (tokenCount > PETRINET_RESOURCE_LIMITS.lexerTokens) {
      throw resourceError("lexerTokens", tokenCount);
    }

    if (
      token.type === VelocitronPetriNetLexer.LBRACE ||
      token.type === VelocitronPetriNetLexer.LBRACK
    ) {
      nestingDepth += 1;
      if (nestingDepth > PETRINET_RESOURCE_LIMITS.nestingDepth) {
        throw resourceError("nestingDepth", nestingDepth);
      }
    } else if (
      token.type === VelocitronPetriNetLexer.RBRACE ||
      token.type === VelocitronPetriNetLexer.RBRACK
    ) {
      nestingDepth = Math.max(0, nestingDepth - 1);
    }
    return token;
  };
}

function statementRule(ruleIndex: number): boolean {
  switch (ruleIndex) {
    case VelocitronPetriNetParser.RULE_netHeader:
    case VelocitronPetriNetParser.RULE_compositionHeader:
    case VelocitronPetriNetParser.RULE_compositionUse:
    case VelocitronPetriNetParser.RULE_compositionWire:
    case VelocitronPetriNetParser.RULE_compositionShare:
    case VelocitronPetriNetParser.RULE_compositionRefine:
    case VelocitronPetriNetParser.RULE_compositionFinal:
    case VelocitronPetriNetParser.RULE_chain:
    case VelocitronPetriNetParser.RULE_placeDeclaration:
    case VelocitronPetriNetParser.RULE_transitionDeclaration:
    case VelocitronPetriNetParser.RULE_transitionHandler:
    case VelocitronPetriNetParser.RULE_transitionGuard:
    case VelocitronPetriNetParser.RULE_transitionTimer:
    case VelocitronPetriNetParser.RULE_transitionTimerMaturity:
    case VelocitronPetriNetParser.RULE_transitionTimerBind:
    case VelocitronPetriNetParser.RULE_transitionBindingName:
    case VelocitronPetriNetParser.RULE_transitionPriority:
    case VelocitronPetriNetParser.RULE_transitionOrder:
    case VelocitronPetriNetParser.RULE_chainOrder:
    case VelocitronPetriNetParser.RULE_placePort:
    case VelocitronPetriNetParser.RULE_placeAccepts:
    case VelocitronPetriNetParser.RULE_placeCapacity:
    case VelocitronPetriNetParser.RULE_arcWeight:
    case VelocitronPetriNetParser.RULE_arcData:
    case VelocitronPetriNetParser.RULE_arcPredicate:
    case VelocitronPetriNetParser.RULE_arcCorrelate:
    case VelocitronPetriNetParser.RULE_initialMarking:
    case VelocitronPetriNetParser.RULE_templateDefinition:
    case VelocitronPetriNetParser.RULE_namedMarking:
    case VelocitronPetriNetParser.RULE_metadataDescription:
    case VelocitronPetriNetParser.RULE_metadataAnnotation:
    case VelocitronPetriNetParser.RULE_viewPosition:
    case VelocitronPetriNetParser.RULE_viewRoute:
    case VelocitronPetriNetParser.RULE_viewSplines:
    case VelocitronPetriNetParser.RULE_viewDetail:
    case VelocitronPetriNetParser.RULE_decoration:
    case VelocitronPetriNetParser.RULE_extensions:
    case VelocitronPetriNetParser.RULE_domainDeclaration:
    case VelocitronPetriNetParser.RULE_finalDeclaration:
    case VelocitronPetriNetParser.RULE_invariantDeclaration:
    case VelocitronPetriNetParser.RULE_actorAssignment:
    case VelocitronPetriNetParser.RULE_actorDeclaration:
    case VelocitronPetriNetParser.RULE_placeLives:
    case VelocitronPetriNetParser.RULE_placeReadsAs:
    case VelocitronPetriNetParser.RULE_placeKept:
      return true;
    default:
      return false;
  }
}

const VIEW_SPLINES = ["ortho", "spline", "curved", "polyline", "line"] as const;
const VIEW_DETAILS = ["full", "summary", "structure"] as const;

class LoweringVisitor {
  readonly contributions: ReadonlyJsonObject[] = [];
  readonly visitor: VelocitronPetriNetVisitor<void>;
  documentKind: "net" | "composition" = "net";

  readonly #coordinates: SourceCoordinates;
  #statement = 0;

  constructor(coordinates: SourceCoordinates) {
    this.#coordinates = coordinates;
    this.visitor = new VelocitronPetriNetVisitor<void>();
    this.visitor.visitDocument = (context) => this.visitDocument(context);
    this.visitor.visitNetHeader = (context) => this.visitNetHeader(context);
    this.visitor.visitCompositionHeader = (context) =>
      this.visitCompositionHeader(context);
    this.visitor.visitCompositionUse = (context) =>
      this.visitCompositionUse(context);
    this.visitor.visitCompositionWire = (context) =>
      this.visitCompositionWire(context);
    this.visitor.visitCompositionShare = (context) =>
      this.visitCompositionShare(context);
    this.visitor.visitCompositionRefine = (context) =>
      this.visitCompositionRefine(context);
    this.visitor.visitCompositionFinal = (context) =>
      this.visitCompositionFinal(context);
    this.visitor.visitChain = (context) => this.visitChain(context);
    this.visitor.visitPlaceDeclaration = (context) =>
      this.visitPlaceDeclaration(context);
    this.visitor.visitTransitionDeclaration = (context) =>
      this.visitTransitionDeclaration(context);
    this.visitor.visitPlacePort = (context) => this.visitPlacePort(context);
    this.visitor.visitTransitionHandler = (context) =>
      this.visitTransitionHandler(context);
    this.visitor.visitTransitionGuard = (context) =>
      this.visitTransitionGuard(context);
    this.visitor.visitTransitionTimer = (context) =>
      this.visitTransitionTimer(context);
    this.visitor.visitTransitionTimerMaturity = (context) =>
      this.visitTransitionTimerMaturity(context);
    this.visitor.visitTransitionTimerBind = (context) =>
      this.visitTransitionTimerBind(context);
    this.visitor.visitTransitionBindingName = (context) =>
      this.visitTransitionBindingName(context);
    this.visitor.visitTransitionPriority = (context) =>
      this.visitTransitionPriority(context);
    this.visitor.visitTransitionOrder = (context) =>
      this.visitTransitionOrder(context);
    this.visitor.visitChainOrder = (context) => this.visitChainOrder(context);
    this.visitor.visitPlaceAccepts = (context) =>
      this.visitPlaceAccepts(context);
    this.visitor.visitPlaceCapacity = (context) =>
      this.visitPlaceCapacity(context);
    this.visitor.visitArcWeight = (context) => this.visitArcWeight(context);
    this.visitor.visitArcData = (context) => this.visitArcData(context);
    this.visitor.visitArcPredicate = (context) =>
      this.visitArcPredicate(context);
    this.visitor.visitArcCorrelate = (context) =>
      this.visitArcCorrelate(context);
    this.visitor.visitInitialMarking = (context) =>
      this.visitInitialMarking(context);
    this.visitor.visitTemplateDefinition = (context) =>
      this.visitTemplateDefinition(context);
    this.visitor.visitNamedMarking = (context) =>
      this.visitNamedMarking(context);
    this.visitor.visitMetadataDescription = (context) =>
      this.visitMetadataDescription(context);
    this.visitor.visitMetadataAnnotation = (context) =>
      this.visitMetadataAnnotation(context);
    this.visitor.visitViewPosition = (context) =>
      this.visitViewPosition(context);
    this.visitor.visitViewRoute = (context) => this.visitViewRoute(context);
    this.visitor.visitViewSplines = (context) =>
      this.#viewStyle(context, "splines", VIEW_SPLINES);
    this.visitor.visitViewDetail = (context) =>
      this.#viewStyle(context, "detail", VIEW_DETAILS);
    this.visitor.visitDecoration = (context) => this.visitDecoration(context);
    this.visitor.visitExtensions = (context) => this.visitExtensions(context);
    this.visitor.visitDomainDeclaration = (context) =>
      this.visitDomainDeclaration(context);
    this.visitor.visitFinalDeclaration = (context) =>
      this.visitFinalDeclaration(context);
    this.visitor.visitInvariantDeclaration = (context) =>
      this.visitInvariantDeclaration(context);
    this.visitor.visitActorAssignment = (context) =>
      this.visitActorAssignment(context);
    this.visitor.visitActorDeclaration = (context) =>
      this.visitActorDeclaration(context);
    this.visitor.visitPlaceLives = (context) => this.visitPlaceLives(context);
    this.visitor.visitPlaceReadsAs = (context) =>
      this.visitPlaceReadsAs(context);
    this.visitor.visitPlaceKept = (context) => this.visitPlaceKept(context);
  }

  #contextStart(context: ParserRuleContext): number {
    return context.start.start;
  }

  #contextEnd(context: ParserRuleContext): number {
    return (context.stop ?? context.start).stop + 1;
  }

  #jsonError(message: string, context: ParserRuleContext): never {
    throw new PetrinetDslError({
      code: "PN101",
      message,
      span: this.#coordinates.diagnosticSpan(
        this.#contextStart(context),
        this.#contextEnd(context),
      ),
    });
  }

  #semanticError(message: string, context: ParserRuleContext): never {
    throw new PetrinetDslError({
      code: "PN202",
      message,
      span: this.#coordinates.diagnosticSpan(
        this.#contextStart(context),
        this.#contextEnd(context),
      ),
    });
  }

  #checkJsonDepth(depth: number): void {
    if (depth > PETRINET_RESOURCE_LIMITS.nestingDepth) {
      throw resourceError("nestingDepth", depth);
    }
  }

  #lowerJsonValue(
    context: JsonValueContext | DomainValueContext,
    depth = 1,
  ): TaggedJsonValue {
    this.#checkJsonDepth(depth);
    // A domainValue is a jsonValue without objects, arrays and null.
    const json = context instanceof DomainValueContext ? undefined : context;
    const objectContext = json?.jsonObject() as JsonObjectContext | undefined;
    if (objectContext) {
      return this.#lowerJsonObject(objectContext, depth);
    }
    const arrayContext = json?.jsonArray() as JsonArrayContext | undefined;
    if (arrayContext) {
      return {
        type: "array",
        items: arrayContext
          .jsonValue_list()
          .map((item) => this.#lowerJsonValue(item, depth + 1)),
      };
    }
    const stringNode = context.STRING() as TerminalNode | undefined;
    if (stringNode) {
      const value = decodeString(stringNode.getText());
      if (containsIsolatedSurrogate(value)) {
        return this.#jsonError(
          "JSON string contains an isolated surrogate",
          context,
        );
      }
      return { type: "string", value };
    }
    const numberNode =
      (context.NUMBER() as TerminalNode | undefined) ??
      (context.POSITIVE_INTEGER() as TerminalNode | undefined) ??
      (context.ZERO() as TerminalNode | undefined);
    if (numberNode) {
      const lexeme = numberNode.getText();
      const parsed = Number(lexeme);
      if (!Number.isFinite(parsed)) {
        return this.#jsonError(
          "JSON number must be finite IEEE-754 binary64",
          context,
        );
      }
      if (
        !lexeme.includes(".") &&
        !lexeme.includes("e") &&
        !lexeme.includes("E") &&
        Math.abs(parsed) > MAX_SAFE_INTEGER
      ) {
        return this.#jsonError(
          "JSON integer exceeds the safe IEEE-754 range",
          context,
        );
      }
      return { type: "number", lexeme };
    }
    if (context.TRUE() as TerminalNode | undefined) {
      return { type: "boolean", value: true };
    }
    if (context.FALSE() as TerminalNode | undefined) {
      return { type: "boolean", value: false };
    }
    return { type: "null" };
  }

  #lowerJsonObject(context: JsonObjectContext, depth = 1): TaggedJsonValue & {
    type: "object";
  } {
    this.#checkJsonDepth(depth);
    const entries: Array<{ key: string; value: TaggedJsonValue }> = [];
    const keys = new Set<string>();
    const keyNodes = context.STRING_list();
    const values = context.jsonValue_list();
    for (let index = 0; index < keyNodes.length; index += 1) {
      const key = decodeString(keyNodes[index]!.getText());
      if (containsIsolatedSurrogate(key)) {
        return this.#jsonError(
          "JSON object key contains an isolated surrogate",
          context,
        );
      }
      if (keys.has(key)) {
        return this.#jsonError(
          `duplicate JSON object key ${pythonStringRepr(key)}`,
          context,
        );
      }
      keys.add(key);
      entries.push({
        key,
        value: this.#lowerJsonValue(values[index] as JsonValueContext, depth + 1),
      });
    }
    return { type: "object", entries };
  }

  #span(start: number, end: number): ReadonlyJsonObject {
    return this.#coordinates.irSpan(start, end) as unknown as ReadonlyJsonObject;
  }

  #contribution(options: {
    kind: string;
    target: ReadonlyJsonObject;
    value: ReadonlyJsonObject;
    start: number;
    end: number;
    part?: number;
  }): void {
    const actual = this.contributions.length + 1;
    if (actual > PETRINET_RESOURCE_LIMITS.contributions) {
      throw resourceError("contributions", actual);
    }
    const part = options.part ?? 0;
    this.contributions.push({
      id: {
        source: this.#coordinates.source.sourceId,
        statement: this.#statement,
        part,
      },
      kind: options.kind,
      ordinal: this.contributions.length,
      span: this.#span(options.start, options.end),
      target: options.target,
      value: options.value,
    });
  }

  visitDocument(context: DocumentContext): void {
    for (const rawChild of context.children ?? []) {
      if (!(rawChild instanceof ParserRuleContext)) {
        continue;
      }
      let child: ParserRuleContext = rawChild;
      if (child instanceof AdditionalChainContext) {
        child = child.chain();
      } else if (child instanceof AdditionalTransitionHandlerContext) {
        child = child.transitionHandler();
      } else if (child instanceof AdditionalInitialMarkingContext) {
        child = child.initialMarking();
      } else if (child instanceof AdditionalTemplateDefinitionContext) {
        child = child.templateDefinition();
      }
      const ruleIndex = (child as ParserRuleContext & { ruleIndex: number })
        .ruleIndex;
      if (statementRule(ruleIndex)) {
        this.visitor.visit(child);
        this.#statement += 1;
      }
    }
  }

  visitNetHeader(context: NetHeaderContext): void {
    const description = context.STRING() as TerminalNode | undefined;
    this.#contribution({
      kind: "document.net-header",
      target: { type: "document" },
      value: {
        name: decodeName(context.name().getText()),
        ...(description ? { description: decodeString(description.getText()) } : {}),
      },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitCompositionHeader(context: CompositionHeaderContext): void {
    this.documentKind = "composition";
    this.#contribution({
      kind: "document.composition-header",
      target: { type: "document" },
      value: { namespace: decodeName(context.name().getText()) },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitCompositionUse(context: CompositionUseContext): void {
    this.#contribution({
      kind: "composition.use",
      target: { type: "document" },
      value: {
        ref: decodeString(context.STRING().getText()),
        alias: context.IDENT().getText(),
      },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitCompositionWire(context: CompositionWireContext): void {
    const aliases = context.IDENT_list();
    const places = context.compositionPlace_list();
    this.#contribution({
      kind: "composition.wire",
      target: { type: "document" },
      value: {
        from: this.#compositionEndpoint(aliases[0]!, places[0]!),
        to: this.#compositionEndpoint(aliases[1]!, places[1]!),
      },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitCompositionShare(context: CompositionShareContext): void {
    const places = context.compositionPlace_list();
    this.#contribution({
      kind: "composition.share",
      target: { type: "document" },
      value: {
        places: context
          .IDENT_list()
          .map((alias, index) => this.#compositionEndpoint(alias, places[index]!)),
      },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitCompositionFinal(context: CompositionFinalContext): void {
    this.#contribution({
      kind: "composition.final",
      target: { type: "document" },
      value: {
        markings: context.compositionFinalMarking_list().map((markingContext) => {
          const places = markingContext.compositionPlace_list();
          return markingContext
            .IDENT_list()
            .map((alias, index) => this.#compositionEndpoint(alias, places[index]!));
        }),
      },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  /** `alias.(name)`, or `alias.(inner.name)` inside a composition. */
  #compositionEndpoint(
    alias: TerminalNode,
    place: CompositionPlaceContext,
  ): ReadonlyJsonObject {
    return {
      alias: alias.getText(),
      place: compositionPath(place),
      span: this.#span(
        alias.symbol.start,
        this.#contextEnd(place as ParserRuleContext),
      ),
    };
  }

  visitCompositionRefine(context: CompositionRefineContext): void {
    const aliases = context.IDENT_list();
    const transition = context.compositionTransition();
    this.#contribution({
      kind: "composition.refine",
      target: { type: "document" },
      value: {
        transition: {
          alias: aliases[0]!.getText(),
          name: compositionPath(transition),
          span: this.#span(
            aliases[0]!.symbol.start,
            this.#contextEnd(transition as ParserRuleContext),
          ),
        },
        by: {
          alias: aliases[1]!.getText(),
          span: this.#span(aliases[1]!.symbol.start, aliases[1]!.symbol.stop + 1),
        },
      },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitChain(context: ChainContext): void {
    const nodes = context.chainNode_list();
    const segments = context.arcSegment_list();
    const handleContext = context.chainHandle() as
      | ChainHandleContext
      | undefined;

    const arcSpecs: ArcSpec[] = [];
    for (let index = 0; index < segments.length; index += 1) {
      const segment = segments[index]!;
      const left = nodes[index] as ChainNodeContext;
      const right = nodes[index + 1] as ChainNodeContext;
      const leftPlace = left.place() as PlaceContext | undefined;
      const rightPlace = right.place() as PlaceContext | undefined;
      if (Boolean(leftPlace) === Boolean(rightPlace)) {
        throw new PetrinetDslError({
          code: "PN101",
          message: "a chain segment must connect a place and a transition",
          span: this.#coordinates.diagnosticSpan(
            this.#contextStart(left),
            this.#contextEnd(right),
          ),
        });
      }
      const arcOperator = segment.arcOperator();
      const operatorText = arcOperator.getText();
      const colorContext = segment.color() as ColorContext | undefined;
      const color: ReadonlyJsonObject = {
        kind: "explicit",
        value: colorContext
          ? decodeName(colorContext.name().getText())
          : "token",
      };
      if (leftPlace) {
        const mode = {
          "->": "consume",
          "->?": "read",
          "->0": "inhibit",
        }[operatorText] as ArcMode | undefined;
        if (!mode) {
          return this.#jsonError("invalid input arc operator", segment);
        }
        const transition = right.transition();
        arcSpecs.push({
          source: {
            type: "place",
            name: decodeName(leftPlace.name().getText()),
          },
          destination: {
            type: "transition",
            name: decodeName(transition.name().getText()),
          },
          color,
          mode,
          start: this.#contextStart(left),
          end: this.#contextEnd(right),
          transition,
        });
      } else {
        if (operatorText !== "->") {
          throw new PetrinetDslError({
            code: "PN101",
            message: `${operatorText} is only allowed on place-to-transition arcs`,
            span: this.#coordinates.diagnosticSpan(
              this.#contextStart(arcOperator),
              this.#contextEnd(arcOperator),
            ),
          });
        }
        arcSpecs.push({
          source: {
            type: "transition",
            name: decodeName(left.transition().name().getText()),
          },
          destination: {
            type: "place",
            name: decodeName((rightPlace as PlaceContext).name().getText()),
          },
          color,
          mode: "produce",
          start: this.#contextStart(left),
          end: this.#contextEnd(right),
          transition: undefined,
        });
      }
    }

    const partOffset = handleContext ? 1 : 0;
    const arcIds: ArcId[] = arcSpecs.map((_arc, index) => ({
      document: this.#coordinates.source.sourceId,
      statement: this.#statement,
      part: partOffset + index,
    }));
    if (handleContext) {
      const handle = decodeName(handleContext.name().getText());
      this.#contribution({
        kind: "arc.handle",
        target: { type: "arcHandle", name: handle },
        value: { arcIds: arcIds as unknown as JsonValue },
        start: this.#contextStart(context),
        end: this.#contextEnd(context),
      });
    }
    for (let index = 0; index < arcSpecs.length; index += 1) {
      const arc = arcSpecs[index]!;
      const value: Record<string, JsonValue> = {
        from: arc.source,
        to: arc.destination,
        color: arc.color,
        mode: arc.mode,
      };
      if (arc.mode === "consume") {
        const transition = arc.transition as TransitionContext;
        value.transitionNameSpan = this.#span(
          this.#contextStart(transition.name()),
          this.#contextEnd(transition.name()),
        );
      }
      this.#contribution({
        kind: "arc.declare",
        target: {
          type: "arc",
          id: arcIds[index] as unknown as JsonValue,
        },
        value,
        start: arc.start,
        end: arc.end,
        part: partOffset + index,
      });
    }
  }

  visitPlaceDeclaration(context: PlaceDeclarationContext): void {
    const place = context.place();
    this.#contribution({
      kind: "place.declare",
      target: { type: "place", name: decodeName(place.name().getText()) },
      value: {},
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitTransitionDeclaration(context: TransitionDeclarationContext): void {
    const transition = context.transition();
    this.#contribution({
      kind: "transition.declare",
      target: {
        type: "transition",
        name: decodeName(transition.name().getText()),
      },
      value: {},
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitPlacePort(context: PlacePortContext): void {
    this.#contribution({
      kind: "place.port",
      target: {
        type: "place",
        name: decodeName(context.place().name().getText()),
      },
      value: {
        direction: context.portDirection().getText(),
        color: decodeName(context.color().name().getText()),
      },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitTransitionHandler(context: TransitionHandlerContext): void {
    const name = decodeName(context.transition().name().getText());
    this.#contribution({
      kind: "transition.handler",
      target: { type: "transition", name },
      value: { handler: decodeString(context.STRING().getText()) },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitTransitionGuard(context: TransitionGuardContext): void {
    const name = decodeName(context.transition().name().getText());
    this.#contribution({
      kind: "transition.guard",
      target: { type: "transition", name },
      value: { guard: decodeString(context.STRING().getText()) },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitTransitionTimer(context: TransitionTimerContext): void {
    const name = decodeName(context.transition().name().getText());
    const clock = decodeName(context.place().name().getText());
    this.#contribution({
      kind: "transition.timer",
      target: { type: "transition", name },
      value: {
        clock: { type: "place", name: clock },
        cel: decodeString(context.STRING().getText()),
      },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitTransitionTimerMaturity(context: TransitionTimerMaturityContext): void {
    const name = decodeName(context.transition().name().getText());
    this.#contribution({
      kind: "transition.timer-maturity",
      target: { type: "transition", name },
      value: { maturity: decodeString(context.STRING().getText()) },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitTransitionTimerBind(context: TransitionTimerBindContext): void {
    const name = decodeName(context.transition().name().getText());
    const place = decodeName(context.place().name().getText());
    this.#contribution({
      kind: "transition.timer-bind",
      target: { type: "transition", name },
      value: {
        name: context.timerBindName().getText(),
        place: { type: "place", name: place },
      },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitTransitionBindingName(context: TransitionBindingNameContext): void {
    const name = decodeName(context.transition().name().getText());
    const place = decodeName(context.place().name().getText());
    this.#contribution({
      kind: "transition.binding-name",
      target: { type: "transition", name },
      value: {
        name: decodeName(context.name().getText()),
        place: { type: "place", name: place },
      },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  #safeInteger(context: ParserRuleContext): number {
    const value = Number(context.getText());
    if (!Number.isSafeInteger(value)) {
      return this.#jsonError(
        "integer exceeds the safe IEEE-754 range",
        context,
      );
    }
    return value;
  }

  visitTransitionPriority(context: TransitionPriorityContext): void {
    const name = decodeName(context.transition().name().getText());
    this.#contribution({
      kind: "transition.priority",
      target: { type: "transition", name },
      value: { priority: this.#safeInteger(context.nonnegativeInteger()) },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }


  visitTransitionOrder(context: TransitionOrderContext): void {
    const name = decodeName(context.transition().name().getText());
    this.#contribution({
      kind: "order.transition",
      target: { type: "transition", name },
      value: { rank: this.#safeInteger(context.positiveInteger()) },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitChainOrder(context: ChainOrderContext): void {
    const name = decodeName(context.name().getText());
    this.#contribution({
      kind: "order.arc-run",
      target: { type: "arcHandle", name },
      value: { rank: this.#safeInteger(context.positiveInteger()) },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitPlaceAccepts(context: PlaceAcceptsContext): void {
    const place = decodeName(context.place().name().getText());
    const colors = context.color_list().map((color) => decodeName(color.getText()));
    if (colors.length !== new Set(colors).size) {
      return this.#semanticError(
        `accepted colors for (${place}) must not contain duplicates`,
        context,
      );
    }
    this.#contribution({
      kind: "place.accepts",
      target: { type: "place", name: place },
      value: { colors },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitPlaceCapacity(context: PlaceCapacityContext): void {
    const place = decodeName(context.place().name().getText());
    const objectContext = context.jsonObject();
    const tagged = this.#lowerJsonObject(objectContext);
    const value = untag(tagged) as ReadonlyJsonObject;
    const valueContexts = new Map<string, JsonValueContext>();
    const keys = objectContext.STRING_list();
    const values = objectContext.jsonValue_list();
    for (let index = 0; index < keys.length; index += 1) {
      valueContexts.set(decodeString(keys[index]!.getText()), values[index]!);
    }
    const members = Object.keys(value);
    if (
      members.length !== 2 ||
      !Object.hasOwn(value, "key") ||
      !Object.hasOwn(value, "max")
    ) {
      return this.#semanticError(
        `capacityPerColorKey for (${place}) must contain exactly key and max`,
        objectContext,
      );
    }
    if (!validCapacityKey(value.key as JsonValue)) {
      return this.#semanticError(
        "capacityPerColorKey key must be a non-empty string or non-empty " +
          `array of non-empty strings for (${place})`,
        valueContexts.get("key") as JsonValueContext,
      );
    }
    const maximum = value.max as JsonValue;
    const maximumEntry = tagged.entries.find((entry) => entry.key === "max")!;
    const maximumIsInteger =
      maximumEntry.value.type === "number" &&
      !/[.eE]/u.test(maximumEntry.value.lexeme);
    if (
      !maximumIsInteger ||
      typeof maximum !== "number" ||
      !Number.isInteger(maximum) ||
      maximum < 1
    ) {
      return this.#semanticError(
        "capacityPerColorKey max must be an integer greater than or equal " +
          `to 1; got ${taggedPythonRepr(maximumEntry.value)} for (${place})`,
        valueContexts.get("max") as JsonValueContext,
      );
    }
    this.#contribution({
      kind: "place.capacity-per-color-key",
      target: { type: "place", name: place },
      value,
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitArcWeight(context: ArcWeightContext): void {
    const handle = decodeName(context.name().getText());
    const valueContext = context.jsonValue();
    const tagged = this.#lowerJsonValue(valueContext);
    const weight = untag(tagged);
    const weightIsInteger =
      tagged.type === "number" && !/[.eE]/u.test(tagged.lexeme);
    if (
      !weightIsInteger ||
      typeof weight !== "number" ||
      !Number.isInteger(weight) ||
      weight < 1
    ) {
      return this.#semanticError(
        "arc weight must be an integer greater than or equal to 1; " +
          `got ${taggedPythonRepr(tagged)} for @${handle}`,
        valueContext,
      );
    }
    this.#contribution({
      kind: "arc.weight",
      target: { type: "arcHandle", name: handle },
      value: { weight },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitArcData(context: ArcDataContext): void {
    const handle = decodeName(context.name().getText());
    if (context.CEL() as TerminalNode | undefined) {
      // The computed variant (ADR 0023): `data cel JsonString` lowers to
      // the produce template's `cel` field, not literal data.
      this.#contribution({
        kind: "arc.produce-cel",
        target: { type: "arcHandle", name: handle },
        value: { cel: decodeString(context.STRING().getText()) },
        start: this.#contextStart(context),
        end: this.#contextEnd(context),
      });
      return;
    }
    this.#contribution({
      kind: "arc.produce-data",
      target: { type: "arcHandle", name: handle },
      value: { data: this.#lowerJsonValue(context.jsonValue()) },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitArcPredicate(context: ArcPredicateContext): void {
    const handle = decodeName(context.name().getText());
    const kind = context.predicateKind().getText();
    this.#contribution({
      kind: "arc.predicate",
      target: { type: "arcHandle", name: handle },
      value: {
        kind,
        [kind]: decodeString(context.STRING().getText()),
      },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitArcCorrelate(context: ArcCorrelateContext): void {
    const handle = decodeName(context.name().getText());
    this.#contribution({
      kind: "arc.correlate",
      target: { type: "arcHandle", name: handle },
      value: { cel: decodeString(context.STRING().getText()) },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  #lowerMarkingValue(context: MarkingValueContext): {
    count: number;
    token: ReadonlyJsonObject;
  } {
    const countContext = context.positiveInteger() as
      | PositiveIntegerContext
      | undefined;
    const count = countContext ? this.#safeInteger(countContext) : 1;
    const templateContext = context.templateReference() as
      | TemplateReferenceContext
      | undefined;
    if (templateContext) {
      return {
        count,
        token: {
          template: {
            type: "template",
            name: decodeName(templateContext.name().getText()),
          },
        },
      };
    }
    return {
      count,
      token: {
        color: "token",
        data: { type: "object", entries: [] },
      },
    };
  }

  visitInitialMarking(context: InitialMarkingContext): void {
    const { count, token } = this.#lowerMarkingValue(context.markingValue());
    this.#contribution({
      kind: "marking.append",
      target: {
        type: "place",
        name: decodeName(context.place().name().getText()),
      },
      value: { count, token },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitTemplateDefinition(context: TemplateDefinitionContext): void {
    const template = decodeName(context.templateReference().name().getText());
    this.#contribution({
      kind: "template.define",
      target: { type: "template", name: template },
      value: { value: this.#lowerJsonValue(context.jsonValue()) },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  #metadataTarget(
    context: MetadataTargetContext | ActorTargetContext,
  ): ReadonlyJsonObject {
    if (context.NET() as TerminalNode | undefined) {
      return { type: "document" };
    }
    const place = context.place() as PlaceContext | undefined;
    if (place) {
      return { type: "place", name: decodeName(place.name().getText()) };
    }
    const transition = context.transition() as TransitionContext | undefined;
    if (transition) {
      return {
        type: "transition",
        name: decodeName(transition.name().getText()),
      };
    }
    return {
      type: "arcHandle",
      name: decodeName((context as MetadataTargetContext).name().getText()),
    };
  }

  visitNamedMarking(context: NamedMarkingContext): void {
    const { count, token } = this.#lowerMarkingValue(context.markingValue());
    this.#contribution({
      kind: "metadata.named-marking",
      target: { type: "document" },
      value: {
        name: decodeName(context.markingName().getText()),
        entries: [
          {
            place: {
              type: "place",
              name: decodeName(context.place().name().getText()),
            },
            count,
            token,
          },
        ],
      },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitMetadataDescription(context: MetadataDescriptionContext): void {
    this.#contribution({
      kind: "documentation.description",
      target: this.#metadataTarget(context.metadataTarget()),
      value: { text: decodeString(context.STRING().getText()) },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitMetadataAnnotation(context: MetadataAnnotationContext): void {
    this.#contribution({
      kind: "documentation.annotation",
      target: this.#metadataTarget(context.metadataTarget()),
      value: {
        key: decodeName(context.name().getText()),
        value: this.#lowerJsonValue(context.jsonValue()),
      },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitViewPosition(context: ViewPositionContext): void {
    const target = context.viewTarget_list();
    const subject = this.#viewTarget(target[0]);
    const base = target.length > 1 ? this.#viewTarget(target[1]) : undefined;
    const delta = this.#lowerJsonObject(context.jsonObject());
    const position: ReadonlyJsonObject =
      base !== undefined ? { from: base, delta } : delta;
    this.#contribution({
      kind: "view.position",
      target: { type: "view", name: decodeName(context.name().getText()) },
      value: { subject, position },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  #viewTarget(target: ViewTargetContext): ReadonlyJsonObject {
    const place = target.place() as PlaceContext | undefined;
    if (place) {
      const placeName = decodeName(place.name().getText());
      const copy = target.transition() as TransitionContext | undefined;
      if (copy) {
        return {
          type: "placeCopy",
          place: placeName,
          transition: decodeName(copy.name().getText()),
        };
      }
      return { type: "place", name: placeName };
    }
    const transition = target.transition() as TransitionContext | undefined;
    if (!transition) {
      throw new Error("view target must be a place, place copy, or transition");
    }
    return { type: "transition", name: decodeName(transition.name().getText()) };
  }

  visitViewRoute(context: ViewRouteContext): void {
    const names = context.name_list();
    this.#contribution({
      kind: "view.route",
      target: {
        type: "arcHandle",
        name: decodeName(names[1]!.getText()),
      },
      value: {
        view: { type: "view", name: decodeName(names[0]!.getText()) },
        points: context
          .jsonArray()
          .jsonValue_list()
          .map((point) => this.#lowerJsonValue(point)),
      },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  #viewStyle(
    context: ViewSplinesContext | ViewDetailContext,
    member: "splines" | "detail",
    allowed: readonly string[],
  ): void {
    const [viewName, rawValue] = context
      .name_list()
      .map((name) => decodeName(name.getText())) as [string, string];
    if (!allowed.includes(rawValue)) {
      this.#semanticError(
        `unknown ${member} value ${pythonStringRepr(rawValue)} for view ${pythonStringRepr(viewName)}; expected one of ${allowed.join(", ")}`,
        context,
      );
    }
    this.#contribution({
      kind: `view.${member}`,
      target: { type: "view", name: viewName },
      value: { [member]: rawValue },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitDecoration(context: DecorationContext): void {
    let kind: string;
    let target: ReadonlyJsonObject;
    let value: ReadonlyJsonObject;
    if (context.COLOR_KEYWORD() as TerminalNode | undefined) {
      const colorName = decodeName(context.color().getText());
      target = { type: "color", name: colorName };
      if (context.SHOW() as TerminalNode | undefined) {
        const fields: string[] = [];
        for (const stringNode of context.STRING_list()) {
          const path = decodeString(stringNode.getText());
          if (!validFieldPath(path)) {
            this.#semanticError(
              `show field path ${stringNode.getText()} has an empty key; write keys separated by single dots`,
              context,
            );
          }
          if (fields.includes(path)) {
            this.#semanticError(
              `show decoration for color ${colorName} repeats field path ${stringNode.getText()}`,
              context,
            );
          }
          fields.push(path);
        }
        kind = "decoration.show";
        value = { fields };
      } else {
        kind = "decoration.quiet";
        value = {};
      }
    } else {
      const targetContext = context.decorationTarget();
      const place = targetContext.place() as PlaceContext | undefined;
      const transition = targetContext.transition() as TransitionContext | undefined;
      const targetName = decodeName(
        (place ?? transition)?.name().getText() ?? targetContext.name().getText(),
      );
      target = {
        type: place ? "place" : transition ? "transition" : "arcHandle",
        name: targetName,
      };
      const stringNode = context.STRING_list()[0] as TerminalNode | undefined;
      const text = stringNode ? decodeString(stringNode.getText()) : undefined;
      if (context.HIGHLIGHT() as TerminalNode | undefined) {
        kind = "decoration.highlight";
        value = text === undefined ? {} : { label: text };
      } else if (context.NOTE() as TerminalNode | undefined) {
        kind = "decoration.note";
        value = { text: text as string };
      } else if (context.BESIDE() as TerminalNode | undefined) {
        if (!place) {
          this.#semanticError(
            `beside decorations apply to fusion places; ${targetContext.getText()} has no local copies to place`,
            context,
          );
        }
        const side = (context.LEFT() as TerminalNode | undefined)
          ? "left"
          : (context.RIGHT() as TerminalNode | undefined)
            ? "right"
            : undefined;
        const besideValue: Record<string, string | boolean> = {};
        if (side !== undefined) besideValue.side = side;
        if (context.UNSHARED() as TerminalNode | undefined) besideValue.share = false;
        kind = "decoration.beside";
        value = besideValue;
      } else {
        if (place) {
          this.#semanticError(
            `summary decorations apply to transitions and arcs; place (${targetName}) has no expression to summarize`,
            context,
          );
        }
        kind = "decoration.summary";
        value = { text: text as string };
      }
    }
    this.#contribution({
      kind,
      target,
      value,
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitExtensions(context: ExtensionsContext): void {
    this.#contribution({
      kind: "document.extensions",
      target: { type: "document" },
      value: { extensions: this.#lowerJsonObject(context.jsonObject()) },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitDomainDeclaration(context: DomainDeclarationContext): void {
    const color = decodeName(context.color().getText());
    const pathContext = context.fieldPath();
    const keys = pathContext.name_list().map((name) => decodeName(name.getText()));
    const path = keys.join(".");
    if (!keys.every((key) => key.length > 0 && !key.includes("."))) {
      return this.#semanticError(
        `domain field path ${pythonStringRepr(path)} for color ${color} needs non-empty keys without dots`,
        pathContext,
      );
    }
    const values: TaggedJsonValue[] = [];
    const seen: JsonValue[] = [];
    for (const valueContext of context.domainValue_list()) {
      const tagged = this.#lowerJsonValue(valueContext);
      const value = untag(tagged);
      if (seen.includes(value)) {
        return this.#semanticError(
          `domain ${color}.${path} repeats the value ${valueContext.getText()}`,
          valueContext,
        );
      }
      seen.push(value);
      values.push(tagged);
    }
    this.#contribution({
      kind: "domain.values",
      target: { type: "color", name: color },
      value: { path, values } as unknown as ReadonlyJsonObject,
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitFinalDeclaration(context: FinalDeclarationContext): void {
    const seen: string[][] = [];
    context.finalMarking_list().forEach((markingContext, part) => {
      const names: string[] = [];
      for (const placeContext of markingContext.place_list()) {
        const name = decodeName(placeContext.name().getText());
        if (names.includes(name)) {
          this.#semanticError(
            `final names (${name}) more than once in one marking`,
            placeContext,
          );
        }
        names.push(name);
      }
      if (
        seen.some(
          (known) =>
            known.length === names.length && known.every((name) => names.includes(name)),
        )
      ) {
        this.#semanticError(
          `final names ${names.map((name) => `(${name})`).join(" + ")} more than once`,
          markingContext,
        );
      }
      seen.push(names);
      this.#contribution({
        kind: "proof.final",
        target: { type: "place", name: names[0]! },
        value: names.length > 1 ? { with: names.slice(1) } : {},
        start: this.#contextStart(markingContext),
        end: this.#contextEnd(markingContext),
        part,
      });
    });
  }

  visitInvariantDeclaration(context: InvariantDeclarationContext): void {
    const terms: Array<{ place: string; weight: number }> = [];
    for (const termContext of context.invariantTerm_list()) {
      const name = decodeName(termContext.place().name().getText());
      if (terms.some((term) => term.place === name)) {
        return this.#semanticError(
          `invariant names (${name}) more than once`,
          termContext,
        );
      }
      const weightContext = termContext.positiveInteger() as
        | PositiveIntegerContext
        | undefined;
      terms.push({
        place: name,
        weight: weightContext ? this.#safeInteger(weightContext) : 1,
      });
    }
    const value: Record<string, JsonValue> = { terms };
    const nameNode = context.STRING() as TerminalNode | undefined;
    if (nameNode) {
      const name = decodeString(nameNode.getText());
      if (name.length === 0) {
        return this.#semanticError("an invariant name must not be empty", context);
      }
      value.name = name;
    }
    const constantContext = context.nonnegativeInteger() as
      | ParserRuleContext
      | undefined;
    if (constantContext) value.constant = this.#safeInteger(constantContext);
    this.#contribution({
      kind: "proof.invariant",
      target: { type: "document", kind: "net" },
      value,
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  #actorName(context: ParserRuleContext): string {
    const actor = decodeName(context.getText());
    if (actor.length === 0) {
      return this.#semanticError("an actor name must not be empty", context);
    }
    return actor;
  }

  visitActorAssignment(context: ActorAssignmentContext): void {
    // The actor is an ordinary annotation under the well-known key
    // `actor`, as `fusion` is: the engine ignores it, the merge carries it.
    this.#contribution({
      kind: "documentation.annotation",
      target: this.#metadataTarget(context.actorTarget()),
      value: {
        key: "actor",
        value: { type: "string", value: this.#actorName(context.name()) },
      },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  visitActorDeclaration(context: ActorDeclarationContext): void {
    this.#contribution({
      kind: "actor.declare",
      target: { type: "document", kind: "net" },
      value: {
        name: this.#actorName(context.name()),
        kind: (context.PERSON() as TerminalNode | undefined)
          ? "person"
          : (context.RECORD() as TerminalNode | undefined)
            ? "record"
            : "system",
      },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  #placeAnnotation(
    context: PlaceLivesContext | PlaceReadsAsContext | PlaceKeptContext,
    key: string,
    value: TaggedJsonValue,
  ): void {
    this.#contribution({
      kind: "documentation.annotation",
      target: { type: "place", name: decodeName(context.place().name().getText()) },
      value: { key, value },
      start: this.#contextStart(context),
      end: this.#contextEnd(context),
    });
  }

  #celObject(text: string): TaggedJsonValue {
    return {
      type: "object",
      entries: [{ key: "cel", value: { type: "string", value: decodeName(text) } }],
    };
  }

  visitPlaceLives(context: PlaceLivesContext): void {
    // Where a place lives in a sequence diagram: a lifeline name, or CEL
    // over the token that computes one. An annotation, as `actor` is.
    const value: TaggedJsonValue = (context.CEL() as TerminalNode | undefined)
      ? this.#celObject(context.STRING().getText())
      : { type: "string", value: this.#actorName(context.name()) };
    this.#placeAnnotation(context, "lives", value);
  }

  visitPlaceReadsAs(context: PlaceReadsAsContext): void {
    this.#placeAnnotation(context, "reads_as", this.#celObject(context.STRING().getText()));
  }

  visitPlaceKept(context: PlaceKeptContext): void {
    // A record this net keeps, there from the start (ADR 0051). An
    // annotation, as `lives` is: the engine ignores it.
    this.#placeAnnotation(context, "kept", {
      type: "object",
      entries: [
        { key: "by", value: { type: "string", value: this.#actorName(context.name()) } },
        { key: "start", value: this.#celObject(context.STRING().getText()) },
      ],
    });
  }
}

/**
 * Parse one complete DSL document into portable, JSON-only Contribution IR.
 *
 * Syntax-only parsing of the same grammar lives in `@velocitron/grammar`
 * (`packages/grammar/typescript`). This function is the lowering step.
 * `python3 tools/dsl_package.py` copies it into `@velocitron/dsl`
 * (`packages/dsl/typescript`). It does not re-export either package. CEL
 * compilation and contribution resolution ship in `@velocitron/petrinet`.
 * Composition merge ships in `packages/merge`.
 */
export function lowerPetrinetText(
  text: string,
  sourceId = "<memory>",
): ContributionIr {
  inspectSource(text, sourceId);
  const coordinates = new SourceCoordinates(sourceId, text);
  const lexer = new VelocitronPetriNetLexer(CharStreams.fromString(text));
  installLexerLimits(lexer);
  const listener = new SyntaxListener(coordinates);
  lexer.removeErrorListeners();
  lexer.addErrorListener(listener as unknown as ErrorListener<number>);

  const stream = new CommonTokenStream(lexer);
  const parser = new VelocitronPetriNetParser(stream);
  parser.removeErrorListeners();
  parser.addErrorListener(listener as unknown as ErrorListener<Token>);
  const tree = parser.document();
  stream.fill();
  if (listener.diagnostics.length > 0) {
    throw new PetrinetDslError(listener.diagnostics[0] as Diagnostic);
  }

  const visitor = new LoweringVisitor(coordinates);
  visitor.visitor.visit(tree);
  return {
    format: CONTRIBUTION_FORMAT,
    version: CONTRIBUTION_VERSION,
    documentKind: visitor.documentKind,
    document: { id: sourceId },
    contributions: visitor.contributions,
  } as unknown as ContributionIr;
}
