# Layer allow-list

`layers.yaml` is the one list of who may import whom. `tools/layer_lint.py`
reads it and checks both languages. import-linter would only see Python, and
dependency-cruiser would only see TypeScript, so each would need its own
copy of this list. One stdlib scanner keeps the allow-list from drifting.
The lint fails when:

- a layer imports a layer that is not itself and not in its `allow` list
- a layer imports another layer through a submodule (`velocitron_engine.schema`,
  `@velocitron/engine/dist/...`) instead of that layer's package root
- a runtime import cycle exists inside a layer or across layers

`import` statements inside `if TYPE_CHECKING:` and TypeScript `import type` /
`export type` count as layer edges, so they still have to be in `allow`.
They do not close a runtime cycle. A module may type-check against another
module that imports it at runtime.

## Updating the list

When a new package lands:

1. Add a layer to `layers.yaml` with its Python module name and TypeScript
   package name.
2. Set `allow` to the layers it imports. Leave it empty when it imports none.
3. Run `python3 tools/layer_lint.py`.

There is no umbrella layer. A package imports another package only when
`allow` names it.
`journal` may import `engine` because a stored record and a replayed marking
use the engine's record and net types. `merge` and `viz` may import `engine`
because a merged or drawn net is the engine's net type in Python. `petrinet`
may import `spec`, `ir`, `grammar`, `cel`, `dsl`, `engine`, and `merge`: compiling a `.petrinet` document lowers
through `dsl`, resolves contribution IR, compiles CEL, and closes through
the JSON parser, which builds the engine net and calls `merge` for
composition ports. `dsl` may import `viz` because canonical emission renders JSON through it. The lowerer still vendors its parser. The engine takes a
CEL adapter instead of importing `velocitron_cel`. Nothing `petrinet`
depends on imports `petrinet`. `play-check` may import `analysis`, `cel`, `dsl`, `play`,
`engine`, `merge`, `petrinet`, and `viz`: it loads a play, compiles the net
the play names, and plays that net. Nothing `play-check` depends on
imports `play-check`. Nothing `journal`
depends on imports `journal`. `runtime` may import `cel`, `engine`, and
`journal`: intended waits compile CEL, and the run loop reserves firings
through the engine. A journal is injected. Record shapes live on the
engine, so the package does not import `journal` today. Nothing `runtime`
depends on imports `runtime`. `analysis` may import `cel`, `engine`,
`kernel`, `petrinet`, `merge`, and `runtime`: prove explores through the
engine, compiles CEL, loads a `.petrinet` document, merges a composition,
reads intended waits, and on the fast path hands the tables it fills to the
kernel. Nothing `analysis` depends on imports `analysis`. The TypeScript package reads a proof
report and does not explore a net. `kernel` imports no other Velocitron
layer: it is a compiled module that explores a net from the tables
`analysis` passes it, and knows nothing of nets, CEL or handlers. There is
no TypeScript package. `codegen` may import `dsl`, `engine`,
`merge`, `petrinet`, and `viz`: it lowers a `.petrinet` document, parses
the net, merges a composition, revalidates that net, and stamps
`net_sha256` with the viz canonical-JSON renderer. Nothing `codegen`
depends on imports `codegen`. The
TypeScript package names the synthesized-handler prefix and does not emit
a Python module. `netbase` may import `cel`, `codegen`, `engine`, and
`runtime`: `VelocitronNet.register_into` checks `net_sha256`, adapts
methods onto the engine registry, and builds `HandlerSpec` values for
async methods. Validation passes `get_default_adapter()` into
`velocitron_engine.Engine`, because that package requires an injected CEL
adapter. Nothing `netbase` depends on imports `netbase`. The TypeScript package re-exports `SYNTH_HANDLER`
and does not register a net. Generated modules still import
`velocitron_netbase`. `skill`
imports no other Velocitron layer. It exposes
`skill_root()`, the bundled authoring skill. That tree stays at
`skills/velocitron/` in this repository. There is no TypeScript package:
the shipped surface is the path, and the files are markdown and examples.
`velocitron_cli` passes `skill_root`. Nothing `skill` depends on
imports `skill`. `cli` may import `analysis`, `cel`, `codegen`, `dsl`, `engine`, `equiv`,
`explain`, `merge`, `petrinet`, `play`, `play-check`, `runtime`, `skill`, and `viz`:
the console commands validate, check, prove, generate, and draw through
those packages, revalidate a merged net with `validate_net`, and read the
skill through `skill_root` unless `configure(skill_source=...)` overrides
it. Nothing `cli` depends on imports `cli`. The TypeScript package names the subcommands and does not dispatch.
Canonical emission lives in `velocitron_dsl`. The CEL backend hint lives
in `velocitron_cel`. `explain_net` lives in `velocitron_explain`.
`compare`, `add_parser`, and `main` live in `velocitron_equiv`.
`velocitron_cli.main` installs those hooks.
`net_document`, `canonical_net_json`, `net_sha256`, and
`SYNTH_HANDLER` live in `velocitron_codegen`. `velocitron_netbase`
re-exports them so registration checks the same digest the generator
stamps. Generated modules import `velocitron_netbase`. `ReplayCursor`,
`ReplayBase`, and `replay_run` live in `velocitron_replay`. That driver
subclasses `velocitron_netbase.VelocitronNet` and calls `Engine.fire`.
`journal` only folds records into a marking. `runtime` does not call
`Engine.fire`. `replay` may import `cel`, `engine`, `journal`, `netbase`,
and `petrinet`: it injects `get_default_adapter()`, reads journal record
types, subclasses the registration base, and checks a recorded revision
with `parse_net`. Nothing `replay` depends on imports `replay`. Generated modules import `velocitron_replay`. The TypeScript package
names the seam and raises `ReplayUnavailableError`. It does not replay a
tape.

`properties` may import `cel`, `engine`, and `journal`: the declarative
property pass checks a marking handed to it and reconstructs intermediate
markings from journal records, compiling CEL for predicates. It does not
explore reachable markings. Nothing `properties` depends on imports
`properties`. The TypeScript package
names `checkMarking`, `checkReplay`, and `capacityProperties` and raises
`PropertiesUnavailableError`. It does not check a marking.
Callers import `velocitron_properties`.

`explain` may import `cel` and `engine`: `explain_net` quotes a validated
net and, when given a marking, asks `Engine.explain_enablement`. It passes
`get_default_adapter()` because the engine package requires an injected CEL
adapter. Nothing `explain` depends on imports `explain`. The TypeScript package names `explainNet` and raises
`ExplainUnavailableError`. It does not render prose. Callers import `velocitron_explain`, and the CLI installs the hook.

`equiv` may import `analysis`, `dsl`, `engine`, `merge`, and `petrinet`:
`compare` reads merged nets, `port_fusion_map` names fused places, and
`main` loads both sides with `velocitron_analysis.load`, catching
`PetrinetDslError` and `NetValidationError`. Nothing `equiv` depends on
imports `equiv`. The TypeScript package
names `compare` and `Equivalence` and raises `EquivUnavailableError`. It
does not compare nets. Callers import `velocitron_equiv`, and the CLI installs the command.

These three are siblings of `analysis`. Each allow list is that module's
imports. `analysis` stays the prover (`cel`, `engine`, `petrinet`, `merge`,
`runtime`). `properties` imports `journal` for record types. `explain`
imports `cel` and `engine` for enablement prose. `equiv` imports `analysis`
because it calls `load`. The DOT library stays a drawing package: explain
calls `Engine.explain_enablement`, and its TypeScript surface is an
unavailable marker.

Two trees are left out of the cycle check because the cycle is not ours to
unwind. Vendored celpy (`_vendor`) is third-party code that imports its
package while that package is still initializing. ANTLR's generated parser
and visitor import each other; edit the `.g4` and regenerate rather than
breaking that pair by hand. A cycle that leaves either of those trees, or
any cycle in code we write, still fails. `import` lines inside a function
do not close a runtime cycle. A relative import of a JSON fixture is data,
not a layer edge.

Run the lint from the repository root:

```bash
python3 tools/layer_lint.py
```

CI runs that command. It exits non-zero and prints each illegal edge.
