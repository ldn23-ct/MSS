# AGENTS.md

## Project Overview

This repository is a Geant4-based Monte Carlo simulation project for studying multiple scattering signals in a slit-collimated gamma-ray imaging / detection setup.

The project goal is not only to remove multiple scattering as noise, but to analyze whether multiple-scattered photons can provide useful signal information under specific geometrical and material conditions.

Current target experiment:

- Phantom material: PMMA
- Defect: cylindrical air void
- Defect diameter: 10 mm
- Defect depth: 10 mm
- Main comparison condition: slit collimator aperture 1 mm vs 2 mm
- Main research question: whether a larger slit aperture increases the usable contribution of multiple-scattered photons and improves defect detectability.

## Primary Documents

Before making architectural or behavioral changes, read the following documents:

- `docs/spec.md`: project specification and simulation requirements
- `docs/architecture.md`: software architecture and module responsibilities
- `docs/decisions.md`: accepted design decisions and rationale
- `docs/milestones.md`: implementation milestones and task boundaries
- `README.md`: build, run, and usage instructions

If a requested change conflicts with these documents, do not silently override them. Explain the conflict and propose a minimal change.

## Development Environment

Assume the following environment unless explicitly updated:

- OS: Ubuntu 24.04
- Geant4: 11.2.0
- Build system: CMake
- Compiler: system default GCC on Ubuntu 24.04
- Language: C++ for simulation code
- Shell: bash

Do not introduce additional external dependencies unless necessary and explicitly justified.

## Build Commands

Use an out-of-source build.

Typical build procedure:

```bash
cmake -S . -B build
cmake --build build -j
```

Do not place generated build files in the repository root.

## Run Commands

Prefer macro-driven execution.

Example pattern:

```bash
./build/<executable_name> macros/<macro_name>.mac
```

If the executable name is unknown, inspect `CMakeLists.txt` before assuming it.

Default output directory:

```text
results/
```

## Testing and Validation

When modifying code, prefer the smallest relevant validation step.

At minimum, check:

1. The project configures successfully with CMake.
2. The project builds successfully.
3. A minimal macro run completes without crashing.
4. Output files are created in the expected directory.
5. Units in output files remain consistent:
   - length: mm
   - energy: keV

For geometry-related changes, ensure that geometry visualization or overlap checks are available when possible.

For multithreading changes, verify that:

- worker temporary outputs are merged correctly;
- temporary files are removed after successful merge in normal mode;
- temporary files are preserved in debug mode.

## Output Rules

The simulation output should focus on photons reaching the detector.

Each output row should represent one detected primary gamma-related record, depending on the current scoring design.

Default compact output should avoid unnecessary identifiers such as:

- `run_id`
- `event_id`
- `track_id`

These may be enabled only in debug mode if needed for diagnosis.

Default units:

- positions and lengths: mm
- energy: keV

Do not add unit columns unless the project specification is updated.

## Debug and Compact Modes

Default behavior:

- single-thread mode: debug-friendly behavior is acceptable;
- multithread mode: compact output is preferred by default.

Debug mode may preserve additional diagnostic information, including intermediate files and detailed identifiers.

Normal mode should keep output compact and remove temporary files after successful merging.

## Macro Command Expectations

Prefer exposing simulation configuration through Geant4 macro commands instead of hardcoding parameters.

Expected configurable items include:

- output directory
- debug / compact output mode
- air defect on / off switch
- source configuration
- detector or scoring configuration
- slit collimator aperture
- placeholder profile selection

Do not hardcode experimental parameters if they are part of the scan condition.

## Geometry Responsibilities

Geometry code should make the following components explicit and easy to locate:

- world volume
- PMMA phantom
- cylindrical air defect
- slit collimator
- detector boundary
- source geometry

Avoid mixing geometry construction, output writing, and run control logic in the same class unless the architecture document explicitly allows it.

## Source and Detector Rules

The source geometry should be implemented in code, not only described in comments.

The detector boundary and scoring region should also be implemented explicitly in code.

When modifying detector logic, preserve the meaning of detector strips / channels. In this project, detector strip position may correspond to different depth-related response regions, not merely arbitrary image pixels.

## Physics and Scattering Analysis

Do not treat all scattered photons as unwanted noise by default.

When adding analysis features, preserve the ability to distinguish at least:

- unscattered photons;
- single-scattered photons;
- multiple-scattered photons;
- total detected photons.

If exact scattering order is not yet implemented, add a clear placeholder or TODO rather than pretending the value is available.

## Coding Style

Use clear C++ class boundaries.

Prefer names that reflect physical or simulation meaning.

Avoid large, monolithic classes.

Do not perform broad refactoring unless the task explicitly asks for it.

When changing existing code:

1. Identify the smallest files that need modification.
2. Explain the intended change.
3. Modify only the necessary scope.
4. Build or provide the exact reason validation could not be run.

## Documentation Rules

When changing behavior, update the relevant document:

- project requirements -> `docs/spec.md`
- architecture/module boundaries -> `docs/architecture.md`
- accepted design choice -> `docs/decisions.md`
- implementation task status -> `docs/milestones.md`
- user-facing build/run instructions -> `README.md`

Do not let code and documentation drift apart.

## Forbidden Actions

Do not:

- rewrite the whole project without being asked;
- replace Geant4 with another simulation framework;
- introduce Python as a required runtime dependency for the Geant4 simulation core;
- add large external libraries without justification;
- hardcode scan parameters that should be controlled by macros;
- silently change output units;
- silently change output schema;
- remove debug information without preserving a debug mode;
- delete existing documentation unless explicitly instructed;
- assume detector strip index is equivalent to image pixel position without checking the project documents;
- fabricate physics results that were not produced by simulation.

## Task Execution Style

For implementation tasks, work in small steps.

Before coding, inspect the relevant files.

For nontrivial changes, provide:

1. files to be modified;
2. intended behavior change;
3. validation command;
4. expected output or acceptance condition.

If the task is ambiguous, ask for clarification before changing code.

If a requested change has multiple valid designs, prefer the design already recorded in `docs/decisions.md`.

## Commit / Patch Expectations

When presenting changes, summarize:

- what changed;
- why it changed;
- how to build;
- how to run;
- how to validate.

Avoid vague summaries such as "improved code" or "fixed issues".
