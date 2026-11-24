// Generated from VelocitronPlay.g4 by ANTLR 4.13.2
// noinspection ES6UnusedImports,JSUnusedGlobalSymbols,JSUnusedLocalSymbols

import {
	ATN,
	ATNDeserializer, DecisionState, DFA, FailedPredicateException,
	RecognitionException, NoViableAltException, BailErrorStrategy,
	Parser, ParserATNSimulator,
	RuleContext, ParserRuleContext, PredictionMode, PredictionContextCache,
	TerminalNode, RuleNode,
	Token, TokenStream,
	Interval, IntervalSet
} from 'antlr4';
import VelocitronPlayVisitor from "./VelocitronPlayVisitor.js";

// for running tests with parameters, TODO: discuss strategy for typed parameters in CI
// eslint-disable-next-line no-unused-vars
type int = number;

export default class VelocitronPlayParser extends Parser {
	public static readonly PLAY = 1;
	public static readonly NET = 2;
	public static readonly USE = 3;
	public static readonly AS = 4;
	public static readonly WIRE = 5;
	public static readonly SHARE = 6;
	public static readonly REFINE = 7;
	public static readonly BY = 8;
	public static readonly MARKING = 9;
	public static readonly INSTANCE = 10;
	public static readonly SCOPE = 11;
	public static readonly SHOW = 12;
	public static readonly SEQUENCE = 13;
	public static readonly ONLY = 14;
	public static readonly PERSON = 15;
	public static readonly SYSTEM = 16;
	public static readonly RECORD = 17;
	public static readonly BOX = 18;
	public static readonly PATH = 19;
	public static readonly FROM = 20;
	public static readonly INJECT = 21;
	public static readonly UPDATE = 22;
	public static readonly ADVANCE = 23;
	public static readonly FIRE = 24;
	public static readonly EXPECT = 25;
	public static readonly ASSUME = 26;
	public static readonly PREDICATE = 27;
	public static readonly GUARD = 28;
	public static readonly WITH = 29;
	public static readonly NOTHING = 30;
	public static readonly EMPTY = 31;
	public static readonly COUNT = 32;
	public static readonly HAS = 33;
	public static readonly ENABLED = 34;
	public static readonly NOT = 35;
	public static readonly NEXT = 36;
	public static readonly QUIESCENT = 37;
	public static readonly TRUE = 38;
	public static readonly FALSE = 39;
	public static readonly NULL = 40;
	public static readonly STEP = 41;
	public static readonly NEIGHBORS = 42;
	public static readonly SUBNET = 43;
	public static readonly AT = 44;
	public static readonly LPAREN = 45;
	public static readonly RPAREN = 46;
	public static readonly LBRACK = 47;
	public static readonly RBRACK = 48;
	public static readonly LBRACE = 49;
	public static readonly RBRACE = 50;
	public static readonly ARROW = 51;
	public static readonly LEFT_ARROW = 52;
	public static readonly DOLLAR = 53;
	public static readonly HASH = 54;
	public static readonly PLUS = 55;
	public static readonly COLON = 56;
	public static readonly COMMA = 57;
	public static readonly DOT = 58;
	public static readonly TILDE = 59;
	public static readonly EQ = 60;
	public static readonly DURATION = 61;
	public static readonly NUMBER = 62;
	public static readonly STRING = 63;
	public static readonly IDENT = 64;
	public static readonly LINE_COMMENT = 65;
	public static readonly WS = 66;
	public static readonly UNSUPPORTED = 67;
	public static override readonly EOF = Token.EOF;
	public static readonly RULE_statement = 0;
	public static readonly RULE_header = 1;
	public static readonly RULE_netSetting = 2;
	public static readonly RULE_useSetting = 3;
	public static readonly RULE_wireSetting = 4;
	public static readonly RULE_shareSetting = 5;
	public static readonly RULE_refineSetting = 6;
	public static readonly RULE_markingSetting = 7;
	public static readonly RULE_instanceSetting = 8;
	public static readonly RULE_scopeSetting = 9;
	public static readonly RULE_sequenceShow = 10;
	public static readonly RULE_colorShow = 11;
	public static readonly RULE_actorSetting = 12;
	public static readonly RULE_boxSetting = 13;
	public static readonly RULE_templateDecl = 14;
	public static readonly RULE_pathDecl = 15;
	public static readonly RULE_step = 16;
	public static readonly RULE_label = 17;
	public static readonly RULE_actorKind = 18;
	public static readonly RULE_stepBody = 19;
	public static readonly RULE_injectBody = 20;
	public static readonly RULE_updateBody = 21;
	public static readonly RULE_advanceBody = 22;
	public static readonly RULE_fireBody = 23;
	public static readonly RULE_expectBody = 24;
	public static readonly RULE_assumeBody = 25;
	public static readonly RULE_withClause = 26;
	public static readonly RULE_outputClause = 27;
	public static readonly RULE_condition = 28;
	public static readonly RULE_timeValue = 29;
	public static readonly RULE_truthValue = 30;
	public static readonly RULE_tokenList = 31;
	public static readonly RULE_tokenExpr = 32;
	public static readonly RULE_place = 33;
	public static readonly RULE_transition = 34;
	public static readonly RULE_wireEnd = 35;
	public static readonly RULE_fieldPath = 36;
	public static readonly RULE_color = 37;
	public static readonly RULE_colorNotSequence = 38;
	public static readonly RULE_name = 39;
	public static readonly RULE_qualifiedName = 40;
	public static readonly RULE_singleName = 41;
	public static readonly RULE_singleNameNotSequence = 42;
	public static readonly RULE_keyword = 43;
	public static readonly RULE_keywordNotSequence = 44;
	public static readonly RULE_jsonValue = 45;
	public static readonly RULE_jsonObject = 46;
	public static readonly RULE_jsonArray = 47;
	public static readonly literalNames: (string | null)[] = [ null, "'play'", 
                                                            "'net'", "'use'", 
                                                            "'as'", "'wire'", 
                                                            "'share'", "'refine'", 
                                                            "'by'", "'marking'", 
                                                            "'instance'", 
                                                            "'scope'", "'show'", 
                                                            "'sequence'", 
                                                            "'only'", "'person'", 
                                                            "'system'", 
                                                            "'record'", 
                                                            "'box'", "'path'", 
                                                            "'from'", "'inject'", 
                                                            "'update'", 
                                                            "'advance'", 
                                                            "'fire'", "'expect'", 
                                                            "'assume'", 
                                                            "'predicate'", 
                                                            "'guard'", "'with'", 
                                                            "'nothing'", 
                                                            "'empty'", "'count'", 
                                                            "'has'", "'enabled'", 
                                                            "'not'", "'next'", 
                                                            "'quiescent'", 
                                                            "'true'", "'false'", 
                                                            "'null'", "'step'", 
                                                            "'neighbors'", 
                                                            "'subnet'", 
                                                            "'@'", "'('", 
                                                            "')'", "'['", 
                                                            "']'", "'{'", 
                                                            "'}'", "'->'", 
                                                            "'<-'", "'$'", 
                                                            "'#'", "'+'", 
                                                            "':'", "','", 
                                                            "'.'", "'~'", 
                                                            "'=='" ];
	public static readonly symbolicNames: (string | null)[] = [ null, "PLAY", 
                                                             "NET", "USE", 
                                                             "AS", "WIRE", 
                                                             "SHARE", "REFINE", 
                                                             "BY", "MARKING", 
                                                             "INSTANCE", 
                                                             "SCOPE", "SHOW", 
                                                             "SEQUENCE", 
                                                             "ONLY", "PERSON", 
                                                             "SYSTEM", "RECORD", 
                                                             "BOX", "PATH", 
                                                             "FROM", "INJECT", 
                                                             "UPDATE", "ADVANCE", 
                                                             "FIRE", "EXPECT", 
                                                             "ASSUME", "PREDICATE", 
                                                             "GUARD", "WITH", 
                                                             "NOTHING", 
                                                             "EMPTY", "COUNT", 
                                                             "HAS", "ENABLED", 
                                                             "NOT", "NEXT", 
                                                             "QUIESCENT", 
                                                             "TRUE", "FALSE", 
                                                             "NULL", "STEP", 
                                                             "NEIGHBORS", 
                                                             "SUBNET", "AT", 
                                                             "LPAREN", "RPAREN", 
                                                             "LBRACK", "RBRACK", 
                                                             "LBRACE", "RBRACE", 
                                                             "ARROW", "LEFT_ARROW", 
                                                             "DOLLAR", "HASH", 
                                                             "PLUS", "COLON", 
                                                             "COMMA", "DOT", 
                                                             "TILDE", "EQ", 
                                                             "DURATION", 
                                                             "NUMBER", "STRING", 
                                                             "IDENT", "LINE_COMMENT", 
                                                             "WS", "UNSUPPORTED" ];
	// tslint:disable:no-trailing-whitespace
	public static readonly ruleNames: string[] = [
		"statement", "header", "netSetting", "useSetting", "wireSetting", "shareSetting", 
		"refineSetting", "markingSetting", "instanceSetting", "scopeSetting", 
		"sequenceShow", "colorShow", "actorSetting", "boxSetting", "templateDecl", 
		"pathDecl", "step", "label", "actorKind", "stepBody", "injectBody", "updateBody", 
		"advanceBody", "fireBody", "expectBody", "assumeBody", "withClause", "outputClause", 
		"condition", "timeValue", "truthValue", "tokenList", "tokenExpr", "place", 
		"transition", "wireEnd", "fieldPath", "color", "colorNotSequence", "name", 
		"qualifiedName", "singleName", "singleNameNotSequence", "keyword", "keywordNotSequence", 
		"jsonValue", "jsonObject", "jsonArray",
	];
	public get grammarFileName(): string { return "VelocitronPlay.g4"; }
	public get literalNames(): (string | null)[] { return VelocitronPlayParser.literalNames; }
	public get symbolicNames(): (string | null)[] { return VelocitronPlayParser.symbolicNames; }
	public get ruleNames(): string[] { return VelocitronPlayParser.ruleNames; }
	public get serializedATN(): number[] { return VelocitronPlayParser._serializedATN; }

	protected createFailedPredicateException(predicate?: string, message?: string): FailedPredicateException {
		return new FailedPredicateException(this, predicate, message);
	}

	constructor(input: TokenStream) {
		super(input);
		this._interp = new ParserATNSimulator(this, VelocitronPlayParser._ATN, VelocitronPlayParser.DecisionsToDFA, new PredictionContextCache());
	}
	// @RuleVersion(0)
	public statement(): StatementContext {
		let localctx: StatementContext = new StatementContext(this, this._ctx, this.state);
		this.enterRule(localctx, 0, VelocitronPlayParser.RULE_statement);
		try {
			this.state = 144;
			this._errHandler.sync(this);
			switch ( this._interp.adaptivePredict(this._input, 0, this._ctx) ) {
			case 1:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 96;
				this.header();
				this.state = 97;
				this.match(VelocitronPlayParser.EOF);
				}
				break;
			case 2:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 99;
				this.netSetting();
				this.state = 100;
				this.match(VelocitronPlayParser.EOF);
				}
				break;
			case 3:
				this.enterOuterAlt(localctx, 3);
				{
				this.state = 102;
				this.useSetting();
				this.state = 103;
				this.match(VelocitronPlayParser.EOF);
				}
				break;
			case 4:
				this.enterOuterAlt(localctx, 4);
				{
				this.state = 105;
				this.wireSetting();
				this.state = 106;
				this.match(VelocitronPlayParser.EOF);
				}
				break;
			case 5:
				this.enterOuterAlt(localctx, 5);
				{
				this.state = 108;
				this.shareSetting();
				this.state = 109;
				this.match(VelocitronPlayParser.EOF);
				}
				break;
			case 6:
				this.enterOuterAlt(localctx, 6);
				{
				this.state = 111;
				this.refineSetting();
				this.state = 112;
				this.match(VelocitronPlayParser.EOF);
				}
				break;
			case 7:
				this.enterOuterAlt(localctx, 7);
				{
				this.state = 114;
				this.markingSetting();
				this.state = 115;
				this.match(VelocitronPlayParser.EOF);
				}
				break;
			case 8:
				this.enterOuterAlt(localctx, 8);
				{
				this.state = 117;
				this.instanceSetting();
				this.state = 118;
				this.match(VelocitronPlayParser.EOF);
				}
				break;
			case 9:
				this.enterOuterAlt(localctx, 9);
				{
				this.state = 120;
				this.scopeSetting();
				this.state = 121;
				this.match(VelocitronPlayParser.EOF);
				}
				break;
			case 10:
				this.enterOuterAlt(localctx, 10);
				{
				this.state = 123;
				this.sequenceShow();
				this.state = 124;
				this.match(VelocitronPlayParser.EOF);
				}
				break;
			case 11:
				this.enterOuterAlt(localctx, 11);
				{
				this.state = 126;
				this.colorShow();
				this.state = 127;
				this.match(VelocitronPlayParser.EOF);
				}
				break;
			case 12:
				this.enterOuterAlt(localctx, 12);
				{
				this.state = 129;
				this.actorSetting();
				this.state = 130;
				this.match(VelocitronPlayParser.EOF);
				}
				break;
			case 13:
				this.enterOuterAlt(localctx, 13);
				{
				this.state = 132;
				this.boxSetting();
				this.state = 133;
				this.match(VelocitronPlayParser.EOF);
				}
				break;
			case 14:
				this.enterOuterAlt(localctx, 14);
				{
				this.state = 135;
				this.templateDecl();
				this.state = 136;
				this.match(VelocitronPlayParser.EOF);
				}
				break;
			case 15:
				this.enterOuterAlt(localctx, 15);
				{
				this.state = 138;
				this.pathDecl();
				this.state = 139;
				this.match(VelocitronPlayParser.EOF);
				}
				break;
			case 16:
				this.enterOuterAlt(localctx, 16);
				{
				this.state = 141;
				this.step();
				this.state = 142;
				this.match(VelocitronPlayParser.EOF);
				}
				break;
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public header(): HeaderContext {
		let localctx: HeaderContext = new HeaderContext(this, this._ctx, this.state);
		this.enterRule(localctx, 2, VelocitronPlayParser.RULE_header);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 146;
			this.match(VelocitronPlayParser.PLAY);
			this.state = 147;
			this.singleName();
			this.state = 149;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if (_la===63) {
				{
				this.state = 148;
				this.match(VelocitronPlayParser.STRING);
				}
			}

			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public netSetting(): NetSettingContext {
		let localctx: NetSettingContext = new NetSettingContext(this, this._ctx, this.state);
		this.enterRule(localctx, 4, VelocitronPlayParser.RULE_netSetting);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 151;
			this.match(VelocitronPlayParser.NET);
			this.state = 152;
			this.match(VelocitronPlayParser.STRING);
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public useSetting(): UseSettingContext {
		let localctx: UseSettingContext = new UseSettingContext(this, this._ctx, this.state);
		this.enterRule(localctx, 6, VelocitronPlayParser.RULE_useSetting);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 154;
			this.match(VelocitronPlayParser.USE);
			this.state = 155;
			this.match(VelocitronPlayParser.STRING);
			this.state = 156;
			this.match(VelocitronPlayParser.AS);
			this.state = 157;
			this.singleName();
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public wireSetting(): WireSettingContext {
		let localctx: WireSettingContext = new WireSettingContext(this, this._ctx, this.state);
		this.enterRule(localctx, 8, VelocitronPlayParser.RULE_wireSetting);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 159;
			this.match(VelocitronPlayParser.WIRE);
			this.state = 160;
			this.wireEnd();
			this.state = 161;
			this.match(VelocitronPlayParser.ARROW);
			this.state = 162;
			this.wireEnd();
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public shareSetting(): ShareSettingContext {
		let localctx: ShareSettingContext = new ShareSettingContext(this, this._ctx, this.state);
		this.enterRule(localctx, 10, VelocitronPlayParser.RULE_shareSetting);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 164;
			this.match(VelocitronPlayParser.SHARE);
			this.state = 165;
			this.wireEnd();
			this.state = 168;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			do {
				{
				{
				this.state = 166;
				this.match(VelocitronPlayParser.TILDE);
				this.state = 167;
				this.wireEnd();
				}
				}
				this.state = 170;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
			} while (_la===59);
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public refineSetting(): RefineSettingContext {
		let localctx: RefineSettingContext = new RefineSettingContext(this, this._ctx, this.state);
		this.enterRule(localctx, 12, VelocitronPlayParser.RULE_refineSetting);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 172;
			this.match(VelocitronPlayParser.REFINE);
			this.state = 173;
			this.singleName();
			this.state = 174;
			this.match(VelocitronPlayParser.DOT);
			this.state = 175;
			this.transition();
			this.state = 176;
			this.match(VelocitronPlayParser.BY);
			this.state = 177;
			this.singleName();
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public markingSetting(): MarkingSettingContext {
		let localctx: MarkingSettingContext = new MarkingSettingContext(this, this._ctx, this.state);
		this.enterRule(localctx, 14, VelocitronPlayParser.RULE_markingSetting);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 179;
			this.match(VelocitronPlayParser.MARKING);
			this.state = 180;
			this.name();
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public instanceSetting(): InstanceSettingContext {
		let localctx: InstanceSettingContext = new InstanceSettingContext(this, this._ctx, this.state);
		this.enterRule(localctx, 16, VelocitronPlayParser.RULE_instanceSetting);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 182;
			this.match(VelocitronPlayParser.INSTANCE);
			this.state = 183;
			this.tokenExpr();
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public scopeSetting(): ScopeSettingContext {
		let localctx: ScopeSettingContext = new ScopeSettingContext(this, this._ctx, this.state);
		this.enterRule(localctx, 18, VelocitronPlayParser.RULE_scopeSetting);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 185;
			this.match(VelocitronPlayParser.SCOPE);
			this.state = 186;
			_la = this._input.LA(1);
			if(!(((((_la - 41)) & ~0x1F) === 0 && ((1 << (_la - 41)) & 7) !== 0))) {
			this._errHandler.recoverInline(this);
			}
			else {
				this._errHandler.reportMatch(this);
			    this.consume();
			}
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public sequenceShow(): SequenceShowContext {
		let localctx: SequenceShowContext = new SequenceShowContext(this, this._ctx, this.state);
		this.enterRule(localctx, 20, VelocitronPlayParser.RULE_sequenceShow);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 188;
			this.match(VelocitronPlayParser.SHOW);
			this.state = 189;
			this.match(VelocitronPlayParser.SEQUENCE);
			this.state = 191;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if (_la===14) {
				{
				this.state = 190;
				this.match(VelocitronPlayParser.ONLY);
				}
			}

			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public colorShow(): ColorShowContext {
		let localctx: ColorShowContext = new ColorShowContext(this, this._ctx, this.state);
		this.enterRule(localctx, 22, VelocitronPlayParser.RULE_colorShow);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 193;
			this.match(VelocitronPlayParser.SHOW);
			this.state = 194;
			this.colorNotSequence();
			this.state = 195;
			this.fieldPath();
			this.state = 200;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			while (_la===57) {
				{
				{
				this.state = 196;
				this.match(VelocitronPlayParser.COMMA);
				this.state = 197;
				this.fieldPath();
				}
				}
				this.state = 202;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
			}
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public actorSetting(): ActorSettingContext {
		let localctx: ActorSettingContext = new ActorSettingContext(this, this._ctx, this.state);
		this.enterRule(localctx, 24, VelocitronPlayParser.RULE_actorSetting);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 203;
			this.actorKind();
			this.state = 204;
			this.name();
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public boxSetting(): BoxSettingContext {
		let localctx: BoxSettingContext = new BoxSettingContext(this, this._ctx, this.state);
		this.enterRule(localctx, 26, VelocitronPlayParser.RULE_boxSetting);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 206;
			this.match(VelocitronPlayParser.BOX);
			this.state = 207;
			this.name();
			this.state = 209;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			do {
				{
				{
				this.state = 208;
				this.name();
				}
				}
				this.state = 211;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
			} while (((((_la - 1)) & ~0x1F) === 0 && ((1 << (_la - 1)) & 4294967295) !== 0) || ((((_la - 33)) & ~0x1F) === 0 && ((1 << (_la - 33)) & 3221227519) !== 0));
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public templateDecl(): TemplateDeclContext {
		let localctx: TemplateDeclContext = new TemplateDeclContext(this, this._ctx, this.state);
		this.enterRule(localctx, 28, VelocitronPlayParser.RULE_templateDecl);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 213;
			this.match(VelocitronPlayParser.DOLLAR);
			this.state = 214;
			this.singleName();
			this.state = 215;
			this.match(VelocitronPlayParser.COLON);
			this.state = 216;
			this.color();
			this.state = 217;
			this.jsonObject();
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public pathDecl(): PathDeclContext {
		let localctx: PathDeclContext = new PathDeclContext(this, this._ctx, this.state);
		this.enterRule(localctx, 30, VelocitronPlayParser.RULE_pathDecl);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 219;
			this.match(VelocitronPlayParser.PATH);
			this.state = 220;
			this.singleName();
			this.state = 222;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if (_la===63) {
				{
				this.state = 221;
				this.match(VelocitronPlayParser.STRING);
				}
			}

			this.state = 224;
			this.match(VelocitronPlayParser.FROM);
			this.state = 225;
			this.match(VelocitronPlayParser.AT);
			this.state = 226;
			this.singleName();
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public step(): StepContext {
		let localctx: StepContext = new StepContext(this, this._ctx, this.state);
		this.enterRule(localctx, 32, VelocitronPlayParser.RULE_step);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 229;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if (_la===44) {
				{
				this.state = 228;
				this.label();
				}
			}

			this.state = 231;
			this.stepBody();
			this.state = 233;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if (_la===63) {
				{
				this.state = 232;
				this.match(VelocitronPlayParser.STRING);
				}
			}

			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public label(): LabelContext {
		let localctx: LabelContext = new LabelContext(this, this._ctx, this.state);
		this.enterRule(localctx, 34, VelocitronPlayParser.RULE_label);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 235;
			this.match(VelocitronPlayParser.AT);
			this.state = 236;
			this.singleName();
			this.state = 237;
			this.match(VelocitronPlayParser.COLON);
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public actorKind(): ActorKindContext {
		let localctx: ActorKindContext = new ActorKindContext(this, this._ctx, this.state);
		this.enterRule(localctx, 36, VelocitronPlayParser.RULE_actorKind);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 239;
			_la = this._input.LA(1);
			if(!((((_la) & ~0x1F) === 0 && ((1 << _la) & 229376) !== 0))) {
			this._errHandler.recoverInline(this);
			}
			else {
				this._errHandler.reportMatch(this);
			    this.consume();
			}
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public stepBody(): StepBodyContext {
		let localctx: StepBodyContext = new StepBodyContext(this, this._ctx, this.state);
		this.enterRule(localctx, 38, VelocitronPlayParser.RULE_stepBody);
		try {
			this.state = 247;
			this._errHandler.sync(this);
			switch (this._input.LA(1)) {
			case 21:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 241;
				this.injectBody();
				}
				break;
			case 22:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 242;
				this.updateBody();
				}
				break;
			case 23:
				this.enterOuterAlt(localctx, 3);
				{
				this.state = 243;
				this.advanceBody();
				}
				break;
			case 24:
				this.enterOuterAlt(localctx, 4);
				{
				this.state = 244;
				this.fireBody();
				}
				break;
			case 25:
				this.enterOuterAlt(localctx, 5);
				{
				this.state = 245;
				this.expectBody();
				}
				break;
			case 26:
				this.enterOuterAlt(localctx, 6);
				{
				this.state = 246;
				this.assumeBody();
				}
				break;
			default:
				throw new NoViableAltException(this);
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public injectBody(): InjectBodyContext {
		let localctx: InjectBodyContext = new InjectBodyContext(this, this._ctx, this.state);
		this.enterRule(localctx, 40, VelocitronPlayParser.RULE_injectBody);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 249;
			this.match(VelocitronPlayParser.INJECT);
			this.state = 250;
			this.place();
			this.state = 251;
			this.match(VelocitronPlayParser.LEFT_ARROW);
			this.state = 252;
			this.tokenList();
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public updateBody(): UpdateBodyContext {
		let localctx: UpdateBodyContext = new UpdateBodyContext(this, this._ctx, this.state);
		this.enterRule(localctx, 42, VelocitronPlayParser.RULE_updateBody);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 254;
			this.match(VelocitronPlayParser.UPDATE);
			this.state = 255;
			this.place();
			this.state = 256;
			this.match(VelocitronPlayParser.LEFT_ARROW);
			this.state = 257;
			this.tokenExpr();
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public advanceBody(): AdvanceBodyContext {
		let localctx: AdvanceBodyContext = new AdvanceBodyContext(this, this._ctx, this.state);
		this.enterRule(localctx, 44, VelocitronPlayParser.RULE_advanceBody);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 259;
			this.match(VelocitronPlayParser.ADVANCE);
			this.state = 261;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if (_la===45) {
				{
				this.state = 260;
				this.place();
				}
			}

			this.state = 264;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if (_la===55) {
				{
				this.state = 263;
				this.match(VelocitronPlayParser.PLUS);
				}
			}

			this.state = 267;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if (((((_la - 1)) & ~0x1F) === 0 && ((1 << (_la - 1)) & 4294967295) !== 0) || ((((_la - 33)) & ~0x1F) === 0 && ((1 << (_la - 33)) & 2952792063) !== 0)) {
				{
				this.state = 266;
				this.timeValue();
				}
			}

			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public fireBody(): FireBodyContext {
		let localctx: FireBodyContext = new FireBodyContext(this, this._ctx, this.state);
		this.enterRule(localctx, 46, VelocitronPlayParser.RULE_fireBody);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 269;
			this.match(VelocitronPlayParser.FIRE);
			this.state = 270;
			this.transition();
			this.state = 274;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			while (_la===29) {
				{
				{
				this.state = 271;
				this.withClause();
				}
				}
				this.state = 276;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
			}
			this.state = 280;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			while (_la===51) {
				{
				{
				this.state = 277;
				this.outputClause();
				}
				}
				this.state = 282;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
			}
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public expectBody(): ExpectBodyContext {
		let localctx: ExpectBodyContext = new ExpectBodyContext(this, this._ctx, this.state);
		this.enterRule(localctx, 48, VelocitronPlayParser.RULE_expectBody);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 283;
			this.match(VelocitronPlayParser.EXPECT);
			this.state = 284;
			this.condition();
			this.state = 289;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			while (_la===57) {
				{
				{
				this.state = 285;
				this.match(VelocitronPlayParser.COMMA);
				this.state = 286;
				this.condition();
				}
				}
				this.state = 291;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
			}
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public assumeBody(): AssumeBodyContext {
		let localctx: AssumeBodyContext = new AssumeBodyContext(this, this._ctx, this.state);
		this.enterRule(localctx, 50, VelocitronPlayParser.RULE_assumeBody);
		try {
			this.state = 301;
			this._errHandler.sync(this);
			switch ( this._interp.adaptivePredict(this._input, 16, this._ctx) ) {
			case 1:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 292;
				this.match(VelocitronPlayParser.ASSUME);
				this.state = 293;
				this.transition();
				this.state = 294;
				this.match(VelocitronPlayParser.GUARD);
				this.state = 295;
				this.truthValue();
				}
				break;
			case 2:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 297;
				this.match(VelocitronPlayParser.ASSUME);
				this.state = 298;
				this.match(VelocitronPlayParser.PREDICATE);
				this.state = 299;
				this.match(VelocitronPlayParser.STRING);
				this.state = 300;
				this.truthValue();
				}
				break;
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public withClause(): WithClauseContext {
		let localctx: WithClauseContext = new WithClauseContext(this, this._ctx, this.state);
		this.enterRule(localctx, 52, VelocitronPlayParser.RULE_withClause);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 303;
			this.match(VelocitronPlayParser.WITH);
			this.state = 304;
			this.place();
			this.state = 310;
			this._errHandler.sync(this);
			switch (this._input.LA(1)) {
			case 49:
				{
				this.state = 305;
				this.jsonObject();
				}
				break;
			case 53:
				{
				this.state = 306;
				this.match(VelocitronPlayParser.DOLLAR);
				this.state = 307;
				this.singleName();
				}
				break;
			case 54:
				{
				this.state = 308;
				this.match(VelocitronPlayParser.HASH);
				this.state = 309;
				this.match(VelocitronPlayParser.NUMBER);
				}
				break;
			default:
				throw new NoViableAltException(this);
			}
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public outputClause(): OutputClauseContext {
		let localctx: OutputClauseContext = new OutputClauseContext(this, this._ctx, this.state);
		this.enterRule(localctx, 54, VelocitronPlayParser.RULE_outputClause);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 312;
			this.match(VelocitronPlayParser.ARROW);
			this.state = 313;
			this.place();
			this.state = 318;
			this._errHandler.sync(this);
			switch ( this._interp.adaptivePredict(this._input, 18, this._ctx) ) {
			case 1:
				{
				this.state = 314;
				this.match(VelocitronPlayParser.NOTHING);
				}
				break;
			case 2:
				{
				this.state = 315;
				this.match(VelocitronPlayParser.PLUS);
				this.state = 316;
				this.jsonObject();
				}
				break;
			case 3:
				{
				this.state = 317;
				this.tokenList();
				}
				break;
			}
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public condition(): ConditionContext {
		let localctx: ConditionContext = new ConditionContext(this, this._ctx, this.state);
		this.enterRule(localctx, 56, VelocitronPlayParser.RULE_condition);
		let _la: number;
		try {
			this.state = 351;
			this._errHandler.sync(this);
			switch ( this._interp.adaptivePredict(this._input, 21, this._ctx) ) {
			case 1:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 320;
				this.place();
				this.state = 321;
				this.match(VelocitronPlayParser.EQ);
				this.state = 322;
				this.tokenList();
				}
				break;
			case 2:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 324;
				this.place();
				this.state = 325;
				this.match(VelocitronPlayParser.EMPTY);
				}
				break;
			case 3:
				this.enterOuterAlt(localctx, 3);
				{
				this.state = 327;
				this.place();
				this.state = 328;
				this.match(VelocitronPlayParser.COUNT);
				this.state = 329;
				this.match(VelocitronPlayParser.NUMBER);
				}
				break;
			case 4:
				this.enterOuterAlt(localctx, 4);
				{
				this.state = 331;
				this.place();
				this.state = 332;
				this.match(VelocitronPlayParser.HAS);
				this.state = 333;
				this.tokenExpr();
				}
				break;
			case 5:
				this.enterOuterAlt(localctx, 5);
				{
				this.state = 335;
				this.match(VelocitronPlayParser.ENABLED);
				this.state = 337;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
				do {
					{
					{
					this.state = 336;
					this.transition();
					}
					}
					this.state = 339;
					this._errHandler.sync(this);
					_la = this._input.LA(1);
				} while (_la===47);
				}
				break;
			case 6:
				this.enterOuterAlt(localctx, 6);
				{
				this.state = 341;
				this.match(VelocitronPlayParser.NOT);
				this.state = 342;
				this.match(VelocitronPlayParser.ENABLED);
				this.state = 344;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
				do {
					{
					{
					this.state = 343;
					this.transition();
					}
					}
					this.state = 346;
					this._errHandler.sync(this);
					_la = this._input.LA(1);
				} while (_la===47);
				}
				break;
			case 7:
				this.enterOuterAlt(localctx, 7);
				{
				this.state = 348;
				this.match(VelocitronPlayParser.NEXT);
				this.state = 349;
				this.transition();
				}
				break;
			case 8:
				this.enterOuterAlt(localctx, 8);
				{
				this.state = 350;
				this.match(VelocitronPlayParser.QUIESCENT);
				}
				break;
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public timeValue(): TimeValueContext {
		let localctx: TimeValueContext = new TimeValueContext(this, this._ctx, this.state);
		this.enterRule(localctx, 58, VelocitronPlayParser.RULE_timeValue);
		try {
			this.state = 356;
			this._errHandler.sync(this);
			switch (this._input.LA(1)) {
			case 62:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 353;
				this.match(VelocitronPlayParser.NUMBER);
				}
				break;
			case 61:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 354;
				this.match(VelocitronPlayParser.DURATION);
				}
				break;
			case 1:
			case 2:
			case 3:
			case 4:
			case 5:
			case 6:
			case 7:
			case 8:
			case 9:
			case 10:
			case 11:
			case 12:
			case 13:
			case 14:
			case 15:
			case 16:
			case 17:
			case 18:
			case 19:
			case 20:
			case 21:
			case 22:
			case 23:
			case 24:
			case 25:
			case 26:
			case 27:
			case 28:
			case 29:
			case 30:
			case 31:
			case 32:
			case 33:
			case 34:
			case 35:
			case 36:
			case 37:
			case 38:
			case 39:
			case 40:
			case 41:
			case 42:
			case 43:
			case 64:
				this.enterOuterAlt(localctx, 3);
				{
				this.state = 355;
				this.singleName();
				}
				break;
			default:
				throw new NoViableAltException(this);
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public truthValue(): TruthValueContext {
		let localctx: TruthValueContext = new TruthValueContext(this, this._ctx, this.state);
		this.enterRule(localctx, 60, VelocitronPlayParser.RULE_truthValue);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 358;
			_la = this._input.LA(1);
			if(!(_la===38 || _la===39)) {
			this._errHandler.recoverInline(this);
			}
			else {
				this._errHandler.reportMatch(this);
			    this.consume();
			}
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public tokenList(): TokenListContext {
		let localctx: TokenListContext = new TokenListContext(this, this._ctx, this.state);
		this.enterRule(localctx, 62, VelocitronPlayParser.RULE_tokenList);
		try {
			let _alt: number;
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 360;
			this.tokenExpr();
			this.state = 365;
			this._errHandler.sync(this);
			_alt = this._interp.adaptivePredict(this._input, 23, this._ctx);
			while (_alt !== 2 && _alt !== ATN.INVALID_ALT_NUMBER) {
				if (_alt === 1) {
					{
					{
					this.state = 361;
					this.match(VelocitronPlayParser.COMMA);
					this.state = 362;
					this.tokenExpr();
					}
					}
				}
				this.state = 367;
				this._errHandler.sync(this);
				_alt = this._interp.adaptivePredict(this._input, 23, this._ctx);
			}
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public tokenExpr(): TokenExprContext {
		let localctx: TokenExprContext = new TokenExprContext(this, this._ctx, this.state);
		this.enterRule(localctx, 64, VelocitronPlayParser.RULE_tokenExpr);
		try {
			this.state = 374;
			this._errHandler.sync(this);
			switch (this._input.LA(1)) {
			case 53:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 368;
				this.match(VelocitronPlayParser.DOLLAR);
				this.state = 369;
				this.singleName();
				}
				break;
			case 49:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 370;
				this.jsonObject();
				}
				break;
			case 1:
			case 2:
			case 3:
			case 4:
			case 5:
			case 6:
			case 7:
			case 8:
			case 9:
			case 10:
			case 11:
			case 12:
			case 13:
			case 14:
			case 15:
			case 16:
			case 17:
			case 18:
			case 19:
			case 20:
			case 21:
			case 22:
			case 23:
			case 24:
			case 25:
			case 26:
			case 27:
			case 28:
			case 29:
			case 30:
			case 31:
			case 32:
			case 33:
			case 34:
			case 35:
			case 36:
			case 37:
			case 38:
			case 39:
			case 40:
			case 41:
			case 42:
			case 43:
			case 63:
			case 64:
				this.enterOuterAlt(localctx, 3);
				{
				this.state = 371;
				this.color();
				this.state = 372;
				this.jsonObject();
				}
				break;
			default:
				throw new NoViableAltException(this);
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public place(): PlaceContext {
		let localctx: PlaceContext = new PlaceContext(this, this._ctx, this.state);
		this.enterRule(localctx, 66, VelocitronPlayParser.RULE_place);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 376;
			this.match(VelocitronPlayParser.LPAREN);
			this.state = 377;
			this.qualifiedName();
			this.state = 378;
			this.match(VelocitronPlayParser.RPAREN);
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public transition(): TransitionContext {
		let localctx: TransitionContext = new TransitionContext(this, this._ctx, this.state);
		this.enterRule(localctx, 68, VelocitronPlayParser.RULE_transition);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 380;
			this.match(VelocitronPlayParser.LBRACK);
			this.state = 381;
			this.qualifiedName();
			this.state = 382;
			this.match(VelocitronPlayParser.RBRACK);
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public wireEnd(): WireEndContext {
		let localctx: WireEndContext = new WireEndContext(this, this._ctx, this.state);
		this.enterRule(localctx, 70, VelocitronPlayParser.RULE_wireEnd);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 384;
			this.singleName();
			this.state = 385;
			this.match(VelocitronPlayParser.DOT);
			this.state = 386;
			this.place();
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public fieldPath(): FieldPathContext {
		let localctx: FieldPathContext = new FieldPathContext(this, this._ctx, this.state);
		this.enterRule(localctx, 72, VelocitronPlayParser.RULE_fieldPath);
		try {
			this.state = 390;
			this._errHandler.sync(this);
			switch (this._input.LA(1)) {
			case 1:
			case 2:
			case 3:
			case 4:
			case 5:
			case 6:
			case 7:
			case 8:
			case 9:
			case 10:
			case 11:
			case 12:
			case 13:
			case 14:
			case 15:
			case 16:
			case 17:
			case 18:
			case 19:
			case 20:
			case 21:
			case 22:
			case 23:
			case 24:
			case 25:
			case 26:
			case 27:
			case 28:
			case 29:
			case 30:
			case 31:
			case 32:
			case 33:
			case 34:
			case 35:
			case 36:
			case 37:
			case 38:
			case 39:
			case 40:
			case 41:
			case 42:
			case 43:
			case 64:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 388;
				this.qualifiedName();
				}
				break;
			case 63:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 389;
				this.match(VelocitronPlayParser.STRING);
				}
				break;
			default:
				throw new NoViableAltException(this);
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public color(): ColorContext {
		let localctx: ColorContext = new ColorContext(this, this._ctx, this.state);
		this.enterRule(localctx, 74, VelocitronPlayParser.RULE_color);
		try {
			this.state = 394;
			this._errHandler.sync(this);
			switch (this._input.LA(1)) {
			case 63:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 392;
				this.match(VelocitronPlayParser.STRING);
				}
				break;
			case 1:
			case 2:
			case 3:
			case 4:
			case 5:
			case 6:
			case 7:
			case 8:
			case 9:
			case 10:
			case 11:
			case 12:
			case 13:
			case 14:
			case 15:
			case 16:
			case 17:
			case 18:
			case 19:
			case 20:
			case 21:
			case 22:
			case 23:
			case 24:
			case 25:
			case 26:
			case 27:
			case 28:
			case 29:
			case 30:
			case 31:
			case 32:
			case 33:
			case 34:
			case 35:
			case 36:
			case 37:
			case 38:
			case 39:
			case 40:
			case 41:
			case 42:
			case 43:
			case 64:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 393;
				this.singleName();
				}
				break;
			default:
				throw new NoViableAltException(this);
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public colorNotSequence(): ColorNotSequenceContext {
		let localctx: ColorNotSequenceContext = new ColorNotSequenceContext(this, this._ctx, this.state);
		this.enterRule(localctx, 76, VelocitronPlayParser.RULE_colorNotSequence);
		try {
			this.state = 398;
			this._errHandler.sync(this);
			switch (this._input.LA(1)) {
			case 63:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 396;
				this.match(VelocitronPlayParser.STRING);
				}
				break;
			case 1:
			case 2:
			case 3:
			case 4:
			case 5:
			case 6:
			case 7:
			case 8:
			case 9:
			case 10:
			case 11:
			case 12:
			case 14:
			case 15:
			case 16:
			case 17:
			case 18:
			case 19:
			case 20:
			case 21:
			case 22:
			case 23:
			case 24:
			case 25:
			case 26:
			case 27:
			case 28:
			case 29:
			case 30:
			case 31:
			case 32:
			case 33:
			case 34:
			case 35:
			case 36:
			case 37:
			case 38:
			case 39:
			case 40:
			case 41:
			case 42:
			case 43:
			case 64:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 397;
				this.singleNameNotSequence();
				}
				break;
			default:
				throw new NoViableAltException(this);
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public name(): NameContext {
		let localctx: NameContext = new NameContext(this, this._ctx, this.state);
		this.enterRule(localctx, 78, VelocitronPlayParser.RULE_name);
		try {
			this.state = 402;
			this._errHandler.sync(this);
			switch (this._input.LA(1)) {
			case 1:
			case 2:
			case 3:
			case 4:
			case 5:
			case 6:
			case 7:
			case 8:
			case 9:
			case 10:
			case 11:
			case 12:
			case 13:
			case 14:
			case 15:
			case 16:
			case 17:
			case 18:
			case 19:
			case 20:
			case 21:
			case 22:
			case 23:
			case 24:
			case 25:
			case 26:
			case 27:
			case 28:
			case 29:
			case 30:
			case 31:
			case 32:
			case 33:
			case 34:
			case 35:
			case 36:
			case 37:
			case 38:
			case 39:
			case 40:
			case 41:
			case 42:
			case 43:
			case 64:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 400;
				this.qualifiedName();
				}
				break;
			case 63:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 401;
				this.match(VelocitronPlayParser.STRING);
				}
				break;
			default:
				throw new NoViableAltException(this);
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public qualifiedName(): QualifiedNameContext {
		let localctx: QualifiedNameContext = new QualifiedNameContext(this, this._ctx, this.state);
		this.enterRule(localctx, 80, VelocitronPlayParser.RULE_qualifiedName);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 404;
			this.singleName();
			this.state = 409;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			while (_la===58) {
				{
				{
				this.state = 405;
				this.match(VelocitronPlayParser.DOT);
				this.state = 406;
				this.singleName();
				}
				}
				this.state = 411;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
			}
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public singleName(): SingleNameContext {
		let localctx: SingleNameContext = new SingleNameContext(this, this._ctx, this.state);
		this.enterRule(localctx, 82, VelocitronPlayParser.RULE_singleName);
		try {
			this.state = 414;
			this._errHandler.sync(this);
			switch (this._input.LA(1)) {
			case 64:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 412;
				this.match(VelocitronPlayParser.IDENT);
				}
				break;
			case 1:
			case 2:
			case 3:
			case 4:
			case 5:
			case 6:
			case 7:
			case 8:
			case 9:
			case 10:
			case 11:
			case 12:
			case 13:
			case 14:
			case 15:
			case 16:
			case 17:
			case 18:
			case 19:
			case 20:
			case 21:
			case 22:
			case 23:
			case 24:
			case 25:
			case 26:
			case 27:
			case 28:
			case 29:
			case 30:
			case 31:
			case 32:
			case 33:
			case 34:
			case 35:
			case 36:
			case 37:
			case 38:
			case 39:
			case 40:
			case 41:
			case 42:
			case 43:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 413;
				this.keyword();
				}
				break;
			default:
				throw new NoViableAltException(this);
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public singleNameNotSequence(): SingleNameNotSequenceContext {
		let localctx: SingleNameNotSequenceContext = new SingleNameNotSequenceContext(this, this._ctx, this.state);
		this.enterRule(localctx, 84, VelocitronPlayParser.RULE_singleNameNotSequence);
		try {
			this.state = 418;
			this._errHandler.sync(this);
			switch (this._input.LA(1)) {
			case 64:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 416;
				this.match(VelocitronPlayParser.IDENT);
				}
				break;
			case 1:
			case 2:
			case 3:
			case 4:
			case 5:
			case 6:
			case 7:
			case 8:
			case 9:
			case 10:
			case 11:
			case 12:
			case 14:
			case 15:
			case 16:
			case 17:
			case 18:
			case 19:
			case 20:
			case 21:
			case 22:
			case 23:
			case 24:
			case 25:
			case 26:
			case 27:
			case 28:
			case 29:
			case 30:
			case 31:
			case 32:
			case 33:
			case 34:
			case 35:
			case 36:
			case 37:
			case 38:
			case 39:
			case 40:
			case 41:
			case 42:
			case 43:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 417;
				this.keywordNotSequence();
				}
				break;
			default:
				throw new NoViableAltException(this);
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public keyword(): KeywordContext {
		let localctx: KeywordContext = new KeywordContext(this, this._ctx, this.state);
		this.enterRule(localctx, 86, VelocitronPlayParser.RULE_keyword);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 420;
			_la = this._input.LA(1);
			if(!((((_la) & ~0x1F) === 0 && ((1 << _la) & 4294967294) !== 0) || ((((_la - 32)) & ~0x1F) === 0 && ((1 << (_la - 32)) & 4095) !== 0))) {
			this._errHandler.recoverInline(this);
			}
			else {
				this._errHandler.reportMatch(this);
			    this.consume();
			}
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public keywordNotSequence(): KeywordNotSequenceContext {
		let localctx: KeywordNotSequenceContext = new KeywordNotSequenceContext(this, this._ctx, this.state);
		this.enterRule(localctx, 88, VelocitronPlayParser.RULE_keywordNotSequence);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 422;
			_la = this._input.LA(1);
			if(!((((_la) & ~0x1F) === 0 && ((1 << _la) & 4294959102) !== 0) || ((((_la - 32)) & ~0x1F) === 0 && ((1 << (_la - 32)) & 4095) !== 0))) {
			this._errHandler.recoverInline(this);
			}
			else {
				this._errHandler.reportMatch(this);
			    this.consume();
			}
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public jsonValue(): JsonValueContext {
		let localctx: JsonValueContext = new JsonValueContext(this, this._ctx, this.state);
		this.enterRule(localctx, 90, VelocitronPlayParser.RULE_jsonValue);
		try {
			this.state = 431;
			this._errHandler.sync(this);
			switch (this._input.LA(1)) {
			case 49:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 424;
				this.jsonObject();
				}
				break;
			case 47:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 425;
				this.jsonArray();
				}
				break;
			case 63:
				this.enterOuterAlt(localctx, 3);
				{
				this.state = 426;
				this.match(VelocitronPlayParser.STRING);
				}
				break;
			case 62:
				this.enterOuterAlt(localctx, 4);
				{
				this.state = 427;
				this.match(VelocitronPlayParser.NUMBER);
				}
				break;
			case 38:
				this.enterOuterAlt(localctx, 5);
				{
				this.state = 428;
				this.match(VelocitronPlayParser.TRUE);
				}
				break;
			case 39:
				this.enterOuterAlt(localctx, 6);
				{
				this.state = 429;
				this.match(VelocitronPlayParser.FALSE);
				}
				break;
			case 40:
				this.enterOuterAlt(localctx, 7);
				{
				this.state = 430;
				this.match(VelocitronPlayParser.NULL);
				}
				break;
			default:
				throw new NoViableAltException(this);
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public jsonObject(): JsonObjectContext {
		let localctx: JsonObjectContext = new JsonObjectContext(this, this._ctx, this.state);
		this.enterRule(localctx, 92, VelocitronPlayParser.RULE_jsonObject);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 433;
			this.match(VelocitronPlayParser.LBRACE);
			this.state = 446;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if (_la===63) {
				{
				this.state = 434;
				this.match(VelocitronPlayParser.STRING);
				this.state = 435;
				this.match(VelocitronPlayParser.COLON);
				this.state = 436;
				this.jsonValue();
				this.state = 443;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
				while (_la===57) {
					{
					{
					this.state = 437;
					this.match(VelocitronPlayParser.COMMA);
					this.state = 438;
					this.match(VelocitronPlayParser.STRING);
					this.state = 439;
					this.match(VelocitronPlayParser.COLON);
					this.state = 440;
					this.jsonValue();
					}
					}
					this.state = 445;
					this._errHandler.sync(this);
					_la = this._input.LA(1);
				}
				}
			}

			this.state = 448;
			this.match(VelocitronPlayParser.RBRACE);
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public jsonArray(): JsonArrayContext {
		let localctx: JsonArrayContext = new JsonArrayContext(this, this._ctx, this.state);
		this.enterRule(localctx, 94, VelocitronPlayParser.RULE_jsonArray);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 450;
			this.match(VelocitronPlayParser.LBRACK);
			this.state = 459;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if (((((_la - 38)) & ~0x1F) === 0 && ((1 << (_la - 38)) & 50334215) !== 0)) {
				{
				this.state = 451;
				this.jsonValue();
				this.state = 456;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
				while (_la===57) {
					{
					{
					this.state = 452;
					this.match(VelocitronPlayParser.COMMA);
					this.state = 453;
					this.jsonValue();
					}
					}
					this.state = 458;
					this._errHandler.sync(this);
					_la = this._input.LA(1);
				}
				}
			}

			this.state = 461;
			this.match(VelocitronPlayParser.RBRACK);
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}

	public static readonly _serializedATN: number[] = [4,1,67,464,2,0,7,0,2,
	1,7,1,2,2,7,2,2,3,7,3,2,4,7,4,2,5,7,5,2,6,7,6,2,7,7,7,2,8,7,8,2,9,7,9,2,
	10,7,10,2,11,7,11,2,12,7,12,2,13,7,13,2,14,7,14,2,15,7,15,2,16,7,16,2,17,
	7,17,2,18,7,18,2,19,7,19,2,20,7,20,2,21,7,21,2,22,7,22,2,23,7,23,2,24,7,
	24,2,25,7,25,2,26,7,26,2,27,7,27,2,28,7,28,2,29,7,29,2,30,7,30,2,31,7,31,
	2,32,7,32,2,33,7,33,2,34,7,34,2,35,7,35,2,36,7,36,2,37,7,37,2,38,7,38,2,
	39,7,39,2,40,7,40,2,41,7,41,2,42,7,42,2,43,7,43,2,44,7,44,2,45,7,45,2,46,
	7,46,2,47,7,47,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,
	1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,
	1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,3,0,145,
	8,0,1,1,1,1,1,1,3,1,150,8,1,1,2,1,2,1,2,1,3,1,3,1,3,1,3,1,3,1,4,1,4,1,4,
	1,4,1,4,1,5,1,5,1,5,1,5,4,5,169,8,5,11,5,12,5,170,1,6,1,6,1,6,1,6,1,6,1,
	6,1,6,1,7,1,7,1,7,1,8,1,8,1,8,1,9,1,9,1,9,1,10,1,10,1,10,3,10,192,8,10,
	1,11,1,11,1,11,1,11,1,11,5,11,199,8,11,10,11,12,11,202,9,11,1,12,1,12,1,
	12,1,13,1,13,1,13,4,13,210,8,13,11,13,12,13,211,1,14,1,14,1,14,1,14,1,14,
	1,14,1,15,1,15,1,15,3,15,223,8,15,1,15,1,15,1,15,1,15,1,16,3,16,230,8,16,
	1,16,1,16,3,16,234,8,16,1,17,1,17,1,17,1,17,1,18,1,18,1,19,1,19,1,19,1,
	19,1,19,1,19,3,19,248,8,19,1,20,1,20,1,20,1,20,1,20,1,21,1,21,1,21,1,21,
	1,21,1,22,1,22,3,22,262,8,22,1,22,3,22,265,8,22,1,22,3,22,268,8,22,1,23,
	1,23,1,23,5,23,273,8,23,10,23,12,23,276,9,23,1,23,5,23,279,8,23,10,23,12,
	23,282,9,23,1,24,1,24,1,24,1,24,5,24,288,8,24,10,24,12,24,291,9,24,1,25,
	1,25,1,25,1,25,1,25,1,25,1,25,1,25,1,25,3,25,302,8,25,1,26,1,26,1,26,1,
	26,1,26,1,26,1,26,3,26,311,8,26,1,27,1,27,1,27,1,27,1,27,1,27,3,27,319,
	8,27,1,28,1,28,1,28,1,28,1,28,1,28,1,28,1,28,1,28,1,28,1,28,1,28,1,28,1,
	28,1,28,1,28,1,28,4,28,338,8,28,11,28,12,28,339,1,28,1,28,1,28,4,28,345,
	8,28,11,28,12,28,346,1,28,1,28,1,28,3,28,352,8,28,1,29,1,29,1,29,3,29,357,
	8,29,1,30,1,30,1,31,1,31,1,31,5,31,364,8,31,10,31,12,31,367,9,31,1,32,1,
	32,1,32,1,32,1,32,1,32,3,32,375,8,32,1,33,1,33,1,33,1,33,1,34,1,34,1,34,
	1,34,1,35,1,35,1,35,1,35,1,36,1,36,3,36,391,8,36,1,37,1,37,3,37,395,8,37,
	1,38,1,38,3,38,399,8,38,1,39,1,39,3,39,403,8,39,1,40,1,40,1,40,5,40,408,
	8,40,10,40,12,40,411,9,40,1,41,1,41,3,41,415,8,41,1,42,1,42,3,42,419,8,
	42,1,43,1,43,1,44,1,44,1,45,1,45,1,45,1,45,1,45,1,45,1,45,3,45,432,8,45,
	1,46,1,46,1,46,1,46,1,46,1,46,1,46,1,46,5,46,442,8,46,10,46,12,46,445,9,
	46,3,46,447,8,46,1,46,1,46,1,47,1,47,1,47,1,47,5,47,455,8,47,10,47,12,47,
	458,9,47,3,47,460,8,47,1,47,1,47,1,47,0,0,48,0,2,4,6,8,10,12,14,16,18,20,
	22,24,26,28,30,32,34,36,38,40,42,44,46,48,50,52,54,56,58,60,62,64,66,68,
	70,72,74,76,78,80,82,84,86,88,90,92,94,0,5,1,0,41,43,1,0,15,17,1,0,38,39,
	1,0,1,43,2,0,1,12,14,43,485,0,144,1,0,0,0,2,146,1,0,0,0,4,151,1,0,0,0,6,
	154,1,0,0,0,8,159,1,0,0,0,10,164,1,0,0,0,12,172,1,0,0,0,14,179,1,0,0,0,
	16,182,1,0,0,0,18,185,1,0,0,0,20,188,1,0,0,0,22,193,1,0,0,0,24,203,1,0,
	0,0,26,206,1,0,0,0,28,213,1,0,0,0,30,219,1,0,0,0,32,229,1,0,0,0,34,235,
	1,0,0,0,36,239,1,0,0,0,38,247,1,0,0,0,40,249,1,0,0,0,42,254,1,0,0,0,44,
	259,1,0,0,0,46,269,1,0,0,0,48,283,1,0,0,0,50,301,1,0,0,0,52,303,1,0,0,0,
	54,312,1,0,0,0,56,351,1,0,0,0,58,356,1,0,0,0,60,358,1,0,0,0,62,360,1,0,
	0,0,64,374,1,0,0,0,66,376,1,0,0,0,68,380,1,0,0,0,70,384,1,0,0,0,72,390,
	1,0,0,0,74,394,1,0,0,0,76,398,1,0,0,0,78,402,1,0,0,0,80,404,1,0,0,0,82,
	414,1,0,0,0,84,418,1,0,0,0,86,420,1,0,0,0,88,422,1,0,0,0,90,431,1,0,0,0,
	92,433,1,0,0,0,94,450,1,0,0,0,96,97,3,2,1,0,97,98,5,0,0,1,98,145,1,0,0,
	0,99,100,3,4,2,0,100,101,5,0,0,1,101,145,1,0,0,0,102,103,3,6,3,0,103,104,
	5,0,0,1,104,145,1,0,0,0,105,106,3,8,4,0,106,107,5,0,0,1,107,145,1,0,0,0,
	108,109,3,10,5,0,109,110,5,0,0,1,110,145,1,0,0,0,111,112,3,12,6,0,112,113,
	5,0,0,1,113,145,1,0,0,0,114,115,3,14,7,0,115,116,5,0,0,1,116,145,1,0,0,
	0,117,118,3,16,8,0,118,119,5,0,0,1,119,145,1,0,0,0,120,121,3,18,9,0,121,
	122,5,0,0,1,122,145,1,0,0,0,123,124,3,20,10,0,124,125,5,0,0,1,125,145,1,
	0,0,0,126,127,3,22,11,0,127,128,5,0,0,1,128,145,1,0,0,0,129,130,3,24,12,
	0,130,131,5,0,0,1,131,145,1,0,0,0,132,133,3,26,13,0,133,134,5,0,0,1,134,
	145,1,0,0,0,135,136,3,28,14,0,136,137,5,0,0,1,137,145,1,0,0,0,138,139,3,
	30,15,0,139,140,5,0,0,1,140,145,1,0,0,0,141,142,3,32,16,0,142,143,5,0,0,
	1,143,145,1,0,0,0,144,96,1,0,0,0,144,99,1,0,0,0,144,102,1,0,0,0,144,105,
	1,0,0,0,144,108,1,0,0,0,144,111,1,0,0,0,144,114,1,0,0,0,144,117,1,0,0,0,
	144,120,1,0,0,0,144,123,1,0,0,0,144,126,1,0,0,0,144,129,1,0,0,0,144,132,
	1,0,0,0,144,135,1,0,0,0,144,138,1,0,0,0,144,141,1,0,0,0,145,1,1,0,0,0,146,
	147,5,1,0,0,147,149,3,82,41,0,148,150,5,63,0,0,149,148,1,0,0,0,149,150,
	1,0,0,0,150,3,1,0,0,0,151,152,5,2,0,0,152,153,5,63,0,0,153,5,1,0,0,0,154,
	155,5,3,0,0,155,156,5,63,0,0,156,157,5,4,0,0,157,158,3,82,41,0,158,7,1,
	0,0,0,159,160,5,5,0,0,160,161,3,70,35,0,161,162,5,51,0,0,162,163,3,70,35,
	0,163,9,1,0,0,0,164,165,5,6,0,0,165,168,3,70,35,0,166,167,5,59,0,0,167,
	169,3,70,35,0,168,166,1,0,0,0,169,170,1,0,0,0,170,168,1,0,0,0,170,171,1,
	0,0,0,171,11,1,0,0,0,172,173,5,7,0,0,173,174,3,82,41,0,174,175,5,58,0,0,
	175,176,3,68,34,0,176,177,5,8,0,0,177,178,3,82,41,0,178,13,1,0,0,0,179,
	180,5,9,0,0,180,181,3,78,39,0,181,15,1,0,0,0,182,183,5,10,0,0,183,184,3,
	64,32,0,184,17,1,0,0,0,185,186,5,11,0,0,186,187,7,0,0,0,187,19,1,0,0,0,
	188,189,5,12,0,0,189,191,5,13,0,0,190,192,5,14,0,0,191,190,1,0,0,0,191,
	192,1,0,0,0,192,21,1,0,0,0,193,194,5,12,0,0,194,195,3,76,38,0,195,200,3,
	72,36,0,196,197,5,57,0,0,197,199,3,72,36,0,198,196,1,0,0,0,199,202,1,0,
	0,0,200,198,1,0,0,0,200,201,1,0,0,0,201,23,1,0,0,0,202,200,1,0,0,0,203,
	204,3,36,18,0,204,205,3,78,39,0,205,25,1,0,0,0,206,207,5,18,0,0,207,209,
	3,78,39,0,208,210,3,78,39,0,209,208,1,0,0,0,210,211,1,0,0,0,211,209,1,0,
	0,0,211,212,1,0,0,0,212,27,1,0,0,0,213,214,5,53,0,0,214,215,3,82,41,0,215,
	216,5,56,0,0,216,217,3,74,37,0,217,218,3,92,46,0,218,29,1,0,0,0,219,220,
	5,19,0,0,220,222,3,82,41,0,221,223,5,63,0,0,222,221,1,0,0,0,222,223,1,0,
	0,0,223,224,1,0,0,0,224,225,5,20,0,0,225,226,5,44,0,0,226,227,3,82,41,0,
	227,31,1,0,0,0,228,230,3,34,17,0,229,228,1,0,0,0,229,230,1,0,0,0,230,231,
	1,0,0,0,231,233,3,38,19,0,232,234,5,63,0,0,233,232,1,0,0,0,233,234,1,0,
	0,0,234,33,1,0,0,0,235,236,5,44,0,0,236,237,3,82,41,0,237,238,5,56,0,0,
	238,35,1,0,0,0,239,240,7,1,0,0,240,37,1,0,0,0,241,248,3,40,20,0,242,248,
	3,42,21,0,243,248,3,44,22,0,244,248,3,46,23,0,245,248,3,48,24,0,246,248,
	3,50,25,0,247,241,1,0,0,0,247,242,1,0,0,0,247,243,1,0,0,0,247,244,1,0,0,
	0,247,245,1,0,0,0,247,246,1,0,0,0,248,39,1,0,0,0,249,250,5,21,0,0,250,251,
	3,66,33,0,251,252,5,52,0,0,252,253,3,62,31,0,253,41,1,0,0,0,254,255,5,22,
	0,0,255,256,3,66,33,0,256,257,5,52,0,0,257,258,3,64,32,0,258,43,1,0,0,0,
	259,261,5,23,0,0,260,262,3,66,33,0,261,260,1,0,0,0,261,262,1,0,0,0,262,
	264,1,0,0,0,263,265,5,55,0,0,264,263,1,0,0,0,264,265,1,0,0,0,265,267,1,
	0,0,0,266,268,3,58,29,0,267,266,1,0,0,0,267,268,1,0,0,0,268,45,1,0,0,0,
	269,270,5,24,0,0,270,274,3,68,34,0,271,273,3,52,26,0,272,271,1,0,0,0,273,
	276,1,0,0,0,274,272,1,0,0,0,274,275,1,0,0,0,275,280,1,0,0,0,276,274,1,0,
	0,0,277,279,3,54,27,0,278,277,1,0,0,0,279,282,1,0,0,0,280,278,1,0,0,0,280,
	281,1,0,0,0,281,47,1,0,0,0,282,280,1,0,0,0,283,284,5,25,0,0,284,289,3,56,
	28,0,285,286,5,57,0,0,286,288,3,56,28,0,287,285,1,0,0,0,288,291,1,0,0,0,
	289,287,1,0,0,0,289,290,1,0,0,0,290,49,1,0,0,0,291,289,1,0,0,0,292,293,
	5,26,0,0,293,294,3,68,34,0,294,295,5,28,0,0,295,296,3,60,30,0,296,302,1,
	0,0,0,297,298,5,26,0,0,298,299,5,27,0,0,299,300,5,63,0,0,300,302,3,60,30,
	0,301,292,1,0,0,0,301,297,1,0,0,0,302,51,1,0,0,0,303,304,5,29,0,0,304,310,
	3,66,33,0,305,311,3,92,46,0,306,307,5,53,0,0,307,311,3,82,41,0,308,309,
	5,54,0,0,309,311,5,62,0,0,310,305,1,0,0,0,310,306,1,0,0,0,310,308,1,0,0,
	0,311,53,1,0,0,0,312,313,5,51,0,0,313,318,3,66,33,0,314,319,5,30,0,0,315,
	316,5,55,0,0,316,319,3,92,46,0,317,319,3,62,31,0,318,314,1,0,0,0,318,315,
	1,0,0,0,318,317,1,0,0,0,319,55,1,0,0,0,320,321,3,66,33,0,321,322,5,60,0,
	0,322,323,3,62,31,0,323,352,1,0,0,0,324,325,3,66,33,0,325,326,5,31,0,0,
	326,352,1,0,0,0,327,328,3,66,33,0,328,329,5,32,0,0,329,330,5,62,0,0,330,
	352,1,0,0,0,331,332,3,66,33,0,332,333,5,33,0,0,333,334,3,64,32,0,334,352,
	1,0,0,0,335,337,5,34,0,0,336,338,3,68,34,0,337,336,1,0,0,0,338,339,1,0,
	0,0,339,337,1,0,0,0,339,340,1,0,0,0,340,352,1,0,0,0,341,342,5,35,0,0,342,
	344,5,34,0,0,343,345,3,68,34,0,344,343,1,0,0,0,345,346,1,0,0,0,346,344,
	1,0,0,0,346,347,1,0,0,0,347,352,1,0,0,0,348,349,5,36,0,0,349,352,3,68,34,
	0,350,352,5,37,0,0,351,320,1,0,0,0,351,324,1,0,0,0,351,327,1,0,0,0,351,
	331,1,0,0,0,351,335,1,0,0,0,351,341,1,0,0,0,351,348,1,0,0,0,351,350,1,0,
	0,0,352,57,1,0,0,0,353,357,5,62,0,0,354,357,5,61,0,0,355,357,3,82,41,0,
	356,353,1,0,0,0,356,354,1,0,0,0,356,355,1,0,0,0,357,59,1,0,0,0,358,359,
	7,2,0,0,359,61,1,0,0,0,360,365,3,64,32,0,361,362,5,57,0,0,362,364,3,64,
	32,0,363,361,1,0,0,0,364,367,1,0,0,0,365,363,1,0,0,0,365,366,1,0,0,0,366,
	63,1,0,0,0,367,365,1,0,0,0,368,369,5,53,0,0,369,375,3,82,41,0,370,375,3,
	92,46,0,371,372,3,74,37,0,372,373,3,92,46,0,373,375,1,0,0,0,374,368,1,0,
	0,0,374,370,1,0,0,0,374,371,1,0,0,0,375,65,1,0,0,0,376,377,5,45,0,0,377,
	378,3,80,40,0,378,379,5,46,0,0,379,67,1,0,0,0,380,381,5,47,0,0,381,382,
	3,80,40,0,382,383,5,48,0,0,383,69,1,0,0,0,384,385,3,82,41,0,385,386,5,58,
	0,0,386,387,3,66,33,0,387,71,1,0,0,0,388,391,3,80,40,0,389,391,5,63,0,0,
	390,388,1,0,0,0,390,389,1,0,0,0,391,73,1,0,0,0,392,395,5,63,0,0,393,395,
	3,82,41,0,394,392,1,0,0,0,394,393,1,0,0,0,395,75,1,0,0,0,396,399,5,63,0,
	0,397,399,3,84,42,0,398,396,1,0,0,0,398,397,1,0,0,0,399,77,1,0,0,0,400,
	403,3,80,40,0,401,403,5,63,0,0,402,400,1,0,0,0,402,401,1,0,0,0,403,79,1,
	0,0,0,404,409,3,82,41,0,405,406,5,58,0,0,406,408,3,82,41,0,407,405,1,0,
	0,0,408,411,1,0,0,0,409,407,1,0,0,0,409,410,1,0,0,0,410,81,1,0,0,0,411,
	409,1,0,0,0,412,415,5,64,0,0,413,415,3,86,43,0,414,412,1,0,0,0,414,413,
	1,0,0,0,415,83,1,0,0,0,416,419,5,64,0,0,417,419,3,88,44,0,418,416,1,0,0,
	0,418,417,1,0,0,0,419,85,1,0,0,0,420,421,7,3,0,0,421,87,1,0,0,0,422,423,
	7,4,0,0,423,89,1,0,0,0,424,432,3,92,46,0,425,432,3,94,47,0,426,432,5,63,
	0,0,427,432,5,62,0,0,428,432,5,38,0,0,429,432,5,39,0,0,430,432,5,40,0,0,
	431,424,1,0,0,0,431,425,1,0,0,0,431,426,1,0,0,0,431,427,1,0,0,0,431,428,
	1,0,0,0,431,429,1,0,0,0,431,430,1,0,0,0,432,91,1,0,0,0,433,446,5,49,0,0,
	434,435,5,63,0,0,435,436,5,56,0,0,436,443,3,90,45,0,437,438,5,57,0,0,438,
	439,5,63,0,0,439,440,5,56,0,0,440,442,3,90,45,0,441,437,1,0,0,0,442,445,
	1,0,0,0,443,441,1,0,0,0,443,444,1,0,0,0,444,447,1,0,0,0,445,443,1,0,0,0,
	446,434,1,0,0,0,446,447,1,0,0,0,447,448,1,0,0,0,448,449,5,50,0,0,449,93,
	1,0,0,0,450,459,5,47,0,0,451,456,3,90,45,0,452,453,5,57,0,0,453,455,3,90,
	45,0,454,452,1,0,0,0,455,458,1,0,0,0,456,454,1,0,0,0,456,457,1,0,0,0,457,
	460,1,0,0,0,458,456,1,0,0,0,459,451,1,0,0,0,459,460,1,0,0,0,460,461,1,0,
	0,0,461,462,5,48,0,0,462,95,1,0,0,0,37,144,149,170,191,200,211,222,229,
	233,247,261,264,267,274,280,289,301,310,318,339,346,351,356,365,374,390,
	394,398,402,409,414,418,431,443,446,456,459];

	private static __ATN: ATN;
	public static get _ATN(): ATN {
		if (!VelocitronPlayParser.__ATN) {
			VelocitronPlayParser.__ATN = new ATNDeserializer().deserialize(VelocitronPlayParser._serializedATN);
		}

		return VelocitronPlayParser.__ATN;
	}


	static DecisionsToDFA = VelocitronPlayParser._ATN.decisionToState.map( (ds: DecisionState, index: number) => new DFA(ds, index) );

}

export class StatementContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public header(): HeaderContext {
		return this.getTypedRuleContext(HeaderContext, 0) as HeaderContext;
	}
	public EOF(): TerminalNode {
		return this.getToken(VelocitronPlayParser.EOF, 0);
	}
	public netSetting(): NetSettingContext {
		return this.getTypedRuleContext(NetSettingContext, 0) as NetSettingContext;
	}
	public useSetting(): UseSettingContext {
		return this.getTypedRuleContext(UseSettingContext, 0) as UseSettingContext;
	}
	public wireSetting(): WireSettingContext {
		return this.getTypedRuleContext(WireSettingContext, 0) as WireSettingContext;
	}
	public shareSetting(): ShareSettingContext {
		return this.getTypedRuleContext(ShareSettingContext, 0) as ShareSettingContext;
	}
	public refineSetting(): RefineSettingContext {
		return this.getTypedRuleContext(RefineSettingContext, 0) as RefineSettingContext;
	}
	public markingSetting(): MarkingSettingContext {
		return this.getTypedRuleContext(MarkingSettingContext, 0) as MarkingSettingContext;
	}
	public instanceSetting(): InstanceSettingContext {
		return this.getTypedRuleContext(InstanceSettingContext, 0) as InstanceSettingContext;
	}
	public scopeSetting(): ScopeSettingContext {
		return this.getTypedRuleContext(ScopeSettingContext, 0) as ScopeSettingContext;
	}
	public sequenceShow(): SequenceShowContext {
		return this.getTypedRuleContext(SequenceShowContext, 0) as SequenceShowContext;
	}
	public colorShow(): ColorShowContext {
		return this.getTypedRuleContext(ColorShowContext, 0) as ColorShowContext;
	}
	public actorSetting(): ActorSettingContext {
		return this.getTypedRuleContext(ActorSettingContext, 0) as ActorSettingContext;
	}
	public boxSetting(): BoxSettingContext {
		return this.getTypedRuleContext(BoxSettingContext, 0) as BoxSettingContext;
	}
	public templateDecl(): TemplateDeclContext {
		return this.getTypedRuleContext(TemplateDeclContext, 0) as TemplateDeclContext;
	}
	public pathDecl(): PathDeclContext {
		return this.getTypedRuleContext(PathDeclContext, 0) as PathDeclContext;
	}
	public step(): StepContext {
		return this.getTypedRuleContext(StepContext, 0) as StepContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_statement;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitStatement) {
			return visitor.visitStatement(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class HeaderContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public PLAY(): TerminalNode {
		return this.getToken(VelocitronPlayParser.PLAY, 0);
	}
	public singleName(): SingleNameContext {
		return this.getTypedRuleContext(SingleNameContext, 0) as SingleNameContext;
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPlayParser.STRING, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_header;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitHeader) {
			return visitor.visitHeader(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class NetSettingContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public NET(): TerminalNode {
		return this.getToken(VelocitronPlayParser.NET, 0);
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPlayParser.STRING, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_netSetting;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitNetSetting) {
			return visitor.visitNetSetting(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class UseSettingContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public USE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.USE, 0);
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPlayParser.STRING, 0);
	}
	public AS(): TerminalNode {
		return this.getToken(VelocitronPlayParser.AS, 0);
	}
	public singleName(): SingleNameContext {
		return this.getTypedRuleContext(SingleNameContext, 0) as SingleNameContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_useSetting;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitUseSetting) {
			return visitor.visitUseSetting(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class WireSettingContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public WIRE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.WIRE, 0);
	}
	public wireEnd_list(): WireEndContext[] {
		return this.getTypedRuleContexts(WireEndContext) as WireEndContext[];
	}
	public wireEnd(i: number): WireEndContext {
		return this.getTypedRuleContext(WireEndContext, i) as WireEndContext;
	}
	public ARROW(): TerminalNode {
		return this.getToken(VelocitronPlayParser.ARROW, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_wireSetting;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitWireSetting) {
			return visitor.visitWireSetting(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ShareSettingContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public SHARE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.SHARE, 0);
	}
	public wireEnd_list(): WireEndContext[] {
		return this.getTypedRuleContexts(WireEndContext) as WireEndContext[];
	}
	public wireEnd(i: number): WireEndContext {
		return this.getTypedRuleContext(WireEndContext, i) as WireEndContext;
	}
	public TILDE_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPlayParser.TILDE);
	}
	public TILDE(i: number): TerminalNode {
		return this.getToken(VelocitronPlayParser.TILDE, i);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_shareSetting;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitShareSetting) {
			return visitor.visitShareSetting(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class RefineSettingContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public REFINE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.REFINE, 0);
	}
	public singleName_list(): SingleNameContext[] {
		return this.getTypedRuleContexts(SingleNameContext) as SingleNameContext[];
	}
	public singleName(i: number): SingleNameContext {
		return this.getTypedRuleContext(SingleNameContext, i) as SingleNameContext;
	}
	public DOT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.DOT, 0);
	}
	public transition(): TransitionContext {
		return this.getTypedRuleContext(TransitionContext, 0) as TransitionContext;
	}
	public BY(): TerminalNode {
		return this.getToken(VelocitronPlayParser.BY, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_refineSetting;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitRefineSetting) {
			return visitor.visitRefineSetting(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class MarkingSettingContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public MARKING(): TerminalNode {
		return this.getToken(VelocitronPlayParser.MARKING, 0);
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_markingSetting;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitMarkingSetting) {
			return visitor.visitMarkingSetting(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class InstanceSettingContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public INSTANCE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.INSTANCE, 0);
	}
	public tokenExpr(): TokenExprContext {
		return this.getTypedRuleContext(TokenExprContext, 0) as TokenExprContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_instanceSetting;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitInstanceSetting) {
			return visitor.visitInstanceSetting(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ScopeSettingContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public SCOPE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.SCOPE, 0);
	}
	public STEP(): TerminalNode {
		return this.getToken(VelocitronPlayParser.STEP, 0);
	}
	public NEIGHBORS(): TerminalNode {
		return this.getToken(VelocitronPlayParser.NEIGHBORS, 0);
	}
	public SUBNET(): TerminalNode {
		return this.getToken(VelocitronPlayParser.SUBNET, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_scopeSetting;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitScopeSetting) {
			return visitor.visitScopeSetting(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class SequenceShowContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public SHOW(): TerminalNode {
		return this.getToken(VelocitronPlayParser.SHOW, 0);
	}
	public SEQUENCE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.SEQUENCE, 0);
	}
	public ONLY(): TerminalNode {
		return this.getToken(VelocitronPlayParser.ONLY, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_sequenceShow;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitSequenceShow) {
			return visitor.visitSequenceShow(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ColorShowContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public SHOW(): TerminalNode {
		return this.getToken(VelocitronPlayParser.SHOW, 0);
	}
	public colorNotSequence(): ColorNotSequenceContext {
		return this.getTypedRuleContext(ColorNotSequenceContext, 0) as ColorNotSequenceContext;
	}
	public fieldPath_list(): FieldPathContext[] {
		return this.getTypedRuleContexts(FieldPathContext) as FieldPathContext[];
	}
	public fieldPath(i: number): FieldPathContext {
		return this.getTypedRuleContext(FieldPathContext, i) as FieldPathContext;
	}
	public COMMA_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPlayParser.COMMA);
	}
	public COMMA(i: number): TerminalNode {
		return this.getToken(VelocitronPlayParser.COMMA, i);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_colorShow;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitColorShow) {
			return visitor.visitColorShow(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ActorSettingContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public actorKind(): ActorKindContext {
		return this.getTypedRuleContext(ActorKindContext, 0) as ActorKindContext;
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_actorSetting;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitActorSetting) {
			return visitor.visitActorSetting(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class BoxSettingContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public BOX(): TerminalNode {
		return this.getToken(VelocitronPlayParser.BOX, 0);
	}
	public name_list(): NameContext[] {
		return this.getTypedRuleContexts(NameContext) as NameContext[];
	}
	public name(i: number): NameContext {
		return this.getTypedRuleContext(NameContext, i) as NameContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_boxSetting;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitBoxSetting) {
			return visitor.visitBoxSetting(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class TemplateDeclContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public DOLLAR(): TerminalNode {
		return this.getToken(VelocitronPlayParser.DOLLAR, 0);
	}
	public singleName(): SingleNameContext {
		return this.getTypedRuleContext(SingleNameContext, 0) as SingleNameContext;
	}
	public COLON(): TerminalNode {
		return this.getToken(VelocitronPlayParser.COLON, 0);
	}
	public color(): ColorContext {
		return this.getTypedRuleContext(ColorContext, 0) as ColorContext;
	}
	public jsonObject(): JsonObjectContext {
		return this.getTypedRuleContext(JsonObjectContext, 0) as JsonObjectContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_templateDecl;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitTemplateDecl) {
			return visitor.visitTemplateDecl(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class PathDeclContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public PATH(): TerminalNode {
		return this.getToken(VelocitronPlayParser.PATH, 0);
	}
	public singleName_list(): SingleNameContext[] {
		return this.getTypedRuleContexts(SingleNameContext) as SingleNameContext[];
	}
	public singleName(i: number): SingleNameContext {
		return this.getTypedRuleContext(SingleNameContext, i) as SingleNameContext;
	}
	public FROM(): TerminalNode {
		return this.getToken(VelocitronPlayParser.FROM, 0);
	}
	public AT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.AT, 0);
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPlayParser.STRING, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_pathDecl;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitPathDecl) {
			return visitor.visitPathDecl(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class StepContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public stepBody(): StepBodyContext {
		return this.getTypedRuleContext(StepBodyContext, 0) as StepBodyContext;
	}
	public label(): LabelContext {
		return this.getTypedRuleContext(LabelContext, 0) as LabelContext;
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPlayParser.STRING, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_step;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitStep) {
			return visitor.visitStep(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class LabelContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public AT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.AT, 0);
	}
	public singleName(): SingleNameContext {
		return this.getTypedRuleContext(SingleNameContext, 0) as SingleNameContext;
	}
	public COLON(): TerminalNode {
		return this.getToken(VelocitronPlayParser.COLON, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_label;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitLabel) {
			return visitor.visitLabel(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ActorKindContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public PERSON(): TerminalNode {
		return this.getToken(VelocitronPlayParser.PERSON, 0);
	}
	public SYSTEM(): TerminalNode {
		return this.getToken(VelocitronPlayParser.SYSTEM, 0);
	}
	public RECORD(): TerminalNode {
		return this.getToken(VelocitronPlayParser.RECORD, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_actorKind;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitActorKind) {
			return visitor.visitActorKind(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class StepBodyContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public injectBody(): InjectBodyContext {
		return this.getTypedRuleContext(InjectBodyContext, 0) as InjectBodyContext;
	}
	public updateBody(): UpdateBodyContext {
		return this.getTypedRuleContext(UpdateBodyContext, 0) as UpdateBodyContext;
	}
	public advanceBody(): AdvanceBodyContext {
		return this.getTypedRuleContext(AdvanceBodyContext, 0) as AdvanceBodyContext;
	}
	public fireBody(): FireBodyContext {
		return this.getTypedRuleContext(FireBodyContext, 0) as FireBodyContext;
	}
	public expectBody(): ExpectBodyContext {
		return this.getTypedRuleContext(ExpectBodyContext, 0) as ExpectBodyContext;
	}
	public assumeBody(): AssumeBodyContext {
		return this.getTypedRuleContext(AssumeBodyContext, 0) as AssumeBodyContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_stepBody;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitStepBody) {
			return visitor.visitStepBody(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class InjectBodyContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public INJECT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.INJECT, 0);
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
	public LEFT_ARROW(): TerminalNode {
		return this.getToken(VelocitronPlayParser.LEFT_ARROW, 0);
	}
	public tokenList(): TokenListContext {
		return this.getTypedRuleContext(TokenListContext, 0) as TokenListContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_injectBody;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitInjectBody) {
			return visitor.visitInjectBody(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class UpdateBodyContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public UPDATE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.UPDATE, 0);
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
	public LEFT_ARROW(): TerminalNode {
		return this.getToken(VelocitronPlayParser.LEFT_ARROW, 0);
	}
	public tokenExpr(): TokenExprContext {
		return this.getTypedRuleContext(TokenExprContext, 0) as TokenExprContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_updateBody;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitUpdateBody) {
			return visitor.visitUpdateBody(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class AdvanceBodyContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public ADVANCE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.ADVANCE, 0);
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
	public PLUS(): TerminalNode {
		return this.getToken(VelocitronPlayParser.PLUS, 0);
	}
	public timeValue(): TimeValueContext {
		return this.getTypedRuleContext(TimeValueContext, 0) as TimeValueContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_advanceBody;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitAdvanceBody) {
			return visitor.visitAdvanceBody(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class FireBodyContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public FIRE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.FIRE, 0);
	}
	public transition(): TransitionContext {
		return this.getTypedRuleContext(TransitionContext, 0) as TransitionContext;
	}
	public withClause_list(): WithClauseContext[] {
		return this.getTypedRuleContexts(WithClauseContext) as WithClauseContext[];
	}
	public withClause(i: number): WithClauseContext {
		return this.getTypedRuleContext(WithClauseContext, i) as WithClauseContext;
	}
	public outputClause_list(): OutputClauseContext[] {
		return this.getTypedRuleContexts(OutputClauseContext) as OutputClauseContext[];
	}
	public outputClause(i: number): OutputClauseContext {
		return this.getTypedRuleContext(OutputClauseContext, i) as OutputClauseContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_fireBody;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitFireBody) {
			return visitor.visitFireBody(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ExpectBodyContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public EXPECT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.EXPECT, 0);
	}
	public condition_list(): ConditionContext[] {
		return this.getTypedRuleContexts(ConditionContext) as ConditionContext[];
	}
	public condition(i: number): ConditionContext {
		return this.getTypedRuleContext(ConditionContext, i) as ConditionContext;
	}
	public COMMA_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPlayParser.COMMA);
	}
	public COMMA(i: number): TerminalNode {
		return this.getToken(VelocitronPlayParser.COMMA, i);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_expectBody;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitExpectBody) {
			return visitor.visitExpectBody(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class AssumeBodyContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public ASSUME(): TerminalNode {
		return this.getToken(VelocitronPlayParser.ASSUME, 0);
	}
	public transition(): TransitionContext {
		return this.getTypedRuleContext(TransitionContext, 0) as TransitionContext;
	}
	public GUARD(): TerminalNode {
		return this.getToken(VelocitronPlayParser.GUARD, 0);
	}
	public truthValue(): TruthValueContext {
		return this.getTypedRuleContext(TruthValueContext, 0) as TruthValueContext;
	}
	public PREDICATE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.PREDICATE, 0);
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPlayParser.STRING, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_assumeBody;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitAssumeBody) {
			return visitor.visitAssumeBody(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class WithClauseContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public WITH(): TerminalNode {
		return this.getToken(VelocitronPlayParser.WITH, 0);
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
	public jsonObject(): JsonObjectContext {
		return this.getTypedRuleContext(JsonObjectContext, 0) as JsonObjectContext;
	}
	public DOLLAR(): TerminalNode {
		return this.getToken(VelocitronPlayParser.DOLLAR, 0);
	}
	public singleName(): SingleNameContext {
		return this.getTypedRuleContext(SingleNameContext, 0) as SingleNameContext;
	}
	public HASH(): TerminalNode {
		return this.getToken(VelocitronPlayParser.HASH, 0);
	}
	public NUMBER(): TerminalNode {
		return this.getToken(VelocitronPlayParser.NUMBER, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_withClause;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitWithClause) {
			return visitor.visitWithClause(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class OutputClauseContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public ARROW(): TerminalNode {
		return this.getToken(VelocitronPlayParser.ARROW, 0);
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
	public NOTHING(): TerminalNode {
		return this.getToken(VelocitronPlayParser.NOTHING, 0);
	}
	public PLUS(): TerminalNode {
		return this.getToken(VelocitronPlayParser.PLUS, 0);
	}
	public jsonObject(): JsonObjectContext {
		return this.getTypedRuleContext(JsonObjectContext, 0) as JsonObjectContext;
	}
	public tokenList(): TokenListContext {
		return this.getTypedRuleContext(TokenListContext, 0) as TokenListContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_outputClause;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitOutputClause) {
			return visitor.visitOutputClause(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ConditionContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
	public EQ(): TerminalNode {
		return this.getToken(VelocitronPlayParser.EQ, 0);
	}
	public tokenList(): TokenListContext {
		return this.getTypedRuleContext(TokenListContext, 0) as TokenListContext;
	}
	public EMPTY(): TerminalNode {
		return this.getToken(VelocitronPlayParser.EMPTY, 0);
	}
	public COUNT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.COUNT, 0);
	}
	public NUMBER(): TerminalNode {
		return this.getToken(VelocitronPlayParser.NUMBER, 0);
	}
	public HAS(): TerminalNode {
		return this.getToken(VelocitronPlayParser.HAS, 0);
	}
	public tokenExpr(): TokenExprContext {
		return this.getTypedRuleContext(TokenExprContext, 0) as TokenExprContext;
	}
	public ENABLED(): TerminalNode {
		return this.getToken(VelocitronPlayParser.ENABLED, 0);
	}
	public transition_list(): TransitionContext[] {
		return this.getTypedRuleContexts(TransitionContext) as TransitionContext[];
	}
	public transition(i: number): TransitionContext {
		return this.getTypedRuleContext(TransitionContext, i) as TransitionContext;
	}
	public NOT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.NOT, 0);
	}
	public NEXT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.NEXT, 0);
	}
	public QUIESCENT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.QUIESCENT, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_condition;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitCondition) {
			return visitor.visitCondition(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class TimeValueContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public NUMBER(): TerminalNode {
		return this.getToken(VelocitronPlayParser.NUMBER, 0);
	}
	public DURATION(): TerminalNode {
		return this.getToken(VelocitronPlayParser.DURATION, 0);
	}
	public singleName(): SingleNameContext {
		return this.getTypedRuleContext(SingleNameContext, 0) as SingleNameContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_timeValue;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitTimeValue) {
			return visitor.visitTimeValue(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class TruthValueContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public TRUE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.TRUE, 0);
	}
	public FALSE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.FALSE, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_truthValue;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitTruthValue) {
			return visitor.visitTruthValue(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class TokenListContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public tokenExpr_list(): TokenExprContext[] {
		return this.getTypedRuleContexts(TokenExprContext) as TokenExprContext[];
	}
	public tokenExpr(i: number): TokenExprContext {
		return this.getTypedRuleContext(TokenExprContext, i) as TokenExprContext;
	}
	public COMMA_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPlayParser.COMMA);
	}
	public COMMA(i: number): TerminalNode {
		return this.getToken(VelocitronPlayParser.COMMA, i);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_tokenList;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitTokenList) {
			return visitor.visitTokenList(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class TokenExprContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public DOLLAR(): TerminalNode {
		return this.getToken(VelocitronPlayParser.DOLLAR, 0);
	}
	public singleName(): SingleNameContext {
		return this.getTypedRuleContext(SingleNameContext, 0) as SingleNameContext;
	}
	public jsonObject(): JsonObjectContext {
		return this.getTypedRuleContext(JsonObjectContext, 0) as JsonObjectContext;
	}
	public color(): ColorContext {
		return this.getTypedRuleContext(ColorContext, 0) as ColorContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_tokenExpr;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitTokenExpr) {
			return visitor.visitTokenExpr(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class PlaceContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public LPAREN(): TerminalNode {
		return this.getToken(VelocitronPlayParser.LPAREN, 0);
	}
	public qualifiedName(): QualifiedNameContext {
		return this.getTypedRuleContext(QualifiedNameContext, 0) as QualifiedNameContext;
	}
	public RPAREN(): TerminalNode {
		return this.getToken(VelocitronPlayParser.RPAREN, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_place;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitPlace) {
			return visitor.visitPlace(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class TransitionContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public LBRACK(): TerminalNode {
		return this.getToken(VelocitronPlayParser.LBRACK, 0);
	}
	public qualifiedName(): QualifiedNameContext {
		return this.getTypedRuleContext(QualifiedNameContext, 0) as QualifiedNameContext;
	}
	public RBRACK(): TerminalNode {
		return this.getToken(VelocitronPlayParser.RBRACK, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_transition;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitTransition) {
			return visitor.visitTransition(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class WireEndContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public singleName(): SingleNameContext {
		return this.getTypedRuleContext(SingleNameContext, 0) as SingleNameContext;
	}
	public DOT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.DOT, 0);
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_wireEnd;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitWireEnd) {
			return visitor.visitWireEnd(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class FieldPathContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public qualifiedName(): QualifiedNameContext {
		return this.getTypedRuleContext(QualifiedNameContext, 0) as QualifiedNameContext;
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPlayParser.STRING, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_fieldPath;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitFieldPath) {
			return visitor.visitFieldPath(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ColorContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPlayParser.STRING, 0);
	}
	public singleName(): SingleNameContext {
		return this.getTypedRuleContext(SingleNameContext, 0) as SingleNameContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_color;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitColor) {
			return visitor.visitColor(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ColorNotSequenceContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPlayParser.STRING, 0);
	}
	public singleNameNotSequence(): SingleNameNotSequenceContext {
		return this.getTypedRuleContext(SingleNameNotSequenceContext, 0) as SingleNameNotSequenceContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_colorNotSequence;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitColorNotSequence) {
			return visitor.visitColorNotSequence(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class NameContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public qualifiedName(): QualifiedNameContext {
		return this.getTypedRuleContext(QualifiedNameContext, 0) as QualifiedNameContext;
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPlayParser.STRING, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_name;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitName) {
			return visitor.visitName(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class QualifiedNameContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public singleName_list(): SingleNameContext[] {
		return this.getTypedRuleContexts(SingleNameContext) as SingleNameContext[];
	}
	public singleName(i: number): SingleNameContext {
		return this.getTypedRuleContext(SingleNameContext, i) as SingleNameContext;
	}
	public DOT_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPlayParser.DOT);
	}
	public DOT(i: number): TerminalNode {
		return this.getToken(VelocitronPlayParser.DOT, i);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_qualifiedName;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitQualifiedName) {
			return visitor.visitQualifiedName(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class SingleNameContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public IDENT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.IDENT, 0);
	}
	public keyword(): KeywordContext {
		return this.getTypedRuleContext(KeywordContext, 0) as KeywordContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_singleName;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitSingleName) {
			return visitor.visitSingleName(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class SingleNameNotSequenceContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public IDENT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.IDENT, 0);
	}
	public keywordNotSequence(): KeywordNotSequenceContext {
		return this.getTypedRuleContext(KeywordNotSequenceContext, 0) as KeywordNotSequenceContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_singleNameNotSequence;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitSingleNameNotSequence) {
			return visitor.visitSingleNameNotSequence(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class KeywordContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public PLAY(): TerminalNode {
		return this.getToken(VelocitronPlayParser.PLAY, 0);
	}
	public NET(): TerminalNode {
		return this.getToken(VelocitronPlayParser.NET, 0);
	}
	public USE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.USE, 0);
	}
	public AS(): TerminalNode {
		return this.getToken(VelocitronPlayParser.AS, 0);
	}
	public WIRE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.WIRE, 0);
	}
	public SHARE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.SHARE, 0);
	}
	public REFINE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.REFINE, 0);
	}
	public BY(): TerminalNode {
		return this.getToken(VelocitronPlayParser.BY, 0);
	}
	public MARKING(): TerminalNode {
		return this.getToken(VelocitronPlayParser.MARKING, 0);
	}
	public INSTANCE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.INSTANCE, 0);
	}
	public SCOPE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.SCOPE, 0);
	}
	public SHOW(): TerminalNode {
		return this.getToken(VelocitronPlayParser.SHOW, 0);
	}
	public SEQUENCE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.SEQUENCE, 0);
	}
	public ONLY(): TerminalNode {
		return this.getToken(VelocitronPlayParser.ONLY, 0);
	}
	public PERSON(): TerminalNode {
		return this.getToken(VelocitronPlayParser.PERSON, 0);
	}
	public SYSTEM(): TerminalNode {
		return this.getToken(VelocitronPlayParser.SYSTEM, 0);
	}
	public RECORD(): TerminalNode {
		return this.getToken(VelocitronPlayParser.RECORD, 0);
	}
	public BOX(): TerminalNode {
		return this.getToken(VelocitronPlayParser.BOX, 0);
	}
	public PATH(): TerminalNode {
		return this.getToken(VelocitronPlayParser.PATH, 0);
	}
	public FROM(): TerminalNode {
		return this.getToken(VelocitronPlayParser.FROM, 0);
	}
	public INJECT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.INJECT, 0);
	}
	public UPDATE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.UPDATE, 0);
	}
	public ADVANCE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.ADVANCE, 0);
	}
	public FIRE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.FIRE, 0);
	}
	public EXPECT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.EXPECT, 0);
	}
	public ASSUME(): TerminalNode {
		return this.getToken(VelocitronPlayParser.ASSUME, 0);
	}
	public PREDICATE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.PREDICATE, 0);
	}
	public GUARD(): TerminalNode {
		return this.getToken(VelocitronPlayParser.GUARD, 0);
	}
	public WITH(): TerminalNode {
		return this.getToken(VelocitronPlayParser.WITH, 0);
	}
	public NOTHING(): TerminalNode {
		return this.getToken(VelocitronPlayParser.NOTHING, 0);
	}
	public EMPTY(): TerminalNode {
		return this.getToken(VelocitronPlayParser.EMPTY, 0);
	}
	public COUNT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.COUNT, 0);
	}
	public HAS(): TerminalNode {
		return this.getToken(VelocitronPlayParser.HAS, 0);
	}
	public ENABLED(): TerminalNode {
		return this.getToken(VelocitronPlayParser.ENABLED, 0);
	}
	public NOT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.NOT, 0);
	}
	public NEXT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.NEXT, 0);
	}
	public QUIESCENT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.QUIESCENT, 0);
	}
	public TRUE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.TRUE, 0);
	}
	public FALSE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.FALSE, 0);
	}
	public NULL(): TerminalNode {
		return this.getToken(VelocitronPlayParser.NULL, 0);
	}
	public STEP(): TerminalNode {
		return this.getToken(VelocitronPlayParser.STEP, 0);
	}
	public NEIGHBORS(): TerminalNode {
		return this.getToken(VelocitronPlayParser.NEIGHBORS, 0);
	}
	public SUBNET(): TerminalNode {
		return this.getToken(VelocitronPlayParser.SUBNET, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_keyword;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitKeyword) {
			return visitor.visitKeyword(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class KeywordNotSequenceContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public PLAY(): TerminalNode {
		return this.getToken(VelocitronPlayParser.PLAY, 0);
	}
	public NET(): TerminalNode {
		return this.getToken(VelocitronPlayParser.NET, 0);
	}
	public USE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.USE, 0);
	}
	public AS(): TerminalNode {
		return this.getToken(VelocitronPlayParser.AS, 0);
	}
	public WIRE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.WIRE, 0);
	}
	public SHARE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.SHARE, 0);
	}
	public REFINE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.REFINE, 0);
	}
	public BY(): TerminalNode {
		return this.getToken(VelocitronPlayParser.BY, 0);
	}
	public MARKING(): TerminalNode {
		return this.getToken(VelocitronPlayParser.MARKING, 0);
	}
	public INSTANCE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.INSTANCE, 0);
	}
	public SCOPE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.SCOPE, 0);
	}
	public SHOW(): TerminalNode {
		return this.getToken(VelocitronPlayParser.SHOW, 0);
	}
	public ONLY(): TerminalNode {
		return this.getToken(VelocitronPlayParser.ONLY, 0);
	}
	public PERSON(): TerminalNode {
		return this.getToken(VelocitronPlayParser.PERSON, 0);
	}
	public SYSTEM(): TerminalNode {
		return this.getToken(VelocitronPlayParser.SYSTEM, 0);
	}
	public RECORD(): TerminalNode {
		return this.getToken(VelocitronPlayParser.RECORD, 0);
	}
	public BOX(): TerminalNode {
		return this.getToken(VelocitronPlayParser.BOX, 0);
	}
	public PATH(): TerminalNode {
		return this.getToken(VelocitronPlayParser.PATH, 0);
	}
	public FROM(): TerminalNode {
		return this.getToken(VelocitronPlayParser.FROM, 0);
	}
	public INJECT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.INJECT, 0);
	}
	public UPDATE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.UPDATE, 0);
	}
	public ADVANCE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.ADVANCE, 0);
	}
	public FIRE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.FIRE, 0);
	}
	public EXPECT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.EXPECT, 0);
	}
	public ASSUME(): TerminalNode {
		return this.getToken(VelocitronPlayParser.ASSUME, 0);
	}
	public PREDICATE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.PREDICATE, 0);
	}
	public GUARD(): TerminalNode {
		return this.getToken(VelocitronPlayParser.GUARD, 0);
	}
	public WITH(): TerminalNode {
		return this.getToken(VelocitronPlayParser.WITH, 0);
	}
	public NOTHING(): TerminalNode {
		return this.getToken(VelocitronPlayParser.NOTHING, 0);
	}
	public EMPTY(): TerminalNode {
		return this.getToken(VelocitronPlayParser.EMPTY, 0);
	}
	public COUNT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.COUNT, 0);
	}
	public HAS(): TerminalNode {
		return this.getToken(VelocitronPlayParser.HAS, 0);
	}
	public ENABLED(): TerminalNode {
		return this.getToken(VelocitronPlayParser.ENABLED, 0);
	}
	public NOT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.NOT, 0);
	}
	public NEXT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.NEXT, 0);
	}
	public QUIESCENT(): TerminalNode {
		return this.getToken(VelocitronPlayParser.QUIESCENT, 0);
	}
	public TRUE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.TRUE, 0);
	}
	public FALSE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.FALSE, 0);
	}
	public NULL(): TerminalNode {
		return this.getToken(VelocitronPlayParser.NULL, 0);
	}
	public STEP(): TerminalNode {
		return this.getToken(VelocitronPlayParser.STEP, 0);
	}
	public NEIGHBORS(): TerminalNode {
		return this.getToken(VelocitronPlayParser.NEIGHBORS, 0);
	}
	public SUBNET(): TerminalNode {
		return this.getToken(VelocitronPlayParser.SUBNET, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_keywordNotSequence;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitKeywordNotSequence) {
			return visitor.visitKeywordNotSequence(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class JsonValueContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public jsonObject(): JsonObjectContext {
		return this.getTypedRuleContext(JsonObjectContext, 0) as JsonObjectContext;
	}
	public jsonArray(): JsonArrayContext {
		return this.getTypedRuleContext(JsonArrayContext, 0) as JsonArrayContext;
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPlayParser.STRING, 0);
	}
	public NUMBER(): TerminalNode {
		return this.getToken(VelocitronPlayParser.NUMBER, 0);
	}
	public TRUE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.TRUE, 0);
	}
	public FALSE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.FALSE, 0);
	}
	public NULL(): TerminalNode {
		return this.getToken(VelocitronPlayParser.NULL, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_jsonValue;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitJsonValue) {
			return visitor.visitJsonValue(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class JsonObjectContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public LBRACE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.LBRACE, 0);
	}
	public RBRACE(): TerminalNode {
		return this.getToken(VelocitronPlayParser.RBRACE, 0);
	}
	public STRING_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPlayParser.STRING);
	}
	public STRING(i: number): TerminalNode {
		return this.getToken(VelocitronPlayParser.STRING, i);
	}
	public COLON_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPlayParser.COLON);
	}
	public COLON(i: number): TerminalNode {
		return this.getToken(VelocitronPlayParser.COLON, i);
	}
	public jsonValue_list(): JsonValueContext[] {
		return this.getTypedRuleContexts(JsonValueContext) as JsonValueContext[];
	}
	public jsonValue(i: number): JsonValueContext {
		return this.getTypedRuleContext(JsonValueContext, i) as JsonValueContext;
	}
	public COMMA_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPlayParser.COMMA);
	}
	public COMMA(i: number): TerminalNode {
		return this.getToken(VelocitronPlayParser.COMMA, i);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_jsonObject;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitJsonObject) {
			return visitor.visitJsonObject(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class JsonArrayContext extends ParserRuleContext {
	constructor(parser?: VelocitronPlayParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public LBRACK(): TerminalNode {
		return this.getToken(VelocitronPlayParser.LBRACK, 0);
	}
	public RBRACK(): TerminalNode {
		return this.getToken(VelocitronPlayParser.RBRACK, 0);
	}
	public jsonValue_list(): JsonValueContext[] {
		return this.getTypedRuleContexts(JsonValueContext) as JsonValueContext[];
	}
	public jsonValue(i: number): JsonValueContext {
		return this.getTypedRuleContext(JsonValueContext, i) as JsonValueContext;
	}
	public COMMA_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPlayParser.COMMA);
	}
	public COMMA(i: number): TerminalNode {
		return this.getToken(VelocitronPlayParser.COMMA, i);
	}
    public get ruleIndex(): number {
    	return VelocitronPlayParser.RULE_jsonArray;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPlayVisitor<Result>): Result {
		if (visitor.visitJsonArray) {
			return visitor.visitJsonArray(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}
