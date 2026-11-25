// Generated from VelocitronPetriNet.g4 by ANTLR 4.13.2
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
import VelocitronPetriNetVisitor from "./VelocitronPetriNetVisitor.js";

// for running tests with parameters, TODO: discuss strategy for typed parameters in CI
// eslint-disable-next-line no-unused-vars
type int = number;

export default class VelocitronPetriNetParser extends Parser {
	public static readonly NET = 1;
	public static readonly COMPOSITION = 2;
	public static readonly USE = 3;
	public static readonly AS = 4;
	public static readonly WIRE = 5;
	public static readonly SHARE = 6;
	public static readonly REFINE = 7;
	public static readonly BY = 8;
	public static readonly PORT = 9;
	public static readonly INPUT = 10;
	public static readonly OUTPUT = 11;
	public static readonly HANDLER = 12;
	public static readonly GUARD = 13;
	public static readonly ORDER = 14;
	public static readonly TIMER = 15;
	public static readonly CLOCK = 16;
	public static readonly BIND = 17;
	public static readonly MATURITY = 18;
	public static readonly PRIORITY = 19;
	public static readonly ACCEPTS = 20;
	public static readonly CAPACITY_PER_COLOR_KEY = 21;
	public static readonly WEIGHT = 22;
	public static readonly DATA = 23;
	public static readonly PREDICATE = 24;
	public static readonly CEL = 25;
	public static readonly CORRELATE = 26;
	public static readonly MARKING = 27;
	public static readonly INITIAL = 28;
	public static readonly DESCRIPTION = 29;
	public static readonly ANNOTATION = 30;
	public static readonly EXTENSIONS = 31;
	public static readonly VIEW = 32;
	public static readonly POSITION = 33;
	public static readonly ROUTE = 34;
	public static readonly AT_KEYWORD = 35;
	public static readonly RELATIVE = 36;
	public static readonly PLUS = 37;
	public static readonly EQUALS = 38;
	public static readonly ORTHOGONAL = 39;
	public static readonly SPLINES = 40;
	public static readonly DETAIL = 41;
	public static readonly DECORATE = 42;
	public static readonly HIGHLIGHT = 43;
	public static readonly NOTE = 44;
	public static readonly SUMMARY = 45;
	public static readonly QUIET = 46;
	public static readonly COLOR_KEYWORD = 47;
	public static readonly BESIDE = 48;
	public static readonly FUSION = 49;
	public static readonly SINGLE = 50;
	public static readonly COPIES = 51;
	public static readonly LEFT = 52;
	public static readonly RIGHT = 53;
	public static readonly UNSHARED = 54;
	public static readonly SHOW = 55;
	public static readonly DOMAIN = 56;
	public static readonly FINAL = 57;
	public static readonly INVARIANT = 58;
	public static readonly ACTOR = 59;
	public static readonly PERSON = 60;
	public static readonly SYSTEM = 61;
	public static readonly RECORD = 62;
	public static readonly LIVES = 63;
	public static readonly IN = 64;
	public static readonly READS = 65;
	public static readonly KEPT = 66;
	public static readonly STARTS = 67;
	public static readonly TRUE = 68;
	public static readonly FALSE = 69;
	public static readonly NULL = 70;
	public static readonly AT = 71;
	public static readonly LPAREN = 72;
	public static readonly RPAREN = 73;
	public static readonly LBRACK = 74;
	public static readonly RBRACK = 75;
	public static readonly LBRACE = 76;
	public static readonly RBRACE = 77;
	public static readonly HYPHEN = 78;
	public static readonly READ_ARROW = 79;
	public static readonly INHIBIT_ARROW = 80;
	public static readonly ARROW = 81;
	public static readonly LEFT_ARROW = 82;
	public static readonly DOLLAR = 83;
	public static readonly STAR = 84;
	public static readonly COLON = 85;
	public static readonly COMMA = 86;
	public static readonly DOT = 87;
	public static readonly TILDE = 88;
	public static readonly POSITIVE_INTEGER = 89;
	public static readonly ZERO = 90;
	public static readonly NUMBER = 91;
	public static readonly STRING = 92;
	public static readonly IDENT = 93;
	public static readonly LINE_COMMENT = 94;
	public static readonly BLOCK_COMMENT = 95;
	public static readonly WS = 96;
	public static readonly CRLF = 97;
	public static readonly UNSUPPORTED = 98;
	public static override readonly EOF = Token.EOF;
	public static readonly RULE_document = 0;
	public static readonly RULE_netHeader = 1;
	public static readonly RULE_compositionHeader = 2;
	public static readonly RULE_compositionUse = 3;
	public static readonly RULE_compositionWire = 4;
	public static readonly RULE_compositionShare = 5;
	public static readonly RULE_compositionRefine = 6;
	public static readonly RULE_compositionFinal = 7;
	public static readonly RULE_compositionFinalMarking = 8;
	public static readonly RULE_compositionPlace = 9;
	public static readonly RULE_compositionTransition = 10;
	public static readonly RULE_chain = 11;
	public static readonly RULE_chainNode = 12;
	public static readonly RULE_arcSegment = 13;
	public static readonly RULE_arcOperator = 14;
	public static readonly RULE_additionalChain = 15;
	public static readonly RULE_chainHandle = 16;
	public static readonly RULE_place = 17;
	public static readonly RULE_transition = 18;
	public static readonly RULE_placeDeclaration = 19;
	public static readonly RULE_transitionDeclaration = 20;
	public static readonly RULE_placePort = 21;
	public static readonly RULE_portDirection = 22;
	public static readonly RULE_transitionHandler = 23;
	public static readonly RULE_additionalTransitionHandler = 24;
	public static readonly RULE_transitionGuard = 25;
	public static readonly RULE_transitionTimer = 26;
	public static readonly RULE_transitionTimerBind = 27;
	public static readonly RULE_transitionTimerMaturity = 28;
	public static readonly RULE_transitionBindingName = 29;
	public static readonly RULE_timerBindName = 30;
	public static readonly RULE_transitionPriority = 31;
	public static readonly RULE_transitionOrder = 32;
	public static readonly RULE_chainOrder = 33;
	public static readonly RULE_placeAccepts = 34;
	public static readonly RULE_placeCapacity = 35;
	public static readonly RULE_arcWeight = 36;
	public static readonly RULE_arcData = 37;
	public static readonly RULE_arcPredicate = 38;
	public static readonly RULE_arcCorrelate = 39;
	public static readonly RULE_predicateKind = 40;
	public static readonly RULE_positiveInteger = 41;
	public static readonly RULE_nonnegativeInteger = 42;
	public static readonly RULE_initialMarking = 43;
	public static readonly RULE_additionalInitialMarking = 44;
	public static readonly RULE_namedMarking = 45;
	public static readonly RULE_markingValue = 46;
	public static readonly RULE_metadataDescription = 47;
	public static readonly RULE_metadataAnnotation = 48;
	public static readonly RULE_metadataTarget = 49;
	public static readonly RULE_viewPosition = 50;
	public static readonly RULE_viewRoute = 51;
	public static readonly RULE_viewSplines = 52;
	public static readonly RULE_viewDetail = 53;
	public static readonly RULE_viewFusion = 54;
	public static readonly RULE_viewTarget = 55;
	public static readonly RULE_decoration = 56;
	public static readonly RULE_decorationTarget = 57;
	public static readonly RULE_extensions = 58;
	public static readonly RULE_domainDeclaration = 59;
	public static readonly RULE_fieldPath = 60;
	public static readonly RULE_domainValue = 61;
	public static readonly RULE_finalDeclaration = 62;
	public static readonly RULE_finalMarking = 63;
	public static readonly RULE_invariantDeclaration = 64;
	public static readonly RULE_invariantTerm = 65;
	public static readonly RULE_actorAssignment = 66;
	public static readonly RULE_actorTarget = 67;
	public static readonly RULE_actorDeclaration = 68;
	public static readonly RULE_placeLives = 69;
	public static readonly RULE_placeReadsAs = 70;
	public static readonly RULE_placeKept = 71;
	public static readonly RULE_templateDefinition = 72;
	public static readonly RULE_additionalTemplateDefinition = 73;
	public static readonly RULE_templateReference = 74;
	public static readonly RULE_color = 75;
	public static readonly RULE_name = 76;
	public static readonly RULE_markingName = 77;
	public static readonly RULE_keyword = 78;
	public static readonly RULE_jsonValue = 79;
	public static readonly RULE_jsonObject = 80;
	public static readonly RULE_jsonArray = 81;
	public static readonly literalNames: (string | null)[] = [ null, "'net'", 
                                                            "'composition'", 
                                                            "'use'", "'as'", 
                                                            "'wire'", "'share'", 
                                                            "'refine'", 
                                                            "'by'", "'port'", 
                                                            "'input'", "'output'", 
                                                            "'handler'", 
                                                            "'guard'", "'order'", 
                                                            "'timer'", "'clock'", 
                                                            "'bind'", "'maturity'", 
                                                            "'priority'", 
                                                            "'accepts'", 
                                                            "'capacityPerColorKey'", 
                                                            "'weight'", 
                                                            "'data'", "'predicate'", 
                                                            "'cel'", "'correlate'", 
                                                            "'marking'", 
                                                            "'initial'", 
                                                            "'description'", 
                                                            "'annotation'", 
                                                            "'extensions'", 
                                                            "'view'", "'position'", 
                                                            "'route'", "'at'", 
                                                            "'relative'", 
                                                            "'+'", "'='", 
                                                            "'orthogonal'", 
                                                            "'splines'", 
                                                            "'detail'", 
                                                            "'decorate'", 
                                                            "'highlight'", 
                                                            "'note'", "'summary'", 
                                                            "'quiet'", "'color'", 
                                                            "'beside'", 
                                                            "'fusion'", 
                                                            "'single'", 
                                                            "'copies'", 
                                                            "'left'", "'right'", 
                                                            "'unshared'", 
                                                            "'show'", "'domain'", 
                                                            "'final'", "'invariant'", 
                                                            "'actor'", "'person'", 
                                                            "'system'", 
                                                            "'record'", 
                                                            "'lives'", "'in'", 
                                                            "'reads'", "'kept'", 
                                                            "'starts'", 
                                                            "'true'", "'false'", 
                                                            "'null'", "'@'", 
                                                            "'('", "')'", 
                                                            "'['", "']'", 
                                                            "'{'", "'}'", 
                                                            "'-'", "'->?'", 
                                                            "'->0'", "'->'", 
                                                            "'<-'", "'$'", 
                                                            "'*'", "':'", 
                                                            "','", "'.'", 
                                                            "'~'", null, 
                                                            "'0'", null, 
                                                            null, null, 
                                                            null, null, 
                                                            null, "'\\r\\n'" ];
	public static readonly symbolicNames: (string | null)[] = [ null, "NET", 
                                                             "COMPOSITION", 
                                                             "USE", "AS", 
                                                             "WIRE", "SHARE", 
                                                             "REFINE", "BY", 
                                                             "PORT", "INPUT", 
                                                             "OUTPUT", "HANDLER", 
                                                             "GUARD", "ORDER", 
                                                             "TIMER", "CLOCK", 
                                                             "BIND", "MATURITY", 
                                                             "PRIORITY", 
                                                             "ACCEPTS", 
                                                             "CAPACITY_PER_COLOR_KEY", 
                                                             "WEIGHT", "DATA", 
                                                             "PREDICATE", 
                                                             "CEL", "CORRELATE", 
                                                             "MARKING", 
                                                             "INITIAL", 
                                                             "DESCRIPTION", 
                                                             "ANNOTATION", 
                                                             "EXTENSIONS", 
                                                             "VIEW", "POSITION", 
                                                             "ROUTE", "AT_KEYWORD", 
                                                             "RELATIVE", 
                                                             "PLUS", "EQUALS", 
                                                             "ORTHOGONAL", 
                                                             "SPLINES", 
                                                             "DETAIL", "DECORATE", 
                                                             "HIGHLIGHT", 
                                                             "NOTE", "SUMMARY", 
                                                             "QUIET", "COLOR_KEYWORD", 
                                                             "BESIDE", "FUSION", 
                                                             "SINGLE", "COPIES", 
                                                             "LEFT", "RIGHT", 
                                                             "UNSHARED", 
                                                             "SHOW", "DOMAIN", 
                                                             "FINAL", "INVARIANT", 
                                                             "ACTOR", "PERSON", 
                                                             "SYSTEM", "RECORD", 
                                                             "LIVES", "IN", 
                                                             "READS", "KEPT", 
                                                             "STARTS", "TRUE", 
                                                             "FALSE", "NULL", 
                                                             "AT", "LPAREN", 
                                                             "RPAREN", "LBRACK", 
                                                             "RBRACK", "LBRACE", 
                                                             "RBRACE", "HYPHEN", 
                                                             "READ_ARROW", 
                                                             "INHIBIT_ARROW", 
                                                             "ARROW", "LEFT_ARROW", 
                                                             "DOLLAR", "STAR", 
                                                             "COLON", "COMMA", 
                                                             "DOT", "TILDE", 
                                                             "POSITIVE_INTEGER", 
                                                             "ZERO", "NUMBER", 
                                                             "STRING", "IDENT", 
                                                             "LINE_COMMENT", 
                                                             "BLOCK_COMMENT", 
                                                             "WS", "CRLF", 
                                                             "UNSUPPORTED" ];
	// tslint:disable:no-trailing-whitespace
	public static readonly ruleNames: string[] = [
		"document", "netHeader", "compositionHeader", "compositionUse", "compositionWire", 
		"compositionShare", "compositionRefine", "compositionFinal", "compositionFinalMarking", 
		"compositionPlace", "compositionTransition", "chain", "chainNode", "arcSegment", 
		"arcOperator", "additionalChain", "chainHandle", "place", "transition", 
		"placeDeclaration", "transitionDeclaration", "placePort", "portDirection", 
		"transitionHandler", "additionalTransitionHandler", "transitionGuard", 
		"transitionTimer", "transitionTimerBind", "transitionTimerMaturity", "transitionBindingName", 
		"timerBindName", "transitionPriority", "transitionOrder", "chainOrder", 
		"placeAccepts", "placeCapacity", "arcWeight", "arcData", "arcPredicate", 
		"arcCorrelate", "predicateKind", "positiveInteger", "nonnegativeInteger", 
		"initialMarking", "additionalInitialMarking", "namedMarking", "markingValue", 
		"metadataDescription", "metadataAnnotation", "metadataTarget", "viewPosition", 
		"viewRoute", "viewSplines", "viewDetail", "viewFusion", "viewTarget", 
		"decoration", "decorationTarget", "extensions", "domainDeclaration", "fieldPath", 
		"domainValue", "finalDeclaration", "finalMarking", "invariantDeclaration", 
		"invariantTerm", "actorAssignment", "actorTarget", "actorDeclaration", 
		"placeLives", "placeReadsAs", "placeKept", "templateDefinition", "additionalTemplateDefinition", 
		"templateReference", "color", "name", "markingName", "keyword", "jsonValue", 
		"jsonObject", "jsonArray",
	];
	public get grammarFileName(): string { return "VelocitronPetriNet.g4"; }
	public get literalNames(): (string | null)[] { return VelocitronPetriNetParser.literalNames; }
	public get symbolicNames(): (string | null)[] { return VelocitronPetriNetParser.symbolicNames; }
	public get ruleNames(): string[] { return VelocitronPetriNetParser.ruleNames; }
	public get serializedATN(): number[] { return VelocitronPetriNetParser._serializedATN; }

	protected createFailedPredicateException(predicate?: string, message?: string): FailedPredicateException {
		return new FailedPredicateException(this, predicate, message);
	}

	constructor(input: TokenStream) {
		super(input);
		this._interp = new ParserATNSimulator(this, VelocitronPetriNetParser._ATN, VelocitronPetriNetParser.DecisionsToDFA, new PredictionContextCache());
	}
	// @RuleVersion(0)
	public document(): DocumentContext {
		let localctx: DocumentContext = new DocumentContext(this, this._ctx, this.state);
		this.enterRule(localctx, 0, VelocitronPetriNetParser.RULE_document);
		let _la: number;
		try {
			this.state = 225;
			this._errHandler.sync(this);
			switch (this._input.LA(1)) {
			case -1:
			case 1:
			case 27:
			case 31:
			case 32:
			case 42:
			case 56:
			case 57:
			case 58:
			case 60:
			case 61:
			case 62:
			case 71:
			case 72:
			case 74:
			case 83:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 165;
				this._errHandler.sync(this);
				switch ( this._interp.adaptivePredict(this._input, 0, this._ctx) ) {
				case 1:
					{
					this.state = 164;
					this.netHeader();
					}
					break;
				}
				this.state = 208;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
				while ((((_la) & ~0x1F) === 0 && ((1 << _la) & 2281701378) !== 0) || ((((_la - 32)) & ~0x1F) === 0 && ((1 << (_la - 32)) & 1996489729) !== 0) || ((((_la - 71)) & ~0x1F) === 0 && ((1 << (_la - 71)) & 4107) !== 0)) {
					{
					this.state = 206;
					this._errHandler.sync(this);
					switch ( this._interp.adaptivePredict(this._input, 1, this._ctx) ) {
					case 1:
						{
						this.state = 167;
						this.chain();
						}
						break;
					case 2:
						{
						this.state = 168;
						this.placeDeclaration();
						}
						break;
					case 3:
						{
						this.state = 169;
						this.transitionDeclaration();
						}
						break;
					case 4:
						{
						this.state = 170;
						this.transitionHandler();
						}
						break;
					case 5:
						{
						this.state = 171;
						this.transitionGuard();
						}
						break;
					case 6:
						{
						this.state = 172;
						this.transitionTimer();
						}
						break;
					case 7:
						{
						this.state = 173;
						this.transitionTimerBind();
						}
						break;
					case 8:
						{
						this.state = 174;
						this.transitionTimerMaturity();
						}
						break;
					case 9:
						{
						this.state = 175;
						this.transitionBindingName();
						}
						break;
					case 10:
						{
						this.state = 176;
						this.transitionPriority();
						}
						break;
					case 11:
						{
						this.state = 177;
						this.transitionOrder();
						}
						break;
					case 12:
						{
						this.state = 178;
						this.chainOrder();
						}
						break;
					case 13:
						{
						this.state = 179;
						this.placePort();
						}
						break;
					case 14:
						{
						this.state = 180;
						this.placeAccepts();
						}
						break;
					case 15:
						{
						this.state = 181;
						this.placeCapacity();
						}
						break;
					case 16:
						{
						this.state = 182;
						this.arcWeight();
						}
						break;
					case 17:
						{
						this.state = 183;
						this.arcData();
						}
						break;
					case 18:
						{
						this.state = 184;
						this.arcPredicate();
						}
						break;
					case 19:
						{
						this.state = 185;
						this.arcCorrelate();
						}
						break;
					case 20:
						{
						this.state = 186;
						this.initialMarking();
						}
						break;
					case 21:
						{
						this.state = 187;
						this.templateDefinition();
						}
						break;
					case 22:
						{
						this.state = 188;
						this.namedMarking();
						}
						break;
					case 23:
						{
						this.state = 189;
						this.metadataDescription();
						}
						break;
					case 24:
						{
						this.state = 190;
						this.metadataAnnotation();
						}
						break;
					case 25:
						{
						this.state = 191;
						this.viewPosition();
						}
						break;
					case 26:
						{
						this.state = 192;
						this.viewRoute();
						}
						break;
					case 27:
						{
						this.state = 193;
						this.viewSplines();
						}
						break;
					case 28:
						{
						this.state = 194;
						this.viewDetail();
						}
						break;
					case 29:
						{
						this.state = 195;
						this.viewFusion();
						}
						break;
					case 30:
						{
						this.state = 196;
						this.decoration();
						}
						break;
					case 31:
						{
						this.state = 197;
						this.extensions();
						}
						break;
					case 32:
						{
						this.state = 198;
						this.domainDeclaration();
						}
						break;
					case 33:
						{
						this.state = 199;
						this.finalDeclaration();
						}
						break;
					case 34:
						{
						this.state = 200;
						this.invariantDeclaration();
						}
						break;
					case 35:
						{
						this.state = 201;
						this.actorAssignment();
						}
						break;
					case 36:
						{
						this.state = 202;
						this.actorDeclaration();
						}
						break;
					case 37:
						{
						this.state = 203;
						this.placeLives();
						}
						break;
					case 38:
						{
						this.state = 204;
						this.placeReadsAs();
						}
						break;
					case 39:
						{
						this.state = 205;
						this.placeKept();
						}
						break;
					}
					}
					this.state = 210;
					this._errHandler.sync(this);
					_la = this._input.LA(1);
				}
				this.state = 211;
				this.match(VelocitronPetriNetParser.EOF);
				}
				break;
			case 2:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 212;
				this.compositionHeader();
				this.state = 220;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
				while ((((_la) & ~0x1F) === 0 && ((1 << _la) & 232) !== 0) || _la===57) {
					{
					this.state = 218;
					this._errHandler.sync(this);
					switch (this._input.LA(1)) {
					case 3:
						{
						this.state = 213;
						this.compositionUse();
						}
						break;
					case 5:
						{
						this.state = 214;
						this.compositionWire();
						}
						break;
					case 6:
						{
						this.state = 215;
						this.compositionShare();
						}
						break;
					case 7:
						{
						this.state = 216;
						this.compositionRefine();
						}
						break;
					case 57:
						{
						this.state = 217;
						this.compositionFinal();
						}
						break;
					default:
						throw new NoViableAltException(this);
					}
					}
					this.state = 222;
					this._errHandler.sync(this);
					_la = this._input.LA(1);
				}
				this.state = 223;
				this.match(VelocitronPetriNetParser.EOF);
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
	public netHeader(): NetHeaderContext {
		let localctx: NetHeaderContext = new NetHeaderContext(this, this._ctx, this.state);
		this.enterRule(localctx, 2, VelocitronPetriNetParser.RULE_netHeader);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 227;
			this.match(VelocitronPetriNetParser.NET);
			this.state = 228;
			this.name();
			this.state = 230;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if (_la===92) {
				{
				this.state = 229;
				this.match(VelocitronPetriNetParser.STRING);
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
	public compositionHeader(): CompositionHeaderContext {
		let localctx: CompositionHeaderContext = new CompositionHeaderContext(this, this._ctx, this.state);
		this.enterRule(localctx, 4, VelocitronPetriNetParser.RULE_compositionHeader);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 232;
			this.match(VelocitronPetriNetParser.COMPOSITION);
			this.state = 233;
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
	public compositionUse(): CompositionUseContext {
		let localctx: CompositionUseContext = new CompositionUseContext(this, this._ctx, this.state);
		this.enterRule(localctx, 6, VelocitronPetriNetParser.RULE_compositionUse);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 235;
			this.match(VelocitronPetriNetParser.USE);
			this.state = 236;
			this.match(VelocitronPetriNetParser.STRING);
			this.state = 237;
			this.match(VelocitronPetriNetParser.AS);
			this.state = 238;
			this.match(VelocitronPetriNetParser.IDENT);
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
	public compositionWire(): CompositionWireContext {
		let localctx: CompositionWireContext = new CompositionWireContext(this, this._ctx, this.state);
		this.enterRule(localctx, 8, VelocitronPetriNetParser.RULE_compositionWire);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 240;
			this.match(VelocitronPetriNetParser.WIRE);
			this.state = 241;
			this.match(VelocitronPetriNetParser.IDENT);
			this.state = 242;
			this.match(VelocitronPetriNetParser.DOT);
			this.state = 243;
			this.compositionPlace();
			this.state = 244;
			this.match(VelocitronPetriNetParser.ARROW);
			this.state = 245;
			this.match(VelocitronPetriNetParser.IDENT);
			this.state = 246;
			this.match(VelocitronPetriNetParser.DOT);
			this.state = 247;
			this.compositionPlace();
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
	public compositionShare(): CompositionShareContext {
		let localctx: CompositionShareContext = new CompositionShareContext(this, this._ctx, this.state);
		this.enterRule(localctx, 10, VelocitronPetriNetParser.RULE_compositionShare);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 249;
			this.match(VelocitronPetriNetParser.SHARE);
			this.state = 250;
			this.match(VelocitronPetriNetParser.IDENT);
			this.state = 251;
			this.match(VelocitronPetriNetParser.DOT);
			this.state = 252;
			this.compositionPlace();
			this.state = 257;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			do {
				{
				{
				this.state = 253;
				this.match(VelocitronPetriNetParser.TILDE);
				this.state = 254;
				this.match(VelocitronPetriNetParser.IDENT);
				this.state = 255;
				this.match(VelocitronPetriNetParser.DOT);
				this.state = 256;
				this.compositionPlace();
				}
				}
				this.state = 259;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
			} while (_la===88);
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
	public compositionRefine(): CompositionRefineContext {
		let localctx: CompositionRefineContext = new CompositionRefineContext(this, this._ctx, this.state);
		this.enterRule(localctx, 12, VelocitronPetriNetParser.RULE_compositionRefine);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 261;
			this.match(VelocitronPetriNetParser.REFINE);
			this.state = 262;
			this.match(VelocitronPetriNetParser.IDENT);
			this.state = 263;
			this.match(VelocitronPetriNetParser.DOT);
			this.state = 264;
			this.compositionTransition();
			this.state = 265;
			this.match(VelocitronPetriNetParser.BY);
			this.state = 266;
			this.match(VelocitronPetriNetParser.IDENT);
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
	public compositionFinal(): CompositionFinalContext {
		let localctx: CompositionFinalContext = new CompositionFinalContext(this, this._ctx, this.state);
		this.enterRule(localctx, 14, VelocitronPetriNetParser.RULE_compositionFinal);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 268;
			this.match(VelocitronPetriNetParser.FINAL);
			this.state = 269;
			this.compositionFinalMarking();
			this.state = 274;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			while (_la===86) {
				{
				{
				this.state = 270;
				this.match(VelocitronPetriNetParser.COMMA);
				this.state = 271;
				this.compositionFinalMarking();
				}
				}
				this.state = 276;
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
	public compositionFinalMarking(): CompositionFinalMarkingContext {
		let localctx: CompositionFinalMarkingContext = new CompositionFinalMarkingContext(this, this._ctx, this.state);
		this.enterRule(localctx, 16, VelocitronPetriNetParser.RULE_compositionFinalMarking);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 277;
			this.match(VelocitronPetriNetParser.IDENT);
			this.state = 278;
			this.match(VelocitronPetriNetParser.DOT);
			this.state = 279;
			this.compositionPlace();
			this.state = 286;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			while (_la===37) {
				{
				{
				this.state = 280;
				this.match(VelocitronPetriNetParser.PLUS);
				this.state = 281;
				this.match(VelocitronPetriNetParser.IDENT);
				this.state = 282;
				this.match(VelocitronPetriNetParser.DOT);
				this.state = 283;
				this.compositionPlace();
				}
				}
				this.state = 288;
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
	public compositionPlace(): CompositionPlaceContext {
		let localctx: CompositionPlaceContext = new CompositionPlaceContext(this, this._ctx, this.state);
		this.enterRule(localctx, 18, VelocitronPetriNetParser.RULE_compositionPlace);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 289;
			this.match(VelocitronPetriNetParser.LPAREN);
			this.state = 290;
			this.name();
			this.state = 295;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			while (_la===87) {
				{
				{
				this.state = 291;
				this.match(VelocitronPetriNetParser.DOT);
				this.state = 292;
				this.name();
				}
				}
				this.state = 297;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
			}
			this.state = 298;
			this.match(VelocitronPetriNetParser.RPAREN);
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
	public compositionTransition(): CompositionTransitionContext {
		let localctx: CompositionTransitionContext = new CompositionTransitionContext(this, this._ctx, this.state);
		this.enterRule(localctx, 20, VelocitronPetriNetParser.RULE_compositionTransition);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 300;
			this.match(VelocitronPetriNetParser.LBRACK);
			this.state = 301;
			this.name();
			this.state = 306;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			while (_la===87) {
				{
				{
				this.state = 302;
				this.match(VelocitronPetriNetParser.DOT);
				this.state = 303;
				this.name();
				}
				}
				this.state = 308;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
			}
			this.state = 309;
			this.match(VelocitronPetriNetParser.RBRACK);
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
	public chain(): ChainContext {
		let localctx: ChainContext = new ChainContext(this, this._ctx, this.state);
		this.enterRule(localctx, 22, VelocitronPetriNetParser.RULE_chain);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 312;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if (_la===71) {
				{
				this.state = 311;
				this.chainHandle();
				}
			}

			this.state = 314;
			this.chainNode();
			this.state = 318;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			do {
				{
				{
				this.state = 315;
				this.arcSegment();
				this.state = 316;
				this.chainNode();
				}
				}
				this.state = 320;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
			} while (((((_la - 78)) & ~0x1F) === 0 && ((1 << (_la - 78)) & 15) !== 0));
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
	public chainNode(): ChainNodeContext {
		let localctx: ChainNodeContext = new ChainNodeContext(this, this._ctx, this.state);
		this.enterRule(localctx, 24, VelocitronPetriNetParser.RULE_chainNode);
		try {
			this.state = 324;
			this._errHandler.sync(this);
			switch (this._input.LA(1)) {
			case 72:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 322;
				this.place();
				}
				break;
			case 74:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 323;
				this.transition();
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
	public arcSegment(): ArcSegmentContext {
		let localctx: ArcSegmentContext = new ArcSegmentContext(this, this._ctx, this.state);
		this.enterRule(localctx, 26, VelocitronPetriNetParser.RULE_arcSegment);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 328;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if (_la===78) {
				{
				this.state = 326;
				this.match(VelocitronPetriNetParser.HYPHEN);
				this.state = 327;
				this.color();
				}
			}

			this.state = 330;
			this.arcOperator();
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
	public arcOperator(): ArcOperatorContext {
		let localctx: ArcOperatorContext = new ArcOperatorContext(this, this._ctx, this.state);
		this.enterRule(localctx, 28, VelocitronPetriNetParser.RULE_arcOperator);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 332;
			_la = this._input.LA(1);
			if(!(((((_la - 79)) & ~0x1F) === 0 && ((1 << (_la - 79)) & 7) !== 0))) {
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
	public additionalChain(): AdditionalChainContext {
		let localctx: AdditionalChainContext = new AdditionalChainContext(this, this._ctx, this.state);
		this.enterRule(localctx, 30, VelocitronPetriNetParser.RULE_additionalChain);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 334;
			this.chain();
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
	public chainHandle(): ChainHandleContext {
		let localctx: ChainHandleContext = new ChainHandleContext(this, this._ctx, this.state);
		this.enterRule(localctx, 32, VelocitronPetriNetParser.RULE_chainHandle);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 336;
			this.match(VelocitronPetriNetParser.AT);
			this.state = 337;
			this.name();
			this.state = 338;
			this.match(VelocitronPetriNetParser.COLON);
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
		this.enterRule(localctx, 34, VelocitronPetriNetParser.RULE_place);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 340;
			this.match(VelocitronPetriNetParser.LPAREN);
			this.state = 341;
			this.name();
			this.state = 342;
			this.match(VelocitronPetriNetParser.RPAREN);
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
		this.enterRule(localctx, 36, VelocitronPetriNetParser.RULE_transition);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 344;
			this.match(VelocitronPetriNetParser.LBRACK);
			this.state = 345;
			this.name();
			this.state = 346;
			this.match(VelocitronPetriNetParser.RBRACK);
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
	public placeDeclaration(): PlaceDeclarationContext {
		let localctx: PlaceDeclarationContext = new PlaceDeclarationContext(this, this._ctx, this.state);
		this.enterRule(localctx, 38, VelocitronPetriNetParser.RULE_placeDeclaration);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 348;
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
	public transitionDeclaration(): TransitionDeclarationContext {
		let localctx: TransitionDeclarationContext = new TransitionDeclarationContext(this, this._ctx, this.state);
		this.enterRule(localctx, 40, VelocitronPetriNetParser.RULE_transitionDeclaration);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 350;
			this.transition();
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
	public placePort(): PlacePortContext {
		let localctx: PlacePortContext = new PlacePortContext(this, this._ctx, this.state);
		this.enterRule(localctx, 42, VelocitronPetriNetParser.RULE_placePort);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 352;
			this.place();
			this.state = 353;
			this.match(VelocitronPetriNetParser.PORT);
			this.state = 354;
			this.portDirection();
			this.state = 355;
			this.color();
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
	public portDirection(): PortDirectionContext {
		let localctx: PortDirectionContext = new PortDirectionContext(this, this._ctx, this.state);
		this.enterRule(localctx, 44, VelocitronPetriNetParser.RULE_portDirection);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 357;
			_la = this._input.LA(1);
			if(!(_la===10 || _la===11)) {
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
	public transitionHandler(): TransitionHandlerContext {
		let localctx: TransitionHandlerContext = new TransitionHandlerContext(this, this._ctx, this.state);
		this.enterRule(localctx, 46, VelocitronPetriNetParser.RULE_transitionHandler);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 359;
			this.transition();
			this.state = 360;
			this.match(VelocitronPetriNetParser.HANDLER);
			this.state = 361;
			this.match(VelocitronPetriNetParser.STRING);
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
	public additionalTransitionHandler(): AdditionalTransitionHandlerContext {
		let localctx: AdditionalTransitionHandlerContext = new AdditionalTransitionHandlerContext(this, this._ctx, this.state);
		this.enterRule(localctx, 48, VelocitronPetriNetParser.RULE_additionalTransitionHandler);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 363;
			this.transitionHandler();
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
	public transitionGuard(): TransitionGuardContext {
		let localctx: TransitionGuardContext = new TransitionGuardContext(this, this._ctx, this.state);
		this.enterRule(localctx, 50, VelocitronPetriNetParser.RULE_transitionGuard);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 365;
			this.transition();
			this.state = 366;
			this.match(VelocitronPetriNetParser.GUARD);
			this.state = 367;
			this.match(VelocitronPetriNetParser.STRING);
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
	public transitionTimer(): TransitionTimerContext {
		let localctx: TransitionTimerContext = new TransitionTimerContext(this, this._ctx, this.state);
		this.enterRule(localctx, 52, VelocitronPetriNetParser.RULE_transitionTimer);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 369;
			this.transition();
			this.state = 370;
			this.match(VelocitronPetriNetParser.TIMER);
			this.state = 371;
			this.match(VelocitronPetriNetParser.CLOCK);
			this.state = 372;
			this.place();
			this.state = 373;
			this.match(VelocitronPetriNetParser.CEL);
			this.state = 374;
			this.match(VelocitronPetriNetParser.STRING);
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
	public transitionTimerBind(): TransitionTimerBindContext {
		let localctx: TransitionTimerBindContext = new TransitionTimerBindContext(this, this._ctx, this.state);
		this.enterRule(localctx, 54, VelocitronPetriNetParser.RULE_transitionTimerBind);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 376;
			this.transition();
			this.state = 377;
			this.match(VelocitronPetriNetParser.TIMER);
			this.state = 378;
			this.match(VelocitronPetriNetParser.BIND);
			this.state = 379;
			this.timerBindName();
			this.state = 380;
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
	public transitionTimerMaturity(): TransitionTimerMaturityContext {
		let localctx: TransitionTimerMaturityContext = new TransitionTimerMaturityContext(this, this._ctx, this.state);
		this.enterRule(localctx, 56, VelocitronPetriNetParser.RULE_transitionTimerMaturity);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 382;
			this.transition();
			this.state = 383;
			this.match(VelocitronPetriNetParser.TIMER);
			this.state = 384;
			this.match(VelocitronPetriNetParser.MATURITY);
			this.state = 385;
			this.match(VelocitronPetriNetParser.CEL);
			this.state = 386;
			this.match(VelocitronPetriNetParser.STRING);
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
	public transitionBindingName(): TransitionBindingNameContext {
		let localctx: TransitionBindingNameContext = new TransitionBindingNameContext(this, this._ctx, this.state);
		this.enterRule(localctx, 58, VelocitronPetriNetParser.RULE_transitionBindingName);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 388;
			this.transition();
			this.state = 389;
			this.match(VelocitronPetriNetParser.BIND);
			this.state = 390;
			this.name();
			this.state = 391;
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
	public timerBindName(): TimerBindNameContext {
		let localctx: TimerBindNameContext = new TimerBindNameContext(this, this._ctx, this.state);
		this.enterRule(localctx, 60, VelocitronPetriNetParser.RULE_timerBindName);
		try {
			this.state = 396;
			this._errHandler.sync(this);
			switch (this._input.LA(1)) {
			case 93:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 393;
				this.match(VelocitronPetriNetParser.IDENT);
				}
				break;
			case 28:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 394;
				this.match(VelocitronPetriNetParser.INITIAL);
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
			case 29:
			case 30:
			case 31:
			case 32:
			case 33:
			case 34:
			case 35:
			case 36:
			case 39:
			case 40:
			case 41:
			case 42:
			case 43:
			case 44:
			case 45:
			case 46:
			case 47:
			case 48:
			case 49:
			case 50:
			case 51:
			case 52:
			case 53:
			case 54:
			case 55:
			case 56:
			case 57:
			case 58:
			case 59:
			case 60:
			case 61:
			case 62:
			case 63:
			case 64:
			case 65:
			case 66:
			case 67:
				this.enterOuterAlt(localctx, 3);
				{
				this.state = 395;
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
	public transitionPriority(): TransitionPriorityContext {
		let localctx: TransitionPriorityContext = new TransitionPriorityContext(this, this._ctx, this.state);
		this.enterRule(localctx, 62, VelocitronPetriNetParser.RULE_transitionPriority);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 398;
			this.transition();
			this.state = 399;
			this.match(VelocitronPetriNetParser.PRIORITY);
			this.state = 400;
			this.nonnegativeInteger();
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
	public transitionOrder(): TransitionOrderContext {
		let localctx: TransitionOrderContext = new TransitionOrderContext(this, this._ctx, this.state);
		this.enterRule(localctx, 64, VelocitronPetriNetParser.RULE_transitionOrder);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 402;
			this.transition();
			this.state = 403;
			this.match(VelocitronPetriNetParser.ORDER);
			this.state = 404;
			this.positiveInteger();
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
	public chainOrder(): ChainOrderContext {
		let localctx: ChainOrderContext = new ChainOrderContext(this, this._ctx, this.state);
		this.enterRule(localctx, 66, VelocitronPetriNetParser.RULE_chainOrder);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 406;
			this.match(VelocitronPetriNetParser.AT);
			this.state = 407;
			this.name();
			this.state = 408;
			this.match(VelocitronPetriNetParser.ORDER);
			this.state = 409;
			this.positiveInteger();
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
	public placeAccepts(): PlaceAcceptsContext {
		let localctx: PlaceAcceptsContext = new PlaceAcceptsContext(this, this._ctx, this.state);
		this.enterRule(localctx, 68, VelocitronPetriNetParser.RULE_placeAccepts);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 411;
			this.place();
			this.state = 412;
			this.match(VelocitronPetriNetParser.ACCEPTS);
			this.state = 413;
			this.match(VelocitronPetriNetParser.LBRACK);
			this.state = 414;
			this.color();
			this.state = 419;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			while (_la===86) {
				{
				{
				this.state = 415;
				this.match(VelocitronPetriNetParser.COMMA);
				this.state = 416;
				this.color();
				}
				}
				this.state = 421;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
			}
			this.state = 422;
			this.match(VelocitronPetriNetParser.RBRACK);
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
	public placeCapacity(): PlaceCapacityContext {
		let localctx: PlaceCapacityContext = new PlaceCapacityContext(this, this._ctx, this.state);
		this.enterRule(localctx, 70, VelocitronPetriNetParser.RULE_placeCapacity);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 424;
			this.place();
			this.state = 425;
			this.match(VelocitronPetriNetParser.CAPACITY_PER_COLOR_KEY);
			this.state = 426;
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
	public arcWeight(): ArcWeightContext {
		let localctx: ArcWeightContext = new ArcWeightContext(this, this._ctx, this.state);
		this.enterRule(localctx, 72, VelocitronPetriNetParser.RULE_arcWeight);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 428;
			this.match(VelocitronPetriNetParser.AT);
			this.state = 429;
			this.name();
			this.state = 430;
			this.match(VelocitronPetriNetParser.WEIGHT);
			this.state = 431;
			this.jsonValue();
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
	public arcData(): ArcDataContext {
		let localctx: ArcDataContext = new ArcDataContext(this, this._ctx, this.state);
		this.enterRule(localctx, 74, VelocitronPetriNetParser.RULE_arcData);
		try {
			this.state = 444;
			this._errHandler.sync(this);
			switch ( this._interp.adaptivePredict(this._input, 18, this._ctx) ) {
			case 1:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 433;
				this.match(VelocitronPetriNetParser.AT);
				this.state = 434;
				this.name();
				this.state = 435;
				this.match(VelocitronPetriNetParser.DATA);
				this.state = 436;
				this.match(VelocitronPetriNetParser.CEL);
				this.state = 437;
				this.match(VelocitronPetriNetParser.STRING);
				}
				break;
			case 2:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 439;
				this.match(VelocitronPetriNetParser.AT);
				this.state = 440;
				this.name();
				this.state = 441;
				this.match(VelocitronPetriNetParser.DATA);
				this.state = 442;
				this.jsonValue();
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
	public arcPredicate(): ArcPredicateContext {
		let localctx: ArcPredicateContext = new ArcPredicateContext(this, this._ctx, this.state);
		this.enterRule(localctx, 76, VelocitronPetriNetParser.RULE_arcPredicate);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 446;
			this.match(VelocitronPetriNetParser.AT);
			this.state = 447;
			this.name();
			this.state = 448;
			this.match(VelocitronPetriNetParser.PREDICATE);
			this.state = 449;
			this.predicateKind();
			this.state = 450;
			this.match(VelocitronPetriNetParser.STRING);
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
	public arcCorrelate(): ArcCorrelateContext {
		let localctx: ArcCorrelateContext = new ArcCorrelateContext(this, this._ctx, this.state);
		this.enterRule(localctx, 78, VelocitronPetriNetParser.RULE_arcCorrelate);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 452;
			this.match(VelocitronPetriNetParser.AT);
			this.state = 453;
			this.name();
			this.state = 454;
			this.match(VelocitronPetriNetParser.CORRELATE);
			this.state = 455;
			this.match(VelocitronPetriNetParser.CEL);
			this.state = 456;
			this.match(VelocitronPetriNetParser.STRING);
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
	public predicateKind(): PredicateKindContext {
		let localctx: PredicateKindContext = new PredicateKindContext(this, this._ctx, this.state);
		this.enterRule(localctx, 80, VelocitronPetriNetParser.RULE_predicateKind);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 458;
			_la = this._input.LA(1);
			if(!(_la===12 || _la===25)) {
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
	public positiveInteger(): PositiveIntegerContext {
		let localctx: PositiveIntegerContext = new PositiveIntegerContext(this, this._ctx, this.state);
		this.enterRule(localctx, 82, VelocitronPetriNetParser.RULE_positiveInteger);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 460;
			this.match(VelocitronPetriNetParser.POSITIVE_INTEGER);
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
	public nonnegativeInteger(): NonnegativeIntegerContext {
		let localctx: NonnegativeIntegerContext = new NonnegativeIntegerContext(this, this._ctx, this.state);
		this.enterRule(localctx, 84, VelocitronPetriNetParser.RULE_nonnegativeInteger);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 462;
			_la = this._input.LA(1);
			if(!(_la===89 || _la===90)) {
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
	public initialMarking(): InitialMarkingContext {
		let localctx: InitialMarkingContext = new InitialMarkingContext(this, this._ctx, this.state);
		this.enterRule(localctx, 86, VelocitronPetriNetParser.RULE_initialMarking);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 464;
			this.match(VelocitronPetriNetParser.MARKING);
			this.state = 465;
			this.match(VelocitronPetriNetParser.INITIAL);
			this.state = 466;
			this.place();
			this.state = 467;
			this.match(VelocitronPetriNetParser.LEFT_ARROW);
			this.state = 468;
			this.markingValue();
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
	public additionalInitialMarking(): AdditionalInitialMarkingContext {
		let localctx: AdditionalInitialMarkingContext = new AdditionalInitialMarkingContext(this, this._ctx, this.state);
		this.enterRule(localctx, 88, VelocitronPetriNetParser.RULE_additionalInitialMarking);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 470;
			this.initialMarking();
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
	public namedMarking(): NamedMarkingContext {
		let localctx: NamedMarkingContext = new NamedMarkingContext(this, this._ctx, this.state);
		this.enterRule(localctx, 90, VelocitronPetriNetParser.RULE_namedMarking);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 472;
			this.match(VelocitronPetriNetParser.MARKING);
			this.state = 473;
			this.markingName();
			this.state = 474;
			this.place();
			this.state = 475;
			this.match(VelocitronPetriNetParser.LEFT_ARROW);
			this.state = 476;
			this.markingValue();
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
	public markingValue(): MarkingValueContext {
		let localctx: MarkingValueContext = new MarkingValueContext(this, this._ctx, this.state);
		this.enterRule(localctx, 92, VelocitronPetriNetParser.RULE_markingValue);
		let _la: number;
		try {
			this.state = 485;
			this._errHandler.sync(this);
			switch ( this._interp.adaptivePredict(this._input, 20, this._ctx) ) {
			case 1:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 481;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
				if (_la===89) {
					{
					this.state = 478;
					this.positiveInteger();
					this.state = 479;
					this.match(VelocitronPetriNetParser.STAR);
					}
				}

				this.state = 483;
				this.templateReference();
				}
				break;
			case 2:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 484;
				this.positiveInteger();
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
	public metadataDescription(): MetadataDescriptionContext {
		let localctx: MetadataDescriptionContext = new MetadataDescriptionContext(this, this._ctx, this.state);
		this.enterRule(localctx, 94, VelocitronPetriNetParser.RULE_metadataDescription);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 487;
			this.metadataTarget();
			this.state = 488;
			this.match(VelocitronPetriNetParser.DESCRIPTION);
			this.state = 489;
			this.match(VelocitronPetriNetParser.STRING);
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
	public metadataAnnotation(): MetadataAnnotationContext {
		let localctx: MetadataAnnotationContext = new MetadataAnnotationContext(this, this._ctx, this.state);
		this.enterRule(localctx, 96, VelocitronPetriNetParser.RULE_metadataAnnotation);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 491;
			this.metadataTarget();
			this.state = 492;
			this.match(VelocitronPetriNetParser.ANNOTATION);
			this.state = 493;
			this.name();
			this.state = 494;
			this.jsonValue();
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
	public metadataTarget(): MetadataTargetContext {
		let localctx: MetadataTargetContext = new MetadataTargetContext(this, this._ctx, this.state);
		this.enterRule(localctx, 98, VelocitronPetriNetParser.RULE_metadataTarget);
		try {
			this.state = 501;
			this._errHandler.sync(this);
			switch (this._input.LA(1)) {
			case 1:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 496;
				this.match(VelocitronPetriNetParser.NET);
				}
				break;
			case 72:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 497;
				this.place();
				}
				break;
			case 74:
				this.enterOuterAlt(localctx, 3);
				{
				this.state = 498;
				this.transition();
				}
				break;
			case 71:
				this.enterOuterAlt(localctx, 4);
				{
				this.state = 499;
				this.match(VelocitronPetriNetParser.AT);
				this.state = 500;
				this.name();
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
	public viewPosition(): ViewPositionContext {
		let localctx: ViewPositionContext = new ViewPositionContext(this, this._ctx, this.state);
		this.enterRule(localctx, 100, VelocitronPetriNetParser.RULE_viewPosition);
		try {
			this.state = 519;
			this._errHandler.sync(this);
			switch ( this._interp.adaptivePredict(this._input, 22, this._ctx) ) {
			case 1:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 503;
				this.match(VelocitronPetriNetParser.VIEW);
				this.state = 504;
				this.name();
				this.state = 505;
				this.match(VelocitronPetriNetParser.POSITION);
				this.state = 506;
				this.viewTarget();
				this.state = 507;
				this.match(VelocitronPetriNetParser.AT_KEYWORD);
				this.state = 508;
				this.jsonObject();
				}
				break;
			case 2:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 510;
				this.match(VelocitronPetriNetParser.VIEW);
				this.state = 511;
				this.name();
				this.state = 512;
				this.match(VelocitronPetriNetParser.POSITION);
				this.state = 513;
				this.viewTarget();
				this.state = 514;
				this.match(VelocitronPetriNetParser.RELATIVE);
				this.state = 515;
				this.viewTarget();
				this.state = 516;
				this.match(VelocitronPetriNetParser.PLUS);
				this.state = 517;
				this.jsonObject();
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
	public viewRoute(): ViewRouteContext {
		let localctx: ViewRouteContext = new ViewRouteContext(this, this._ctx, this.state);
		this.enterRule(localctx, 102, VelocitronPetriNetParser.RULE_viewRoute);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 521;
			this.match(VelocitronPetriNetParser.VIEW);
			this.state = 522;
			this.name();
			this.state = 523;
			this.match(VelocitronPetriNetParser.ROUTE);
			this.state = 524;
			this.match(VelocitronPetriNetParser.AT);
			this.state = 525;
			this.name();
			this.state = 526;
			this.match(VelocitronPetriNetParser.ORTHOGONAL);
			this.state = 527;
			this.jsonArray();
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
	public viewSplines(): ViewSplinesContext {
		let localctx: ViewSplinesContext = new ViewSplinesContext(this, this._ctx, this.state);
		this.enterRule(localctx, 104, VelocitronPetriNetParser.RULE_viewSplines);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 529;
			this.match(VelocitronPetriNetParser.VIEW);
			this.state = 530;
			this.name();
			this.state = 531;
			this.match(VelocitronPetriNetParser.SPLINES);
			this.state = 532;
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
	public viewDetail(): ViewDetailContext {
		let localctx: ViewDetailContext = new ViewDetailContext(this, this._ctx, this.state);
		this.enterRule(localctx, 106, VelocitronPetriNetParser.RULE_viewDetail);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 534;
			this.match(VelocitronPetriNetParser.VIEW);
			this.state = 535;
			this.name();
			this.state = 536;
			this.match(VelocitronPetriNetParser.DETAIL);
			this.state = 537;
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
	public viewFusion(): ViewFusionContext {
		let localctx: ViewFusionContext = new ViewFusionContext(this, this._ctx, this.state);
		this.enterRule(localctx, 108, VelocitronPetriNetParser.RULE_viewFusion);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 539;
			this.match(VelocitronPetriNetParser.VIEW);
			this.state = 540;
			this.name();
			this.state = 541;
			this.match(VelocitronPetriNetParser.FUSION);
			this.state = 542;
			this.place();
			this.state = 543;
			_la = this._input.LA(1);
			if(!(_la===50 || _la===51)) {
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
	public viewTarget(): ViewTargetContext {
		let localctx: ViewTargetContext = new ViewTargetContext(this, this._ctx, this.state);
		this.enterRule(localctx, 110, VelocitronPetriNetParser.RULE_viewTarget);
		let _la: number;
		try {
			this.state = 551;
			this._errHandler.sync(this);
			switch (this._input.LA(1)) {
			case 72:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 545;
				this.place();
				this.state = 548;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
				if (_la===71) {
					{
					this.state = 546;
					this.match(VelocitronPetriNetParser.AT);
					this.state = 547;
					this.transition();
					}
				}

				}
				break;
			case 74:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 550;
				this.transition();
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
	public decoration(): DecorationContext {
		let localctx: DecorationContext = new DecorationContext(this, this._ctx, this.state);
		this.enterRule(localctx, 112, VelocitronPetriNetParser.RULE_decoration);
		let _la: number;
		try {
			this.state = 596;
			this._errHandler.sync(this);
			switch ( this._interp.adaptivePredict(this._input, 29, this._ctx) ) {
			case 1:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 553;
				this.match(VelocitronPetriNetParser.DECORATE);
				this.state = 554;
				this.decorationTarget();
				this.state = 555;
				this.match(VelocitronPetriNetParser.HIGHLIGHT);
				this.state = 557;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
				if (_la===92) {
					{
					this.state = 556;
					this.match(VelocitronPetriNetParser.STRING);
					}
				}

				}
				break;
			case 2:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 559;
				this.match(VelocitronPetriNetParser.DECORATE);
				this.state = 560;
				this.decorationTarget();
				this.state = 561;
				this.match(VelocitronPetriNetParser.NOTE);
				this.state = 562;
				this.match(VelocitronPetriNetParser.STRING);
				}
				break;
			case 3:
				this.enterOuterAlt(localctx, 3);
				{
				this.state = 564;
				this.match(VelocitronPetriNetParser.DECORATE);
				this.state = 565;
				this.decorationTarget();
				this.state = 566;
				this.match(VelocitronPetriNetParser.SUMMARY);
				this.state = 567;
				this.match(VelocitronPetriNetParser.STRING);
				}
				break;
			case 4:
				this.enterOuterAlt(localctx, 4);
				{
				this.state = 569;
				this.match(VelocitronPetriNetParser.DECORATE);
				this.state = 570;
				this.decorationTarget();
				this.state = 571;
				this.match(VelocitronPetriNetParser.BESIDE);
				this.state = 573;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
				if (_la===52 || _la===53) {
					{
					this.state = 572;
					_la = this._input.LA(1);
					if(!(_la===52 || _la===53)) {
					this._errHandler.recoverInline(this);
					}
					else {
						this._errHandler.reportMatch(this);
					    this.consume();
					}
					}
				}

				this.state = 576;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
				if (_la===54) {
					{
					this.state = 575;
					this.match(VelocitronPetriNetParser.UNSHARED);
					}
				}

				}
				break;
			case 5:
				this.enterOuterAlt(localctx, 5);
				{
				this.state = 578;
				this.match(VelocitronPetriNetParser.DECORATE);
				this.state = 579;
				this.decorationTarget();
				this.state = 580;
				this.match(VelocitronPetriNetParser.SINGLE);
				}
				break;
			case 6:
				this.enterOuterAlt(localctx, 6);
				{
				this.state = 582;
				this.match(VelocitronPetriNetParser.DECORATE);
				this.state = 583;
				this.match(VelocitronPetriNetParser.COLOR_KEYWORD);
				this.state = 584;
				this.color();
				this.state = 585;
				this.match(VelocitronPetriNetParser.QUIET);
				}
				break;
			case 7:
				this.enterOuterAlt(localctx, 7);
				{
				this.state = 587;
				this.match(VelocitronPetriNetParser.DECORATE);
				this.state = 588;
				this.match(VelocitronPetriNetParser.COLOR_KEYWORD);
				this.state = 589;
				this.color();
				this.state = 590;
				this.match(VelocitronPetriNetParser.SHOW);
				this.state = 592;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
				do {
					{
					{
					this.state = 591;
					this.match(VelocitronPetriNetParser.STRING);
					}
					}
					this.state = 594;
					this._errHandler.sync(this);
					_la = this._input.LA(1);
				} while (_la===92);
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
	public decorationTarget(): DecorationTargetContext {
		let localctx: DecorationTargetContext = new DecorationTargetContext(this, this._ctx, this.state);
		this.enterRule(localctx, 114, VelocitronPetriNetParser.RULE_decorationTarget);
		try {
			this.state = 602;
			this._errHandler.sync(this);
			switch (this._input.LA(1)) {
			case 72:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 598;
				this.place();
				}
				break;
			case 74:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 599;
				this.transition();
				}
				break;
			case 71:
				this.enterOuterAlt(localctx, 3);
				{
				this.state = 600;
				this.match(VelocitronPetriNetParser.AT);
				this.state = 601;
				this.name();
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
	public extensions(): ExtensionsContext {
		let localctx: ExtensionsContext = new ExtensionsContext(this, this._ctx, this.state);
		this.enterRule(localctx, 116, VelocitronPetriNetParser.RULE_extensions);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 604;
			this.match(VelocitronPetriNetParser.EXTENSIONS);
			this.state = 605;
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
	public domainDeclaration(): DomainDeclarationContext {
		let localctx: DomainDeclarationContext = new DomainDeclarationContext(this, this._ctx, this.state);
		this.enterRule(localctx, 118, VelocitronPetriNetParser.RULE_domainDeclaration);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 607;
			this.match(VelocitronPetriNetParser.DOMAIN);
			this.state = 608;
			this.color();
			this.state = 609;
			this.match(VelocitronPetriNetParser.DOT);
			this.state = 610;
			this.fieldPath();
			this.state = 612;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			do {
				{
				{
				this.state = 611;
				this.domainValue();
				}
				}
				this.state = 614;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
			} while (((((_la - 68)) & ~0x1F) === 0 && ((1 << (_la - 68)) & 31457283) !== 0));
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
		this.enterRule(localctx, 120, VelocitronPetriNetParser.RULE_fieldPath);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 616;
			this.name();
			this.state = 621;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			while (_la===87) {
				{
				{
				this.state = 617;
				this.match(VelocitronPetriNetParser.DOT);
				this.state = 618;
				this.name();
				}
				}
				this.state = 623;
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
	public domainValue(): DomainValueContext {
		let localctx: DomainValueContext = new DomainValueContext(this, this._ctx, this.state);
		this.enterRule(localctx, 122, VelocitronPetriNetParser.RULE_domainValue);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 624;
			_la = this._input.LA(1);
			if(!(((((_la - 68)) & ~0x1F) === 0 && ((1 << (_la - 68)) & 31457283) !== 0))) {
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
	public finalDeclaration(): FinalDeclarationContext {
		let localctx: FinalDeclarationContext = new FinalDeclarationContext(this, this._ctx, this.state);
		this.enterRule(localctx, 124, VelocitronPetriNetParser.RULE_finalDeclaration);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 626;
			this.match(VelocitronPetriNetParser.FINAL);
			this.state = 627;
			this.finalMarking();
			this.state = 632;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			while (_la===86) {
				{
				{
				this.state = 628;
				this.match(VelocitronPetriNetParser.COMMA);
				this.state = 629;
				this.finalMarking();
				}
				}
				this.state = 634;
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
	public finalMarking(): FinalMarkingContext {
		let localctx: FinalMarkingContext = new FinalMarkingContext(this, this._ctx, this.state);
		this.enterRule(localctx, 126, VelocitronPetriNetParser.RULE_finalMarking);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 635;
			this.place();
			this.state = 640;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			while (_la===37) {
				{
				{
				this.state = 636;
				this.match(VelocitronPetriNetParser.PLUS);
				this.state = 637;
				this.place();
				}
				}
				this.state = 642;
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
	public invariantDeclaration(): InvariantDeclarationContext {
		let localctx: InvariantDeclarationContext = new InvariantDeclarationContext(this, this._ctx, this.state);
		this.enterRule(localctx, 128, VelocitronPetriNetParser.RULE_invariantDeclaration);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 643;
			this.match(VelocitronPetriNetParser.INVARIANT);
			this.state = 645;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if (_la===92) {
				{
				this.state = 644;
				this.match(VelocitronPetriNetParser.STRING);
				}
			}

			this.state = 647;
			this.invariantTerm();
			this.state = 652;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			while (_la===37) {
				{
				{
				this.state = 648;
				this.match(VelocitronPetriNetParser.PLUS);
				this.state = 649;
				this.invariantTerm();
				}
				}
				this.state = 654;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
			}
			this.state = 657;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if (_la===38) {
				{
				this.state = 655;
				this.match(VelocitronPetriNetParser.EQUALS);
				this.state = 656;
				this.nonnegativeInteger();
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
	public invariantTerm(): InvariantTermContext {
		let localctx: InvariantTermContext = new InvariantTermContext(this, this._ctx, this.state);
		this.enterRule(localctx, 130, VelocitronPetriNetParser.RULE_invariantTerm);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 662;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if (_la===89) {
				{
				this.state = 659;
				this.positiveInteger();
				this.state = 660;
				this.match(VelocitronPetriNetParser.STAR);
				}
			}

			this.state = 664;
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
	public actorAssignment(): ActorAssignmentContext {
		let localctx: ActorAssignmentContext = new ActorAssignmentContext(this, this._ctx, this.state);
		this.enterRule(localctx, 132, VelocitronPetriNetParser.RULE_actorAssignment);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 666;
			this.actorTarget();
			this.state = 667;
			this.match(VelocitronPetriNetParser.ACTOR);
			this.state = 668;
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
	public actorTarget(): ActorTargetContext {
		let localctx: ActorTargetContext = new ActorTargetContext(this, this._ctx, this.state);
		this.enterRule(localctx, 134, VelocitronPetriNetParser.RULE_actorTarget);
		try {
			this.state = 673;
			this._errHandler.sync(this);
			switch (this._input.LA(1)) {
			case 1:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 670;
				this.match(VelocitronPetriNetParser.NET);
				}
				break;
			case 72:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 671;
				this.place();
				}
				break;
			case 74:
				this.enterOuterAlt(localctx, 3);
				{
				this.state = 672;
				this.transition();
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
	public actorDeclaration(): ActorDeclarationContext {
		let localctx: ActorDeclarationContext = new ActorDeclarationContext(this, this._ctx, this.state);
		this.enterRule(localctx, 136, VelocitronPetriNetParser.RULE_actorDeclaration);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 675;
			_la = this._input.LA(1);
			if(!(((((_la - 60)) & ~0x1F) === 0 && ((1 << (_la - 60)) & 7) !== 0))) {
			this._errHandler.recoverInline(this);
			}
			else {
				this._errHandler.reportMatch(this);
			    this.consume();
			}
			this.state = 676;
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
	public placeLives(): PlaceLivesContext {
		let localctx: PlaceLivesContext = new PlaceLivesContext(this, this._ctx, this.state);
		this.enterRule(localctx, 138, VelocitronPetriNetParser.RULE_placeLives);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 678;
			this.place();
			this.state = 679;
			this.match(VelocitronPetriNetParser.LIVES);
			this.state = 680;
			this.match(VelocitronPetriNetParser.IN);
			this.state = 684;
			this._errHandler.sync(this);
			switch ( this._interp.adaptivePredict(this._input, 40, this._ctx) ) {
			case 1:
				{
				this.state = 681;
				this.match(VelocitronPetriNetParser.CEL);
				this.state = 682;
				this.match(VelocitronPetriNetParser.STRING);
				}
				break;
			case 2:
				{
				this.state = 683;
				this.name();
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
	public placeReadsAs(): PlaceReadsAsContext {
		let localctx: PlaceReadsAsContext = new PlaceReadsAsContext(this, this._ctx, this.state);
		this.enterRule(localctx, 140, VelocitronPetriNetParser.RULE_placeReadsAs);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 686;
			this.place();
			this.state = 687;
			this.match(VelocitronPetriNetParser.READS);
			this.state = 688;
			this.match(VelocitronPetriNetParser.AS);
			this.state = 689;
			this.match(VelocitronPetriNetParser.CEL);
			this.state = 690;
			this.match(VelocitronPetriNetParser.STRING);
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
	public placeKept(): PlaceKeptContext {
		let localctx: PlaceKeptContext = new PlaceKeptContext(this, this._ctx, this.state);
		this.enterRule(localctx, 142, VelocitronPetriNetParser.RULE_placeKept);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 692;
			this.place();
			this.state = 693;
			this.match(VelocitronPetriNetParser.KEPT);
			this.state = 694;
			this.match(VelocitronPetriNetParser.BY);
			this.state = 695;
			this.name();
			this.state = 696;
			this.match(VelocitronPetriNetParser.STARTS);
			this.state = 697;
			this.match(VelocitronPetriNetParser.AS);
			this.state = 698;
			this.match(VelocitronPetriNetParser.CEL);
			this.state = 699;
			this.match(VelocitronPetriNetParser.STRING);
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
	public templateDefinition(): TemplateDefinitionContext {
		let localctx: TemplateDefinitionContext = new TemplateDefinitionContext(this, this._ctx, this.state);
		this.enterRule(localctx, 144, VelocitronPetriNetParser.RULE_templateDefinition);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 701;
			this.templateReference();
			this.state = 702;
			this.match(VelocitronPetriNetParser.COLON);
			this.state = 703;
			this.color();
			this.state = 704;
			this.jsonValue();
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
	public additionalTemplateDefinition(): AdditionalTemplateDefinitionContext {
		let localctx: AdditionalTemplateDefinitionContext = new AdditionalTemplateDefinitionContext(this, this._ctx, this.state);
		this.enterRule(localctx, 146, VelocitronPetriNetParser.RULE_additionalTemplateDefinition);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 706;
			this.templateDefinition();
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
	public templateReference(): TemplateReferenceContext {
		let localctx: TemplateReferenceContext = new TemplateReferenceContext(this, this._ctx, this.state);
		this.enterRule(localctx, 148, VelocitronPetriNetParser.RULE_templateReference);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 708;
			this.match(VelocitronPetriNetParser.DOLLAR);
			this.state = 709;
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
	public color(): ColorContext {
		let localctx: ColorContext = new ColorContext(this, this._ctx, this.state);
		this.enterRule(localctx, 150, VelocitronPetriNetParser.RULE_color);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 711;
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
	public name(): NameContext {
		let localctx: NameContext = new NameContext(this, this._ctx, this.state);
		this.enterRule(localctx, 152, VelocitronPetriNetParser.RULE_name);
		try {
			this.state = 717;
			this._errHandler.sync(this);
			switch (this._input.LA(1)) {
			case 93:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 713;
				this.match(VelocitronPetriNetParser.IDENT);
				}
				break;
			case 92:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 714;
				this.match(VelocitronPetriNetParser.STRING);
				}
				break;
			case 28:
				this.enterOuterAlt(localctx, 3);
				{
				this.state = 715;
				this.match(VelocitronPetriNetParser.INITIAL);
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
			case 29:
			case 30:
			case 31:
			case 32:
			case 33:
			case 34:
			case 35:
			case 36:
			case 39:
			case 40:
			case 41:
			case 42:
			case 43:
			case 44:
			case 45:
			case 46:
			case 47:
			case 48:
			case 49:
			case 50:
			case 51:
			case 52:
			case 53:
			case 54:
			case 55:
			case 56:
			case 57:
			case 58:
			case 59:
			case 60:
			case 61:
			case 62:
			case 63:
			case 64:
			case 65:
			case 66:
			case 67:
				this.enterOuterAlt(localctx, 4);
				{
				this.state = 716;
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
	public markingName(): MarkingNameContext {
		let localctx: MarkingNameContext = new MarkingNameContext(this, this._ctx, this.state);
		this.enterRule(localctx, 154, VelocitronPetriNetParser.RULE_markingName);
		try {
			this.state = 722;
			this._errHandler.sync(this);
			switch (this._input.LA(1)) {
			case 93:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 719;
				this.match(VelocitronPetriNetParser.IDENT);
				}
				break;
			case 92:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 720;
				this.match(VelocitronPetriNetParser.STRING);
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
			case 29:
			case 30:
			case 31:
			case 32:
			case 33:
			case 34:
			case 35:
			case 36:
			case 39:
			case 40:
			case 41:
			case 42:
			case 43:
			case 44:
			case 45:
			case 46:
			case 47:
			case 48:
			case 49:
			case 50:
			case 51:
			case 52:
			case 53:
			case 54:
			case 55:
			case 56:
			case 57:
			case 58:
			case 59:
			case 60:
			case 61:
			case 62:
			case 63:
			case 64:
			case 65:
			case 66:
			case 67:
				this.enterOuterAlt(localctx, 3);
				{
				this.state = 721;
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
	public keyword(): KeywordContext {
		let localctx: KeywordContext = new KeywordContext(this, this._ctx, this.state);
		this.enterRule(localctx, 156, VelocitronPetriNetParser.RULE_keyword);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 724;
			_la = this._input.LA(1);
			if(!((((_la) & ~0x1F) === 0 && ((1 << _la) & 4026531838) !== 0) || ((((_la - 32)) & ~0x1F) === 0 && ((1 << (_la - 32)) & 4294967199) !== 0) || ((((_la - 64)) & ~0x1F) === 0 && ((1 << (_la - 64)) & 15) !== 0))) {
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
		this.enterRule(localctx, 158, VelocitronPetriNetParser.RULE_jsonValue);
		try {
			this.state = 735;
			this._errHandler.sync(this);
			switch (this._input.LA(1)) {
			case 76:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 726;
				this.jsonObject();
				}
				break;
			case 74:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 727;
				this.jsonArray();
				}
				break;
			case 92:
				this.enterOuterAlt(localctx, 3);
				{
				this.state = 728;
				this.match(VelocitronPetriNetParser.STRING);
				}
				break;
			case 91:
				this.enterOuterAlt(localctx, 4);
				{
				this.state = 729;
				this.match(VelocitronPetriNetParser.NUMBER);
				}
				break;
			case 89:
				this.enterOuterAlt(localctx, 5);
				{
				this.state = 730;
				this.match(VelocitronPetriNetParser.POSITIVE_INTEGER);
				}
				break;
			case 90:
				this.enterOuterAlt(localctx, 6);
				{
				this.state = 731;
				this.match(VelocitronPetriNetParser.ZERO);
				}
				break;
			case 68:
				this.enterOuterAlt(localctx, 7);
				{
				this.state = 732;
				this.match(VelocitronPetriNetParser.TRUE);
				}
				break;
			case 69:
				this.enterOuterAlt(localctx, 8);
				{
				this.state = 733;
				this.match(VelocitronPetriNetParser.FALSE);
				}
				break;
			case 70:
				this.enterOuterAlt(localctx, 9);
				{
				this.state = 734;
				this.match(VelocitronPetriNetParser.NULL);
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
		this.enterRule(localctx, 160, VelocitronPetriNetParser.RULE_jsonObject);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 737;
			this.match(VelocitronPetriNetParser.LBRACE);
			this.state = 750;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if (_la===92) {
				{
				this.state = 738;
				this.match(VelocitronPetriNetParser.STRING);
				this.state = 739;
				this.match(VelocitronPetriNetParser.COLON);
				this.state = 740;
				this.jsonValue();
				this.state = 747;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
				while (_la===86) {
					{
					{
					this.state = 741;
					this.match(VelocitronPetriNetParser.COMMA);
					this.state = 742;
					this.match(VelocitronPetriNetParser.STRING);
					this.state = 743;
					this.match(VelocitronPetriNetParser.COLON);
					this.state = 744;
					this.jsonValue();
					}
					}
					this.state = 749;
					this._errHandler.sync(this);
					_la = this._input.LA(1);
				}
				}
			}

			this.state = 752;
			this.match(VelocitronPetriNetParser.RBRACE);
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
		this.enterRule(localctx, 162, VelocitronPetriNetParser.RULE_jsonArray);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 754;
			this.match(VelocitronPetriNetParser.LBRACK);
			this.state = 763;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if (((((_la - 68)) & ~0x1F) === 0 && ((1 << (_la - 68)) & 31457607) !== 0)) {
				{
				this.state = 755;
				this.jsonValue();
				this.state = 760;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
				while (_la===86) {
					{
					{
					this.state = 756;
					this.match(VelocitronPetriNetParser.COMMA);
					this.state = 757;
					this.jsonValue();
					}
					}
					this.state = 762;
					this._errHandler.sync(this);
					_la = this._input.LA(1);
				}
				}
			}

			this.state = 765;
			this.match(VelocitronPetriNetParser.RBRACK);
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

	public static readonly _serializedATN: number[] = [4,1,98,768,2,0,7,0,2,
	1,7,1,2,2,7,2,2,3,7,3,2,4,7,4,2,5,7,5,2,6,7,6,2,7,7,7,2,8,7,8,2,9,7,9,2,
	10,7,10,2,11,7,11,2,12,7,12,2,13,7,13,2,14,7,14,2,15,7,15,2,16,7,16,2,17,
	7,17,2,18,7,18,2,19,7,19,2,20,7,20,2,21,7,21,2,22,7,22,2,23,7,23,2,24,7,
	24,2,25,7,25,2,26,7,26,2,27,7,27,2,28,7,28,2,29,7,29,2,30,7,30,2,31,7,31,
	2,32,7,32,2,33,7,33,2,34,7,34,2,35,7,35,2,36,7,36,2,37,7,37,2,38,7,38,2,
	39,7,39,2,40,7,40,2,41,7,41,2,42,7,42,2,43,7,43,2,44,7,44,2,45,7,45,2,46,
	7,46,2,47,7,47,2,48,7,48,2,49,7,49,2,50,7,50,2,51,7,51,2,52,7,52,2,53,7,
	53,2,54,7,54,2,55,7,55,2,56,7,56,2,57,7,57,2,58,7,58,2,59,7,59,2,60,7,60,
	2,61,7,61,2,62,7,62,2,63,7,63,2,64,7,64,2,65,7,65,2,66,7,66,2,67,7,67,2,
	68,7,68,2,69,7,69,2,70,7,70,2,71,7,71,2,72,7,72,2,73,7,73,2,74,7,74,2,75,
	7,75,2,76,7,76,2,77,7,77,2,78,7,78,2,79,7,79,2,80,7,80,2,81,7,81,1,0,3,
	0,166,8,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,
	0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,
	0,1,0,1,0,1,0,1,0,1,0,5,0,207,8,0,10,0,12,0,210,9,0,1,0,1,0,1,0,1,0,1,0,
	1,0,1,0,5,0,219,8,0,10,0,12,0,222,9,0,1,0,1,0,3,0,226,8,0,1,1,1,1,1,1,3,
	1,231,8,1,1,2,1,2,1,2,1,3,1,3,1,3,1,3,1,3,1,4,1,4,1,4,1,4,1,4,1,4,1,4,1,
	4,1,4,1,5,1,5,1,5,1,5,1,5,1,5,1,5,1,5,4,5,258,8,5,11,5,12,5,259,1,6,1,6,
	1,6,1,6,1,6,1,6,1,6,1,7,1,7,1,7,1,7,5,7,273,8,7,10,7,12,7,276,9,7,1,8,1,
	8,1,8,1,8,1,8,1,8,1,8,5,8,285,8,8,10,8,12,8,288,9,8,1,9,1,9,1,9,1,9,5,9,
	294,8,9,10,9,12,9,297,9,9,1,9,1,9,1,10,1,10,1,10,1,10,5,10,305,8,10,10,
	10,12,10,308,9,10,1,10,1,10,1,11,3,11,313,8,11,1,11,1,11,1,11,1,11,4,11,
	319,8,11,11,11,12,11,320,1,12,1,12,3,12,325,8,12,1,13,1,13,3,13,329,8,13,
	1,13,1,13,1,14,1,14,1,15,1,15,1,16,1,16,1,16,1,16,1,17,1,17,1,17,1,17,1,
	18,1,18,1,18,1,18,1,19,1,19,1,20,1,20,1,21,1,21,1,21,1,21,1,21,1,22,1,22,
	1,23,1,23,1,23,1,23,1,24,1,24,1,25,1,25,1,25,1,25,1,26,1,26,1,26,1,26,1,
	26,1,26,1,26,1,27,1,27,1,27,1,27,1,27,1,27,1,28,1,28,1,28,1,28,1,28,1,28,
	1,29,1,29,1,29,1,29,1,29,1,30,1,30,1,30,3,30,397,8,30,1,31,1,31,1,31,1,
	31,1,32,1,32,1,32,1,32,1,33,1,33,1,33,1,33,1,33,1,34,1,34,1,34,1,34,1,34,
	1,34,5,34,418,8,34,10,34,12,34,421,9,34,1,34,1,34,1,35,1,35,1,35,1,35,1,
	36,1,36,1,36,1,36,1,36,1,37,1,37,1,37,1,37,1,37,1,37,1,37,1,37,1,37,1,37,
	1,37,3,37,445,8,37,1,38,1,38,1,38,1,38,1,38,1,38,1,39,1,39,1,39,1,39,1,
	39,1,39,1,40,1,40,1,41,1,41,1,42,1,42,1,43,1,43,1,43,1,43,1,43,1,43,1,44,
	1,44,1,45,1,45,1,45,1,45,1,45,1,45,1,46,1,46,1,46,3,46,482,8,46,1,46,1,
	46,3,46,486,8,46,1,47,1,47,1,47,1,47,1,48,1,48,1,48,1,48,1,48,1,49,1,49,
	1,49,1,49,1,49,3,49,502,8,49,1,50,1,50,1,50,1,50,1,50,1,50,1,50,1,50,1,
	50,1,50,1,50,1,50,1,50,1,50,1,50,1,50,3,50,520,8,50,1,51,1,51,1,51,1,51,
	1,51,1,51,1,51,1,51,1,52,1,52,1,52,1,52,1,52,1,53,1,53,1,53,1,53,1,53,1,
	54,1,54,1,54,1,54,1,54,1,54,1,55,1,55,1,55,3,55,549,8,55,1,55,3,55,552,
	8,55,1,56,1,56,1,56,1,56,3,56,558,8,56,1,56,1,56,1,56,1,56,1,56,1,56,1,
	56,1,56,1,56,1,56,1,56,1,56,1,56,1,56,3,56,574,8,56,1,56,3,56,577,8,56,
	1,56,1,56,1,56,1,56,1,56,1,56,1,56,1,56,1,56,1,56,1,56,1,56,1,56,1,56,4,
	56,593,8,56,11,56,12,56,594,3,56,597,8,56,1,57,1,57,1,57,1,57,3,57,603,
	8,57,1,58,1,58,1,58,1,59,1,59,1,59,1,59,1,59,4,59,613,8,59,11,59,12,59,
	614,1,60,1,60,1,60,5,60,620,8,60,10,60,12,60,623,9,60,1,61,1,61,1,62,1,
	62,1,62,1,62,5,62,631,8,62,10,62,12,62,634,9,62,1,63,1,63,1,63,5,63,639,
	8,63,10,63,12,63,642,9,63,1,64,1,64,3,64,646,8,64,1,64,1,64,1,64,5,64,651,
	8,64,10,64,12,64,654,9,64,1,64,1,64,3,64,658,8,64,1,65,1,65,1,65,3,65,663,
	8,65,1,65,1,65,1,66,1,66,1,66,1,66,1,67,1,67,1,67,3,67,674,8,67,1,68,1,
	68,1,68,1,69,1,69,1,69,1,69,1,69,1,69,3,69,685,8,69,1,70,1,70,1,70,1,70,
	1,70,1,70,1,71,1,71,1,71,1,71,1,71,1,71,1,71,1,71,1,71,1,72,1,72,1,72,1,
	72,1,72,1,73,1,73,1,74,1,74,1,74,1,75,1,75,1,76,1,76,1,76,1,76,3,76,718,
	8,76,1,77,1,77,1,77,3,77,723,8,77,1,78,1,78,1,79,1,79,1,79,1,79,1,79,1,
	79,1,79,1,79,1,79,3,79,736,8,79,1,80,1,80,1,80,1,80,1,80,1,80,1,80,1,80,
	5,80,746,8,80,10,80,12,80,749,9,80,3,80,751,8,80,1,80,1,80,1,81,1,81,1,
	81,1,81,5,81,759,8,81,10,81,12,81,762,9,81,3,81,764,8,81,1,81,1,81,1,81,
	0,0,82,0,2,4,6,8,10,12,14,16,18,20,22,24,26,28,30,32,34,36,38,40,42,44,
	46,48,50,52,54,56,58,60,62,64,66,68,70,72,74,76,78,80,82,84,86,88,90,92,
	94,96,98,100,102,104,106,108,110,112,114,116,118,120,122,124,126,128,130,
	132,134,136,138,140,142,144,146,148,150,152,154,156,158,160,162,0,9,1,0,
	79,81,1,0,10,11,2,0,12,12,25,25,1,0,89,90,1,0,50,51,1,0,52,53,2,0,68,69,
	89,92,1,0,60,62,3,0,1,27,29,36,39,67,793,0,225,1,0,0,0,2,227,1,0,0,0,4,
	232,1,0,0,0,6,235,1,0,0,0,8,240,1,0,0,0,10,249,1,0,0,0,12,261,1,0,0,0,14,
	268,1,0,0,0,16,277,1,0,0,0,18,289,1,0,0,0,20,300,1,0,0,0,22,312,1,0,0,0,
	24,324,1,0,0,0,26,328,1,0,0,0,28,332,1,0,0,0,30,334,1,0,0,0,32,336,1,0,
	0,0,34,340,1,0,0,0,36,344,1,0,0,0,38,348,1,0,0,0,40,350,1,0,0,0,42,352,
	1,0,0,0,44,357,1,0,0,0,46,359,1,0,0,0,48,363,1,0,0,0,50,365,1,0,0,0,52,
	369,1,0,0,0,54,376,1,0,0,0,56,382,1,0,0,0,58,388,1,0,0,0,60,396,1,0,0,0,
	62,398,1,0,0,0,64,402,1,0,0,0,66,406,1,0,0,0,68,411,1,0,0,0,70,424,1,0,
	0,0,72,428,1,0,0,0,74,444,1,0,0,0,76,446,1,0,0,0,78,452,1,0,0,0,80,458,
	1,0,0,0,82,460,1,0,0,0,84,462,1,0,0,0,86,464,1,0,0,0,88,470,1,0,0,0,90,
	472,1,0,0,0,92,485,1,0,0,0,94,487,1,0,0,0,96,491,1,0,0,0,98,501,1,0,0,0,
	100,519,1,0,0,0,102,521,1,0,0,0,104,529,1,0,0,0,106,534,1,0,0,0,108,539,
	1,0,0,0,110,551,1,0,0,0,112,596,1,0,0,0,114,602,1,0,0,0,116,604,1,0,0,0,
	118,607,1,0,0,0,120,616,1,0,0,0,122,624,1,0,0,0,124,626,1,0,0,0,126,635,
	1,0,0,0,128,643,1,0,0,0,130,662,1,0,0,0,132,666,1,0,0,0,134,673,1,0,0,0,
	136,675,1,0,0,0,138,678,1,0,0,0,140,686,1,0,0,0,142,692,1,0,0,0,144,701,
	1,0,0,0,146,706,1,0,0,0,148,708,1,0,0,0,150,711,1,0,0,0,152,717,1,0,0,0,
	154,722,1,0,0,0,156,724,1,0,0,0,158,735,1,0,0,0,160,737,1,0,0,0,162,754,
	1,0,0,0,164,166,3,2,1,0,165,164,1,0,0,0,165,166,1,0,0,0,166,208,1,0,0,0,
	167,207,3,22,11,0,168,207,3,38,19,0,169,207,3,40,20,0,170,207,3,46,23,0,
	171,207,3,50,25,0,172,207,3,52,26,0,173,207,3,54,27,0,174,207,3,56,28,0,
	175,207,3,58,29,0,176,207,3,62,31,0,177,207,3,64,32,0,178,207,3,66,33,0,
	179,207,3,42,21,0,180,207,3,68,34,0,181,207,3,70,35,0,182,207,3,72,36,0,
	183,207,3,74,37,0,184,207,3,76,38,0,185,207,3,78,39,0,186,207,3,86,43,0,
	187,207,3,144,72,0,188,207,3,90,45,0,189,207,3,94,47,0,190,207,3,96,48,
	0,191,207,3,100,50,0,192,207,3,102,51,0,193,207,3,104,52,0,194,207,3,106,
	53,0,195,207,3,108,54,0,196,207,3,112,56,0,197,207,3,116,58,0,198,207,3,
	118,59,0,199,207,3,124,62,0,200,207,3,128,64,0,201,207,3,132,66,0,202,207,
	3,136,68,0,203,207,3,138,69,0,204,207,3,140,70,0,205,207,3,142,71,0,206,
	167,1,0,0,0,206,168,1,0,0,0,206,169,1,0,0,0,206,170,1,0,0,0,206,171,1,0,
	0,0,206,172,1,0,0,0,206,173,1,0,0,0,206,174,1,0,0,0,206,175,1,0,0,0,206,
	176,1,0,0,0,206,177,1,0,0,0,206,178,1,0,0,0,206,179,1,0,0,0,206,180,1,0,
	0,0,206,181,1,0,0,0,206,182,1,0,0,0,206,183,1,0,0,0,206,184,1,0,0,0,206,
	185,1,0,0,0,206,186,1,0,0,0,206,187,1,0,0,0,206,188,1,0,0,0,206,189,1,0,
	0,0,206,190,1,0,0,0,206,191,1,0,0,0,206,192,1,0,0,0,206,193,1,0,0,0,206,
	194,1,0,0,0,206,195,1,0,0,0,206,196,1,0,0,0,206,197,1,0,0,0,206,198,1,0,
	0,0,206,199,1,0,0,0,206,200,1,0,0,0,206,201,1,0,0,0,206,202,1,0,0,0,206,
	203,1,0,0,0,206,204,1,0,0,0,206,205,1,0,0,0,207,210,1,0,0,0,208,206,1,0,
	0,0,208,209,1,0,0,0,209,211,1,0,0,0,210,208,1,0,0,0,211,226,5,0,0,1,212,
	220,3,4,2,0,213,219,3,6,3,0,214,219,3,8,4,0,215,219,3,10,5,0,216,219,3,
	12,6,0,217,219,3,14,7,0,218,213,1,0,0,0,218,214,1,0,0,0,218,215,1,0,0,0,
	218,216,1,0,0,0,218,217,1,0,0,0,219,222,1,0,0,0,220,218,1,0,0,0,220,221,
	1,0,0,0,221,223,1,0,0,0,222,220,1,0,0,0,223,224,5,0,0,1,224,226,1,0,0,0,
	225,165,1,0,0,0,225,212,1,0,0,0,226,1,1,0,0,0,227,228,5,1,0,0,228,230,3,
	152,76,0,229,231,5,92,0,0,230,229,1,0,0,0,230,231,1,0,0,0,231,3,1,0,0,0,
	232,233,5,2,0,0,233,234,3,152,76,0,234,5,1,0,0,0,235,236,5,3,0,0,236,237,
	5,92,0,0,237,238,5,4,0,0,238,239,5,93,0,0,239,7,1,0,0,0,240,241,5,5,0,0,
	241,242,5,93,0,0,242,243,5,87,0,0,243,244,3,18,9,0,244,245,5,81,0,0,245,
	246,5,93,0,0,246,247,5,87,0,0,247,248,3,18,9,0,248,9,1,0,0,0,249,250,5,
	6,0,0,250,251,5,93,0,0,251,252,5,87,0,0,252,257,3,18,9,0,253,254,5,88,0,
	0,254,255,5,93,0,0,255,256,5,87,0,0,256,258,3,18,9,0,257,253,1,0,0,0,258,
	259,1,0,0,0,259,257,1,0,0,0,259,260,1,0,0,0,260,11,1,0,0,0,261,262,5,7,
	0,0,262,263,5,93,0,0,263,264,5,87,0,0,264,265,3,20,10,0,265,266,5,8,0,0,
	266,267,5,93,0,0,267,13,1,0,0,0,268,269,5,57,0,0,269,274,3,16,8,0,270,271,
	5,86,0,0,271,273,3,16,8,0,272,270,1,0,0,0,273,276,1,0,0,0,274,272,1,0,0,
	0,274,275,1,0,0,0,275,15,1,0,0,0,276,274,1,0,0,0,277,278,5,93,0,0,278,279,
	5,87,0,0,279,286,3,18,9,0,280,281,5,37,0,0,281,282,5,93,0,0,282,283,5,87,
	0,0,283,285,3,18,9,0,284,280,1,0,0,0,285,288,1,0,0,0,286,284,1,0,0,0,286,
	287,1,0,0,0,287,17,1,0,0,0,288,286,1,0,0,0,289,290,5,72,0,0,290,295,3,152,
	76,0,291,292,5,87,0,0,292,294,3,152,76,0,293,291,1,0,0,0,294,297,1,0,0,
	0,295,293,1,0,0,0,295,296,1,0,0,0,296,298,1,0,0,0,297,295,1,0,0,0,298,299,
	5,73,0,0,299,19,1,0,0,0,300,301,5,74,0,0,301,306,3,152,76,0,302,303,5,87,
	0,0,303,305,3,152,76,0,304,302,1,0,0,0,305,308,1,0,0,0,306,304,1,0,0,0,
	306,307,1,0,0,0,307,309,1,0,0,0,308,306,1,0,0,0,309,310,5,75,0,0,310,21,
	1,0,0,0,311,313,3,32,16,0,312,311,1,0,0,0,312,313,1,0,0,0,313,314,1,0,0,
	0,314,318,3,24,12,0,315,316,3,26,13,0,316,317,3,24,12,0,317,319,1,0,0,0,
	318,315,1,0,0,0,319,320,1,0,0,0,320,318,1,0,0,0,320,321,1,0,0,0,321,23,
	1,0,0,0,322,325,3,34,17,0,323,325,3,36,18,0,324,322,1,0,0,0,324,323,1,0,
	0,0,325,25,1,0,0,0,326,327,5,78,0,0,327,329,3,150,75,0,328,326,1,0,0,0,
	328,329,1,0,0,0,329,330,1,0,0,0,330,331,3,28,14,0,331,27,1,0,0,0,332,333,
	7,0,0,0,333,29,1,0,0,0,334,335,3,22,11,0,335,31,1,0,0,0,336,337,5,71,0,
	0,337,338,3,152,76,0,338,339,5,85,0,0,339,33,1,0,0,0,340,341,5,72,0,0,341,
	342,3,152,76,0,342,343,5,73,0,0,343,35,1,0,0,0,344,345,5,74,0,0,345,346,
	3,152,76,0,346,347,5,75,0,0,347,37,1,0,0,0,348,349,3,34,17,0,349,39,1,0,
	0,0,350,351,3,36,18,0,351,41,1,0,0,0,352,353,3,34,17,0,353,354,5,9,0,0,
	354,355,3,44,22,0,355,356,3,150,75,0,356,43,1,0,0,0,357,358,7,1,0,0,358,
	45,1,0,0,0,359,360,3,36,18,0,360,361,5,12,0,0,361,362,5,92,0,0,362,47,1,
	0,0,0,363,364,3,46,23,0,364,49,1,0,0,0,365,366,3,36,18,0,366,367,5,13,0,
	0,367,368,5,92,0,0,368,51,1,0,0,0,369,370,3,36,18,0,370,371,5,15,0,0,371,
	372,5,16,0,0,372,373,3,34,17,0,373,374,5,25,0,0,374,375,5,92,0,0,375,53,
	1,0,0,0,376,377,3,36,18,0,377,378,5,15,0,0,378,379,5,17,0,0,379,380,3,60,
	30,0,380,381,3,34,17,0,381,55,1,0,0,0,382,383,3,36,18,0,383,384,5,15,0,
	0,384,385,5,18,0,0,385,386,5,25,0,0,386,387,5,92,0,0,387,57,1,0,0,0,388,
	389,3,36,18,0,389,390,5,17,0,0,390,391,3,152,76,0,391,392,3,34,17,0,392,
	59,1,0,0,0,393,397,5,93,0,0,394,397,5,28,0,0,395,397,3,156,78,0,396,393,
	1,0,0,0,396,394,1,0,0,0,396,395,1,0,0,0,397,61,1,0,0,0,398,399,3,36,18,
	0,399,400,5,19,0,0,400,401,3,84,42,0,401,63,1,0,0,0,402,403,3,36,18,0,403,
	404,5,14,0,0,404,405,3,82,41,0,405,65,1,0,0,0,406,407,5,71,0,0,407,408,
	3,152,76,0,408,409,5,14,0,0,409,410,3,82,41,0,410,67,1,0,0,0,411,412,3,
	34,17,0,412,413,5,20,0,0,413,414,5,74,0,0,414,419,3,150,75,0,415,416,5,
	86,0,0,416,418,3,150,75,0,417,415,1,0,0,0,418,421,1,0,0,0,419,417,1,0,0,
	0,419,420,1,0,0,0,420,422,1,0,0,0,421,419,1,0,0,0,422,423,5,75,0,0,423,
	69,1,0,0,0,424,425,3,34,17,0,425,426,5,21,0,0,426,427,3,160,80,0,427,71,
	1,0,0,0,428,429,5,71,0,0,429,430,3,152,76,0,430,431,5,22,0,0,431,432,3,
	158,79,0,432,73,1,0,0,0,433,434,5,71,0,0,434,435,3,152,76,0,435,436,5,23,
	0,0,436,437,5,25,0,0,437,438,5,92,0,0,438,445,1,0,0,0,439,440,5,71,0,0,
	440,441,3,152,76,0,441,442,5,23,0,0,442,443,3,158,79,0,443,445,1,0,0,0,
	444,433,1,0,0,0,444,439,1,0,0,0,445,75,1,0,0,0,446,447,5,71,0,0,447,448,
	3,152,76,0,448,449,5,24,0,0,449,450,3,80,40,0,450,451,5,92,0,0,451,77,1,
	0,0,0,452,453,5,71,0,0,453,454,3,152,76,0,454,455,5,26,0,0,455,456,5,25,
	0,0,456,457,5,92,0,0,457,79,1,0,0,0,458,459,7,2,0,0,459,81,1,0,0,0,460,
	461,5,89,0,0,461,83,1,0,0,0,462,463,7,3,0,0,463,85,1,0,0,0,464,465,5,27,
	0,0,465,466,5,28,0,0,466,467,3,34,17,0,467,468,5,82,0,0,468,469,3,92,46,
	0,469,87,1,0,0,0,470,471,3,86,43,0,471,89,1,0,0,0,472,473,5,27,0,0,473,
	474,3,154,77,0,474,475,3,34,17,0,475,476,5,82,0,0,476,477,3,92,46,0,477,
	91,1,0,0,0,478,479,3,82,41,0,479,480,5,84,0,0,480,482,1,0,0,0,481,478,1,
	0,0,0,481,482,1,0,0,0,482,483,1,0,0,0,483,486,3,148,74,0,484,486,3,82,41,
	0,485,481,1,0,0,0,485,484,1,0,0,0,486,93,1,0,0,0,487,488,3,98,49,0,488,
	489,5,29,0,0,489,490,5,92,0,0,490,95,1,0,0,0,491,492,3,98,49,0,492,493,
	5,30,0,0,493,494,3,152,76,0,494,495,3,158,79,0,495,97,1,0,0,0,496,502,5,
	1,0,0,497,502,3,34,17,0,498,502,3,36,18,0,499,500,5,71,0,0,500,502,3,152,
	76,0,501,496,1,0,0,0,501,497,1,0,0,0,501,498,1,0,0,0,501,499,1,0,0,0,502,
	99,1,0,0,0,503,504,5,32,0,0,504,505,3,152,76,0,505,506,5,33,0,0,506,507,
	3,110,55,0,507,508,5,35,0,0,508,509,3,160,80,0,509,520,1,0,0,0,510,511,
	5,32,0,0,511,512,3,152,76,0,512,513,5,33,0,0,513,514,3,110,55,0,514,515,
	5,36,0,0,515,516,3,110,55,0,516,517,5,37,0,0,517,518,3,160,80,0,518,520,
	1,0,0,0,519,503,1,0,0,0,519,510,1,0,0,0,520,101,1,0,0,0,521,522,5,32,0,
	0,522,523,3,152,76,0,523,524,5,34,0,0,524,525,5,71,0,0,525,526,3,152,76,
	0,526,527,5,39,0,0,527,528,3,162,81,0,528,103,1,0,0,0,529,530,5,32,0,0,
	530,531,3,152,76,0,531,532,5,40,0,0,532,533,3,152,76,0,533,105,1,0,0,0,
	534,535,5,32,0,0,535,536,3,152,76,0,536,537,5,41,0,0,537,538,3,152,76,0,
	538,107,1,0,0,0,539,540,5,32,0,0,540,541,3,152,76,0,541,542,5,49,0,0,542,
	543,3,34,17,0,543,544,7,4,0,0,544,109,1,0,0,0,545,548,3,34,17,0,546,547,
	5,71,0,0,547,549,3,36,18,0,548,546,1,0,0,0,548,549,1,0,0,0,549,552,1,0,
	0,0,550,552,3,36,18,0,551,545,1,0,0,0,551,550,1,0,0,0,552,111,1,0,0,0,553,
	554,5,42,0,0,554,555,3,114,57,0,555,557,5,43,0,0,556,558,5,92,0,0,557,556,
	1,0,0,0,557,558,1,0,0,0,558,597,1,0,0,0,559,560,5,42,0,0,560,561,3,114,
	57,0,561,562,5,44,0,0,562,563,5,92,0,0,563,597,1,0,0,0,564,565,5,42,0,0,
	565,566,3,114,57,0,566,567,5,45,0,0,567,568,5,92,0,0,568,597,1,0,0,0,569,
	570,5,42,0,0,570,571,3,114,57,0,571,573,5,48,0,0,572,574,7,5,0,0,573,572,
	1,0,0,0,573,574,1,0,0,0,574,576,1,0,0,0,575,577,5,54,0,0,576,575,1,0,0,
	0,576,577,1,0,0,0,577,597,1,0,0,0,578,579,5,42,0,0,579,580,3,114,57,0,580,
	581,5,50,0,0,581,597,1,0,0,0,582,583,5,42,0,0,583,584,5,47,0,0,584,585,
	3,150,75,0,585,586,5,46,0,0,586,597,1,0,0,0,587,588,5,42,0,0,588,589,5,
	47,0,0,589,590,3,150,75,0,590,592,5,55,0,0,591,593,5,92,0,0,592,591,1,0,
	0,0,593,594,1,0,0,0,594,592,1,0,0,0,594,595,1,0,0,0,595,597,1,0,0,0,596,
	553,1,0,0,0,596,559,1,0,0,0,596,564,1,0,0,0,596,569,1,0,0,0,596,578,1,0,
	0,0,596,582,1,0,0,0,596,587,1,0,0,0,597,113,1,0,0,0,598,603,3,34,17,0,599,
	603,3,36,18,0,600,601,5,71,0,0,601,603,3,152,76,0,602,598,1,0,0,0,602,599,
	1,0,0,0,602,600,1,0,0,0,603,115,1,0,0,0,604,605,5,31,0,0,605,606,3,160,
	80,0,606,117,1,0,0,0,607,608,5,56,0,0,608,609,3,150,75,0,609,610,5,87,0,
	0,610,612,3,120,60,0,611,613,3,122,61,0,612,611,1,0,0,0,613,614,1,0,0,0,
	614,612,1,0,0,0,614,615,1,0,0,0,615,119,1,0,0,0,616,621,3,152,76,0,617,
	618,5,87,0,0,618,620,3,152,76,0,619,617,1,0,0,0,620,623,1,0,0,0,621,619,
	1,0,0,0,621,622,1,0,0,0,622,121,1,0,0,0,623,621,1,0,0,0,624,625,7,6,0,0,
	625,123,1,0,0,0,626,627,5,57,0,0,627,632,3,126,63,0,628,629,5,86,0,0,629,
	631,3,126,63,0,630,628,1,0,0,0,631,634,1,0,0,0,632,630,1,0,0,0,632,633,
	1,0,0,0,633,125,1,0,0,0,634,632,1,0,0,0,635,640,3,34,17,0,636,637,5,37,
	0,0,637,639,3,34,17,0,638,636,1,0,0,0,639,642,1,0,0,0,640,638,1,0,0,0,640,
	641,1,0,0,0,641,127,1,0,0,0,642,640,1,0,0,0,643,645,5,58,0,0,644,646,5,
	92,0,0,645,644,1,0,0,0,645,646,1,0,0,0,646,647,1,0,0,0,647,652,3,130,65,
	0,648,649,5,37,0,0,649,651,3,130,65,0,650,648,1,0,0,0,651,654,1,0,0,0,652,
	650,1,0,0,0,652,653,1,0,0,0,653,657,1,0,0,0,654,652,1,0,0,0,655,656,5,38,
	0,0,656,658,3,84,42,0,657,655,1,0,0,0,657,658,1,0,0,0,658,129,1,0,0,0,659,
	660,3,82,41,0,660,661,5,84,0,0,661,663,1,0,0,0,662,659,1,0,0,0,662,663,
	1,0,0,0,663,664,1,0,0,0,664,665,3,34,17,0,665,131,1,0,0,0,666,667,3,134,
	67,0,667,668,5,59,0,0,668,669,3,152,76,0,669,133,1,0,0,0,670,674,5,1,0,
	0,671,674,3,34,17,0,672,674,3,36,18,0,673,670,1,0,0,0,673,671,1,0,0,0,673,
	672,1,0,0,0,674,135,1,0,0,0,675,676,7,7,0,0,676,677,3,152,76,0,677,137,
	1,0,0,0,678,679,3,34,17,0,679,680,5,63,0,0,680,684,5,64,0,0,681,682,5,25,
	0,0,682,685,5,92,0,0,683,685,3,152,76,0,684,681,1,0,0,0,684,683,1,0,0,0,
	685,139,1,0,0,0,686,687,3,34,17,0,687,688,5,65,0,0,688,689,5,4,0,0,689,
	690,5,25,0,0,690,691,5,92,0,0,691,141,1,0,0,0,692,693,3,34,17,0,693,694,
	5,66,0,0,694,695,5,8,0,0,695,696,3,152,76,0,696,697,5,67,0,0,697,698,5,
	4,0,0,698,699,5,25,0,0,699,700,5,92,0,0,700,143,1,0,0,0,701,702,3,148,74,
	0,702,703,5,85,0,0,703,704,3,150,75,0,704,705,3,158,79,0,705,145,1,0,0,
	0,706,707,3,144,72,0,707,147,1,0,0,0,708,709,5,83,0,0,709,710,3,152,76,
	0,710,149,1,0,0,0,711,712,3,152,76,0,712,151,1,0,0,0,713,718,5,93,0,0,714,
	718,5,92,0,0,715,718,5,28,0,0,716,718,3,156,78,0,717,713,1,0,0,0,717,714,
	1,0,0,0,717,715,1,0,0,0,717,716,1,0,0,0,718,153,1,0,0,0,719,723,5,93,0,
	0,720,723,5,92,0,0,721,723,3,156,78,0,722,719,1,0,0,0,722,720,1,0,0,0,722,
	721,1,0,0,0,723,155,1,0,0,0,724,725,7,8,0,0,725,157,1,0,0,0,726,736,3,160,
	80,0,727,736,3,162,81,0,728,736,5,92,0,0,729,736,5,91,0,0,730,736,5,89,
	0,0,731,736,5,90,0,0,732,736,5,68,0,0,733,736,5,69,0,0,734,736,5,70,0,0,
	735,726,1,0,0,0,735,727,1,0,0,0,735,728,1,0,0,0,735,729,1,0,0,0,735,730,
	1,0,0,0,735,731,1,0,0,0,735,732,1,0,0,0,735,733,1,0,0,0,735,734,1,0,0,0,
	736,159,1,0,0,0,737,750,5,76,0,0,738,739,5,92,0,0,739,740,5,85,0,0,740,
	747,3,158,79,0,741,742,5,86,0,0,742,743,5,92,0,0,743,744,5,85,0,0,744,746,
	3,158,79,0,745,741,1,0,0,0,746,749,1,0,0,0,747,745,1,0,0,0,747,748,1,0,
	0,0,748,751,1,0,0,0,749,747,1,0,0,0,750,738,1,0,0,0,750,751,1,0,0,0,751,
	752,1,0,0,0,752,753,5,77,0,0,753,161,1,0,0,0,754,763,5,74,0,0,755,760,3,
	158,79,0,756,757,5,86,0,0,757,759,3,158,79,0,758,756,1,0,0,0,759,762,1,
	0,0,0,760,758,1,0,0,0,760,761,1,0,0,0,761,764,1,0,0,0,762,760,1,0,0,0,763,
	755,1,0,0,0,763,764,1,0,0,0,764,765,1,0,0,0,765,766,5,75,0,0,766,163,1,
	0,0,0,48,165,206,208,218,220,225,230,259,274,286,295,306,312,320,324,328,
	396,419,444,481,485,501,519,548,551,557,573,576,594,596,602,614,621,632,
	640,645,652,657,662,673,684,717,722,735,747,750,760,763];

	private static __ATN: ATN;
	public static get _ATN(): ATN {
		if (!VelocitronPetriNetParser.__ATN) {
			VelocitronPetriNetParser.__ATN = new ATNDeserializer().deserialize(VelocitronPetriNetParser._serializedATN);
		}

		return VelocitronPetriNetParser.__ATN;
	}


	static DecisionsToDFA = VelocitronPetriNetParser._ATN.decisionToState.map( (ds: DecisionState, index: number) => new DFA(ds, index) );

}

export class DocumentContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public EOF(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.EOF, 0);
	}
	public netHeader(): NetHeaderContext {
		return this.getTypedRuleContext(NetHeaderContext, 0) as NetHeaderContext;
	}
	public chain_list(): ChainContext[] {
		return this.getTypedRuleContexts(ChainContext) as ChainContext[];
	}
	public chain(i: number): ChainContext {
		return this.getTypedRuleContext(ChainContext, i) as ChainContext;
	}
	public placeDeclaration_list(): PlaceDeclarationContext[] {
		return this.getTypedRuleContexts(PlaceDeclarationContext) as PlaceDeclarationContext[];
	}
	public placeDeclaration(i: number): PlaceDeclarationContext {
		return this.getTypedRuleContext(PlaceDeclarationContext, i) as PlaceDeclarationContext;
	}
	public transitionDeclaration_list(): TransitionDeclarationContext[] {
		return this.getTypedRuleContexts(TransitionDeclarationContext) as TransitionDeclarationContext[];
	}
	public transitionDeclaration(i: number): TransitionDeclarationContext {
		return this.getTypedRuleContext(TransitionDeclarationContext, i) as TransitionDeclarationContext;
	}
	public transitionHandler_list(): TransitionHandlerContext[] {
		return this.getTypedRuleContexts(TransitionHandlerContext) as TransitionHandlerContext[];
	}
	public transitionHandler(i: number): TransitionHandlerContext {
		return this.getTypedRuleContext(TransitionHandlerContext, i) as TransitionHandlerContext;
	}
	public transitionGuard_list(): TransitionGuardContext[] {
		return this.getTypedRuleContexts(TransitionGuardContext) as TransitionGuardContext[];
	}
	public transitionGuard(i: number): TransitionGuardContext {
		return this.getTypedRuleContext(TransitionGuardContext, i) as TransitionGuardContext;
	}
	public transitionTimer_list(): TransitionTimerContext[] {
		return this.getTypedRuleContexts(TransitionTimerContext) as TransitionTimerContext[];
	}
	public transitionTimer(i: number): TransitionTimerContext {
		return this.getTypedRuleContext(TransitionTimerContext, i) as TransitionTimerContext;
	}
	public transitionTimerBind_list(): TransitionTimerBindContext[] {
		return this.getTypedRuleContexts(TransitionTimerBindContext) as TransitionTimerBindContext[];
	}
	public transitionTimerBind(i: number): TransitionTimerBindContext {
		return this.getTypedRuleContext(TransitionTimerBindContext, i) as TransitionTimerBindContext;
	}
	public transitionTimerMaturity_list(): TransitionTimerMaturityContext[] {
		return this.getTypedRuleContexts(TransitionTimerMaturityContext) as TransitionTimerMaturityContext[];
	}
	public transitionTimerMaturity(i: number): TransitionTimerMaturityContext {
		return this.getTypedRuleContext(TransitionTimerMaturityContext, i) as TransitionTimerMaturityContext;
	}
	public transitionBindingName_list(): TransitionBindingNameContext[] {
		return this.getTypedRuleContexts(TransitionBindingNameContext) as TransitionBindingNameContext[];
	}
	public transitionBindingName(i: number): TransitionBindingNameContext {
		return this.getTypedRuleContext(TransitionBindingNameContext, i) as TransitionBindingNameContext;
	}
	public transitionPriority_list(): TransitionPriorityContext[] {
		return this.getTypedRuleContexts(TransitionPriorityContext) as TransitionPriorityContext[];
	}
	public transitionPriority(i: number): TransitionPriorityContext {
		return this.getTypedRuleContext(TransitionPriorityContext, i) as TransitionPriorityContext;
	}
	public transitionOrder_list(): TransitionOrderContext[] {
		return this.getTypedRuleContexts(TransitionOrderContext) as TransitionOrderContext[];
	}
	public transitionOrder(i: number): TransitionOrderContext {
		return this.getTypedRuleContext(TransitionOrderContext, i) as TransitionOrderContext;
	}
	public chainOrder_list(): ChainOrderContext[] {
		return this.getTypedRuleContexts(ChainOrderContext) as ChainOrderContext[];
	}
	public chainOrder(i: number): ChainOrderContext {
		return this.getTypedRuleContext(ChainOrderContext, i) as ChainOrderContext;
	}
	public placePort_list(): PlacePortContext[] {
		return this.getTypedRuleContexts(PlacePortContext) as PlacePortContext[];
	}
	public placePort(i: number): PlacePortContext {
		return this.getTypedRuleContext(PlacePortContext, i) as PlacePortContext;
	}
	public placeAccepts_list(): PlaceAcceptsContext[] {
		return this.getTypedRuleContexts(PlaceAcceptsContext) as PlaceAcceptsContext[];
	}
	public placeAccepts(i: number): PlaceAcceptsContext {
		return this.getTypedRuleContext(PlaceAcceptsContext, i) as PlaceAcceptsContext;
	}
	public placeCapacity_list(): PlaceCapacityContext[] {
		return this.getTypedRuleContexts(PlaceCapacityContext) as PlaceCapacityContext[];
	}
	public placeCapacity(i: number): PlaceCapacityContext {
		return this.getTypedRuleContext(PlaceCapacityContext, i) as PlaceCapacityContext;
	}
	public arcWeight_list(): ArcWeightContext[] {
		return this.getTypedRuleContexts(ArcWeightContext) as ArcWeightContext[];
	}
	public arcWeight(i: number): ArcWeightContext {
		return this.getTypedRuleContext(ArcWeightContext, i) as ArcWeightContext;
	}
	public arcData_list(): ArcDataContext[] {
		return this.getTypedRuleContexts(ArcDataContext) as ArcDataContext[];
	}
	public arcData(i: number): ArcDataContext {
		return this.getTypedRuleContext(ArcDataContext, i) as ArcDataContext;
	}
	public arcPredicate_list(): ArcPredicateContext[] {
		return this.getTypedRuleContexts(ArcPredicateContext) as ArcPredicateContext[];
	}
	public arcPredicate(i: number): ArcPredicateContext {
		return this.getTypedRuleContext(ArcPredicateContext, i) as ArcPredicateContext;
	}
	public arcCorrelate_list(): ArcCorrelateContext[] {
		return this.getTypedRuleContexts(ArcCorrelateContext) as ArcCorrelateContext[];
	}
	public arcCorrelate(i: number): ArcCorrelateContext {
		return this.getTypedRuleContext(ArcCorrelateContext, i) as ArcCorrelateContext;
	}
	public initialMarking_list(): InitialMarkingContext[] {
		return this.getTypedRuleContexts(InitialMarkingContext) as InitialMarkingContext[];
	}
	public initialMarking(i: number): InitialMarkingContext {
		return this.getTypedRuleContext(InitialMarkingContext, i) as InitialMarkingContext;
	}
	public templateDefinition_list(): TemplateDefinitionContext[] {
		return this.getTypedRuleContexts(TemplateDefinitionContext) as TemplateDefinitionContext[];
	}
	public templateDefinition(i: number): TemplateDefinitionContext {
		return this.getTypedRuleContext(TemplateDefinitionContext, i) as TemplateDefinitionContext;
	}
	public namedMarking_list(): NamedMarkingContext[] {
		return this.getTypedRuleContexts(NamedMarkingContext) as NamedMarkingContext[];
	}
	public namedMarking(i: number): NamedMarkingContext {
		return this.getTypedRuleContext(NamedMarkingContext, i) as NamedMarkingContext;
	}
	public metadataDescription_list(): MetadataDescriptionContext[] {
		return this.getTypedRuleContexts(MetadataDescriptionContext) as MetadataDescriptionContext[];
	}
	public metadataDescription(i: number): MetadataDescriptionContext {
		return this.getTypedRuleContext(MetadataDescriptionContext, i) as MetadataDescriptionContext;
	}
	public metadataAnnotation_list(): MetadataAnnotationContext[] {
		return this.getTypedRuleContexts(MetadataAnnotationContext) as MetadataAnnotationContext[];
	}
	public metadataAnnotation(i: number): MetadataAnnotationContext {
		return this.getTypedRuleContext(MetadataAnnotationContext, i) as MetadataAnnotationContext;
	}
	public viewPosition_list(): ViewPositionContext[] {
		return this.getTypedRuleContexts(ViewPositionContext) as ViewPositionContext[];
	}
	public viewPosition(i: number): ViewPositionContext {
		return this.getTypedRuleContext(ViewPositionContext, i) as ViewPositionContext;
	}
	public viewRoute_list(): ViewRouteContext[] {
		return this.getTypedRuleContexts(ViewRouteContext) as ViewRouteContext[];
	}
	public viewRoute(i: number): ViewRouteContext {
		return this.getTypedRuleContext(ViewRouteContext, i) as ViewRouteContext;
	}
	public viewSplines_list(): ViewSplinesContext[] {
		return this.getTypedRuleContexts(ViewSplinesContext) as ViewSplinesContext[];
	}
	public viewSplines(i: number): ViewSplinesContext {
		return this.getTypedRuleContext(ViewSplinesContext, i) as ViewSplinesContext;
	}
	public viewDetail_list(): ViewDetailContext[] {
		return this.getTypedRuleContexts(ViewDetailContext) as ViewDetailContext[];
	}
	public viewDetail(i: number): ViewDetailContext {
		return this.getTypedRuleContext(ViewDetailContext, i) as ViewDetailContext;
	}
	public viewFusion_list(): ViewFusionContext[] {
		return this.getTypedRuleContexts(ViewFusionContext) as ViewFusionContext[];
	}
	public viewFusion(i: number): ViewFusionContext {
		return this.getTypedRuleContext(ViewFusionContext, i) as ViewFusionContext;
	}
	public decoration_list(): DecorationContext[] {
		return this.getTypedRuleContexts(DecorationContext) as DecorationContext[];
	}
	public decoration(i: number): DecorationContext {
		return this.getTypedRuleContext(DecorationContext, i) as DecorationContext;
	}
	public extensions_list(): ExtensionsContext[] {
		return this.getTypedRuleContexts(ExtensionsContext) as ExtensionsContext[];
	}
	public extensions(i: number): ExtensionsContext {
		return this.getTypedRuleContext(ExtensionsContext, i) as ExtensionsContext;
	}
	public domainDeclaration_list(): DomainDeclarationContext[] {
		return this.getTypedRuleContexts(DomainDeclarationContext) as DomainDeclarationContext[];
	}
	public domainDeclaration(i: number): DomainDeclarationContext {
		return this.getTypedRuleContext(DomainDeclarationContext, i) as DomainDeclarationContext;
	}
	public finalDeclaration_list(): FinalDeclarationContext[] {
		return this.getTypedRuleContexts(FinalDeclarationContext) as FinalDeclarationContext[];
	}
	public finalDeclaration(i: number): FinalDeclarationContext {
		return this.getTypedRuleContext(FinalDeclarationContext, i) as FinalDeclarationContext;
	}
	public invariantDeclaration_list(): InvariantDeclarationContext[] {
		return this.getTypedRuleContexts(InvariantDeclarationContext) as InvariantDeclarationContext[];
	}
	public invariantDeclaration(i: number): InvariantDeclarationContext {
		return this.getTypedRuleContext(InvariantDeclarationContext, i) as InvariantDeclarationContext;
	}
	public actorAssignment_list(): ActorAssignmentContext[] {
		return this.getTypedRuleContexts(ActorAssignmentContext) as ActorAssignmentContext[];
	}
	public actorAssignment(i: number): ActorAssignmentContext {
		return this.getTypedRuleContext(ActorAssignmentContext, i) as ActorAssignmentContext;
	}
	public actorDeclaration_list(): ActorDeclarationContext[] {
		return this.getTypedRuleContexts(ActorDeclarationContext) as ActorDeclarationContext[];
	}
	public actorDeclaration(i: number): ActorDeclarationContext {
		return this.getTypedRuleContext(ActorDeclarationContext, i) as ActorDeclarationContext;
	}
	public placeLives_list(): PlaceLivesContext[] {
		return this.getTypedRuleContexts(PlaceLivesContext) as PlaceLivesContext[];
	}
	public placeLives(i: number): PlaceLivesContext {
		return this.getTypedRuleContext(PlaceLivesContext, i) as PlaceLivesContext;
	}
	public placeReadsAs_list(): PlaceReadsAsContext[] {
		return this.getTypedRuleContexts(PlaceReadsAsContext) as PlaceReadsAsContext[];
	}
	public placeReadsAs(i: number): PlaceReadsAsContext {
		return this.getTypedRuleContext(PlaceReadsAsContext, i) as PlaceReadsAsContext;
	}
	public placeKept_list(): PlaceKeptContext[] {
		return this.getTypedRuleContexts(PlaceKeptContext) as PlaceKeptContext[];
	}
	public placeKept(i: number): PlaceKeptContext {
		return this.getTypedRuleContext(PlaceKeptContext, i) as PlaceKeptContext;
	}
	public compositionHeader(): CompositionHeaderContext {
		return this.getTypedRuleContext(CompositionHeaderContext, 0) as CompositionHeaderContext;
	}
	public compositionUse_list(): CompositionUseContext[] {
		return this.getTypedRuleContexts(CompositionUseContext) as CompositionUseContext[];
	}
	public compositionUse(i: number): CompositionUseContext {
		return this.getTypedRuleContext(CompositionUseContext, i) as CompositionUseContext;
	}
	public compositionWire_list(): CompositionWireContext[] {
		return this.getTypedRuleContexts(CompositionWireContext) as CompositionWireContext[];
	}
	public compositionWire(i: number): CompositionWireContext {
		return this.getTypedRuleContext(CompositionWireContext, i) as CompositionWireContext;
	}
	public compositionShare_list(): CompositionShareContext[] {
		return this.getTypedRuleContexts(CompositionShareContext) as CompositionShareContext[];
	}
	public compositionShare(i: number): CompositionShareContext {
		return this.getTypedRuleContext(CompositionShareContext, i) as CompositionShareContext;
	}
	public compositionRefine_list(): CompositionRefineContext[] {
		return this.getTypedRuleContexts(CompositionRefineContext) as CompositionRefineContext[];
	}
	public compositionRefine(i: number): CompositionRefineContext {
		return this.getTypedRuleContext(CompositionRefineContext, i) as CompositionRefineContext;
	}
	public compositionFinal_list(): CompositionFinalContext[] {
		return this.getTypedRuleContexts(CompositionFinalContext) as CompositionFinalContext[];
	}
	public compositionFinal(i: number): CompositionFinalContext {
		return this.getTypedRuleContext(CompositionFinalContext, i) as CompositionFinalContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_document;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitDocument) {
			return visitor.visitDocument(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class NetHeaderContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public NET(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.NET, 0);
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.STRING, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_netHeader;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitNetHeader) {
			return visitor.visitNetHeader(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class CompositionHeaderContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public COMPOSITION(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.COMPOSITION, 0);
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_compositionHeader;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitCompositionHeader) {
			return visitor.visitCompositionHeader(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class CompositionUseContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public USE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.USE, 0);
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.STRING, 0);
	}
	public AS(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.AS, 0);
	}
	public IDENT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.IDENT, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_compositionUse;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitCompositionUse) {
			return visitor.visitCompositionUse(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class CompositionWireContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public WIRE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.WIRE, 0);
	}
	public IDENT_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPetriNetParser.IDENT);
	}
	public IDENT(i: number): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.IDENT, i);
	}
	public DOT_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPetriNetParser.DOT);
	}
	public DOT(i: number): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.DOT, i);
	}
	public compositionPlace_list(): CompositionPlaceContext[] {
		return this.getTypedRuleContexts(CompositionPlaceContext) as CompositionPlaceContext[];
	}
	public compositionPlace(i: number): CompositionPlaceContext {
		return this.getTypedRuleContext(CompositionPlaceContext, i) as CompositionPlaceContext;
	}
	public ARROW(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.ARROW, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_compositionWire;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitCompositionWire) {
			return visitor.visitCompositionWire(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class CompositionShareContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public SHARE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.SHARE, 0);
	}
	public IDENT_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPetriNetParser.IDENT);
	}
	public IDENT(i: number): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.IDENT, i);
	}
	public DOT_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPetriNetParser.DOT);
	}
	public DOT(i: number): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.DOT, i);
	}
	public compositionPlace_list(): CompositionPlaceContext[] {
		return this.getTypedRuleContexts(CompositionPlaceContext) as CompositionPlaceContext[];
	}
	public compositionPlace(i: number): CompositionPlaceContext {
		return this.getTypedRuleContext(CompositionPlaceContext, i) as CompositionPlaceContext;
	}
	public TILDE_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPetriNetParser.TILDE);
	}
	public TILDE(i: number): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.TILDE, i);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_compositionShare;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitCompositionShare) {
			return visitor.visitCompositionShare(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class CompositionRefineContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public REFINE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.REFINE, 0);
	}
	public IDENT_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPetriNetParser.IDENT);
	}
	public IDENT(i: number): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.IDENT, i);
	}
	public DOT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.DOT, 0);
	}
	public compositionTransition(): CompositionTransitionContext {
		return this.getTypedRuleContext(CompositionTransitionContext, 0) as CompositionTransitionContext;
	}
	public BY(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.BY, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_compositionRefine;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitCompositionRefine) {
			return visitor.visitCompositionRefine(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class CompositionFinalContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public FINAL(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.FINAL, 0);
	}
	public compositionFinalMarking_list(): CompositionFinalMarkingContext[] {
		return this.getTypedRuleContexts(CompositionFinalMarkingContext) as CompositionFinalMarkingContext[];
	}
	public compositionFinalMarking(i: number): CompositionFinalMarkingContext {
		return this.getTypedRuleContext(CompositionFinalMarkingContext, i) as CompositionFinalMarkingContext;
	}
	public COMMA_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPetriNetParser.COMMA);
	}
	public COMMA(i: number): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.COMMA, i);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_compositionFinal;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitCompositionFinal) {
			return visitor.visitCompositionFinal(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class CompositionFinalMarkingContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public IDENT_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPetriNetParser.IDENT);
	}
	public IDENT(i: number): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.IDENT, i);
	}
	public DOT_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPetriNetParser.DOT);
	}
	public DOT(i: number): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.DOT, i);
	}
	public compositionPlace_list(): CompositionPlaceContext[] {
		return this.getTypedRuleContexts(CompositionPlaceContext) as CompositionPlaceContext[];
	}
	public compositionPlace(i: number): CompositionPlaceContext {
		return this.getTypedRuleContext(CompositionPlaceContext, i) as CompositionPlaceContext;
	}
	public PLUS_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPetriNetParser.PLUS);
	}
	public PLUS(i: number): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.PLUS, i);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_compositionFinalMarking;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitCompositionFinalMarking) {
			return visitor.visitCompositionFinalMarking(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class CompositionPlaceContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public LPAREN(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.LPAREN, 0);
	}
	public name_list(): NameContext[] {
		return this.getTypedRuleContexts(NameContext) as NameContext[];
	}
	public name(i: number): NameContext {
		return this.getTypedRuleContext(NameContext, i) as NameContext;
	}
	public RPAREN(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.RPAREN, 0);
	}
	public DOT_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPetriNetParser.DOT);
	}
	public DOT(i: number): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.DOT, i);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_compositionPlace;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitCompositionPlace) {
			return visitor.visitCompositionPlace(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class CompositionTransitionContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public LBRACK(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.LBRACK, 0);
	}
	public name_list(): NameContext[] {
		return this.getTypedRuleContexts(NameContext) as NameContext[];
	}
	public name(i: number): NameContext {
		return this.getTypedRuleContext(NameContext, i) as NameContext;
	}
	public RBRACK(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.RBRACK, 0);
	}
	public DOT_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPetriNetParser.DOT);
	}
	public DOT(i: number): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.DOT, i);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_compositionTransition;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitCompositionTransition) {
			return visitor.visitCompositionTransition(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ChainContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public chainNode_list(): ChainNodeContext[] {
		return this.getTypedRuleContexts(ChainNodeContext) as ChainNodeContext[];
	}
	public chainNode(i: number): ChainNodeContext {
		return this.getTypedRuleContext(ChainNodeContext, i) as ChainNodeContext;
	}
	public chainHandle(): ChainHandleContext {
		return this.getTypedRuleContext(ChainHandleContext, 0) as ChainHandleContext;
	}
	public arcSegment_list(): ArcSegmentContext[] {
		return this.getTypedRuleContexts(ArcSegmentContext) as ArcSegmentContext[];
	}
	public arcSegment(i: number): ArcSegmentContext {
		return this.getTypedRuleContext(ArcSegmentContext, i) as ArcSegmentContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_chain;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitChain) {
			return visitor.visitChain(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ChainNodeContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
	public transition(): TransitionContext {
		return this.getTypedRuleContext(TransitionContext, 0) as TransitionContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_chainNode;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitChainNode) {
			return visitor.visitChainNode(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ArcSegmentContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public arcOperator(): ArcOperatorContext {
		return this.getTypedRuleContext(ArcOperatorContext, 0) as ArcOperatorContext;
	}
	public HYPHEN(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.HYPHEN, 0);
	}
	public color(): ColorContext {
		return this.getTypedRuleContext(ColorContext, 0) as ColorContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_arcSegment;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitArcSegment) {
			return visitor.visitArcSegment(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ArcOperatorContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public ARROW(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.ARROW, 0);
	}
	public READ_ARROW(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.READ_ARROW, 0);
	}
	public INHIBIT_ARROW(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.INHIBIT_ARROW, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_arcOperator;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitArcOperator) {
			return visitor.visitArcOperator(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class AdditionalChainContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public chain(): ChainContext {
		return this.getTypedRuleContext(ChainContext, 0) as ChainContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_additionalChain;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitAdditionalChain) {
			return visitor.visitAdditionalChain(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ChainHandleContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public AT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.AT, 0);
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
	public COLON(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.COLON, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_chainHandle;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitChainHandle) {
			return visitor.visitChainHandle(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class PlaceContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public LPAREN(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.LPAREN, 0);
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
	public RPAREN(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.RPAREN, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_place;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitPlace) {
			return visitor.visitPlace(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class TransitionContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public LBRACK(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.LBRACK, 0);
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
	public RBRACK(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.RBRACK, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_transition;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitTransition) {
			return visitor.visitTransition(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class PlaceDeclarationContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_placeDeclaration;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitPlaceDeclaration) {
			return visitor.visitPlaceDeclaration(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class TransitionDeclarationContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public transition(): TransitionContext {
		return this.getTypedRuleContext(TransitionContext, 0) as TransitionContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_transitionDeclaration;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitTransitionDeclaration) {
			return visitor.visitTransitionDeclaration(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class PlacePortContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
	public PORT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.PORT, 0);
	}
	public portDirection(): PortDirectionContext {
		return this.getTypedRuleContext(PortDirectionContext, 0) as PortDirectionContext;
	}
	public color(): ColorContext {
		return this.getTypedRuleContext(ColorContext, 0) as ColorContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_placePort;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitPlacePort) {
			return visitor.visitPlacePort(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class PortDirectionContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public INPUT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.INPUT, 0);
	}
	public OUTPUT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.OUTPUT, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_portDirection;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitPortDirection) {
			return visitor.visitPortDirection(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class TransitionHandlerContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public transition(): TransitionContext {
		return this.getTypedRuleContext(TransitionContext, 0) as TransitionContext;
	}
	public HANDLER(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.HANDLER, 0);
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.STRING, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_transitionHandler;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitTransitionHandler) {
			return visitor.visitTransitionHandler(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class AdditionalTransitionHandlerContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public transitionHandler(): TransitionHandlerContext {
		return this.getTypedRuleContext(TransitionHandlerContext, 0) as TransitionHandlerContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_additionalTransitionHandler;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitAdditionalTransitionHandler) {
			return visitor.visitAdditionalTransitionHandler(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class TransitionGuardContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public transition(): TransitionContext {
		return this.getTypedRuleContext(TransitionContext, 0) as TransitionContext;
	}
	public GUARD(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.GUARD, 0);
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.STRING, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_transitionGuard;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitTransitionGuard) {
			return visitor.visitTransitionGuard(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class TransitionTimerContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public transition(): TransitionContext {
		return this.getTypedRuleContext(TransitionContext, 0) as TransitionContext;
	}
	public TIMER(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.TIMER, 0);
	}
	public CLOCK(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.CLOCK, 0);
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
	public CEL(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.CEL, 0);
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.STRING, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_transitionTimer;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitTransitionTimer) {
			return visitor.visitTransitionTimer(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class TransitionTimerBindContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public transition(): TransitionContext {
		return this.getTypedRuleContext(TransitionContext, 0) as TransitionContext;
	}
	public TIMER(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.TIMER, 0);
	}
	public BIND(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.BIND, 0);
	}
	public timerBindName(): TimerBindNameContext {
		return this.getTypedRuleContext(TimerBindNameContext, 0) as TimerBindNameContext;
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_transitionTimerBind;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitTransitionTimerBind) {
			return visitor.visitTransitionTimerBind(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class TransitionTimerMaturityContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public transition(): TransitionContext {
		return this.getTypedRuleContext(TransitionContext, 0) as TransitionContext;
	}
	public TIMER(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.TIMER, 0);
	}
	public MATURITY(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.MATURITY, 0);
	}
	public CEL(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.CEL, 0);
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.STRING, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_transitionTimerMaturity;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitTransitionTimerMaturity) {
			return visitor.visitTransitionTimerMaturity(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class TransitionBindingNameContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public transition(): TransitionContext {
		return this.getTypedRuleContext(TransitionContext, 0) as TransitionContext;
	}
	public BIND(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.BIND, 0);
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_transitionBindingName;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitTransitionBindingName) {
			return visitor.visitTransitionBindingName(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class TimerBindNameContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public IDENT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.IDENT, 0);
	}
	public INITIAL(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.INITIAL, 0);
	}
	public keyword(): KeywordContext {
		return this.getTypedRuleContext(KeywordContext, 0) as KeywordContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_timerBindName;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitTimerBindName) {
			return visitor.visitTimerBindName(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class TransitionPriorityContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public transition(): TransitionContext {
		return this.getTypedRuleContext(TransitionContext, 0) as TransitionContext;
	}
	public PRIORITY(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.PRIORITY, 0);
	}
	public nonnegativeInteger(): NonnegativeIntegerContext {
		return this.getTypedRuleContext(NonnegativeIntegerContext, 0) as NonnegativeIntegerContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_transitionPriority;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitTransitionPriority) {
			return visitor.visitTransitionPriority(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class TransitionOrderContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public transition(): TransitionContext {
		return this.getTypedRuleContext(TransitionContext, 0) as TransitionContext;
	}
	public ORDER(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.ORDER, 0);
	}
	public positiveInteger(): PositiveIntegerContext {
		return this.getTypedRuleContext(PositiveIntegerContext, 0) as PositiveIntegerContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_transitionOrder;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitTransitionOrder) {
			return visitor.visitTransitionOrder(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ChainOrderContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public AT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.AT, 0);
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
	public ORDER(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.ORDER, 0);
	}
	public positiveInteger(): PositiveIntegerContext {
		return this.getTypedRuleContext(PositiveIntegerContext, 0) as PositiveIntegerContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_chainOrder;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitChainOrder) {
			return visitor.visitChainOrder(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class PlaceAcceptsContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
	public ACCEPTS(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.ACCEPTS, 0);
	}
	public LBRACK(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.LBRACK, 0);
	}
	public color_list(): ColorContext[] {
		return this.getTypedRuleContexts(ColorContext) as ColorContext[];
	}
	public color(i: number): ColorContext {
		return this.getTypedRuleContext(ColorContext, i) as ColorContext;
	}
	public RBRACK(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.RBRACK, 0);
	}
	public COMMA_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPetriNetParser.COMMA);
	}
	public COMMA(i: number): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.COMMA, i);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_placeAccepts;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitPlaceAccepts) {
			return visitor.visitPlaceAccepts(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class PlaceCapacityContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
	public CAPACITY_PER_COLOR_KEY(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.CAPACITY_PER_COLOR_KEY, 0);
	}
	public jsonObject(): JsonObjectContext {
		return this.getTypedRuleContext(JsonObjectContext, 0) as JsonObjectContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_placeCapacity;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitPlaceCapacity) {
			return visitor.visitPlaceCapacity(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ArcWeightContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public AT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.AT, 0);
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
	public WEIGHT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.WEIGHT, 0);
	}
	public jsonValue(): JsonValueContext {
		return this.getTypedRuleContext(JsonValueContext, 0) as JsonValueContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_arcWeight;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitArcWeight) {
			return visitor.visitArcWeight(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ArcDataContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public AT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.AT, 0);
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
	public DATA(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.DATA, 0);
	}
	public CEL(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.CEL, 0);
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.STRING, 0);
	}
	public jsonValue(): JsonValueContext {
		return this.getTypedRuleContext(JsonValueContext, 0) as JsonValueContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_arcData;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitArcData) {
			return visitor.visitArcData(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ArcPredicateContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public AT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.AT, 0);
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
	public PREDICATE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.PREDICATE, 0);
	}
	public predicateKind(): PredicateKindContext {
		return this.getTypedRuleContext(PredicateKindContext, 0) as PredicateKindContext;
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.STRING, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_arcPredicate;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitArcPredicate) {
			return visitor.visitArcPredicate(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ArcCorrelateContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public AT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.AT, 0);
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
	public CORRELATE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.CORRELATE, 0);
	}
	public CEL(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.CEL, 0);
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.STRING, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_arcCorrelate;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitArcCorrelate) {
			return visitor.visitArcCorrelate(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class PredicateKindContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public CEL(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.CEL, 0);
	}
	public HANDLER(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.HANDLER, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_predicateKind;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitPredicateKind) {
			return visitor.visitPredicateKind(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class PositiveIntegerContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public POSITIVE_INTEGER(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.POSITIVE_INTEGER, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_positiveInteger;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitPositiveInteger) {
			return visitor.visitPositiveInteger(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class NonnegativeIntegerContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public POSITIVE_INTEGER(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.POSITIVE_INTEGER, 0);
	}
	public ZERO(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.ZERO, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_nonnegativeInteger;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitNonnegativeInteger) {
			return visitor.visitNonnegativeInteger(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class InitialMarkingContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public MARKING(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.MARKING, 0);
	}
	public INITIAL(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.INITIAL, 0);
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
	public LEFT_ARROW(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.LEFT_ARROW, 0);
	}
	public markingValue(): MarkingValueContext {
		return this.getTypedRuleContext(MarkingValueContext, 0) as MarkingValueContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_initialMarking;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitInitialMarking) {
			return visitor.visitInitialMarking(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class AdditionalInitialMarkingContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public initialMarking(): InitialMarkingContext {
		return this.getTypedRuleContext(InitialMarkingContext, 0) as InitialMarkingContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_additionalInitialMarking;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitAdditionalInitialMarking) {
			return visitor.visitAdditionalInitialMarking(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class NamedMarkingContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public MARKING(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.MARKING, 0);
	}
	public markingName(): MarkingNameContext {
		return this.getTypedRuleContext(MarkingNameContext, 0) as MarkingNameContext;
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
	public LEFT_ARROW(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.LEFT_ARROW, 0);
	}
	public markingValue(): MarkingValueContext {
		return this.getTypedRuleContext(MarkingValueContext, 0) as MarkingValueContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_namedMarking;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitNamedMarking) {
			return visitor.visitNamedMarking(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class MarkingValueContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public templateReference(): TemplateReferenceContext {
		return this.getTypedRuleContext(TemplateReferenceContext, 0) as TemplateReferenceContext;
	}
	public positiveInteger(): PositiveIntegerContext {
		return this.getTypedRuleContext(PositiveIntegerContext, 0) as PositiveIntegerContext;
	}
	public STAR(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.STAR, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_markingValue;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitMarkingValue) {
			return visitor.visitMarkingValue(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class MetadataDescriptionContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public metadataTarget(): MetadataTargetContext {
		return this.getTypedRuleContext(MetadataTargetContext, 0) as MetadataTargetContext;
	}
	public DESCRIPTION(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.DESCRIPTION, 0);
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.STRING, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_metadataDescription;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitMetadataDescription) {
			return visitor.visitMetadataDescription(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class MetadataAnnotationContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public metadataTarget(): MetadataTargetContext {
		return this.getTypedRuleContext(MetadataTargetContext, 0) as MetadataTargetContext;
	}
	public ANNOTATION(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.ANNOTATION, 0);
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
	public jsonValue(): JsonValueContext {
		return this.getTypedRuleContext(JsonValueContext, 0) as JsonValueContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_metadataAnnotation;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitMetadataAnnotation) {
			return visitor.visitMetadataAnnotation(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class MetadataTargetContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public NET(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.NET, 0);
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
	public transition(): TransitionContext {
		return this.getTypedRuleContext(TransitionContext, 0) as TransitionContext;
	}
	public AT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.AT, 0);
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_metadataTarget;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitMetadataTarget) {
			return visitor.visitMetadataTarget(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ViewPositionContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public VIEW(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.VIEW, 0);
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
	public POSITION(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.POSITION, 0);
	}
	public viewTarget_list(): ViewTargetContext[] {
		return this.getTypedRuleContexts(ViewTargetContext) as ViewTargetContext[];
	}
	public viewTarget(i: number): ViewTargetContext {
		return this.getTypedRuleContext(ViewTargetContext, i) as ViewTargetContext;
	}
	public AT_KEYWORD(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.AT_KEYWORD, 0);
	}
	public jsonObject(): JsonObjectContext {
		return this.getTypedRuleContext(JsonObjectContext, 0) as JsonObjectContext;
	}
	public RELATIVE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.RELATIVE, 0);
	}
	public PLUS(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.PLUS, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_viewPosition;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitViewPosition) {
			return visitor.visitViewPosition(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ViewRouteContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public VIEW(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.VIEW, 0);
	}
	public name_list(): NameContext[] {
		return this.getTypedRuleContexts(NameContext) as NameContext[];
	}
	public name(i: number): NameContext {
		return this.getTypedRuleContext(NameContext, i) as NameContext;
	}
	public ROUTE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.ROUTE, 0);
	}
	public AT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.AT, 0);
	}
	public ORTHOGONAL(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.ORTHOGONAL, 0);
	}
	public jsonArray(): JsonArrayContext {
		return this.getTypedRuleContext(JsonArrayContext, 0) as JsonArrayContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_viewRoute;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitViewRoute) {
			return visitor.visitViewRoute(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ViewSplinesContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public VIEW(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.VIEW, 0);
	}
	public name_list(): NameContext[] {
		return this.getTypedRuleContexts(NameContext) as NameContext[];
	}
	public name(i: number): NameContext {
		return this.getTypedRuleContext(NameContext, i) as NameContext;
	}
	public SPLINES(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.SPLINES, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_viewSplines;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitViewSplines) {
			return visitor.visitViewSplines(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ViewDetailContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public VIEW(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.VIEW, 0);
	}
	public name_list(): NameContext[] {
		return this.getTypedRuleContexts(NameContext) as NameContext[];
	}
	public name(i: number): NameContext {
		return this.getTypedRuleContext(NameContext, i) as NameContext;
	}
	public DETAIL(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.DETAIL, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_viewDetail;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitViewDetail) {
			return visitor.visitViewDetail(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ViewFusionContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public VIEW(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.VIEW, 0);
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
	public FUSION(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.FUSION, 0);
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
	public SINGLE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.SINGLE, 0);
	}
	public COPIES(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.COPIES, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_viewFusion;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitViewFusion) {
			return visitor.visitViewFusion(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ViewTargetContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
	public AT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.AT, 0);
	}
	public transition(): TransitionContext {
		return this.getTypedRuleContext(TransitionContext, 0) as TransitionContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_viewTarget;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitViewTarget) {
			return visitor.visitViewTarget(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class DecorationContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public DECORATE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.DECORATE, 0);
	}
	public decorationTarget(): DecorationTargetContext {
		return this.getTypedRuleContext(DecorationTargetContext, 0) as DecorationTargetContext;
	}
	public HIGHLIGHT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.HIGHLIGHT, 0);
	}
	public STRING_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPetriNetParser.STRING);
	}
	public STRING(i: number): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.STRING, i);
	}
	public NOTE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.NOTE, 0);
	}
	public SUMMARY(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.SUMMARY, 0);
	}
	public BESIDE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.BESIDE, 0);
	}
	public UNSHARED(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.UNSHARED, 0);
	}
	public LEFT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.LEFT, 0);
	}
	public RIGHT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.RIGHT, 0);
	}
	public SINGLE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.SINGLE, 0);
	}
	public COLOR_KEYWORD(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.COLOR_KEYWORD, 0);
	}
	public color(): ColorContext {
		return this.getTypedRuleContext(ColorContext, 0) as ColorContext;
	}
	public QUIET(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.QUIET, 0);
	}
	public SHOW(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.SHOW, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_decoration;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitDecoration) {
			return visitor.visitDecoration(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class DecorationTargetContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
	public transition(): TransitionContext {
		return this.getTypedRuleContext(TransitionContext, 0) as TransitionContext;
	}
	public AT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.AT, 0);
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_decorationTarget;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitDecorationTarget) {
			return visitor.visitDecorationTarget(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ExtensionsContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public EXTENSIONS(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.EXTENSIONS, 0);
	}
	public jsonObject(): JsonObjectContext {
		return this.getTypedRuleContext(JsonObjectContext, 0) as JsonObjectContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_extensions;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitExtensions) {
			return visitor.visitExtensions(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class DomainDeclarationContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public DOMAIN(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.DOMAIN, 0);
	}
	public color(): ColorContext {
		return this.getTypedRuleContext(ColorContext, 0) as ColorContext;
	}
	public DOT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.DOT, 0);
	}
	public fieldPath(): FieldPathContext {
		return this.getTypedRuleContext(FieldPathContext, 0) as FieldPathContext;
	}
	public domainValue_list(): DomainValueContext[] {
		return this.getTypedRuleContexts(DomainValueContext) as DomainValueContext[];
	}
	public domainValue(i: number): DomainValueContext {
		return this.getTypedRuleContext(DomainValueContext, i) as DomainValueContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_domainDeclaration;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitDomainDeclaration) {
			return visitor.visitDomainDeclaration(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class FieldPathContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public name_list(): NameContext[] {
		return this.getTypedRuleContexts(NameContext) as NameContext[];
	}
	public name(i: number): NameContext {
		return this.getTypedRuleContext(NameContext, i) as NameContext;
	}
	public DOT_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPetriNetParser.DOT);
	}
	public DOT(i: number): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.DOT, i);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_fieldPath;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitFieldPath) {
			return visitor.visitFieldPath(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class DomainValueContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.STRING, 0);
	}
	public NUMBER(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.NUMBER, 0);
	}
	public POSITIVE_INTEGER(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.POSITIVE_INTEGER, 0);
	}
	public ZERO(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.ZERO, 0);
	}
	public TRUE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.TRUE, 0);
	}
	public FALSE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.FALSE, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_domainValue;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitDomainValue) {
			return visitor.visitDomainValue(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class FinalDeclarationContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public FINAL(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.FINAL, 0);
	}
	public finalMarking_list(): FinalMarkingContext[] {
		return this.getTypedRuleContexts(FinalMarkingContext) as FinalMarkingContext[];
	}
	public finalMarking(i: number): FinalMarkingContext {
		return this.getTypedRuleContext(FinalMarkingContext, i) as FinalMarkingContext;
	}
	public COMMA_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPetriNetParser.COMMA);
	}
	public COMMA(i: number): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.COMMA, i);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_finalDeclaration;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitFinalDeclaration) {
			return visitor.visitFinalDeclaration(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class FinalMarkingContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public place_list(): PlaceContext[] {
		return this.getTypedRuleContexts(PlaceContext) as PlaceContext[];
	}
	public place(i: number): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, i) as PlaceContext;
	}
	public PLUS_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPetriNetParser.PLUS);
	}
	public PLUS(i: number): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.PLUS, i);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_finalMarking;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitFinalMarking) {
			return visitor.visitFinalMarking(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class InvariantDeclarationContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public INVARIANT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.INVARIANT, 0);
	}
	public invariantTerm_list(): InvariantTermContext[] {
		return this.getTypedRuleContexts(InvariantTermContext) as InvariantTermContext[];
	}
	public invariantTerm(i: number): InvariantTermContext {
		return this.getTypedRuleContext(InvariantTermContext, i) as InvariantTermContext;
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.STRING, 0);
	}
	public PLUS_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPetriNetParser.PLUS);
	}
	public PLUS(i: number): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.PLUS, i);
	}
	public EQUALS(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.EQUALS, 0);
	}
	public nonnegativeInteger(): NonnegativeIntegerContext {
		return this.getTypedRuleContext(NonnegativeIntegerContext, 0) as NonnegativeIntegerContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_invariantDeclaration;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitInvariantDeclaration) {
			return visitor.visitInvariantDeclaration(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class InvariantTermContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
	public positiveInteger(): PositiveIntegerContext {
		return this.getTypedRuleContext(PositiveIntegerContext, 0) as PositiveIntegerContext;
	}
	public STAR(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.STAR, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_invariantTerm;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitInvariantTerm) {
			return visitor.visitInvariantTerm(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ActorAssignmentContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public actorTarget(): ActorTargetContext {
		return this.getTypedRuleContext(ActorTargetContext, 0) as ActorTargetContext;
	}
	public ACTOR(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.ACTOR, 0);
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_actorAssignment;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitActorAssignment) {
			return visitor.visitActorAssignment(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ActorTargetContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public NET(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.NET, 0);
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
	public transition(): TransitionContext {
		return this.getTypedRuleContext(TransitionContext, 0) as TransitionContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_actorTarget;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitActorTarget) {
			return visitor.visitActorTarget(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ActorDeclarationContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
	public PERSON(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.PERSON, 0);
	}
	public SYSTEM(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.SYSTEM, 0);
	}
	public RECORD(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.RECORD, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_actorDeclaration;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitActorDeclaration) {
			return visitor.visitActorDeclaration(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class PlaceLivesContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
	public LIVES(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.LIVES, 0);
	}
	public IN(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.IN, 0);
	}
	public CEL(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.CEL, 0);
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.STRING, 0);
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_placeLives;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitPlaceLives) {
			return visitor.visitPlaceLives(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class PlaceReadsAsContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
	public READS(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.READS, 0);
	}
	public AS(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.AS, 0);
	}
	public CEL(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.CEL, 0);
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.STRING, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_placeReadsAs;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitPlaceReadsAs) {
			return visitor.visitPlaceReadsAs(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class PlaceKeptContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public place(): PlaceContext {
		return this.getTypedRuleContext(PlaceContext, 0) as PlaceContext;
	}
	public KEPT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.KEPT, 0);
	}
	public BY(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.BY, 0);
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
	public STARTS(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.STARTS, 0);
	}
	public AS(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.AS, 0);
	}
	public CEL(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.CEL, 0);
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.STRING, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_placeKept;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitPlaceKept) {
			return visitor.visitPlaceKept(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class TemplateDefinitionContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public templateReference(): TemplateReferenceContext {
		return this.getTypedRuleContext(TemplateReferenceContext, 0) as TemplateReferenceContext;
	}
	public COLON(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.COLON, 0);
	}
	public color(): ColorContext {
		return this.getTypedRuleContext(ColorContext, 0) as ColorContext;
	}
	public jsonValue(): JsonValueContext {
		return this.getTypedRuleContext(JsonValueContext, 0) as JsonValueContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_templateDefinition;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitTemplateDefinition) {
			return visitor.visitTemplateDefinition(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class AdditionalTemplateDefinitionContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public templateDefinition(): TemplateDefinitionContext {
		return this.getTypedRuleContext(TemplateDefinitionContext, 0) as TemplateDefinitionContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_additionalTemplateDefinition;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitAdditionalTemplateDefinition) {
			return visitor.visitAdditionalTemplateDefinition(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class TemplateReferenceContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public DOLLAR(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.DOLLAR, 0);
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_templateReference;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitTemplateReference) {
			return visitor.visitTemplateReference(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class ColorContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public name(): NameContext {
		return this.getTypedRuleContext(NameContext, 0) as NameContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_color;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitColor) {
			return visitor.visitColor(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class NameContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public IDENT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.IDENT, 0);
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.STRING, 0);
	}
	public INITIAL(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.INITIAL, 0);
	}
	public keyword(): KeywordContext {
		return this.getTypedRuleContext(KeywordContext, 0) as KeywordContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_name;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitName) {
			return visitor.visitName(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class MarkingNameContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public IDENT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.IDENT, 0);
	}
	public STRING(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.STRING, 0);
	}
	public keyword(): KeywordContext {
		return this.getTypedRuleContext(KeywordContext, 0) as KeywordContext;
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_markingName;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitMarkingName) {
			return visitor.visitMarkingName(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class KeywordContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public NET(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.NET, 0);
	}
	public COMPOSITION(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.COMPOSITION, 0);
	}
	public USE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.USE, 0);
	}
	public AS(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.AS, 0);
	}
	public WIRE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.WIRE, 0);
	}
	public SHARE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.SHARE, 0);
	}
	public REFINE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.REFINE, 0);
	}
	public BY(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.BY, 0);
	}
	public PORT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.PORT, 0);
	}
	public INPUT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.INPUT, 0);
	}
	public OUTPUT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.OUTPUT, 0);
	}
	public HANDLER(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.HANDLER, 0);
	}
	public GUARD(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.GUARD, 0);
	}
	public ORDER(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.ORDER, 0);
	}
	public TIMER(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.TIMER, 0);
	}
	public CLOCK(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.CLOCK, 0);
	}
	public BIND(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.BIND, 0);
	}
	public MATURITY(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.MATURITY, 0);
	}
	public PRIORITY(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.PRIORITY, 0);
	}
	public ACCEPTS(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.ACCEPTS, 0);
	}
	public CAPACITY_PER_COLOR_KEY(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.CAPACITY_PER_COLOR_KEY, 0);
	}
	public WEIGHT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.WEIGHT, 0);
	}
	public DATA(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.DATA, 0);
	}
	public PREDICATE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.PREDICATE, 0);
	}
	public CEL(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.CEL, 0);
	}
	public CORRELATE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.CORRELATE, 0);
	}
	public MARKING(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.MARKING, 0);
	}
	public DESCRIPTION(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.DESCRIPTION, 0);
	}
	public ANNOTATION(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.ANNOTATION, 0);
	}
	public EXTENSIONS(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.EXTENSIONS, 0);
	}
	public VIEW(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.VIEW, 0);
	}
	public POSITION(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.POSITION, 0);
	}
	public ROUTE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.ROUTE, 0);
	}
	public AT_KEYWORD(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.AT_KEYWORD, 0);
	}
	public RELATIVE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.RELATIVE, 0);
	}
	public ORTHOGONAL(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.ORTHOGONAL, 0);
	}
	public SPLINES(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.SPLINES, 0);
	}
	public DETAIL(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.DETAIL, 0);
	}
	public DECORATE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.DECORATE, 0);
	}
	public HIGHLIGHT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.HIGHLIGHT, 0);
	}
	public NOTE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.NOTE, 0);
	}
	public SUMMARY(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.SUMMARY, 0);
	}
	public QUIET(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.QUIET, 0);
	}
	public COLOR_KEYWORD(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.COLOR_KEYWORD, 0);
	}
	public BESIDE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.BESIDE, 0);
	}
	public FUSION(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.FUSION, 0);
	}
	public SINGLE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.SINGLE, 0);
	}
	public COPIES(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.COPIES, 0);
	}
	public LEFT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.LEFT, 0);
	}
	public RIGHT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.RIGHT, 0);
	}
	public UNSHARED(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.UNSHARED, 0);
	}
	public SHOW(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.SHOW, 0);
	}
	public DOMAIN(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.DOMAIN, 0);
	}
	public FINAL(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.FINAL, 0);
	}
	public INVARIANT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.INVARIANT, 0);
	}
	public ACTOR(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.ACTOR, 0);
	}
	public PERSON(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.PERSON, 0);
	}
	public SYSTEM(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.SYSTEM, 0);
	}
	public RECORD(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.RECORD, 0);
	}
	public LIVES(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.LIVES, 0);
	}
	public IN(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.IN, 0);
	}
	public READS(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.READS, 0);
	}
	public KEPT(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.KEPT, 0);
	}
	public STARTS(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.STARTS, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_keyword;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitKeyword) {
			return visitor.visitKeyword(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class JsonValueContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
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
		return this.getToken(VelocitronPetriNetParser.STRING, 0);
	}
	public NUMBER(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.NUMBER, 0);
	}
	public POSITIVE_INTEGER(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.POSITIVE_INTEGER, 0);
	}
	public ZERO(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.ZERO, 0);
	}
	public TRUE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.TRUE, 0);
	}
	public FALSE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.FALSE, 0);
	}
	public NULL(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.NULL, 0);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_jsonValue;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitJsonValue) {
			return visitor.visitJsonValue(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class JsonObjectContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public LBRACE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.LBRACE, 0);
	}
	public RBRACE(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.RBRACE, 0);
	}
	public STRING_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPetriNetParser.STRING);
	}
	public STRING(i: number): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.STRING, i);
	}
	public COLON_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPetriNetParser.COLON);
	}
	public COLON(i: number): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.COLON, i);
	}
	public jsonValue_list(): JsonValueContext[] {
		return this.getTypedRuleContexts(JsonValueContext) as JsonValueContext[];
	}
	public jsonValue(i: number): JsonValueContext {
		return this.getTypedRuleContext(JsonValueContext, i) as JsonValueContext;
	}
	public COMMA_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPetriNetParser.COMMA);
	}
	public COMMA(i: number): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.COMMA, i);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_jsonObject;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitJsonObject) {
			return visitor.visitJsonObject(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}


export class JsonArrayContext extends ParserRuleContext {
	constructor(parser?: VelocitronPetriNetParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public LBRACK(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.LBRACK, 0);
	}
	public RBRACK(): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.RBRACK, 0);
	}
	public jsonValue_list(): JsonValueContext[] {
		return this.getTypedRuleContexts(JsonValueContext) as JsonValueContext[];
	}
	public jsonValue(i: number): JsonValueContext {
		return this.getTypedRuleContext(JsonValueContext, i) as JsonValueContext;
	}
	public COMMA_list(): TerminalNode[] {
	    	return this.getTokens(VelocitronPetriNetParser.COMMA);
	}
	public COMMA(i: number): TerminalNode {
		return this.getToken(VelocitronPetriNetParser.COMMA, i);
	}
    public get ruleIndex(): number {
    	return VelocitronPetriNetParser.RULE_jsonArray;
	}
	// @Override
	public accept<Result>(visitor: VelocitronPetriNetVisitor<Result>): Result {
		if (visitor.visitJsonArray) {
			return visitor.visitJsonArray(this);
		} else {
			return visitor.visitChildren(this);
		}
	}
}
