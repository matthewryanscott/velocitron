"""The hand-written base every generated net class extends.

The seven-step registration contract — hash, copy, register, validate,
record, adapt — is spelled on :class:`VelocitronNet`'s own docstring; a
merged ``Net`` has no single source text, so the hash works from the model.
``net_document``, ``canonical_net_json``, and ``net_sha256`` live in
``velocitron_codegen`` and are re-exported here, so a generated module and
registration check the same bytes.

Validation builds ``velocitron_engine.Engine`` with
``get_default_adapter()``. That package requires an injected CEL adapter
and does not select one. This module does not import ``velocitron``.

References: ADR 0058 (Decisions 2 and 3); ADR 0023 (a host may synthesize
handlers); ADR 0032 (binding_names); ADR 0037 (round-trips).
"""

from __future__ import annotations

import abc
import inspect
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from dataclasses import replace as _replace
from functools import update_wrapper
from typing import Any, ClassVar, cast

from velocitron_cel import CelAdapter, get_default_adapter
from velocitron_codegen import (
    SYNTH_HANDLER,
    canonical_net_json,
    net_document,
    net_sha256,
)
from velocitron_engine import (
    Arc,
    Engine,
    GuardHandler,
    GuardHandlerInput,
    HandlerNotFound,
    HandlerRegistry,
    Net,
    PredicateHandler,
    PredicateHandlerInput,
    ProduceTemplate,
    Token,
    Transition,
    TransitionHandler,
    TransitionHandlerInput,
    TransitionHandlerOutput,
    error_text,
    evaluate_produce_cel,
)
from velocitron_runtime import HandlerSpec, RuntimeContext, ScopeResolver

__all__ = [
    "SYNTH_HANDLER",
    "HashMismatch",
    "Registration",
    "VelocitronNet",
    "canonical_net_json",
    "handler_spec",
    "net_document",
    "net_sha256",
]

# A synthesized ref's spelling, owned by ``velocitron_codegen`` so the
# generator and registration share one prefix. The Engine rejects a
# transition name not declared in the net (UnknownTransitionError), so no
# user handler ref — which is always keyed by a DECLARED transition's name —
# can collide with the `velocitron:synth:` prefix. Colons do not appear in
# declared names.
SYNTH_PREFIX_LEN = len(SYNTH_HANDLER)


def _synth_ref(qualified_transition: str) -> str:
    """The synthesized ref for one qualified transition."""
    return f"{SYNTH_HANDLER}{qualified_transition}"


# ── The actor-filter handler (ADR 0058, Decision 2) ─────────────────────────


class _NotThisActor:
    """A never-answers transition handler for another actor's transition.

    Registered under the synthesized ref the net copy carries: it returns
    ``failed`` with ``error.type = "NotThisActor"`` and never raises, so a
    firing that should have happened elsewhere shows in the journal as a
    failure instead of silence. The Engine keys its output by the transition
    the net still declares, and the marking is unchanged.
    """

    def __init__(self, qualified: str) -> None:
        self._qualified = qualified

    def __call__(self, inp: TransitionHandlerInput) -> TransitionHandlerOutput:
        return TransitionHandlerOutput(
            status="failed",
            outputTokens={},
            error={
                "type": "NotThisActor",
                "message": f"{self._qualified} belongs to another actor",
            },
            metadata={},
        )


# ── The decorator ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _HandlerSpecInfo:
    lane: str | None
    blocking: bool
    scope: ScopeResolver | None


def handler_spec(
    *,
    lane: str | None = None,
    blocking: bool = False,
    scope: ScopeResolver | None = None,
) -> Callable[[Any], Any]:
    """Declare one async method's Runtime handler facts on the function.

    ``lane`` overrides the base's ``default_lane``; ``blocking`` and
    ``scope`` pass through to :class:`velocitron_runtime.HandlerSpec`
    (ADR 0058, Decision 3).
    """

    def decorate(function: Callable[..., Any]) -> Callable[..., Any]:
        function.__velocitron_handler_spec__ = _HandlerSpecInfo(  # type: ignore[attr-defined]
            lane, blocking, scope
        )
        return function

    return decorate


@dataclass(frozen=True)
class Registration:
    """One completed registration: the net copy, and the async spec table."""

    net: Net
    handler_specs: Mapping[str, HandlerSpec]
    # The registry the registration went into (the composition class's
    # build_registry creates one when the caller passes none, and the
    # Engine the caller constructs wants THIS instance; the replay's
    # driver reads it too). None when the caller passed their own.
    registry: HandlerRegistry | None = None


class HashMismatch(Exception):
    """The net's canonical hash differs from ``SOURCE_SHA256``.

    The class and the net disagree, so the net changed after the module was
    generated. Regenerate it with ``velocitron codegen``.
    """


class VelocitronNet(abc.ABC):
    """The base class of every generated net module.

    The generated module fills the ``ClassVar`` declarative tables; a
    hand-written subclass fills them the same way. ``register_into`` is the
    one entry point. The adapter's parameters are named after
    ``INPUT_PLACES[t]`` (the transition's consume and read source places in
    arc order) and read the tokens the Engine bound under them; the method
    returns ``{output_place: [tokens...]}`` and the adapter maps each to its
    merged destination by position against the copy's produce arcs. A raise
    from the method is a ``failed`` output, the marking unchanged, never a
    crash; an adapter's own error (a bad return shape, a lookup miss)
    propagates (ADR 0058, Decision 3).

    ``ASYNC`` registers per-method :class:`velocitron_runtime.HandlerSpec`
    values instead of per-transition registry handlers. Guards and
    predicates stay synchronous registry callables under ``ASYNC`` too
    (ADR 0058, Decision 1).
    """

    NET_NAME: ClassVar[str] = ""
    SOURCE: ClassVar[str] = ""
    SOURCE_SHA256: ClassVar[str] = ""
    HANDLER_REFS: ClassVar[dict[str, str]] = {}
    GUARD_REFS: ClassVar[dict[str, str]] = {}
    PREDICATE_REFS: ClassVar[dict[str, str]] = {}
    GENERATED_METHODS: ClassVar[dict[str, str]] = {}
    INPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {}
    OUTPUT_PLACES: ClassVar[dict[str, tuple[str, ...]]] = {}
    ASYNC: ClassVar[bool] = False

    # A class default too, so a subclass whose own ``__init__`` skips this
    # one still evaluates ``data cel`` (through the default adapter).
    cel_adapter: CelAdapter | None = None

    def __init__(self, *, cel_adapter: CelAdapter | None = None) -> None:
        self.cel_adapter = cel_adapter

    # ── the generated handlers' two fill helpers ─────────────────────

    def _carry(self, tokens: list[Token], color: str, destination_place: str) -> Token:
        """The carry rule as `play check` plays it (SC303), at run time.

        Copies the first token of ``color`` in ``tokens`` (the one consumed
        token of that color the generator proved at generation time).
        ``destination_place`` is the output place the carried token lands on;
        it names the error only. The generator emits the call only for an
        output whose carry was resolvable then; if the net changed since, the
        hash gate says so at registration.
        """
        for token in tokens:
            if token.type == color:
                return Token(type=token.type, data=deepcopy(token.data))
        raise KeyError(
            f"{destination_place} holds no {color} token to carry (the net "
            "changed since codegen; regenerate "
            f"{self.NET_NAME!r} with `velocitron codegen`)"
        )

    def _cel(self, cel: str, binding: Mapping[str, Sequence[Token]]) -> dict[str, Any]:
        """Evaluate a produce ``data cel`` through the Engine's own scope.

        Same evaluator, same ``{"binding": ...}`` scope (ADR 0058, Decision
        2), so a generated handler deposits what the Engine's fallback
        would. ``binding`` holds the method's parameters; the token data
        goes in keyed by local place name, the ADR 0017 map. The
        standalone leaf keys by place name (no ``binding_names`` to
        translate: the generator wrote the parameter names that way). An
        alias-carrying member translates through ``binding_names`` before
        calling, exactly as the adapter does. Raises on any evaluation
        error — the method's raise is a ``failed`` firing by the adapter's
        contract.
        """
        adapter = self.cel_adapter or get_default_adapter()
        binding_data = {
            place: [token.data for token in tokens] for place, tokens in binding.items()
        }
        result = evaluate_produce_cel(cel, binding_data, cel_adapter=adapter)
        if not isinstance(result, dict):
            raise TypeError(f"produce cel {cel!r} must yield a JSON object")
        return cast(dict[str, Any], result)

    # ── the adapter seam ─────────────────────────────────────────────

    def _serve(
        self,
        transition: str,
        inp: TransitionHandlerInput,
        method: Callable[..., Any],
    ) -> TransitionHandlerOutput:
        """Default adapter path: named arguments, method call, wrap.

        Raises of the method become ``failed``, carrying the raise itself
        as ``exception`` (in-process only: the journal records ``error``);
        the adapter's own work (argument binding, output translation) is
        outside the method's ``try``. Replay overrides this seam to answer
        from the tape.
        """
        arguments = self._method_arguments(transition, inp)
        try:
            outputs = method(**arguments)
        except Exception as error:  # noqa: BLE001 - a user method's raise
            return _failed(error)
        return self._translate_outputs(transition, outputs)

    async def _serve_async(
        self,
        transition: str,
        inp: TransitionHandlerInput,
        method: Callable[..., Any],
        context: RuntimeContext,
    ) -> TransitionHandlerOutput:
        """The ASYNC adapter path: awaits the method with ``context=ctx``."""
        arguments = self._method_arguments(transition, inp)
        try:
            outputs = await method(**arguments, context=context)
        except Exception as error:  # noqa: BLE001 - a user method's raise
            return _failed(error)
        return self._translate_outputs(transition, outputs)

    def _method_arguments(
        self, transition: str, inp: TransitionHandlerInput
    ) -> dict[str, Any]:
        """The method's keyword arguments from ``inputTokens``.

        ``transition`` names the COPY's transition. Under an alias the copy's
        transition carries the merged ``binding_names``, so each parameter
        ``p`` reads ``inputTokens[binding_names[p]]``; standalone, the key is
        the place itself. A key absent from ``inputTokens`` is ``[]`` — the
        adapter's translation of the engine's contract, not data.
        """
        binding_names = self._transition(transition).binding_names
        input_tokens = inp["inputTokens"]
        arguments: dict[str, Any] = {}
        for place in self.INPUT_PLACES[self._local_key(transition)]:
            key = binding_names.get(place, place) if binding_names else place
            arguments[place] = list(input_tokens.get(key, []))
        return arguments

    def _local_key(self, transition: str) -> str:
        """The class-tables' key for a copy's transition: the local name.

        The generated tables (``INPUT_PLACES``, ``OUTPUT_PLACES``,
        ``GENERATED_METHODS``) key by the member's own transition names; a
        merged copy's names are ``<alias>.<t>``, so the alias prefix comes
        off. A standalone net's names are already local.
        """
        return _local_name(transition, getattr(self, "_alias", None))

    def _translate_outputs(
        self, transition: str, outputs: Any
    ) -> TransitionHandlerOutput:
        """Map the method's ``{local place: [tokens]}`` to merged names.

        ``OUTPUT_PLACES[t][i]`` pairs with the ``i``-th produce arc of the
        copy's transition in arc order; two local places that map to one
        merged place concatenate. The mapping's own errors (a bad return
        shape above all) propagate — the adapter's bug, never a firing
        outcome. Returns the ``completed`` output for the Engine.
        """
        if not isinstance(outputs, Mapping):
            raise TypeError(
                f"{transition}'s handler must return a dict of output places"
            )
        # The generated TypedDict return declares {place: [Token, ...]};
        # the adapter trusts the annotation (a raise from a deposit check
        # is the Engine's contract surface, not this adapter's).
        outputs_typed = cast(Mapping[str, list[Token]], outputs)
        merged: dict[str, list[Token]] = {}
        local = self._local_key(transition)
        produce_arcs = self._produce_arcs(transition)
        if outputs:
            if len(produce_arcs) != len(self.OUTPUT_PLACES[local]):
                raise ValueError(
                    f"OUTPUT_PLACES[{local}] does not match the net's produce arcs"
                )
            for index, (_, template) in enumerate(produce_arcs):
                local_place = self.OUTPUT_PLACES[local][index]
                raw_tokens = outputs_typed.get(local_place, [])
                merged.setdefault(template.destination, []).extend(raw_tokens)
        return {
            "status": "completed",
            "outputTokens": merged,
            "error": None,
            "metadata": {},
        }

    def _produce_arcs(self, transition: str) -> tuple[tuple[Arc, ProduceTemplate], ...]:
        produced: list[tuple[Arc, ProduceTemplate]] = []
        for arc in self._net.arcs:
            if arc.from_transition == transition and arc.produce is not None:
                produced.append((arc, arc.produce))
        return tuple(produced)

    def _transition(self, transition: str) -> Transition:
        """The copy's transition named ``transition``."""
        for candidate in self._net.transitions:
            if candidate.name == transition:
                return candidate
        raise KeyError(transition)

    def _transition_adapter(
        self, transition: Transition, method: Callable[..., Any]
    ) -> TransitionHandler:
        """The sync Engine adapter: one closure per registered method."""
        qualified = transition.name

        def real_adapter(inp: TransitionHandlerInput) -> TransitionHandlerOutput:
            return self._serve(qualified, inp, method)

        update_wrapper(real_adapter, method)
        return real_adapter

    def _guard_adapter(self, method_name: str, ref: str) -> GuardHandler:
        """The guard adapter: same keyword parameters as ``fire_<t>``.

        Guards and predicates are plain ``def`` callables whatever ``ASYNC``
        says (ADR 0058, Decision 1). A ref whose method the class does not
        define raises ``HandlerNotFound`` at registration — the sandwich
        rule's earliest seam (the spec's step 5 case 9). An ``async def``
        guard method is rejected: a guard awaited lazily would silently
        turn every awaitable truthy.
        """
        method = getattr(self, method_name, None)
        if method is None:
            raise HandlerNotFound(ref)
        if inspect.iscoroutinefunction(method):
            raise TypeError(f"guard {method_name} must be a plain def, not async def")

        def adapter(inp: GuardHandlerInput) -> bool:
            serve_guard = getattr(self, "_serve_guard", None)
            if serve_guard is not None:
                # The replay mixin's seam: answer from the tape or the
                # live class; the recorded method is not called. The
                # mixin's own raises sit outside the method ``try``.
                return serve_guard(
                    inp["firingContext"]["firingId"],
                    ref,
                    inp["transitionId"],
                    inp,
                )
            arguments = self._method_arguments(inp["transitionId"], inp)
            return bool(method(**arguments))

        update_wrapper(adapter, method, updated=())
        adapter.__qualname__ = f"{type(self).__qualname__}.{method_name}"
        adapter.__name__ = method_name
        return adapter

    def _predicate_adapter(self, method_name: str, ref: str) -> PredicateHandler:
        """The predicate adapter: ``predicate_<name>(token) -> bool``.

        The same missing-method and async-def rules as the guard adapter.
        A raise from the method itself reads as ``False`` — the engine's
        symmetric degradation for any predicate handler failure; the trace
        card makes the raise visible.
        """
        method = getattr(self, method_name, None)
        if method is None:
            raise HandlerNotFound(ref)
        if inspect.iscoroutinefunction(method):
            raise TypeError(
                f"predicate {method_name} must be a plain def, not async def"
            )

        def adapter(inp: PredicateHandlerInput) -> bool:
            serve_predicate = getattr(self, "_serve_predicate", None)
            if serve_predicate is not None:
                # The replay mixin's seam: answer from the tape or the
                # live class; the recorded method is not called. The
                # mixin's own raises sit outside the method ``try``.
                return serve_predicate(inp["firingContext"]["firingId"], ref, inp)
            return bool(method(inp["token"]))

        update_wrapper(adapter, method, updated=())
        adapter.__qualname__ = f"{type(self).__qualname__}.{method_name}"
        adapter.__name__ = method_name
        return adapter

    # ── registration ────────────────────────────────────────────────

    def _validate_registration(
        self, engine: Engine, copy: Net, alias: str | None
    ) -> None:
        """Step 5: validate (ADR 0009's sandwich rule, scoped).

        Standalone sync: the Engine's own ``validate`` — every ref of the
        copy is either an adapter or the never-answers handler, so it
        passes and still catches a forgotten guard or predicate. With an
        ``alias`` or under ``ASYNC`` (the transition handlers live in the
        spec table, not the registry), walk this member's slice the same
        way: its guards, its named predicate handlers, and — sync with an
        alias — its own transitions' handler refs.
        """
        if alias is None and not self.ASYNC:
            engine.validate(copy)
            return
        prefix = None if alias is None else f"{alias}."
        for transition in copy.transitions:
            if transition.guard is not None:
                engine.registry.resolve_guard(transition.guard)
            if (
                (prefix is None or transition.name.startswith(prefix))
                and not self.ASYNC
                and transition.handler is not None
            ):
                engine.registry.resolve_transition(transition.handler)
        for arc in copy.arcs:
            if arc.consume is None or arc.consume.predicate is None:
                continue
            if arc.consume.predicate.handler is not None:
                engine.registry.resolve_predicate(arc.consume.predicate.handler)

    def _net_copy(self, net: Net, alias: str | None) -> Net:
        """The fresh in-memory copy with one synthesized ref per handlerless
        transition of this class's slice.

        Standalone, the slice is every transition; with ``alias``, the
        ``<alias>.<t>`` ones. The spelling ``velocitron:synth:<qualified
        transition>`` cannot collide with a user ref (above). The whole net
        is copied either way, so the composition class can thread one copy
        through every member (ADR 0058, Decision 4).
        """
        prefix = None if alias is None else f"{alias}."
        transitions = list(net.transitions)
        for index, transition in enumerate(transitions):
            if transition.handler is not None:
                continue
            if prefix is not None and not transition.name.startswith(prefix):
                continue
            transitions[index] = _replace(
                transition, handler=_synth_ref(transition.name)
            )
        return _replace(net, transitions=transitions)

    def _check_shared_refs(self, transitions: Sequence[Transition]) -> None:
        """One ref, one transition: two sharers refuse registration."""
        owners: dict[str, str] = {}
        for transition in transitions:
            if transition.handler is None:
                continue
            previous = owners.setdefault(transition.handler, transition.name)
            if previous != transition.name:
                raise ValueError(
                    f"handler ref '{transition.handler}' is claimed by two "
                    f"transitions: {previous!r} and {transition.name!r}"
                )

    def register_into(
        self,
        registry: HandlerRegistry,
        net: Net,
        *,
        alias: str | None = None,
        default_lane: str | None = None,
        journal: object | None = None,
        validate: bool = True,
    ) -> Registration:
        """Register this class's methods for ``net``; return the registration.

        With ``alias``, ``net`` is a merged composition net and this class
        registers its ``<alias>.<t>`` transitions only: parameter names
        translate through the merged ``binding_names``, and the hash check
        is skipped (the composition class hashed the merged net; the
        member-file hash moved to generation time, ADR 0058, Decision 4).
        """
        if alias is None:
            actual = net_sha256(net)
            if actual != self.SOURCE_SHA256:
                raise HashMismatch(
                    f"SOURCE_SHA256 of {type(self).__name__} does not match the net "
                    f"{net.name}: regenerate with `velocitron codegen`"
                )

        # The copy: per call, fresh — the composition class threads one copy
        # through every member and validates only the outermost, so two
        # registrations never share synthesized refs.
        copy = self._net_copy(net, alias)
        transitions = _transitions_of(copy, alias)

        self._check_shared_refs(transitions)

        # The adapter's translation tables key by the copy's qualified
        # transition names; the instance serves one net copy per registration.
        self._net = copy
        self._alias = alias

        specs: dict[str, HandlerSpec] = {}
        for transition in transitions:
            local = _local_name(transition.name, alias)
            ref = transition.handler
            assert ref is not None  # the copy always carries a handler
            # A synthesized ref is not a user ref the class declares; the
            # method comes from GENERATED_METHODS alone.
            user_ref = None if ref.startswith(SYNTH_HANDLER) else ref
            method_name = self.HANDLER_REFS.get(user_ref or "")
            if method_name is None:
                method_name = self.GENERATED_METHODS.get(local)
            if method_name is None:
                # Another actor's: one synthesized ref, never answers. The
                # Runtime's own spec table never contains it; the
                # composition class builds that table from its members'
                # handler_specs, which name only resolved methods.
                registry.register_transition(ref, _NotThisActor(transition.name))
                continue
            method = getattr(self, method_name)
            wrapper = method
            if self.ASYNC:
                specs[ref] = _spec_for_method(self, transition, method, default_lane)
            else:
                registry.register_transition(
                    ref, self._transition_adapter(transition, wrapper)
                )

        for guard_ref, guard_name in self.GUARD_REFS.items():
            registry.register_guard(
                guard_ref, self._guard_adapter(guard_name, guard_ref)
            )
        for predicate_ref, predicate_name in self.PREDICATE_REFS.items():
            registry.register_predicate(
                predicate_ref, self._predicate_adapter(predicate_name, predicate_ref)
            )

        # One shared place declared three times is the composition class's
        # concern (ADR 0058 open item 3); the base reads the copy as given.

        if validate:
            engine = Engine(registry, cel_adapter=get_default_adapter())
            self._validate_registration(engine, copy, alias)

        if journal is not None:
            record_net_revision = getattr(journal, "record_net_revision", None)
            if callable(record_net_revision):
                record_net_revision(net_document(copy))

        return Registration(net=copy, handler_specs=specs, registry=registry)


def _failed(error: Exception) -> TransitionHandlerOutput:
    """The ``failed`` output for a method's raise: ``error`` names it (with
    its notes) for the journal, and ``exception`` keeps it for a strict
    advance."""
    return {
        "status": "failed",
        "outputTokens": {},
        "error": {"type": type(error).__name__, "message": error_text(error)},
        "metadata": {},
        "exception": error,
    }


def _transitions_of(net: Net, alias: str | None) -> list[Transition]:
    if alias is None:
        return list(net.transitions)
    prefix = f"{alias}."
    found = [t for t in net.transitions if t.name.startswith(prefix)]
    if not found:
        raise ValueError(f"net {net.name} has no transitions under '{alias}.'")
    return found


def _local_name(qualified: str, alias: str | None) -> str:
    if alias is None:
        return qualified
    prefix = f"{alias}."
    if not qualified.startswith(prefix):
        raise ValueError(f"transition {qualified!r} is not under alias {alias!r}")
    return qualified[len(prefix) :]


def _method_spec(method: Callable[..., Any]) -> _HandlerSpecInfo | None:
    return getattr(method, "__velocitron_handler_spec__", None)


def _spec_for_method(
    instance: VelocitronNet,
    transition: Transition,
    method: Callable[..., Any],
    default_lane: str | None,
) -> HandlerSpec:
    """One ``HandlerSpec`` per method (ADR 0058, Decision 3).

    The lane comes from the method's ``@handler_spec(lane=...)``, else the
    caller's ``default_lane``, else ``ValueError`` — the Runtime refuses a
    spec whose lane it does not know, and a missing lane is the same
    refusal one step earlier, naming the method. ``blocking`` and ``scope``
    pass through.
    """
    declared = _method_spec(method)
    lane = None
    blocking = False
    scope: ScopeResolver | None = None
    if declared is not None:
        lane = declared.lane
        blocking = declared.blocking
        scope = declared.scope
    if lane is None:
        lane = default_lane
    if lane is None:
        raise ValueError(
            f"handler {method.__qualname__} of transition {transition.name!r} "
            "has no lane: decorate the method with @handler_spec(lane=...) "
            "or pass default_lane="
        )
    qualified = transition.name

    async def async_adapter(
        inp: TransitionHandlerInput, ctx: RuntimeContext
    ) -> TransitionHandlerOutput:
        return await instance._serve_async(  # pyright: ignore[reportPrivateUsage]
            qualified, inp, method, ctx
        )

    update_wrapper(async_adapter, method)
    return HandlerSpec(handler=async_adapter, lane=lane, scope=scope, blocking=blocking)
