# TypeScript integration tests

`implementations/typescript` is the private workspace package
`@velocitron/typescript-tests`. It is not a library and it does not publish
`@velocitron/core`.

The Vitest suite imports `@velocitron/petrinet`, `@velocitron/engine`,
`@velocitron/runtime`, `@velocitron/dsl`, `@velocitron/cel`, and
`@velocitron/journal`. `Engine` comes from `@velocitron/runtime`, which
fills `createDefaultCelAdapter()` when the caller omits `celAdapter`.

Schema generators in `tools/` write the Ajv validators under
`packages/petrinet/typescript/src/generated/`. From the repository root:

```console
pnpm install
pnpm --filter @velocitron/typescript-tests test
pnpm --filter @velocitron/typescript-tests typecheck
```
