# Generated from VelocitronPetriNet.g4 by ANTLR 4.13.2
# ruff: noqa: F403, F405
from antlr4 import *

if "." in __name__:
    from .VelocitronPetriNetParser import VelocitronPetriNetParser
else:
    from VelocitronPetriNetParser import VelocitronPetriNetParser

# This class defines a complete generic visitor for a parse tree produced by VelocitronPetriNetParser.


class VelocitronPetriNetVisitor(ParseTreeVisitor):
    # Visit a parse tree produced by VelocitronPetriNetParser#document.
    def visitDocument(self, ctx: VelocitronPetriNetParser.DocumentContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#netHeader.
    def visitNetHeader(self, ctx: VelocitronPetriNetParser.NetHeaderContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#compositionHeader.
    def visitCompositionHeader(
        self, ctx: VelocitronPetriNetParser.CompositionHeaderContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#compositionUse.
    def visitCompositionUse(self, ctx: VelocitronPetriNetParser.CompositionUseContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#compositionWire.
    def visitCompositionWire(
        self, ctx: VelocitronPetriNetParser.CompositionWireContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#compositionShare.
    def visitCompositionShare(
        self, ctx: VelocitronPetriNetParser.CompositionShareContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#compositionRefine.
    def visitCompositionRefine(
        self, ctx: VelocitronPetriNetParser.CompositionRefineContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#compositionFinal.
    def visitCompositionFinal(
        self, ctx: VelocitronPetriNetParser.CompositionFinalContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#compositionFinalMarking.
    def visitCompositionFinalMarking(
        self, ctx: VelocitronPetriNetParser.CompositionFinalMarkingContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#compositionPlace.
    def visitCompositionPlace(
        self, ctx: VelocitronPetriNetParser.CompositionPlaceContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#compositionTransition.
    def visitCompositionTransition(
        self, ctx: VelocitronPetriNetParser.CompositionTransitionContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#chain.
    def visitChain(self, ctx: VelocitronPetriNetParser.ChainContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#chainNode.
    def visitChainNode(self, ctx: VelocitronPetriNetParser.ChainNodeContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#arcSegment.
    def visitArcSegment(self, ctx: VelocitronPetriNetParser.ArcSegmentContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#arcOperator.
    def visitArcOperator(self, ctx: VelocitronPetriNetParser.ArcOperatorContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#additionalChain.
    def visitAdditionalChain(
        self, ctx: VelocitronPetriNetParser.AdditionalChainContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#chainHandle.
    def visitChainHandle(self, ctx: VelocitronPetriNetParser.ChainHandleContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#place.
    def visitPlace(self, ctx: VelocitronPetriNetParser.PlaceContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#transition.
    def visitTransition(self, ctx: VelocitronPetriNetParser.TransitionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#placeDeclaration.
    def visitPlaceDeclaration(
        self, ctx: VelocitronPetriNetParser.PlaceDeclarationContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#transitionDeclaration.
    def visitTransitionDeclaration(
        self, ctx: VelocitronPetriNetParser.TransitionDeclarationContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#placePort.
    def visitPlacePort(self, ctx: VelocitronPetriNetParser.PlacePortContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#portDirection.
    def visitPortDirection(self, ctx: VelocitronPetriNetParser.PortDirectionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#transitionHandler.
    def visitTransitionHandler(
        self, ctx: VelocitronPetriNetParser.TransitionHandlerContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#additionalTransitionHandler.
    def visitAdditionalTransitionHandler(
        self, ctx: VelocitronPetriNetParser.AdditionalTransitionHandlerContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#transitionGuard.
    def visitTransitionGuard(
        self, ctx: VelocitronPetriNetParser.TransitionGuardContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#transitionTimer.
    def visitTransitionTimer(
        self, ctx: VelocitronPetriNetParser.TransitionTimerContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#transitionTimerBind.
    def visitTransitionTimerBind(
        self, ctx: VelocitronPetriNetParser.TransitionTimerBindContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#transitionTimerMaturity.
    def visitTransitionTimerMaturity(
        self, ctx: VelocitronPetriNetParser.TransitionTimerMaturityContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#transitionBindingName.
    def visitTransitionBindingName(
        self, ctx: VelocitronPetriNetParser.TransitionBindingNameContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#timerBindName.
    def visitTimerBindName(self, ctx: VelocitronPetriNetParser.TimerBindNameContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#transitionPriority.
    def visitTransitionPriority(
        self, ctx: VelocitronPetriNetParser.TransitionPriorityContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#transitionOrder.
    def visitTransitionOrder(
        self, ctx: VelocitronPetriNetParser.TransitionOrderContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#chainOrder.
    def visitChainOrder(self, ctx: VelocitronPetriNetParser.ChainOrderContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#placeAccepts.
    def visitPlaceAccepts(self, ctx: VelocitronPetriNetParser.PlaceAcceptsContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#placeCapacity.
    def visitPlaceCapacity(self, ctx: VelocitronPetriNetParser.PlaceCapacityContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#arcWeight.
    def visitArcWeight(self, ctx: VelocitronPetriNetParser.ArcWeightContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#arcData.
    def visitArcData(self, ctx: VelocitronPetriNetParser.ArcDataContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#arcPredicate.
    def visitArcPredicate(self, ctx: VelocitronPetriNetParser.ArcPredicateContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#arcCorrelate.
    def visitArcCorrelate(self, ctx: VelocitronPetriNetParser.ArcCorrelateContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#predicateKind.
    def visitPredicateKind(self, ctx: VelocitronPetriNetParser.PredicateKindContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#positiveInteger.
    def visitPositiveInteger(
        self, ctx: VelocitronPetriNetParser.PositiveIntegerContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#nonnegativeInteger.
    def visitNonnegativeInteger(
        self, ctx: VelocitronPetriNetParser.NonnegativeIntegerContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#initialMarking.
    def visitInitialMarking(self, ctx: VelocitronPetriNetParser.InitialMarkingContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#additionalInitialMarking.
    def visitAdditionalInitialMarking(
        self, ctx: VelocitronPetriNetParser.AdditionalInitialMarkingContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#namedMarking.
    def visitNamedMarking(self, ctx: VelocitronPetriNetParser.NamedMarkingContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#markingValue.
    def visitMarkingValue(self, ctx: VelocitronPetriNetParser.MarkingValueContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#metadataDescription.
    def visitMetadataDescription(
        self, ctx: VelocitronPetriNetParser.MetadataDescriptionContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#metadataAnnotation.
    def visitMetadataAnnotation(
        self, ctx: VelocitronPetriNetParser.MetadataAnnotationContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#metadataTarget.
    def visitMetadataTarget(self, ctx: VelocitronPetriNetParser.MetadataTargetContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#viewPosition.
    def visitViewPosition(self, ctx: VelocitronPetriNetParser.ViewPositionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#viewRoute.
    def visitViewRoute(self, ctx: VelocitronPetriNetParser.ViewRouteContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#viewSplines.
    def visitViewSplines(self, ctx: VelocitronPetriNetParser.ViewSplinesContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#viewDetail.
    def visitViewDetail(self, ctx: VelocitronPetriNetParser.ViewDetailContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#viewFusion.
    def visitViewFusion(self, ctx: VelocitronPetriNetParser.ViewFusionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#viewTarget.
    def visitViewTarget(self, ctx: VelocitronPetriNetParser.ViewTargetContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#decoration.
    def visitDecoration(self, ctx: VelocitronPetriNetParser.DecorationContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#decorationTarget.
    def visitDecorationTarget(
        self, ctx: VelocitronPetriNetParser.DecorationTargetContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#extensions.
    def visitExtensions(self, ctx: VelocitronPetriNetParser.ExtensionsContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#domainDeclaration.
    def visitDomainDeclaration(
        self, ctx: VelocitronPetriNetParser.DomainDeclarationContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#fieldPath.
    def visitFieldPath(self, ctx: VelocitronPetriNetParser.FieldPathContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#domainValue.
    def visitDomainValue(self, ctx: VelocitronPetriNetParser.DomainValueContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#finalDeclaration.
    def visitFinalDeclaration(
        self, ctx: VelocitronPetriNetParser.FinalDeclarationContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#finalMarking.
    def visitFinalMarking(self, ctx: VelocitronPetriNetParser.FinalMarkingContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#invariantDeclaration.
    def visitInvariantDeclaration(
        self, ctx: VelocitronPetriNetParser.InvariantDeclarationContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#invariantTerm.
    def visitInvariantTerm(self, ctx: VelocitronPetriNetParser.InvariantTermContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#actorAssignment.
    def visitActorAssignment(
        self, ctx: VelocitronPetriNetParser.ActorAssignmentContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#actorTarget.
    def visitActorTarget(self, ctx: VelocitronPetriNetParser.ActorTargetContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#actorDeclaration.
    def visitActorDeclaration(
        self, ctx: VelocitronPetriNetParser.ActorDeclarationContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#placeLives.
    def visitPlaceLives(self, ctx: VelocitronPetriNetParser.PlaceLivesContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#placeReadsAs.
    def visitPlaceReadsAs(self, ctx: VelocitronPetriNetParser.PlaceReadsAsContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#placeKept.
    def visitPlaceKept(self, ctx: VelocitronPetriNetParser.PlaceKeptContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#templateDefinition.
    def visitTemplateDefinition(
        self, ctx: VelocitronPetriNetParser.TemplateDefinitionContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#additionalTemplateDefinition.
    def visitAdditionalTemplateDefinition(
        self, ctx: VelocitronPetriNetParser.AdditionalTemplateDefinitionContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#templateReference.
    def visitTemplateReference(
        self, ctx: VelocitronPetriNetParser.TemplateReferenceContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#color.
    def visitColor(self, ctx: VelocitronPetriNetParser.ColorContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#name.
    def visitName(self, ctx: VelocitronPetriNetParser.NameContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#markingName.
    def visitMarkingName(self, ctx: VelocitronPetriNetParser.MarkingNameContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#keyword.
    def visitKeyword(self, ctx: VelocitronPetriNetParser.KeywordContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#jsonValue.
    def visitJsonValue(self, ctx: VelocitronPetriNetParser.JsonValueContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#jsonObject.
    def visitJsonObject(self, ctx: VelocitronPetriNetParser.JsonObjectContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPetriNetParser#jsonArray.
    def visitJsonArray(self, ctx: VelocitronPetriNetParser.JsonArrayContext):
        return self.visitChildren(ctx)


del VelocitronPetriNetParser
