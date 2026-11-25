grammar VelocitronPetriNet;

document
    : netHeader?
      ( chain
      | placeDeclaration
      | transitionDeclaration
      | transitionHandler
      | transitionGuard
      | transitionTimer
      | transitionTimerBind
      | transitionTimerMaturity
      | transitionBindingName
      | transitionPriority
      | transitionOrder
      | chainOrder
      | placePort
      | placeAccepts
      | placeCapacity
      | arcWeight
      | arcData
      | arcPredicate
      | arcCorrelate
      | initialMarking
      | templateDefinition
      | namedMarking
      | metadataDescription
      | metadataAnnotation
      | viewPosition
      | viewRoute
      | viewSplines
      | viewDetail
      | decoration
      | extensions
      | domainDeclaration
      | finalDeclaration
      | invariantDeclaration
      | actorAssignment
      | actorDeclaration
      | placeLives
      | placeReadsAs
      | placeKept
      )* EOF
    | compositionHeader (compositionUse | compositionWire | compositionShare | compositionRefine | compositionFinal)* EOF
    ;

netHeader
    : NET name STRING?
    ;

compositionHeader
    : COMPOSITION name
    ;

compositionUse
    : USE STRING AS IDENT
    ;

compositionWire
    : WIRE IDENT DOT compositionPlace ARROW IDENT DOT compositionPlace
    ;

compositionShare
    : SHARE IDENT DOT compositionPlace (TILDE IDENT DOT compositionPlace)+
    ;

compositionRefine
    : REFINE IDENT DOT compositionTransition BY IDENT
    ;

compositionFinal
    : FINAL compositionFinalMarking (COMMA compositionFinalMarking)*
    ;

compositionFinalMarking
    : IDENT DOT compositionPlace (PLUS IDENT DOT compositionPlace)*
    ;

compositionPlace
    : LPAREN name (DOT name)* RPAREN
    ;

compositionTransition
    : LBRACK name (DOT name)* RBRACK
    ;

chain
    : chainHandle? chainNode (arcSegment chainNode)+
    ;

chainNode
    : place
    | transition
    ;

arcSegment
    : (HYPHEN color)? arcOperator
    ;

arcOperator
    : ARROW
    | READ_ARROW
    | INHIBIT_ARROW
    ;

additionalChain
    : chain
    ;

chainHandle
    : AT name COLON
    ;

place
    : LPAREN name RPAREN
    ;

transition
    : LBRACK name RBRACK
    ;

placeDeclaration
    : place
    ;

transitionDeclaration
    : transition
    ;

placePort
    : place PORT portDirection color
    ;

portDirection
    : INPUT
    | OUTPUT
    ;

transitionHandler
    : transition HANDLER STRING
    ;

additionalTransitionHandler
    : transitionHandler
    ;

transitionGuard
    : transition GUARD STRING
    ;

transitionTimer
    : transition TIMER CLOCK place CEL STRING
    ;

transitionTimerBind
    : transition TIMER BIND timerBindName place
    ;

transitionTimerMaturity
    : transition TIMER MATURITY CEL STRING
    ;

transitionBindingName
    : transition BIND name place
    ;

timerBindName
    : IDENT
    | INITIAL
    | keyword
    ;

transitionPriority
    : transition PRIORITY nonnegativeInteger
    ;

transitionOrder
    : transition ORDER positiveInteger
    ;

chainOrder
    : AT name ORDER positiveInteger
    ;

placeAccepts
    : place ACCEPTS LBRACK color (COMMA color)* RBRACK
    ;

placeCapacity
    : place CAPACITY_PER_COLOR_KEY jsonObject
    ;

arcWeight
    : AT name WEIGHT jsonValue
    ;

arcData
    : AT name DATA CEL STRING
    | AT name DATA jsonValue
    ;

arcPredicate
    : AT name PREDICATE predicateKind STRING
    ;

arcCorrelate
    : AT name CORRELATE CEL STRING
    ;

predicateKind
    : CEL
    | HANDLER
    ;

positiveInteger
    : POSITIVE_INTEGER
    ;

nonnegativeInteger
    : POSITIVE_INTEGER
    | ZERO
    ;

initialMarking
    : MARKING INITIAL place LEFT_ARROW markingValue
    ;

additionalInitialMarking
    : initialMarking
    ;

namedMarking
    : MARKING markingName place LEFT_ARROW markingValue
    ;

markingValue
    : (positiveInteger STAR)? templateReference
    | positiveInteger
    ;

metadataDescription
    : metadataTarget DESCRIPTION STRING
    ;

metadataAnnotation
    : metadataTarget ANNOTATION name jsonValue
    ;

metadataTarget
    : NET
    | place
    | transition
    | AT name
    ;

viewPosition
    : VIEW name POSITION viewTarget AT_KEYWORD jsonObject
    | VIEW name POSITION viewTarget RELATIVE viewTarget PLUS jsonObject
    ;

viewRoute
    : VIEW name ROUTE AT name ORTHOGONAL jsonArray
    ;

viewSplines
    : VIEW name SPLINES name
    ;

viewDetail
    : VIEW name DETAIL name
    ;

viewTarget
    : place (AT transition)?
    | transition
    ;

decoration
    : DECORATE decorationTarget HIGHLIGHT STRING?
    | DECORATE decorationTarget NOTE STRING
    | DECORATE decorationTarget SUMMARY STRING
    | DECORATE decorationTarget BESIDE (LEFT | RIGHT)? UNSHARED?
    | DECORATE COLOR_KEYWORD color QUIET
    | DECORATE COLOR_KEYWORD color SHOW STRING+
    ;

decorationTarget
    : place
    | transition
    | AT name
    ;

extensions
    : EXTENSIONS jsonObject
    ;

domainDeclaration
    : DOMAIN color DOT fieldPath domainValue+
    ;

fieldPath
    : name (DOT name)*
    ;

domainValue
    : STRING
    | NUMBER
    | POSITIVE_INTEGER
    | ZERO
    | TRUE
    | FALSE
    ;

finalDeclaration
    : FINAL finalMarking (COMMA finalMarking)*
    ;

finalMarking
    : place (PLUS place)*
    ;

invariantDeclaration
    : INVARIANT STRING? invariantTerm (PLUS invariantTerm)* (EQUALS nonnegativeInteger)?
    ;

invariantTerm
    : (positiveInteger STAR)? place
    ;

actorAssignment
    : actorTarget ACTOR name
    ;

actorTarget
    : NET
    | place
    | transition
    ;

actorDeclaration
    : (PERSON | SYSTEM | RECORD) name
    ;

placeLives
    : place LIVES IN (CEL STRING | name)
    ;

placeReadsAs
    : place READS AS CEL STRING
    ;

placeKept
    : place KEPT BY name STARTS AS CEL STRING
    ;

templateDefinition
    : templateReference COLON color jsonValue
    ;

additionalTemplateDefinition
    : templateDefinition
    ;

templateReference
    : DOLLAR name
    ;

color
    : name
    ;

name
    : IDENT
    | STRING
    | INITIAL
    | keyword
    ;

// A bare `initial` after `marking` is always the initial marking.
markingName
    : IDENT
    | STRING
    | keyword
    ;

keyword
    : NET
    | COMPOSITION
    | USE
    | AS
    | WIRE
    | SHARE
    | REFINE
    | BY
    | PORT
    | INPUT
    | OUTPUT
    | HANDLER
    | GUARD
    | ORDER
    | TIMER
    | CLOCK
    | BIND
    | MATURITY
    | PRIORITY
    | ACCEPTS
    | CAPACITY_PER_COLOR_KEY
    | WEIGHT
    | DATA
    | PREDICATE
    | CEL
    | CORRELATE
    | MARKING
    | DESCRIPTION
    | ANNOTATION
    | EXTENSIONS
    | VIEW
    | POSITION
    | ROUTE
    | AT_KEYWORD
    | RELATIVE
    | ORTHOGONAL
    | SPLINES
    | DETAIL
    | DECORATE
    | HIGHLIGHT
    | NOTE
    | SUMMARY
    | QUIET
    | COLOR_KEYWORD
    | BESIDE
    | LEFT
    | RIGHT
    | UNSHARED
    | SHOW
    | DOMAIN
    | FINAL
    | INVARIANT
    | ACTOR
    | PERSON
    | SYSTEM
    | RECORD
    | LIVES
    | IN
    | READS
    | KEPT
    | STARTS
    ;

jsonValue
    : jsonObject
    | jsonArray
    | STRING
    | NUMBER
    | POSITIVE_INTEGER
    | ZERO
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

NET
    : 'net'
    ;

COMPOSITION
    : 'composition'
    ;

USE
    : 'use'
    ;

AS
    : 'as'
    ;

WIRE
    : 'wire'
    ;

SHARE
    : 'share'
    ;

REFINE
    : 'refine'
    ;

BY
    : 'by'
    ;

PORT
    : 'port'
    ;

INPUT
    : 'input'
    ;

OUTPUT
    : 'output'
    ;

HANDLER
    : 'handler'
    ;

GUARD
    : 'guard'
    ;

ORDER
    : 'order'
    ;

TIMER
    : 'timer'
    ;

CLOCK
    : 'clock'
    ;

BIND
    : 'bind'
    ;

MATURITY
    : 'maturity'
    ;

PRIORITY
    : 'priority'
    ;

ACCEPTS
    : 'accepts'
    ;

CAPACITY_PER_COLOR_KEY
    : 'capacityPerColorKey'
    ;

WEIGHT
    : 'weight'
    ;

DATA
    : 'data'
    ;

PREDICATE
    : 'predicate'
    ;

CEL
    : 'cel'
    ;

CORRELATE
    : 'correlate'
    ;

MARKING
    : 'marking'
    ;

INITIAL
    : 'initial'
    ;

DESCRIPTION
    : 'description'
    ;

ANNOTATION
    : 'annotation'
    ;

EXTENSIONS
    : 'extensions'
    ;

VIEW
    : 'view'
    ;

POSITION
    : 'position'
    ;

ROUTE
    : 'route'
    ;

AT_KEYWORD
    : 'at'
    ;

RELATIVE
    : 'relative'
    ;

PLUS
    : '+'
    ;

EQUALS
    : '='
    ;

ORTHOGONAL
    : 'orthogonal'
    ;

SPLINES
    : 'splines'
    ;

DETAIL
    : 'detail'
    ;

DECORATE
    : 'decorate'
    ;

HIGHLIGHT
    : 'highlight'
    ;

NOTE
    : 'note'
    ;

SUMMARY
    : 'summary'
    ;

QUIET
    : 'quiet'
    ;

COLOR_KEYWORD
    : 'color'
    ;

BESIDE
    : 'beside'
    ;

LEFT
    : 'left'
    ;

RIGHT
    : 'right'
    ;

UNSHARED
    : 'unshared'
    ;

SHOW
    : 'show'
    ;

DOMAIN
    : 'domain'
    ;

FINAL
    : 'final'
    ;

INVARIANT
    : 'invariant'
    ;

ACTOR
    : 'actor'
    ;

PERSON
    : 'person'
    ;

SYSTEM
    : 'system'
    ;

RECORD
    : 'record'
    ;

LIVES
    : 'lives'
    ;

IN
    : 'in'
    ;

READS
    : 'reads'
    ;

KEPT
    : 'kept'
    ;

STARTS
    : 'starts'
    ;

TRUE
    : 'true'
    ;

FALSE
    : 'false'
    ;

NULL
    : 'null'
    ;


AT
    : '@'
    ;
LPAREN
    : '('
    ;

RPAREN
    : ')'
    ;

LBRACK
    : '['
    ;

RBRACK
    : ']'
    ;

LBRACE
    : '{'
    ;

RBRACE
    : '}'
    ;

HYPHEN
    : '-'
    ;

READ_ARROW
    : '->?'
    ;

INHIBIT_ARROW
    : '->0'
    ;

ARROW
    : '->'
    ;

LEFT_ARROW
    : '<-'
    ;

DOLLAR
    : '$'
    ;

STAR
    : '*'
    ;

COLON
    : ':'
    ;

COMMA
    : ','
    ;

DOT
    : '.'
    ;

TILDE
    : '~'
    ;

POSITIVE_INTEGER
    : [1-9] [0-9]*
    ;

ZERO
    : '0'
    ;


NUMBER
    : '-'? ('0' | [1-9] [0-9]*) ('.' [0-9]+)? ([eE] [+-]? [0-9]+)?
    ;

STRING
    : '"' (ESCAPE | ~["\\\u0000-\u001F])* '"'
    ;

IDENT
    : [A-Za-z_] [A-Za-z0-9_]*
    ;

LINE_COMMENT
    : '//' ~[\r\n]* -> skip
    ;

BLOCK_COMMENT
    : '/*' .*? '*/' -> skip
    ;

WS
    : [ \t\n]+ -> skip
    ;

CRLF
    : '\r\n' -> skip
    ;

UNSUPPORTED
    : .
    ;

fragment ESCAPE
    : '\\' (["\\/bfnrt] | 'u' HEX_DIGIT HEX_DIGIT HEX_DIGIT HEX_DIGIT)
    ;

fragment HEX_DIGIT
    : [0-9a-fA-F]
    ;
