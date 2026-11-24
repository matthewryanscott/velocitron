// Generated from VelocitronPlay.g4 by ANTLR 4.13.2

import {ParseTreeVisitor} from 'antlr4';


import { StatementContext } from "./VelocitronPlayParser.js";
import { HeaderContext } from "./VelocitronPlayParser.js";
import { NetSettingContext } from "./VelocitronPlayParser.js";
import { UseSettingContext } from "./VelocitronPlayParser.js";
import { WireSettingContext } from "./VelocitronPlayParser.js";
import { ShareSettingContext } from "./VelocitronPlayParser.js";
import { RefineSettingContext } from "./VelocitronPlayParser.js";
import { MarkingSettingContext } from "./VelocitronPlayParser.js";
import { InstanceSettingContext } from "./VelocitronPlayParser.js";
import { ScopeSettingContext } from "./VelocitronPlayParser.js";
import { SequenceShowContext } from "./VelocitronPlayParser.js";
import { ColorShowContext } from "./VelocitronPlayParser.js";
import { ActorSettingContext } from "./VelocitronPlayParser.js";
import { BoxSettingContext } from "./VelocitronPlayParser.js";
import { TemplateDeclContext } from "./VelocitronPlayParser.js";
import { PathDeclContext } from "./VelocitronPlayParser.js";
import { StepContext } from "./VelocitronPlayParser.js";
import { LabelContext } from "./VelocitronPlayParser.js";
import { ActorKindContext } from "./VelocitronPlayParser.js";
import { StepBodyContext } from "./VelocitronPlayParser.js";
import { InjectBodyContext } from "./VelocitronPlayParser.js";
import { UpdateBodyContext } from "./VelocitronPlayParser.js";
import { AdvanceBodyContext } from "./VelocitronPlayParser.js";
import { FireBodyContext } from "./VelocitronPlayParser.js";
import { ExpectBodyContext } from "./VelocitronPlayParser.js";
import { AssumeBodyContext } from "./VelocitronPlayParser.js";
import { WithClauseContext } from "./VelocitronPlayParser.js";
import { OutputClauseContext } from "./VelocitronPlayParser.js";
import { ConditionContext } from "./VelocitronPlayParser.js";
import { TimeValueContext } from "./VelocitronPlayParser.js";
import { TruthValueContext } from "./VelocitronPlayParser.js";
import { TokenListContext } from "./VelocitronPlayParser.js";
import { TokenExprContext } from "./VelocitronPlayParser.js";
import { PlaceContext } from "./VelocitronPlayParser.js";
import { TransitionContext } from "./VelocitronPlayParser.js";
import { WireEndContext } from "./VelocitronPlayParser.js";
import { FieldPathContext } from "./VelocitronPlayParser.js";
import { ColorContext } from "./VelocitronPlayParser.js";
import { ColorNotSequenceContext } from "./VelocitronPlayParser.js";
import { NameContext } from "./VelocitronPlayParser.js";
import { QualifiedNameContext } from "./VelocitronPlayParser.js";
import { SingleNameContext } from "./VelocitronPlayParser.js";
import { SingleNameNotSequenceContext } from "./VelocitronPlayParser.js";
import { KeywordContext } from "./VelocitronPlayParser.js";
import { KeywordNotSequenceContext } from "./VelocitronPlayParser.js";
import { JsonValueContext } from "./VelocitronPlayParser.js";
import { JsonObjectContext } from "./VelocitronPlayParser.js";
import { JsonArrayContext } from "./VelocitronPlayParser.js";


/**
 * This interface defines a complete generic visitor for a parse tree produced
 * by `VelocitronPlayParser`.
 *
 * @param <Result> The return type of the visit operation. Use `void` for
 * operations with no return type.
 */
export default class VelocitronPlayVisitor<Result> extends ParseTreeVisitor<Result> {
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.statement`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitStatement?: (ctx: StatementContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.header`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitHeader?: (ctx: HeaderContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.netSetting`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitNetSetting?: (ctx: NetSettingContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.useSetting`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitUseSetting?: (ctx: UseSettingContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.wireSetting`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitWireSetting?: (ctx: WireSettingContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.shareSetting`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitShareSetting?: (ctx: ShareSettingContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.refineSetting`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitRefineSetting?: (ctx: RefineSettingContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.markingSetting`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitMarkingSetting?: (ctx: MarkingSettingContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.instanceSetting`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitInstanceSetting?: (ctx: InstanceSettingContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.scopeSetting`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitScopeSetting?: (ctx: ScopeSettingContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.sequenceShow`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitSequenceShow?: (ctx: SequenceShowContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.colorShow`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitColorShow?: (ctx: ColorShowContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.actorSetting`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitActorSetting?: (ctx: ActorSettingContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.boxSetting`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitBoxSetting?: (ctx: BoxSettingContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.templateDecl`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitTemplateDecl?: (ctx: TemplateDeclContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.pathDecl`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitPathDecl?: (ctx: PathDeclContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.step`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitStep?: (ctx: StepContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.label`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitLabel?: (ctx: LabelContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.actorKind`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitActorKind?: (ctx: ActorKindContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.stepBody`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitStepBody?: (ctx: StepBodyContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.injectBody`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitInjectBody?: (ctx: InjectBodyContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.updateBody`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitUpdateBody?: (ctx: UpdateBodyContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.advanceBody`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitAdvanceBody?: (ctx: AdvanceBodyContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.fireBody`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitFireBody?: (ctx: FireBodyContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.expectBody`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitExpectBody?: (ctx: ExpectBodyContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.assumeBody`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitAssumeBody?: (ctx: AssumeBodyContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.withClause`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitWithClause?: (ctx: WithClauseContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.outputClause`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitOutputClause?: (ctx: OutputClauseContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.condition`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitCondition?: (ctx: ConditionContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.timeValue`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitTimeValue?: (ctx: TimeValueContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.truthValue`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitTruthValue?: (ctx: TruthValueContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.tokenList`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitTokenList?: (ctx: TokenListContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.tokenExpr`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitTokenExpr?: (ctx: TokenExprContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.place`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitPlace?: (ctx: PlaceContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.transition`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitTransition?: (ctx: TransitionContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.wireEnd`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitWireEnd?: (ctx: WireEndContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.fieldPath`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitFieldPath?: (ctx: FieldPathContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.color`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitColor?: (ctx: ColorContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.colorNotSequence`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitColorNotSequence?: (ctx: ColorNotSequenceContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.name`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitName?: (ctx: NameContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.qualifiedName`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitQualifiedName?: (ctx: QualifiedNameContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.singleName`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitSingleName?: (ctx: SingleNameContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.singleNameNotSequence`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitSingleNameNotSequence?: (ctx: SingleNameNotSequenceContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.keyword`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitKeyword?: (ctx: KeywordContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.keywordNotSequence`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitKeywordNotSequence?: (ctx: KeywordNotSequenceContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.jsonValue`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitJsonValue?: (ctx: JsonValueContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.jsonObject`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitJsonObject?: (ctx: JsonObjectContext) => Result;
	/**
	 * Visit a parse tree produced by `VelocitronPlayParser.jsonArray`.
	 * @param ctx the parse tree
	 * @return the visitor result
	 */
	visitJsonArray?: (ctx: JsonArrayContext) => Result;
}
