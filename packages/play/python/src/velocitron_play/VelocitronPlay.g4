// Formal syntax of one Velocitron `.play` statement.
//
// The line discipline is not in this grammar. A layout pass, specified in
// packages/spec/play-language.md ("Source text"), isolates each statement:
// a statement starts at column 0, a line that starts with a space or a tab
// continues it, a blank line continues it only when another continuation
// follows, `///` lines are Markdown prose, and `//` starts a comment.
// `parse_play` / `parsePlay` runs that pass, then parses each statement here.
//
// ANTLR 4.13.2. The grammar is action-free. JSON objects are syntax here;
// duplicate keys and the decoded values are checked while lowering.

grammar VelocitronPlay;

statement
    : header EOF
    | netSetting EOF
    | useSetting EOF
    | wireSetting EOF
    | shareSetting EOF
    | refineSetting EOF
    | markingSetting EOF
    | instanceSetting EOF
    | scopeSetting EOF
    | sequenceShow EOF
    | colorShow EOF
    | actorSetting EOF
    | boxSetting EOF
    | templateDecl EOF
    | pathDecl EOF
    | step EOF
    ;

header
    : PLAY singleName STRING?
    ;

netSetting
    : NET STRING
    ;

useSetting
    : USE STRING AS singleName
    ;

wireSetting
    : WIRE wireEnd ARROW wireEnd
    ;

shareSetting
    : SHARE wireEnd (TILDE wireEnd)+
    ;

refineSetting
    : REFINE singleName DOT transition BY singleName
    ;

markingSetting
    : MARKING name
    ;

instanceSetting
    : INSTANCE tokenExpr
    ;

scopeSetting
    : SCOPE (STEP | NEIGHBORS | SUBNET)
    ;

// `show sequence` is this rule, not a color. A color named sequence is quoted.
sequenceShow
    : SHOW SEQUENCE ONLY?
    ;

colorShow
    : SHOW colorNotSequence fieldPath (COMMA fieldPath)*
    ;

actorSetting
    : actorKind name
    ;

boxSetting
    : BOX name name+
    ;

templateDecl
    : DOLLAR singleName COLON color jsonObject
    ;

pathDecl
    : PATH singleName STRING? FROM AT singleName
    ;

step
    : label? stepBody STRING?
    ;

label
    : AT singleName COLON
    ;

actorKind
    : PERSON
    | SYSTEM
    | RECORD
    ;

stepBody
    : injectBody
    | updateBody
    | advanceBody
    | fireBody
    | expectBody
    | assumeBody
    ;

injectBody
    : INJECT place LEFT_ARROW tokenList
    ;

updateBody
    : UPDATE place LEFT_ARROW tokenExpr
    ;

// A missing or non-numeric time is still this rule; lowering reports SC103.
advanceBody
    : ADVANCE place? PLUS? timeValue?
    ;

fireBody
    : FIRE transition withClause* outputClause*
    ;

expectBody
    : EXPECT condition (COMMA condition)*
    ;

assumeBody
    : ASSUME transition GUARD truthValue
    | ASSUME PREDICATE STRING truthValue
    ;

withClause
    : WITH place (jsonObject | DOLLAR singleName | HASH NUMBER)
    ;

outputClause
    : ARROW place (NOTHING | PLUS jsonObject | tokenList)
    ;

condition
    : place EQ tokenList
    | place EMPTY
    | place COUNT NUMBER
    | place HAS tokenExpr
    | ENABLED transition+
    | NOT ENABLED transition+
    | NEXT transition
    | QUIESCENT
    ;

timeValue
    : NUMBER
    | DURATION
    | singleName
    ;

truthValue
    : TRUE
    | FALSE
    ;

tokenList
    : tokenExpr (COMMA tokenExpr)*
    ;

tokenExpr
    : DOLLAR singleName
    | jsonObject
    | color jsonObject
    ;

place
    : LPAREN qualifiedName RPAREN
    ;

transition
    : LBRACK qualifiedName RBRACK
    ;

wireEnd
    : singleName DOT place
    ;

fieldPath
    : qualifiedName
    | STRING
    ;

color
    : STRING
    | singleName
    ;

// Unquoted `sequence` is the sequence-diagram setting, not a color.
colorNotSequence
    : STRING
    | singleNameNotSequence
    ;

name
    : qualifiedName
    | STRING
    ;

qualifiedName
    : singleName (DOT singleName)*
    ;

singleName
    : IDENT
    | keyword
    ;

singleNameNotSequence
    : IDENT
    | keywordNotSequence
    ;

keyword
    : PLAY
    | NET
    | USE
    | AS
    | WIRE
    | SHARE
    | REFINE
    | BY
    | MARKING
    | INSTANCE
    | SCOPE
    | SHOW
    | SEQUENCE
    | ONLY
    | PERSON
    | SYSTEM
    | RECORD
    | BOX
    | PATH
    | FROM
    | INJECT
    | UPDATE
    | ADVANCE
    | FIRE
    | EXPECT
    | ASSUME
    | PREDICATE
    | GUARD
    | WITH
    | NOTHING
    | EMPTY
    | COUNT
    | HAS
    | ENABLED
    | NOT
    | NEXT
    | QUIESCENT
    | TRUE
    | FALSE
    | NULL
    | STEP
    | NEIGHBORS
    | SUBNET
    ;

keywordNotSequence
    : PLAY
    | NET
    | USE
    | AS
    | WIRE
    | SHARE
    | REFINE
    | BY
    | MARKING
    | INSTANCE
    | SCOPE
    | SHOW
    | ONLY
    | PERSON
    | SYSTEM
    | RECORD
    | BOX
    | PATH
    | FROM
    | INJECT
    | UPDATE
    | ADVANCE
    | FIRE
    | EXPECT
    | ASSUME
    | PREDICATE
    | GUARD
    | WITH
    | NOTHING
    | EMPTY
    | COUNT
    | HAS
    | ENABLED
    | NOT
    | NEXT
    | QUIESCENT
    | TRUE
    | FALSE
    | NULL
    | STEP
    | NEIGHBORS
    | SUBNET
    ;

jsonValue
    : jsonObject
    | jsonArray
    | STRING
    | NUMBER
    | TRUE
    | FALSE
    | NULL
    ;

jsonObject
    : LBRACE (STRING COLON jsonValue (COMMA STRING COLON jsonValue)*)? RBRACE
    ;

jsonArray
    : LBRACK (jsonValue (COMMA jsonValue)*)? RBRACK
    ;

PLAY: 'play';
NET: 'net';
USE: 'use';
AS: 'as';
WIRE: 'wire';
SHARE: 'share';
REFINE: 'refine';
BY: 'by';
MARKING: 'marking';
INSTANCE: 'instance';
SCOPE: 'scope';
SHOW: 'show';
SEQUENCE: 'sequence';
ONLY: 'only';
PERSON: 'person';
SYSTEM: 'system';
RECORD: 'record';
BOX: 'box';
PATH: 'path';
FROM: 'from';
INJECT: 'inject';
UPDATE: 'update';
ADVANCE: 'advance';
FIRE: 'fire';
EXPECT: 'expect';
ASSUME: 'assume';
PREDICATE: 'predicate';
GUARD: 'guard';
WITH: 'with';
NOTHING: 'nothing';
EMPTY: 'empty';
COUNT: 'count';
HAS: 'has';
ENABLED: 'enabled';
NOT: 'not';
NEXT: 'next';
QUIESCENT: 'quiescent';
TRUE: 'true';
FALSE: 'false';
NULL: 'null';
STEP: 'step';
NEIGHBORS: 'neighbors';
SUBNET: 'subnet';

AT: '@';
LPAREN: '(';
RPAREN: ')';
LBRACK: '[';
RBRACK: ']';
LBRACE: '{';
RBRACE: '}';
ARROW: '->';
LEFT_ARROW: '<-';
DOLLAR: '$';
HASH: '#';
PLUS: '+';
COLON: ':';
COMMA: ',';
DOT: '.';
TILDE: '~';
EQ: '==';

DURATION
    : UNIT 'd' (UNIT 'h')? (UNIT 'm')? (UNIT 's')?
    | UNIT 'h' (UNIT 'm')? (UNIT 's')?
    | UNIT 'm' UNIT 's'
    | UNIT 'm'
    | UNIT 's'
    ;

NUMBER
    : '-'? DIGITS ('.' DIGITS)? EXPONENT?
    ;

STRING
    : '"' (~["\\\r\n] | '\\' .)* '"'
    ;

IDENT
    : [A-Za-z_] [A-Za-z0-9_]*
    ;

LINE_COMMENT
    : '//' ~[\r\n]* -> skip
    ;

WS
    : [ \t\r\n]+ -> skip
    ;

UNSUPPORTED
    : .
    ;

fragment UNIT
    : DIGITS ('.' DIGITS)?
    ;

fragment DIGITS
    : [0-9]+
    ;

fragment EXPONENT
    : [eE] [+-]? DIGITS
    ;
