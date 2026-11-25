/**
 * Render an already-built Velocitron net as Graphviz DOT.
 *
 * `netToDot` draws one net. `applyView` pins authored positions and routes
 * onto that drawing. `fusionLayout` places fusion copies, including one
 * shared copy between two neighbor transitions of one choice.
 *
 * Pass a net the caller already built. This package does not parse
 * documents, compile CEL, or install a console script, and it does not
 * import the umbrella implementation. Composition diagrams, the feature
 * legend, and paired walkthrough graphs stay in the Python package. The
 * published TypeScript implementation does not render nets.
 *
 * This package is the TypeScript renderer. Edit it here. The umbrella does
 * not render nets.
 */

export {renderCanonicalJson} from "./canonical.js";
export {
  DETAIL_LEVELS,
  fusionCopy,
  fusionLayout,
  markingRows,
  memberLabel,
  netRenderModel,
  netToDot,
  siblingGroups,
} from "./render.js";
export type {
  BesidePlacement,
  Detail,
  FusionLayout,
  MarkingRow,
  NetRenderOptions,
  RenderModel,
  RenderStyle,
} from "./render.js";
export type {
  Arc,
  ConsumePattern,
  Marking,
  Net,
  Place,
  Port,
  Predicate,
  ProduceTemplate,
  Token,
  Transition,
} from "./schema/types.js";
export {
  BESIDE_MARGIN,
  DEFAULT_VIEW,
  NAME_POINT,
  NODE_PAD,
  SMALL_POINT,
  ViewApplicationError,
  applyView,
  besideGap,
  nodeWidth,
  textWidth,
  hasView,
  readDecorations,
  resolvePositions,
  viewSetting,
} from "./view.js";
export type {Decoration, Decorations} from "./view.js";
