// Generated from VelocitronPetriNet.g4 by ANTLR 4.13.2

import {ParseTreeVisitor} from 'antlr4';


import { DocumentContext } from "./VelocitronPetriNetParser.js";
import { NetHeaderContext } from "./VelocitronPetriNetParser.js";
import { CompositionHeaderContext } from "./VelocitronPetriNetParser.js";
import { CompositionUseContext } from "./VelocitronPetriNetParser.js";
import { CompositionWireContext } from "./VelocitronPetriNetParser.js";
import { CompositionShareContext } from "./VelocitronPetriNetParser.js";
import { CompositionRefineContext } from "./VelocitronPetriNetParser.js";
import { CompositionFinalContext } from "./VelocitronPetriNetParser.js";
import { CompositionFinalMarkingContext } from "./VelocitronPetriNetParser.js";
import { CompositionPlaceContext } from "./VelocitronPetriNetParser.js";
import { CompositionTransitionContext } from "./VelocitronPetriNetParser.js";
import { ChainContext } from "./VelocitronPetriNetParser.js";
import { ChainNodeContext } from "./VelocitronPetriNetParser.js";
import { ArcSegmentContext } from "./VelocitronPetriNetParser.js";
import { ArcOperatorContext } from "./VelocitronPetriNetParser.js";
import { AdditionalChainContext } from "./VelocitronPetriNetParser.js";
import { ChainHandleContext } from "./VelocitronPetriNetParser.js";
import { PlaceContext } from "./VelocitronPetriNetParser.js";
import { TransitionContext } from "./VelocitronPetriNetParser.js";
import { PlaceDeclarationContext } from "./VelocitronPetriNetParser.js";
import { TransitionDeclarationContext } from "./VelocitronPetriNetParser.js";
import { PlacePortContext } from "./VelocitronPetriNetParser.js";
import { PortDirectionContext } from "./VelocitronPetriNetParser.js";
import { TransitionHandlerContext } from "./VelocitronPetriNetParser.js";
import { AdditionalTransitionHandlerContext } from "./VelocitronPetriNetParser.js";
import { TransitionGuardContext } from "./VelocitronPetriNetParser.js";
import { TransitionTimerContext } from "./VelocitronPetriNetParser.js";
import { TransitionTimerBindContext } from "./VelocitronPetriNetParser.js";
import { TransitionTimerMaturityContext } from "./VelocitronPetriNetParser.js";
import { TransitionBindingNameContext } from "./VelocitronPetriNetParser.js";
import { TimerBindNameContext } from "./VelocitronPetriNetParser.js";
import { TransitionPriorityContext } from "./VelocitronPetriNetParser.js";
import { TransitionOrderContext } from "./VelocitronPetriNetParser.js";
import { ChainOrderContext } from "./VelocitronPetriNetParser.js";
import { PlaceAcceptsContext } from "./VelocitronPetriNetParser.js";
import { PlaceCapacityContext } from "./VelocitronPetriNetParser.js";
import { ArcWeightContext } from "./VelocitronPetriNetParser.js";
import { ArcDataContext } from "./VelocitronPetriNetParser.js";
import { ArcPredicateContext } from "./VelocitronPetriNetParser.js";
import { ArcCorrelateContext } from "./VelocitronPetriNetParser.js";
import { PredicateKindContext } from "./VelocitronPetriNetParser.js";
import { PositiveIntegerContext } from "./VelocitronPetriNetParser.js";
import { NonnegativeIntegerContext } from "./VelocitronPetriNetParser.js";
import { InitialMarkingContext } from "./VelocitronPetriNetParser.js";
import { AdditionalInitialMarkingContext } from "./VelocitronPetriNetParser.js";
import { NamedMarkingContext } from "./VelocitronPetriNetParser.js";
import { MarkingValueContext } from "./VelocitronPetriNetParser.js";
import { MetadataDescriptionContext } from "./VelocitronPetriNetParser.js";
import { MetadataAnnotationContext } from "./VelocitronPetriNetParser.js";
import { MetadataTargetContext } from "./VelocitronPetriNetParser.js";
import { ViewPositionContext } from "./VelocitronPetriNetParser.js";
import { ViewRouteContext } from "./VelocitronPetriNetParser.js";
import { ViewSplinesContext } from "./VelocitronPetriNetParser.js";
import { ViewDetailContext } from "./VelocitronPetriNetParser.js";
import { ViewTargetContext } from "./VelocitronPetriNetParser.js";
import { DecorationContext } from "./VelocitronPetriNetParser.js";
import { DecorationTargetContext } from "./VelocitronPetriNetParser.js";
import { ExtensionsContext } from "./VelocitronPetriNetParser.js";
import { DomainDeclarationContext } from "./VelocitronPetriNetParser.js";
import { FieldPathContext } from "./VelocitronPetriNetParser.js";
import { DomainValueContext } from "./VelocitronPetriNetParser.js";
import { FinalDeclarationContext } from "./VelocitronPetriNetParser.js";
import { FinalMarkingContext } from "./VelocitronPetriNetParser.js";
import { InvariantDeclarationContext } from "./VelocitronPetriNetParser.js";
import { InvariantTermContext } from "./VelocitronPetriNetParser.js";
import { ActorAssignmentContext } from "./VelocitronPetriNetParser.js";
import { ActorTargetContext } from "./VelocitronPetriNetParser.js";
import { ActorDeclarationContext } from "./VelocitronPetriNetParser.js";
import { PlaceLivesContext } from "./VelocitronPetriNetParser.js";
import { PlaceReadsAsContext } from "./VelocitronPetriNetParser.js";
import { PlaceKeptContext } from "./VelocitronPetriNetParser.js";
import { TemplateDefinitionContext } from "./VelocitronPetriNetParser.js";
import { AdditionalTemplateDefinitionContext } from "./VelocitronPetriNetParser.js";
import { TemplateReferenceContext } from "./VelocitronPetriNetParser.js";
import { ColorContext } from "./VelocitronPetriNetParser.js";
import { NameContext } from "./VelocitronPetriNetParser.js";
import { MarkingNameContext } from "./VelocitronPetriNetParser.js";
import { KeywordContext } from "./VelocitronPetriNetParser.js";
import { JsonValueContext } from "./VelocitronPetriNetParser.js";
import { JsonObjectContext } from "./VelocitronPetriNetParser.js";
import { JsonArrayContext } from "./VelocitronPetriNetParser.js";


/**
 * This interface defines a complete generic visitor for a parse tree produced
 * by `VelocitronPetriNetParser`.
 *
 * @param <Result> The return type of the visit operation. Use `void` for
 * operations with no return type.
 */
export default class VelocitronPetriNetVisitor<Result> extends ParseTreeVisitor<Result> {
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.document`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitDocument?: (ctx: DocumentContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.netHeader`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitNetHeader?: (ctx: NetHeaderContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.compositionHeader`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitCompositionHeader?: (ctx: CompositionHeaderContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.compositionUse`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitCompositionUse?: (ctx: CompositionUseContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.compositionWire`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitCompositionWire?: (ctx: CompositionWireContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.compositionShare`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitCompositionShare?: (ctx: CompositionShareContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.compositionRefine`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitCompositionRefine?: (ctx: CompositionRefineContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.compositionFinal`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitCompositionFinal?: (ctx: CompositionFinalContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.compositionFinalMarking`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitCompositionFinalMarking?: (ctx: CompositionFinalMarkingContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.compositionPlace`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitCompositionPlace?: (ctx: CompositionPlaceContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.compositionTransition`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitCompositionTransition?: (ctx: CompositionTransitionContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.chain`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitChain?: (ctx: ChainContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.chainNode`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitChainNode?: (ctx: ChainNodeContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.arcSegment`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitArcSegment?: (ctx: ArcSegmentContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.arcOperator`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitArcOperator?: (ctx: ArcOperatorContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.additionalChain`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitAdditionalChain?: (ctx: AdditionalChainContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.chainHandle`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitChainHandle?: (ctx: ChainHandleContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.place`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitPlace?: (ctx: PlaceContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.transition`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitTransition?: (ctx: TransitionContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.placeDeclaration`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitPlaceDeclaration?: (ctx: PlaceDeclarationContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.transitionDeclaration`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitTransitionDeclaration?: (ctx: TransitionDeclarationContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.placePort`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitPlacePort?: (ctx: PlacePortContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.portDirection`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitPortDirection?: (ctx: PortDirectionContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.transitionHandler`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitTransitionHandler?: (ctx: TransitionHandlerContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.additionalTransitionHandler`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitAdditionalTransitionHandler?: (ctx: AdditionalTransitionHandlerContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.transitionGuard`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitTransitionGuard?: (ctx: TransitionGuardContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.transitionTimer`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitTransitionTimer?: (ctx: TransitionTimerContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.transitionTimerBind`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitTransitionTimerBind?: (ctx: TransitionTimerBindContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.transitionTimerMaturity`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitTransitionTimerMaturity?: (ctx: TransitionTimerMaturityContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.transitionBindingName`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitTransitionBindingName?: (ctx: TransitionBindingNameContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.timerBindName`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitTimerBindName?: (ctx: TimerBindNameContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.transitionPriority`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitTransitionPriority?: (ctx: TransitionPriorityContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.transitionOrder`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitTransitionOrder?: (ctx: TransitionOrderContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.chainOrder`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitChainOrder?: (ctx: ChainOrderContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.placeAccepts`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitPlaceAccepts?: (ctx: PlaceAcceptsContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.placeCapacity`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitPlaceCapacity?: (ctx: PlaceCapacityContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.arcWeight`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitArcWeight?: (ctx: ArcWeightContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.arcData`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitArcData?: (ctx: ArcDataContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.arcPredicate`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitArcPredicate?: (ctx: ArcPredicateContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.arcCorrelate`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitArcCorrelate?: (ctx: ArcCorrelateContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.predicateKind`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitPredicateKind?: (ctx: PredicateKindContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.positiveInteger`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitPositiveInteger?: (ctx: PositiveIntegerContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.nonnegativeInteger`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitNonnegativeInteger?: (ctx: NonnegativeIntegerContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.initialMarking`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitInitialMarking?: (ctx: InitialMarkingContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.additionalInitialMarking`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitAdditionalInitialMarking?: (ctx: AdditionalInitialMarkingContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.namedMarking`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitNamedMarking?: (ctx: NamedMarkingContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.markingValue`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitMarkingValue?: (ctx: MarkingValueContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.metadataDescription`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitMetadataDescription?: (ctx: MetadataDescriptionContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.metadataAnnotation`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitMetadataAnnotation?: (ctx: MetadataAnnotationContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.metadataTarget`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitMetadataTarget?: (ctx: MetadataTargetContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.viewPosition`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitViewPosition?: (ctx: ViewPositionContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.viewRoute`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitViewRoute?: (ctx: ViewRouteContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.viewSplines`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitViewSplines?: (ctx: ViewSplinesContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.viewDetail`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitViewDetail?: (ctx: ViewDetailContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.viewTarget`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitViewTarget?: (ctx: ViewTargetContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.decoration`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitDecoration?: (ctx: DecorationContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.decorationTarget`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitDecorationTarget?: (ctx: DecorationTargetContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.extensions`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitExtensions?: (ctx: ExtensionsContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.domainDeclaration`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitDomainDeclaration?: (ctx: DomainDeclarationContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.fieldPath`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitFieldPath?: (ctx: FieldPathContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.domainValue`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitDomainValue?: (ctx: DomainValueContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.finalDeclaration`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitFinalDeclaration?: (ctx: FinalDeclarationContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.finalMarking`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitFinalMarking?: (ctx: FinalMarkingContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.invariantDeclaration`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitInvariantDeclaration?: (ctx: InvariantDeclarationContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.invariantTerm`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitInvariantTerm?: (ctx: InvariantTermContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.actorAssignment`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitActorAssignment?: (ctx: ActorAssignmentContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.actorTarget`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitActorTarget?: (ctx: ActorTargetContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.actorDeclaration`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitActorDeclaration?: (ctx: ActorDeclarationContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.placeLives`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitPlaceLives?: (ctx: PlaceLivesContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.placeReadsAs`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitPlaceReadsAs?: (ctx: PlaceReadsAsContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.placeKept`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitPlaceKept?: (ctx: PlaceKeptContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.templateDefinition`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitTemplateDefinition?: (ctx: TemplateDefinitionContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.additionalTemplateDefinition`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitAdditionalTemplateDefinition?: (ctx: AdditionalTemplateDefinitionContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.templateReference`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitTemplateReference?: (ctx: TemplateReferenceContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.color`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitColor?: (ctx: ColorContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.name`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitName?: (ctx: NameContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.markingName`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitMarkingName?: (ctx: MarkingNameContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.keyword`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitKeyword?: (ctx: KeywordContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.jsonValue`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitJsonValue?: (ctx: JsonValueContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.jsonObject`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitJsonObject?: (ctx: JsonObjectContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPetriNetParser.jsonArray`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitJsonArray?: (ctx: JsonArrayContext) => Result;
}
