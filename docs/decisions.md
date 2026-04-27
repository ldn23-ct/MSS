# decisions.md

## Purpose

This document records accepted design decisions for the BackscatterSim project.

It is intended to prevent design drift when using Codex to generate or modify code. It should not duplicate the full project specification. The authoritative functional requirements remain in `spec.md`; this file records why key implementation choices were made and what Codex must not change without an explicit spec update.

Use this file together with:

- `spec.md` for project requirements and acceptance criteria.
- `architecture.md` for module boundaries and data flow.
- `milestones.md` for staged implementation order.

---

## Decision status labels

| Status | Meaning |
|---|---|
| Accepted | This decision is active and should be followed. |
| Proposed | This decision is being considered but is not yet binding. |
| Superseded | This decision has been replaced by a later decision. |
| Deferred | This decision is intentionally postponed. |

---

## Global rule for Codex

When implementation choices are ambiguous, Codex must follow this priority order:

1. `spec.md`
2. `decisions.md`
3. `architecture.md`
4. `milestones.md`
5. Existing code, if it does not conflict with the documents above

Codex must not silently change any accepted decision in this file. If a change is necessary, it must be handled as a documentation change first, then an implementation change.

---

## Decision index

| ID | Decision | Status |
|---|---|---|
| D001 | Keep the first version focused on event-level Monte Carlo data generation | Accepted |
| D002 | Use a fixed right-handed coordinate system with PMMA depth along +z | Accepted |
| D003 | Model the detector as an ideal counting plane | Accepted |
| D004 | Define collimator geometry through an external CSV profile file | Accepted |
| D005 | Use `G4ExtrudedSolid` for the two tungsten collimator jaws | Accepted |
| D006 | Use `G4EmLivermorePhysics` with a global production cut of 0.1 mm | Accepted |
| D007 | Define one event as one primary gamma | Accepted |
| D008 | Support mono and spectrum energy modes, but keep the source geometry fixed in version 1 | Accepted |
| D009 | Track only primary gamma scattering history inside PMMA | Accepted |
| D010 | Output only detector-reaching primary gamma events | Accepted |
| D011 | Keep CSV schemas stable and encode run metadata in filenames | Accepted |
| D012 | Use per-thread temporary CSV files and master-side merge for multi-thread output | Accepted |
| D013 | Use macro commands for runtime configuration, but keep selected geometry constants fixed | Accepted |
| D014 | Fail fast on invalid collimator profile data | Accepted |
| D015 | Keep module responsibilities narrow and separated | Accepted |
| D016 | Implement the project milestone by milestone | Accepted |
| D017 | Defer reconstruction, detector response, and post-processing analysis | Accepted |

---

## D001: Keep the first version focused on event-level Monte Carlo data generation

**Status:** Accepted  
**Date:** 2026-04-27

### Context

The project is intended to support analysis of gamma backscatter behavior under different collimator opening/profile conditions. The first version must produce data suitable for later statistical analysis, not perform the full analysis pipeline inside the Geant4 program.

### Decision

The first version will only generate event-level CSV data for detector-reaching primary gamma particles.

It will not include:

- image reconstruction,
- real detector material response,
- detector energy deposition modeling,
- post-processing analysis scripts,
- batch scanning over all profiles,
- full scatter trajectory output.

### Rationale

Keeping version 1 limited makes the project easier to implement, test, and debug. The Geant4 application should first establish a reliable physical event generator before analysis or reconstruction code is added.

### Consequences

- The output CSV becomes the boundary between simulation and downstream analysis.
- Later analysis scripts should read CSV files rather than depend on Geant4 runtime internals.
- Codex must not add reconstruction or detector-response features unless the specification is updated first.

---

## D002: Use a fixed right-handed coordinate system with PMMA depth along +z

**Status:** Accepted  
**Date:** 2026-04-27

### Context

The simulation contains a source, PMMA phantom, air defect, collimator, and detector plane. Incorrect axis conventions would propagate into geometry construction, source direction sampling, detector crossing logic, and later analysis.

### Decision

Use a right-handed coordinate system:

- `+z` points from the PMMA front surface into the PMMA interior.
- `x` is the main transverse direction and corresponds to the detector-side post-processing coordinate.
- `y` is the slit/jaw extrusion direction and is not the main analysis dimension.
- Source and detector are located on the `z < 0` side.
- The PMMA front surface is at `z = 0`.

### Rationale

This convention makes depth interpretation explicit and keeps detector crossing tests simple: detected backscattered gamma travels toward decreasing `z` and crosses the detector plane at `z = -73 mm`.

### Consequences

- Geometry, source sampling, and detector crossing code must use this convention consistently.
- Codex must not swap depth to another axis.
- Any future plotting or analysis script should treat `z` as PMMA depth.

---

## D003: Model the detector as an ideal counting plane

**Status:** Accepted  
**Date:** 2026-04-27

### Context

The current research question concerns PMMA scattering history and detector-reaching gamma statistics, not detector material response.

### Decision

The detector will be implemented as an ideal plane at:

```text
z = -73 mm
x = [53, 161] mm
y = [-50, 50] mm
```

The detector will not be modeled as a real scintillator, semiconductor, or energy-depositing physical volume in version 1.

### Rationale

An ideal plane isolates the transport and scattering problem from detector response modeling. This reduces implementation complexity and avoids mixing detector-response effects into the first-stage scattering statistics.

### Consequences

- Detector hit detection is based on geometric boundary crossing, not sensitive detector energy deposition.
- `det_energy` means gamma kinetic energy at plane crossing, not deposited energy.
- Codex must not add detector material response or sensitive detector logic unless version 1 scope changes.

---

## D004: Define collimator geometry through an external CSV profile file

**Status:** Accepted  
**Date:** 2026-04-27

### Context

The project needs to compare different collimator jaw profiles/openings. Hard-coding every geometry into C++ would make profile comparison difficult and error-prone.

### Decision

The collimator geometry is defined by an external CSV file containing profile groups. Each selected profile contains:

- one `profile_id`,
- two jaws: `jaw_0` and `jaw_1`,
- five vertices per jaw,
- each vertex defined by global `(x_mm, z_mm)` coordinates.

Version 1 selects one profile per run via macro command:

```text
/geometry/collimatorProfileFile data/collimator_profiles.csv
/geometry/collimatorProfileId P001
```

### Rationale

External CSV profiles allow geometry variation without recompilation. Single-profile selection keeps version 1 simpler than full automatic batch scanning.

### Alternatives considered

| Alternative | Reason not selected for version 1 |
|---|---|
| Hard-code jaw vertices in C++ | Makes profile comparison cumbersome. |
| Generate real jaw profiles inside C++ | Adds geometry-generation logic outside current scope. |
| Automatically iterate over all profiles | Useful later, but complicates run management and output naming. |

### Consequences

- `CollimatorProfileReader` is responsible for parsing and validating profile data.
- `CollimatorBuilder` is responsible only for converting validated profile data into Geant4 solids.
- Codex must not change the CSV schema without updating `spec.md` first.

---

## D005: Use `G4ExtrudedSolid` for the two tungsten collimator jaws

**Status:** Accepted  
**Date:** 2026-04-27

### Context

Each collimator jaw is a convex pentagon in the global x-z plane extruded along the global y direction.

### Decision

Each jaw will be implemented using `G4ExtrudedSolid`.

The mapping is:

| Physical coordinate | `G4ExtrudedSolid` local coordinate |
|---|---|
| global `x` | local `x` |
| global `z` | local `y` |
| global `y` | local `z` extrusion direction |

After construction, the solid is rotated so that the local extrusion direction corresponds to the global y direction. A rotation of `+90 deg` around the x axis is acceptable according to the project specification.

### Rationale

`G4ExtrudedSolid` directly represents a 2D polygon extruded along one axis, matching the jaw geometry. It avoids Boolean subtraction and keeps the collimator construction inspectable.

### Consequences

- Input CSV coordinates are global x-z coordinates, not local coordinates around a collimator center.
- The builder must not apply an additional `collimator_center_z` offset.
- Codex must be careful not to accidentally treat the CSV `z_mm` value as a local Geant4 extrusion coordinate.

---

## D006: Use `G4EmLivermorePhysics` with a global production cut of 0.1 mm

**Status:** Accepted  
**Date:** 2026-04-27

### Context

The simulation focuses on low-energy gamma interactions in PMMA, especially Compton and Rayleigh scattering.

### Decision

Use:

```cpp
G4EmLivermorePhysics
```

Set the global production cut to:

```text
0.1 mm
```

### Rationale

The Livermore electromagnetic model is appropriate for low-energy electromagnetic interactions and includes Rayleigh scattering, which is explicitly part of the PMMA scatter statistics.

### Alternatives considered

| Alternative | Reason not selected for version 1 |
|---|---|
| Default Geant4 EM physics | Less explicit for low-energy gamma focus. |
| Penelope EM physics | Possible later comparison, but not the version 1 baseline. |
| Custom physics list from scratch | Unnecessary for the first working version. |

### Consequences

- `PhysicsList` should be simple and explicit.
- Codex must not substitute a different physics list unless the decision is updated.
- Later validation studies may compare physics lists, but that is outside version 1.

---

## D007: Define one event as one primary gamma

**Status:** Accepted  
**Date:** 2026-04-27

### Context

The output CSV row represents the result of one primary gamma if it reaches the detector plane.

### Decision

Use:

```text
1 event = 1 primary gamma
```

Therefore:

```text
/run/beamOn N
```

means simulating `N` incident gamma particles.

### Rationale

This mapping makes event-level statistics straightforward. It also simplifies scatter-count storage, detector-hit storage, and downstream normalization.

### Consequences

- `EventAction` can maintain one scatter summary per event.
- Output rows can be interpreted as detector-reaching primary gamma histories.
- Codex must not emit multiple primary gamma particles in a single event for version 1.

---

## D008: Support mono and spectrum energy modes, but keep the source geometry fixed in version 1

**Status:** Accepted  
**Date:** 2026-04-27

### Context

The project needs both a simple monoenergetic mode for debugging and a spectrum mode for later realistic input. However, source geometry itself is already defined in the specification.

### Decision

Support two energy modes:

```text
/source/energyMode mono
/source/energyMode spectrum
```

The source is a point gamma source at `(0, 0, -185 mm)` using target-plane sampling on a circular spot at `z = 0` with radius `1.5 mm`.

Version 1 will not support macro commands for source position or beam spot size.

### Rationale

Separating energy-mode variability from source-geometry variability keeps the first version manageable while still supporting both debug and future realistic spectrum runs.

### Consequences

- `PrimaryGeneratorAction` handles fixed geometry and delegates spectrum sampling to `SpectrumSampler`.
- Codex must not add source-position or beam-spot macro commands unless `spec.md` is updated.

---

## D009: Track only primary gamma scattering history inside PMMA

**Status:** Accepted  
**Date:** 2026-04-27

### Context

The target statistic is the PMMA scattering history of detector-reaching primary gamma particles. Secondary particles and non-PMMA interactions would change the meaning of the output fields.

### Decision

Only track particles satisfying:

```text
particle_name == gamma
track_id == 1
parent_id == 0
```

Only count PMMA interactions with process name:

```text
compt
Rayl
```

Do not count:

- photoelectric effect,
- collimator interactions,
- air interactions,
- world interactions,
- secondary gamma interactions.

### Rationale

This definition keeps `scatter_count_total`, `compton_count`, and `rayleigh_count` tied to one physical object: the primary gamma that eventually may reach the detector.

### Consequences

- `SteppingAction` must filter by particle identity and track identity before updating scatter statistics.
- Volume/location checks must ensure that counted interactions occur inside PMMA.
- Codex must not include secondary gamma or tungsten interactions in PMMA scatter counts.

---

## D010: Output only detector-reaching primary gamma events

**Status:** Accepted  
**Date:** 2026-04-27

### Context

The output data is intended for detector-side analysis. Events that never cross the detector plane would significantly increase output size while not contributing directly to detector statistics.

### Decision

CSV output includes only primary gamma events that cross the detector plane within its x-y bounds.

Events are not output if:

- the primary gamma does not reach the detector plane,
- the particle is not the primary gamma,
- the particle is not a gamma.

### Rationale

This keeps output compact and aligned with the intended statistical analysis: among detected primary gamma, evaluate scattering history and distribution.

### Consequences

- `EventAction` writes a row only if the detector-hit flag is set.
- A zero-scatter detector hit is still output.
- Codex must not output all simulated events unless the output policy is explicitly changed.

---

## D011: Keep CSV schemas stable and encode run metadata in filenames

**Status:** Accepted  
**Date:** 2026-04-27

### Context

The CSV fields are used for downstream analysis. Uncontrolled schema changes would break scripts and make comparisons difficult.

### Decision

Maintain two schemas:

- compact schema for formal statistical runs,
- debug schema with extra event/track/direction fields.

Run metadata such as profile ID, energy mode, mono energy, random seed, and debug mode is encoded in the output filename, not repeated in every CSV row.

### Rationale

A stable row schema simplifies post-processing. Putting run-level metadata in filenames avoids repeated columns and keeps each row focused on detected primary gamma properties.

### Consequences

- Codex must not add new CSV columns unless `spec.md` is updated.
- Output filenames are part of the data contract.
- Any post-processing script must parse run-level metadata from the filename or external run configuration.

---

## D012: Use per-thread temporary CSV files and master-side merge for multi-thread output

**Status:** Accepted  
**Date:** 2026-04-27

### Context

Geant4 multi-threaded runs can involve multiple worker threads. Sharing one `std::ofstream` across worker threads risks race conditions and corrupted output.

### Decision

Use this strategy:

1. Each worker thread writes its own temporary CSV file.
2. No worker threads share the same `std::ofstream`.
3. At run end, the master merges worker CSV files.
4. The final merged file keeps only one header.
5. In compact mode, temporary files are deleted after successful merge.
6. In debug mode, temporary files are retained after successful merge.
7. If merge fails, temporary files are retained and the program reports an error.

### Rationale

Per-thread files avoid output locking complexity and make debugging easier when multi-thread output problems occur.

### Consequences

- `CsvWriter` must be thread-aware.
- `RunAction` triggers merge at run end.
- Codex must not implement shared-stream multi-thread output.

---

## D013: Use macro commands for runtime configuration, but keep selected geometry constants fixed

**Status:** Accepted  
**Date:** 2026-04-27

### Context

Some runtime choices should be configurable without recompilation, while other geometric constants are intentionally fixed in version 1 to prevent uncontrolled scope expansion.

### Decision

Support macro commands for:

- collimator profile file,
- collimator profile ID,
- air defect enable/disable,
- energy mode,
- mono energy,
- spectrum file,
- random seed,
- number of threads,
- output directory,
- debug mode.

Do not support macro commands for:

- source position,
- detector bounds,
- detector plane position,
- beam spot size,
- PMMA dimensions,
- air defect dimensions.

### Rationale

The selected macros cover expected version 1 experiments while keeping geometry and data interpretation stable.

### Consequences

- `SimulationConfig` should centralize configurable runtime values.
- Fixed geometry constants should be defined clearly in code, preferably near the owning module.
- Codex must not add extra macro commands unless the specification is updated.

---

## D014: Fail fast on invalid collimator profile data

**Status:** Accepted  
**Date:** 2026-04-27

### Context

A malformed collimator profile can produce invalid geometry, silent misalignment, or misleading simulation results.

### Decision

The program must stop with a clear error if the selected profile has any of the following problems:

- missing `profile_id`,
- not exactly two jaws,
- a jaw does not have exactly five vertices,
- missing or duplicated `vertex_id`,
- empty, non-numeric, NaN, or infinite coordinate,
- zero-area polygon,
- non-convex pentagon.

### Rationale

Failing fast prevents invalid geometry from producing plausible-looking but incorrect output.

### Consequences

- Profile validation belongs in `CollimatorProfileReader`, not in `CollimatorBuilder`.
- Error messages should identify the failed profile and the reason.
- Codex must not silently repair invalid profile data.

---

## D015: Keep module responsibilities narrow and separated

**Status:** Accepted  
**Date:** 2026-04-27

### Context

The project will be built with Codex assistance. Narrow module boundaries reduce accidental coupling and make code easier to review milestone by milestone.

### Decision

Use the following responsibility split:

| Module | Responsibility |
|---|---|
| `DetectorConstruction` | Build world, PMMA, air defect, detector helper plane, and call collimator builder. |
| `CollimatorProfileReader` | Read and validate profile CSV data. |
| `CollimatorBuilder` | Convert validated profile data into tungsten Geant4 geometry. |
| `PrimaryGeneratorAction` | Generate one primary gamma per event. |
| `SpectrumSampler` | Read spectrum CSV and sample initial gamma energy. |
| `EventAction` | Store one event's initial energy, scatter summary, and detector-hit record. |
| `SteppingAction` | Detect PMMA scatter processes and detector plane crossing. |
| `CsvWriter` | Write thread-local CSV files and merge them. |
| `RunAction` | Manage random seed, output lifecycle, and run-end merge. |

### Rationale

This split matches the Geant4 lifecycle and makes each milestone testable.

### Consequences

- Codex should not place CSV writing inside `SteppingAction`.
- Codex should not parse collimator CSV inside `DetectorConstruction` except by calling `CollimatorProfileReader`.
- Codex should not mix spectrum parsing into `PrimaryGeneratorAction` if a dedicated `SpectrumSampler` exists.

---

## D016: Implement the project milestone by milestone

**Status:** Accepted  
**Date:** 2026-04-27

### Context

Generating the entire project in one Codex request would make errors difficult to isolate.

### Decision

Implement the project according to `milestones.md`.

Codex should implement only the requested milestone and should not implement future milestones unless explicitly instructed.

### Rationale

Milestone-based implementation supports incremental review, compilation, and testing.

### Consequences

- Each Codex prompt should specify the target milestone.
- After each milestone, Codex should summarize changed files, tests performed, and deferred work.
- If a later milestone requires changing earlier code, the change should be minimal and explained.

---

## D017: Defer reconstruction, detector response, and post-processing analysis

**Status:** Accepted  
**Date:** 2026-04-27

### Context

The broader research direction may eventually include image reconstruction, real detector response, post-processing analysis, and batch profile scanning. These are not needed for the first executable Geant4 simulation.

### Decision

Defer the following work:

- image reconstruction,
- real detector material response,
- detector energy deposition statistics,
- Python post-processing scripts,
- batch scanning over all profile IDs,
- all scatter point trajectory output,
- source position macro commands,
- detector bounds macro commands,
- real collimator profile generation logic.

### Rationale

These features are valid future extensions, but including them in version 1 would increase implementation risk and blur the acceptance criteria.

### Consequences

- The version 1 acceptance target is a correct event-level simulation and CSV output pipeline.
- Deferred features should be added only after version 1 tests pass.
- Codex must not interpret deferred work as current implementation scope.

---

## Adding a new decision

Use this template for future decisions:

```md
## DXXX: Short decision title

**Status:** Proposed | Accepted | Superseded | Deferred  
**Date:** YYYY-MM-DD

### Context

What problem or ambiguity requires a decision?

### Decision

What has been decided?

### Rationale

Why this option was selected.

### Alternatives considered

| Alternative | Reason not selected |
|---|---|
| ... | ... |

### Consequences

What this affects in implementation, testing, or future extension.
```

---

## Change control

Accepted decisions should not be edited casually. If a decision changes:

1. Mark the old decision as `Superseded`.
2. Add a new decision with a new ID.
3. Explain what changed and why.
4. Update `spec.md`, `architecture.md`, or `milestones.md` if the change affects requirements, code structure, or implementation order.
