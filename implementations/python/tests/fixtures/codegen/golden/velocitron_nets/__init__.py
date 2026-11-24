"""The generated member modules' package (empty on purpose).

The single-net and composition codegen goldens live here so the
composition modules' `from velocitron_nets.<stem> import ...` imports
resolve the same way a real deployment's do (the members in one package
beside the composition module). Nothing is imported by runtime code.
"""