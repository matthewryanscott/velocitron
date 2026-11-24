# Generated from VelocitronPlay.g4 by ANTLR 4.13.2
# ruff: noqa: F403, F405
from antlr4 import *

if "." in __name__:
    from .VelocitronPlayParser import VelocitronPlayParser
else:
    from VelocitronPlayParser import VelocitronPlayParser

# This class defines a complete generic visitor for a parse tree produced by VelocitronPlayParser.


class VelocitronPlayVisitor(ParseTreeVisitor):
    # Visit a parse tree produced by VelocitronPlayParser#statement.
    def visitStatement(self, ctx: VelocitronPlayParser.StatementContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#header.
    def visitHeader(self, ctx: VelocitronPlayParser.HeaderContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#netSetting.
    def visitNetSetting(self, ctx: VelocitronPlayParser.NetSettingContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#useSetting.
    def visitUseSetting(self, ctx: VelocitronPlayParser.UseSettingContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#wireSetting.
    def visitWireSetting(self, ctx: VelocitronPlayParser.WireSettingContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#shareSetting.
    def visitShareSetting(self, ctx: VelocitronPlayParser.ShareSettingContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#refineSetting.
    def visitRefineSetting(self, ctx: VelocitronPlayParser.RefineSettingContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#markingSetting.
    def visitMarkingSetting(self, ctx: VelocitronPlayParser.MarkingSettingContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#instanceSetting.
    def visitInstanceSetting(self, ctx: VelocitronPlayParser.InstanceSettingContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#scopeSetting.
    def visitScopeSetting(self, ctx: VelocitronPlayParser.ScopeSettingContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#sequenceShow.
    def visitSequenceShow(self, ctx: VelocitronPlayParser.SequenceShowContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#colorShow.
    def visitColorShow(self, ctx: VelocitronPlayParser.ColorShowContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#actorSetting.
    def visitActorSetting(self, ctx: VelocitronPlayParser.ActorSettingContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#boxSetting.
    def visitBoxSetting(self, ctx: VelocitronPlayParser.BoxSettingContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#templateDecl.
    def visitTemplateDecl(self, ctx: VelocitronPlayParser.TemplateDeclContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#pathDecl.
    def visitPathDecl(self, ctx: VelocitronPlayParser.PathDeclContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#step.
    def visitStep(self, ctx: VelocitronPlayParser.StepContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#label.
    def visitLabel(self, ctx: VelocitronPlayParser.LabelContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#actorKind.
    def visitActorKind(self, ctx: VelocitronPlayParser.ActorKindContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#stepBody.
    def visitStepBody(self, ctx: VelocitronPlayParser.StepBodyContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#injectBody.
    def visitInjectBody(self, ctx: VelocitronPlayParser.InjectBodyContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#updateBody.
    def visitUpdateBody(self, ctx: VelocitronPlayParser.UpdateBodyContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#advanceBody.
    def visitAdvanceBody(self, ctx: VelocitronPlayParser.AdvanceBodyContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#fireBody.
    def visitFireBody(self, ctx: VelocitronPlayParser.FireBodyContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#expectBody.
    def visitExpectBody(self, ctx: VelocitronPlayParser.ExpectBodyContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#assumeBody.
    def visitAssumeBody(self, ctx: VelocitronPlayParser.AssumeBodyContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#withClause.
    def visitWithClause(self, ctx: VelocitronPlayParser.WithClauseContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#outputClause.
    def visitOutputClause(self, ctx: VelocitronPlayParser.OutputClauseContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#condition.
    def visitCondition(self, ctx: VelocitronPlayParser.ConditionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#timeValue.
    def visitTimeValue(self, ctx: VelocitronPlayParser.TimeValueContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#truthValue.
    def visitTruthValue(self, ctx: VelocitronPlayParser.TruthValueContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#tokenList.
    def visitTokenList(self, ctx: VelocitronPlayParser.TokenListContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#tokenExpr.
    def visitTokenExpr(self, ctx: VelocitronPlayParser.TokenExprContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#place.
    def visitPlace(self, ctx: VelocitronPlayParser.PlaceContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#transition.
    def visitTransition(self, ctx: VelocitronPlayParser.TransitionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#wireEnd.
    def visitWireEnd(self, ctx: VelocitronPlayParser.WireEndContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#fieldPath.
    def visitFieldPath(self, ctx: VelocitronPlayParser.FieldPathContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#color.
    def visitColor(self, ctx: VelocitronPlayParser.ColorContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#colorNotSequence.
    def visitColorNotSequence(self, ctx: VelocitronPlayParser.ColorNotSequenceContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#name.
    def visitName(self, ctx: VelocitronPlayParser.NameContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#qualifiedName.
    def visitQualifiedName(self, ctx: VelocitronPlayParser.QualifiedNameContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#singleName.
    def visitSingleName(self, ctx: VelocitronPlayParser.SingleNameContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#singleNameNotSequence.
    def visitSingleNameNotSequence(
        self, ctx: VelocitronPlayParser.SingleNameNotSequenceContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#keyword.
    def visitKeyword(self, ctx: VelocitronPlayParser.KeywordContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#keywordNotSequence.
    def visitKeywordNotSequence(
        self, ctx: VelocitronPlayParser.KeywordNotSequenceContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#jsonValue.
    def visitJsonValue(self, ctx: VelocitronPlayParser.JsonValueContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#jsonObject.
    def visitJsonObject(self, ctx: VelocitronPlayParser.JsonObjectContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by VelocitronPlayParser#jsonArray.
    def visitJsonArray(self, ctx: VelocitronPlayParser.JsonArrayContext):
        return self.visitChildren(ctx)


del VelocitronPlayParser
