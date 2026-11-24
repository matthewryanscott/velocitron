# `packages/merge`

The composition merge transform, in two language packages:

- [`python/`](python/) — distribution `velocitron-merge`, import `velocitron_merge`
- [`typescript/`](typescript/) — package `@velocitron/merge` (`"private": true`)

`merge_nets` / `mergeNets` alias-qualifies already-parsed nets and fuses
wired ports and shares into one net. `port_fusion_map` / `portFusionMap`
names the fused place of each wired or shared member.
`merge_composition` / `mergeComposition` runs that transform for a
composition whose nets are already parsed.

The directory is `packages/merge`, not `packages/composition-merge`. The
sibling packages are one word (`ir`, `grammar`, `cel`, `dsl`), and this is
the only merge transform in the runtime.

Nothing here is published to npm or PyPI. Consumers install a git
subdirectory of `circuitmeridian/velocitron`. Each language
README has the install snippet.

`velocitron_petrinet` calls this package and then revalidates the merged
net. `python3 tools/merge_package.py check` fails if a retired facade
grows the transform back.

Parsing, `parse_composition` validation, CEL compilation, and that
revalidation ship in `packages/petrinet`. Play checking ships in
`packages/play-check`. The firing engine ships in `packages/engine` and
the net render library ships in `packages/viz`. The net and composition
values are the already-parsed shapes the transform walks. Contribution IR
(`packages/ir`) is a different document, so this package does not depend
on `velocitron-ir` or `@velocitron/ir`.
