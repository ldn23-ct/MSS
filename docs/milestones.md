# milestones.md

## Purpose

This document defines the staged implementation plan for the `BackscatterSim` Geant4 project.

It is written for Codex-assisted development. Its purpose is to keep implementation incremental, reviewable, and aligned with `spec.md` and `architecture.md`.

This file is not a research schedule and not a paper-writing plan. It only covers code implementation milestones for the first working version of the project.

---

## How to use this file with Codex

Use one milestone at a time.

For each Codex session:

1. Ask Codex to read:
   - `spec.md`
   - `architecture.md`
   - `milestones.md`
2. Tell Codex which milestone to implement.
3. Tell Codex not to implement later milestones.
4. Review changed files before moving to the next milestone.
5. Run the milestone-specific checks before continuing.

Recommended interaction pattern:

```text
Read spec.md, architecture.md, and milestones.md.
Implement Milestone N only.
Do not implement Milestone N+1 or later.
After implementation, summarize:
- files changed
- what was implemented
- how to test it
- what was intentionally left for later
```

---

## Global rules for Codex

Codex must follow these rules for every milestone.

### Required behavior

- Always align implementation with `spec.md` first.
- Use `architecture.md` for module boundaries and data flow.
- Implement only the requested milestone.
- Keep code simple, explicit, and testable.
- Prefer clear runtime errors over silent fallback behavior.
- Preserve the CSV schema defined in `spec.md`.
- Preserve the macro command names defined in `spec.md`.
- Preserve the coordinate system defined in `spec.md`.
- Preserve the first-version scope.
- After each milestone, summarize changed files and remaining deferred work.

### Forbidden behavior

- Do not implement future milestones unless explicitly requested.
- Do not add image reconstruction.
- Do not add detector material response.
- Do not add energy deposition scoring.
- Do not add automatic scanning over all collimator profiles.
- Do not output full scatter trajectories.
- Do not add source position macro commands.
- Do not add detector bounds macro commands.
- Do not change the output CSV fields unless `spec.md` is updated first.
- Do not replace the specified output strategy with a different one.
- Do not let multiple worker threads write to the same `std::ofstream`.
- Do not silently ignore invalid profile, spectrum, geometry, or output configuration.

---

## Milestone overview

| Milestone | Name | Main deliverable |
|---:|---|---|
| M0 | Repository skeleton | Minimal buildable Geant4 project structure |
| M1 | Runtime configuration and macro commands | Central config object and UI command layer |
| M2 | Collimator profile reader | CSV reader and validator for collimator profiles |
| M3 | Basic geometry construction | World, PMMA, optional air defect, detector helper plane |
| M4 | Collimator geometry construction | Two tungsten pentagonal jaws built from profile data |
| M5 | Primary generator and spectrum sampler | Mono/spectrum gamma source with cone-beam target sampling |
| M6 | Event-level state model | Per-event scatter and detector-hit state |
| M7 | Stepping logic | Scatter counting and detector crossing logic |
| M8 | CSV output in single-thread mode | Debug/compact CSV writing for one thread |
| M9 | Multi-thread output merge | Per-thread temporary CSV files and master merge |
| M10 | Macros, README alignment, and acceptance tests | Runnable macros, sample data, README, validation checklist |

---

# Milestone 0: Repository skeleton

## Goal

Create a minimal buildable Geant4 project skeleton for `BackscatterSim`.

This milestone should establish the repository layout, CMake configuration, entry point, and placeholder classes. It should not implement real simulation behavior yet.

## Files to create or modify

Create:

- `CMakeLists.txt`
- `main.cc`
- `include/DetectorConstruction.hh`
- `src/DetectorConstruction.cc`
- `include/PhysicsList.hh`
- `src/PhysicsList.cc`
- `include/PrimaryGeneratorAction.hh`
- `src/PrimaryGeneratorAction.cc`
- `include/RunAction.hh`
- `src/RunAction.cc`
- `include/EventAction.hh`
- `src/EventAction.cc`
- `include/SteppingAction.hh`
- `src/SteppingAction.cc`
- `include/CollimatorProfileReader.hh`
- `src/CollimatorProfileReader.cc`
- `include/CollimatorBuilder.hh`
- `src/CollimatorBuilder.cc`
- `include/SpectrumSampler.hh`
- `src/SpectrumSampler.cc`
- `include/CsvWriter.hh`
- `src/CsvWriter.cc`
- `macros/.gitkeep`
- `data/.gitkeep`
- `results/.gitkeep`

## Tasks

### Task 0.1: Create project layout

Create the expected top-level structure:

```text
BackscatterSim/
├── CMakeLists.txt
├── main.cc
├── include/
├── src/
├── macros/
├── data/
└── results/
```

### Task 0.2: Configure CMake

Configure CMake for:

- project name: `BackscatterSim`
- C++ standard: C++17
- Geant4 package discovery
- executable target: `BackscatterSim`
- include directory: `include/`
- source files under `src/`

### Task 0.3: Implement minimal entry point

In `main.cc`:

- create the Geant4 run manager using `G4RunManagerFactory::CreateRunManager(G4RunManagerType::Default)`
- register placeholder detector construction
- register placeholder physics list
- register placeholder user actions
- support macro execution from command-line argument
- support interactive mode only if no macro file is passed

### Task 0.4: Add placeholder classes

Create placeholder implementations for the core classes so the project compiles.

At this stage, placeholder classes may have minimal behavior only.

## Done when

- The project configures with CMake.
- The project builds with `make -j`.
- The executable `BackscatterSim` is produced.
- Running the executable with no macro does not crash immediately.
- No real geometry, source, detector crossing, CSV output, or profile parsing is implemented yet.

## Do

- Keep all placeholder classes minimal.
- Use the class names from `spec.md`.
- Use C++17.
- Keep source and header files separated.

## Do not

- Do not implement real PMMA geometry.
- Do not implement the collimator.
- Do not implement macro command handling.
- Do not implement CSV output.
- Do not implement scatter tracking.
- Do not implement spectrum sampling.
- Do not add analysis scripts.

## Suggested Codex prompt

```text
Read spec.md, architecture.md, and milestones.md.
Implement Milestone 0 only: Repository skeleton.
Create a minimal buildable Geant4 project with the expected file structure, CMakeLists.txt, main.cc, and placeholder classes.
Do not implement geometry details, macro commands, CSV output, source sampling, scatter tracking, or multi-thread output.
After implementation, summarize files changed and the exact build commands to test this milestone.
```

---

# Milestone 1: Runtime configuration and macro commands

## Goal

Create a central runtime configuration layer and macro command interface.

This milestone should make the project able to receive and store the first-version macro parameters. It should not yet use those parameters to build full geometry, emit particles, or write CSV files.

## Files to create or modify

Create:

- `include/SimulationConfig.hh`
- `src/SimulationConfig.cc`
- `include/SimulationMessenger.hh`
- `src/SimulationMessenger.cc`

Modify:

- `CMakeLists.txt`
- `main.cc`
- `include/DetectorConstruction.hh`
- `src/DetectorConstruction.cc`
- `include/PrimaryGeneratorAction.hh`
- `src/PrimaryGeneratorAction.cc`
- `include/RunAction.hh`
- `src/RunAction.cc`

## Tasks

### Task 1.1: Define `SimulationConfig`

Create a configuration object containing first-version runtime parameters:

```cpp
struct SimulationConfig {
    std::string collimatorProfileFile = "data/collimator_profiles.csv";
    std::string collimatorProfileId = "P001";
    bool enableAirDefect = true;

    std::string energyMode = "mono";
    double monoEnergy_keV = 160.0;
    std::string spectrumFile = "data/spectrum.csv";

    long randomSeed = 12345;
    int numberOfThreads = 1;

    std::string outputDirectory = "results";
    bool debugOutput = true;
};
```

The exact implementation can differ, but the stored values and defaults must match the specification.

### Task 1.2: Implement macro commands

Implement macro commands:

```text
/geometry/collimatorProfileFile data/collimator_profiles.csv
/geometry/collimatorProfileId P001
/geometry/enableAirDefect true

/source/energyMode mono
/source/monoEnergy 160 keV
/source/spectrumFile data/spectrum.csv

/run/randomSeed 12345
/run/numberOfThreads 8

/output/directory results
/output/debug false
```

### Task 1.3: Validate simple command values

Implement basic validation:

- `energyMode` must be `mono` or `spectrum`.
- `monoEnergy` must be positive.
- `numberOfThreads` must be at least 1.
- `outputDirectory` must not be empty.
- `collimatorProfileId` must not be empty.
- `collimatorProfileFile` must not be empty.
- `spectrumFile` must not be empty when energy mode is `spectrum`.

### Task 1.4: Share config with core classes

Pass or share the configuration object with:

- `DetectorConstruction`
- `PrimaryGeneratorAction`
- `RunAction`

The ownership model should be explicit and avoid dangling references.

### Task 1.5: Set thread count from configuration

Ensure `/run/numberOfThreads` can configure the run manager thread count when using multi-threaded Geant4.

The implementation must not hard-code single-thread or multi-thread mode.

## Done when

- All required macro commands exist.
- Macro commands update the central configuration object.
- Invalid simple values produce clear errors.
- The project still builds.
- No full simulation behavior is introduced yet.

## Do

- Keep macro command names exactly as defined.
- Keep defaults consistent with `spec.md`.
- Make configuration access simple and explicit.
- Use Geant4 UI command classes where appropriate.

## Do not

- Do not build the full geometry in this milestone.
- Do not read the collimator profile CSV yet.
- Do not read the spectrum CSV yet.
- Do not write output CSV files.
- Do not implement scatter tracking.
- Do not modify the output CSV schema.

## Suggested Codex prompt

```text
Read spec.md, architecture.md, and milestones.md.
Implement Milestone 1 only: Runtime configuration and macro commands.
Create SimulationConfig and a messenger for all required first-version macro commands.
The commands should update configuration values and perform basic validation.
Do not implement geometry, collimator profile reading, spectrum reading, CSV output, scatter tracking, or multi-thread file merging.
After implementation, summarize files changed and how to test macro command parsing.
```

---

# Milestone 2: Collimator profile reader

## Goal

Implement a standalone reader for external collimator profile CSV files.

The reader must load one selected `profile_id`, validate it, and return a structured `CollimatorProfile` object. This milestone must not construct Geant4 solids.

## Files to create or modify

Modify:

- `include/CollimatorProfileReader.hh`
- `src/CollimatorProfileReader.cc`
- `CMakeLists.txt` if needed

Optional test/support files:

- `data/collimator_profiles.csv`
- small local invalid sample files for manual testing, if useful

## Tasks

### Task 2.1: Define profile data structures

Define data structures:

```cpp
struct XZPoint {
    double x_mm;
    double z_mm;
};

struct PentagonJawProfile {
    std::string jaw_id;
    std::array<XZPoint, 5> vertices;
};

struct CollimatorProfile {
    std::string profile_id;
    PentagonJawProfile jaw0;
    PentagonJawProfile jaw1;
};
```

The exact names may follow project style, but the semantic structure must be equivalent.

### Task 2.2: Parse CSV rows

Read CSV columns:

```text
profile_id,jaw_id,vertex_id,x_mm,z_mm
```

Rows not matching the selected `profile_id` should be ignored.

### Task 2.3: Validate selected profile existence

Reject with a clear runtime error if:

- the file cannot be opened
- the selected `profile_id` is not found
- required CSV columns are missing
- a required field is empty

### Task 2.4: Validate jaws and vertices

Reject with a clear runtime error if:

- the selected profile does not contain exactly two jaws
- jaw IDs are not `jaw_0` and `jaw_1`
- a jaw does not contain exactly five vertices
- `vertex_id` is missing
- `vertex_id` is duplicated
- `vertex_id` is outside `0..4`

### Task 2.5: Validate numeric coordinates

Reject with a clear runtime error if:

- `x_mm` or `z_mm` is not numeric
- `x_mm` or `z_mm` is NaN
- `x_mm` or `z_mm` is infinite

### Task 2.6: Validate polygon geometry

For each jaw:

- compute signed polygon area
- reject zero-area polygons
- verify convexity
- reject non-convex pentagons

The reader does not need to verify that z coordinates lie in a specific range.

## Done when

- Valid `P001` data can be loaded.
- Invalid profile ID produces a clear error.
- Missing or duplicated vertex IDs produce clear errors.
- Non-finite coordinates produce clear errors.
- Zero-area and non-convex pentagons produce clear errors.
- No Geant4 geometry is constructed in this milestone.

## Do

- Keep the reader independent of Geant4 geometry classes.
- Return plain C++ data structures.
- Use clear exception messages or fatal errors.
- Preserve input units as mm.
- Preserve input coordinates as global `x_mm` and `z_mm`.

## Do not

- Do not create `G4ExtrudedSolid`.
- Do not create tungsten logical volumes.
- Do not implement profile batch scanning.
- Do not modify the CSV format.
- Do not add extra required columns.
- Do not silently repair invalid profiles.

## Suggested Codex prompt

```text
Read spec.md, architecture.md, and milestones.md.
Implement Milestone 2 only: Collimator profile reader.
Implement CollimatorProfileReader as a standalone CSV reader and validator for one selected profile_id.
It must validate jaw count, jaw IDs, vertex IDs, finite coordinates, polygon area, and convexity.
Do not construct Geant4 solids, do not build tungsten volumes, and do not implement profile batch scanning.
After implementation, summarize files changed and provide manual test cases for valid and invalid profiles.
```

---

# Milestone 3: Basic geometry construction

## Goal

Construct the basic Geant4 geometry excluding the tungsten collimator.

This milestone should build:

- World
- PMMA phantom
- optional air defect
- detector helper plane for visualization
- detector boundary configuration for later stepping logic

## Files to create or modify

Modify:

- `include/DetectorConstruction.hh`
- `src/DetectorConstruction.cc`
- `include/SimulationConfig.hh` if geometry constants need a home
- `src/SimulationConfig.cc` if needed

## Tasks

### Task 3.1: Build World

Create World volume:

- shape: box
- size: `1000 mm × 1000 mm × 1000 mm`
- center: `(0, 0, 0)`
- material: `G4_Galactic`

### Task 3.2: Build PMMA phantom

Create PMMA phantom:

- material: `G4_PLEXIGLASS`
- shape: box
- size: `200 mm × 200 mm × 65 mm`
- center: `(0, 0, 32.5 mm)`
- z range: `[0, 65] mm`

### Task 3.3: Build optional air defect

If `enableAirDefect == true`, create air cylinder as a daughter volume inside the PMMA phantom:

- material: `G4_AIR`
- shape: cylinder
- radius: `5 mm`
- full length: `10 mm`
- axis: z-axis
- center: `(0, 0, 55 mm)` in global coordinates
- z range: `[50, 60] mm`

Do not use Boolean subtraction.

### Task 3.4: Define detector boundary config

Create or expose a detector plane configuration:

```cpp
struct DetectorPlaneConfig {
    double z_mm = -73.0;
    double x_min_mm = 53.0;
    double x_max_mm = 161.0;
    double y_min_mm = -50.0;
    double y_max_mm = 50.0;
};
```

This config will later be used by `SteppingAction`.

### Task 3.5: Add detector helper plane for visualization

Add a thin, non-sensitive visualization helper plane or marker at:

- `z = -73 mm`
- `x = [53, 161] mm`
- `y = [-50, 50] mm`

This helper must not simulate detector material response.

### Task 3.6: Add basic visualization attributes

Make major volumes visually distinguishable:

- World can be invisible.
- PMMA should be visible or semi-transparent.
- Air defect should be visible when enabled.
- Detector helper plane should be visible.

## Done when

- `vis.mac` or a temporary visualization macro can show World, PMMA, optional air defect, and detector helper plane.
- Air defect appears when enabled and is absent when disabled.
- Detector plane is located at `z = -73 mm` with the specified bounds.
- No tungsten collimator is built yet.

## Do

- Use Geant4 NIST materials.
- Preserve the coordinate system from `spec.md`.
- Keep detector helper plane non-physical for response modeling.
- Make geometry constants easy to inspect.

## Do not

- Do not build collimator jaws.
- Do not implement source generation.
- Do not implement scatter tracking.
- Do not implement detector crossing logic.
- Do not write CSV files.
- Do not add detector material response.
- Do not add macro commands for source position or detector bounds.

## Suggested Codex prompt

```text
Read spec.md, architecture.md, and milestones.md.
Implement Milestone 3 only: Basic geometry construction.
Build World, PMMA phantom, optional air defect, detector plane configuration, and a visualization helper plane.
Do not build the tungsten collimator, do not implement source generation, stepping logic, detector response, or CSV output.
After implementation, summarize files changed and explain how to visually check the geometry.
```

---

# Milestone 4: Collimator geometry construction

## Goal

Construct the two tungsten collimator jaws from a validated external profile.

This milestone connects `CollimatorProfileReader` and `CollimatorBuilder` to `DetectorConstruction`.

## Files to create or modify

Modify:

- `include/CollimatorBuilder.hh`
- `src/CollimatorBuilder.cc`
- `include/DetectorConstruction.hh`
- `src/DetectorConstruction.cc`
- `include/CollimatorProfileReader.hh` only if integration requires a small interface adjustment
- `src/CollimatorProfileReader.cc` only if integration requires a small interface adjustment

## Tasks

### Task 4.1: Define `CollimatorBuilder` interface

Create a builder interface that accepts:

- validated `CollimatorProfile`
- parent/world logical volume
- material manager or tungsten material

It should construct two physical tungsten jaw volumes.

### Task 4.2: Use `G4ExtrudedSolid`

Each jaw must be built using `G4ExtrudedSolid`.

Input profile points are global `(x_mm, z_mm)` coordinates.

Map them into the `G4ExtrudedSolid` local 2D section as:

| Input | `G4ExtrudedSolid` local coordinate |
|---|---|
| global x | local x |
| global z | local y |

The extrusion direction is local z.

### Task 4.3: Apply rotation for global y extrusion

Rotate the extruded solid so that local z extrusion maps to global y direction.

The intended mapping is:

```text
local x -> global x
local y -> global z
local z -> global -y
```

This is equivalent to rotation around the x-axis by `+90 deg`. Since the jaw is symmetric along y, local z mapping to global +y or -y gives equivalent geometric coverage.

### Task 4.4: Set y extrusion length

Each jaw must be extruded over:

- full length: `120 mm`
- global y range: `[-60, 60] mm`

### Task 4.5: Use tungsten material

Use Geant4 NIST tungsten material:

```cpp
G4_W
```

### Task 4.6: Integrate with `DetectorConstruction`

In `DetectorConstruction`:

- read selected profile file from config
- select profile ID from config
- validate via `CollimatorProfileReader`
- build collimator via `CollimatorBuilder`

## Done when

- Valid `P001` profile builds two tungsten jaw volumes.
- Invalid profile data still stops at profile reader validation.
- Visualization shows two pentagonal tungsten jaws.
- The jaws are positioned using global x-z coordinates from the CSV without adding an extra z offset.
- No detector crossing or output logic is implemented in this milestone.

## Do

- Preserve global x-z coordinates from the profile file.
- Use `G4ExtrudedSolid`.
- Use y extrusion length of `120 mm`.
- Keep jaw construction separate from profile reading.
- Add visualization attributes for tungsten jaws.

## Do not

- Do not modify the profile CSV format.
- Do not implement profile batch scanning.
- Do not add extra coordinate offsets.
- Do not check that z coordinates fall in `[-28, -20] mm`.
- Do not implement detector crossing.
- Do not implement scatter tracking.
- Do not write CSV files.

## Suggested Codex prompt

```text
Read spec.md, architecture.md, and milestones.md.
Implement Milestone 4 only: Collimator geometry construction.
Use CollimatorProfileReader output to build two tungsten jaws with G4ExtrudedSolid.
Preserve global x-z coordinates from the CSV and rotate the extrusion so the jaw extends along global y.
Do not modify the CSV format, do not implement profile batch scanning, and do not implement stepping or output logic.
After implementation, summarize files changed and explain how to visually verify the collimator geometry.
```

---

# Milestone 5: Primary generator and spectrum sampler

## Goal

Implement the primary gamma source.

The source must support:

- one event = one primary gamma
- mono energy mode
- spectrum energy mode
- point source at `(0, 0, -185 mm)`
- target-plane disk sampling at PMMA front surface `z = 0 mm`

## Files to create or modify

Modify:

- `include/PrimaryGeneratorAction.hh`
- `src/PrimaryGeneratorAction.cc`
- `include/SpectrumSampler.hh`
- `src/SpectrumSampler.cc`
- `include/SimulationConfig.hh` if needed
- `src/SimulationConfig.cc` if needed

## Tasks

### Task 5.1: Implement point gamma source

Use a primary generator method compatible with Geant4.

For each event:

- particle: gamma
- source position: `(0, 0, -185 mm)`
- number of primaries: 1

### Task 5.2: Implement mono energy mode

When:

```text
/source/energyMode mono
```

Use:

```text
/source/monoEnergy 160 keV
```

or the configured mono energy value.

### Task 5.3: Implement spectrum sampler

Implement `SpectrumSampler` to read CSV:

```csv
energy_keV,weight
40,0.01
45,0.03
50,0.06
```

Validation requirements:

- file must exist
- required columns must exist
- energy must be positive
- weight must be non-negative
- at least one weight must be positive
- values must be finite

Sampling requirements:

- normalize weights
- build cumulative distribution function
- sample one energy per event

### Task 5.4: Implement target-plane disk sampling

For each event:

1. sample a point uniformly in a disk on plane `z = 0 mm`
2. disk center: `(0, 0, 0)`
3. disk radius: `1.5 mm`
4. initial direction:

```text
normalize((x_target, y_target, 0) - (0, 0, -185))
```

### Task 5.5: Store initial energy for event state

Provide a clean way for `PrimaryGeneratorAction` to pass the sampled initial energy to `EventAction` later.

At this milestone, a stub method or clear interface is sufficient if M6 will finalize event state handling.

## Done when

- One primary gamma is generated per event.
- Mono mode works with default `160 keV`.
- Spectrum mode can load and sample from `data/spectrum.csv`.
- Direction points from the source to a sampled target point on the disk at `z = 0 mm`.
- Source collimator is not modeled.

## Do

- Use units explicitly.
- Keep source geometry fixed in code for first version.
- Keep target disk radius fixed at `1.5 mm`.
- Keep energy units in keV for input and internal clarity.
- Validate spectrum input strictly.

## Do not

- Do not simulate a source collimator.
- Do not add macro commands for source position or beam spot radius.
- Do not implement detector crossing logic.
- Do not implement scatter counting.
- Do not write output CSV files.
- Do not implement image reconstruction or analysis scripts.

## Suggested Codex prompt

```text
Read spec.md, architecture.md, and milestones.md.
Implement Milestone 5 only: Primary generator and spectrum sampler.
Generate one primary gamma per event from the fixed point source at (0,0,-185 mm), using target-plane disk sampling at z=0 with radius 1.5 mm.
Support mono and spectrum energy modes, including strict spectrum CSV validation and CDF sampling.
Do not simulate source collimator, detector crossing, scatter tracking, CSV output, or post-processing.
After implementation, summarize files changed and how to test mono and spectrum modes.
```

---

# Milestone 6: Event-level state model

## Goal

Create the event-level state model used to accumulate scatter and detector-hit information for one primary gamma.

This milestone defines what information an event records, but it does not yet implement the step-level logic that fills it.

## Files to create or modify

Modify:

- `include/EventAction.hh`
- `src/EventAction.cc`
- `include/PrimaryGeneratorAction.hh`
- `src/PrimaryGeneratorAction.cc`
- `include/RunAction.hh` if needed for later writer access
- `src/RunAction.cc` if needed

Optional new file:

- `include/EventRecord.hh`

## Tasks

### Task 6.1: Define scatter state

For each event, store:

- `initial_energy`
- `scatter_count_total`
- `compton_count`
- `rayleigh_count`
- `first_scatter_x`
- `first_scatter_y`
- `first_scatter_z`
- `last_scatter_x`
- `last_scatter_y`
- `last_scatter_z`

If no scatter occurs, first and last scatter positions must remain NaN.

### Task 6.2: Define detector hit state

For each event, store whether the primary gamma has been detected.

If detected, store:

- `det_x`
- `det_y`
- `det_z`
- `det_energy`
- `det_dir_x`
- `det_dir_y`
- `det_dir_z`

Debug fields may be stored even if compact output later omits them.

### Task 6.3: Implement event reset

At the beginning of each event:

- reset scatter counts to zero
- reset first/last scatter positions to NaN
- reset detector hit flag
- reset detector hit values
- prepare to receive initial energy

### Task 6.4: Implement state update methods

Add methods such as:

- `SetInitialEnergy(...)`
- `RecordComptonScatter(position)`
- `RecordRayleighScatter(position)`
- `RecordDetectorHit(...)`
- `HasDetectorHit()`
- `GetRecord()`

Exact names may differ, but state transitions must be clear.

### Task 6.5: Define multiple-scatter flag

Compute:

```text
is_multiple_scatter = scatter_count_total >= 2
```

This can be stored or computed when needed.

## Done when

- Event state resets correctly at event start.
- Initial energy can be stored.
- Scatter state can be updated through explicit methods.
- Detector hit state can be recorded through an explicit method.
- `is_multiple_scatter` is available as a derived value.
- No CSV file is written yet.

## Do

- Keep event state per event.
- Use NaN for missing first/last scatter positions.
- Keep units consistent with `spec.md`: mm and keV.
- Keep debug fields available for later output.

## Do not

- Do not implement step-level process detection yet.
- Do not implement detector plane crossing yet.
- Do not write CSV files.
- Do not implement multi-thread merging.
- Do not output unhit events.
- Do not add fields outside the specified schema unless they are internal-only and justified.

## Suggested Codex prompt

```text
Read spec.md, architecture.md, and milestones.md.
Implement Milestone 6 only: Event-level state model.
Create clear per-event state for initial energy, Compton/Rayleigh counts, first/last scatter positions, detector hit information, and is_multiple_scatter.
Implement reset and update methods, but do not implement step-level process detection, detector crossing, CSV writing, or multi-thread output.
After implementation, summarize files changed and describe how EventAction state is updated.
```

---

# Milestone 7: Stepping logic

## Goal

Implement step-level logic for primary gamma scatter tracking and detector plane crossing.

This milestone connects `SteppingAction` to `EventAction` and `DetectorConstruction` detector bounds.

## Files to create or modify

Modify:

- `include/SteppingAction.hh`
- `src/SteppingAction.cc`
- `include/EventAction.hh`
- `src/EventAction.cc` if event state methods need adjustment
- `include/DetectorConstruction.hh` if detector config accessor is needed
- `src/DetectorConstruction.cc` if detector config accessor is needed

## Tasks

### Task 7.1: Filter to primary gamma only

Only process tracks satisfying:

```text
particle_name == gamma
track_id == 1
parent_id == 0
```

All other particles and secondary photons must be ignored for scatter-history statistics and detector output.

### Task 7.2: Detect PMMA internal scattering

For each step, determine whether the relevant interaction occurred inside PMMA.

Count only processes:

```text
compt
Rayl
```

Only count Compton and Rayleigh scattering inside PMMA.

Do not count:

- photoelectric effect
- collimator interactions
- air interactions
- world interactions
- secondary particle interactions

### Task 7.3: Record scatter position

When a valid Compton or Rayleigh event occurs inside PMMA, use:

```cpp
step->GetPostStepPoint()->GetPosition()
```

Update:

- total scatter count
- Compton count or Rayleigh count
- first scatter position if this is the first scatter
- last scatter position

### Task 7.4: Detect detector plane crossing

The detector plane is:

```text
z = -73 mm
```

Crossing condition:

```text
preStep.z > detector_z
postStep.z <= detector_z
direction.z < 0
```

### Task 7.5: Compute crossing point by linear interpolation

Compute the detector crossing point from the pre-step and post-step positions.

The crossing point must lie within:

```text
53 mm <= det_x <= 161 mm
-50 mm <= det_y <= 50 mm
```

### Task 7.6: Record detector hit

When a primary gamma crosses the detector plane within bounds, record:

- `det_x`
- `det_y`
- `det_z`
- `det_energy`
- `det_dir_x`
- `det_dir_y`
- `det_dir_z`

Prevent duplicate hit recording for the same event if the same primary track crosses the plane more than once.

## Done when

- Only primary gamma tracks contribute to event records.
- PMMA Compton and Rayleigh scatter counts are updated correctly.
- First and last scatter positions are updated correctly.
- Detector hits are recorded only for valid plane crossings within bounds.
- Events not reaching the detector remain unhit.
- No CSV file is written yet unless M8 has already been implemented separately.

## Do

- Use process names `compt` and `Rayl`.
- Use post-step point for scatter position.
- Use linear interpolation for detector crossing.
- Use the detector bounds from `DetectorConstruction` or a shared config object.
- Keep step logic narrow and explicit.

## Do not

- Do not count secondary gamma tracks.
- Do not count scatter in tungsten, air, or world.
- Do not count photoelectric effect as scatter.
- Do not output unhit events.
- Do not change the CSV schema.
- Do not implement detector material response.
- Do not write full trajectory output.

## Suggested Codex prompt

```text
Read spec.md, architecture.md, and milestones.md.
Implement Milestone 7 only: Stepping logic.
Only process primary gamma tracks. Count PMMA-internal Compton and Rayleigh scatters using post-step positions, and detect detector plane crossing at z=-73 mm using linear interpolation and detector bounds.
Do not count secondary particles, tungsten interactions, air/world interactions, or photoelectric effect.
Do not change the CSV schema, do not add detector response, and do not output full trajectories.
After implementation, summarize files changed and describe how to inspect scatter and detector-hit state.
```

---

# Milestone 8: CSV output in single-thread mode

## Goal

Implement CSV output for single-thread mode.

This milestone should create the output file, write the correct header, and write one row per detected primary gamma.

Multi-thread temporary files and merging are deferred to Milestone 9.

## Files to create or modify

Modify:

- `include/CsvWriter.hh`
- `src/CsvWriter.cc`
- `include/RunAction.hh`
- `src/RunAction.cc`
- `include/EventAction.hh`
- `src/EventAction.cc`
- `include/SimulationConfig.hh` if file naming helpers are added
- `src/SimulationConfig.cc` if file naming helpers are added

## Tasks

### Task 8.1: Implement output directory creation

Use configured output directory:

```text
/output/directory results
```

Default:

```text
results/
```

If the directory does not exist, create it.

If creation fails, report a clear error and stop.

### Task 8.2: Implement file naming for single-thread mode

Use file names from `spec.md`.

Mono compact:

```text
results/hits_profile_{profile_id}_mono_{energy}keV_seed{seed}.csv
```

Mono debug:

```text
results/hits_profile_{profile_id}_mono_{energy}keV_seed{seed}_debug.csv
```

Spectrum compact:

```text
results/hits_profile_{profile_id}_spectrum_seed{seed}.csv
```

Spectrum debug:

```text
results/hits_profile_{profile_id}_spectrum_seed{seed}_debug.csv
```

### Task 8.3: Implement compact header

Compact header:

```csv
initial_energy,det_x,det_y,det_energy,scatter_count_total,compton_count,rayleigh_count,is_multiple_scatter,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z
```

### Task 8.4: Implement debug header

Debug header:

```csv
event_id,track_id,parent_id,det_z,det_dir_x,det_dir_y,det_dir_z,initial_energy,det_x,det_y,det_energy,scatter_count_total,compton_count,rayleigh_count,is_multiple_scatter,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z
```

### Task 8.5: Write only detected events

At end of event:

- if primary gamma reached detector: write one row
- if not detected: write nothing

### Task 8.6: Connect writer lifecycle

`RunAction` should manage writer lifecycle:

- open writer at run start
- close writer at run end

`EventAction` should write event rows through the writer or a controlled interface.

## Done when

- Single-thread `debug` mode writes a CSV file with debug header.
- Single-thread `compact` mode writes a CSV file with compact header.
- Only detected primary gamma events are written.
- No extra columns are added.
- Output units follow the project convention: mm and keV.
- Multi-thread merge is not implemented yet.

## Do

- Preserve exact field order.
- Write one row per detected primary gamma.
- Use NaN for missing scatter positions.
- Keep debug and compact modes separate.
- Keep output directory creation explicit.

## Do not

- Do not implement multi-thread merge in this milestone.
- Do not let multiple threads share one `std::ofstream`.
- Do not add `run_id`, `profile_id`, `energy_mode`, or `random_seed` as CSV columns.
- Do not output unhit events.
- Do not change field names.
- Do not add post-processing analysis.

## Suggested Codex prompt

```text
Read spec.md, architecture.md, and milestones.md.
Implement Milestone 8 only: CSV output in single-thread mode.
Create CsvWriter, write exact debug and compact headers, generate file names from profile_id, energy mode, mono energy, seed, and debug mode, and write one row only for detected primary gamma events.
Do not implement multi-thread merging, do not share ofstream across threads, and do not add columns beyond the specified CSV schema.
After implementation, summarize files changed and how to test single-thread debug and compact output.
```

---

# Milestone 9: Multi-thread output merge

## Goal

Implement multi-thread-safe CSV output.

Each worker thread must write its own temporary CSV file. The master must merge thread files at the end of the run.

## Files to create or modify

Modify:

- `include/CsvWriter.hh`
- `src/CsvWriter.cc`
- `include/RunAction.hh`
- `src/RunAction.cc`
- `include/EventAction.hh` if writer access needs adjustment
- `src/EventAction.cc` if writer access needs adjustment
- `include/SimulationConfig.hh` if helper methods are needed
- `src/SimulationConfig.cc` if helper methods are needed

## Tasks

### Task 9.1: Create temporary output directory

Thread temporary files must be placed in:

```text
results/tmp/
```

or under the configured output directory:

```text
{outputDirectory}/tmp/
```

If creation fails, report a clear error and stop.

### Task 9.2: Implement per-thread temporary file naming

Temporary files should include:

- profile ID
- energy mode
- mono energy if mono mode
- seed
- debug suffix if debug mode
- thread ID

Examples:

```text
results/tmp/hits_profile_P001_mono_160keV_seed12345_thread0.csv
results/tmp/hits_profile_P001_mono_160keV_seed12345_thread1.csv
results/tmp/hits_profile_P001_mono_160keV_seed12345_debug_thread0.csv
```

### Task 9.3: Ensure each worker writes independently

Each worker thread must own or access only its own writer/file.

No multiple worker threads may write to the same `std::ofstream`.

### Task 9.4: Merge temporary files on master

At run end, the master should merge temporary files into the final output file.

Rules:

- keep only one header
- preserve all data rows
- report clear error if any expected temp file cannot be read
- report clear error if final output file cannot be written

### Task 9.5: Delete or preserve temp files based on mode

After successful merge:

- compact mode: delete corresponding temp files
- debug mode: preserve corresponding temp files

If merge fails:

- preserve all temporary files
- report error

### Task 9.6: Preserve single-thread behavior

Single-thread output should still work.

Implementation may use the same per-thread file path even for thread 0 if this simplifies the design, but final behavior must match expected output file naming.

## Done when

- Multi-thread compact run writes per-thread temporary CSV files.
- Master merges temporary CSV files into one final compact CSV file.
- Only one header appears in the final file.
- Compact mode deletes temp files after successful merge.
- Debug mode preserves temp files after successful merge.
- Merge failure preserves temp files and reports an error.
- No shared `std::ofstream` is used across threads.

## Do

- Use thread-local or per-thread writer ownership.
- Keep merge logic on master.
- Keep compact/debug behavior exactly as specified.
- Keep headers identical to Milestone 8.
- Preserve final file naming rules.

## Do not

- Do not allow worker threads to write to the final file directly.
- Do not share one `std::ofstream` between threads.
- Do not merge from worker threads.
- Do not delete temp files on merge failure.
- Do not add columns to identify thread ID in compact output.
- Do not change single-thread CSV schema.

## Suggested Codex prompt

```text
Read spec.md, architecture.md, and milestones.md.
Implement Milestone 9 only: Multi-thread output merge.
Each worker thread must write an independent temporary CSV file under results/tmp, and the master must merge them at run end with only one header.
Compact mode should delete temp files after successful merge; debug mode should preserve temp files. Merge failure must preserve temp files and report an error.
Do not let multiple threads share an ofstream, do not let workers write directly to the final output file, and do not change the CSV schema.
After implementation, summarize files changed and provide single-thread and multi-thread test commands.
```

---

# Milestone 10: Macros, README alignment, and acceptance tests

## Goal

Complete first-version project usability materials and acceptance checks.

This milestone should ensure the project can be built, run, visualized, and checked against the first-version requirements.

## Files to create or modify

Create or modify:

- `macros/run.mac`
- `macros/run_mt.mac`
- `macros/vis.mac`
- `data/collimator_profiles.csv`
- `data/spectrum.csv`
- `README.md`
- optional `tests/` or `docs/acceptance_checklist.md` if useful

## Tasks

### Task 10.1: Create `macros/run.mac`

Single-thread minimal test macro:

```text
/run/numberOfThreads 1
/run/randomSeed 12345

/geometry/collimatorProfileFile data/collimator_profiles.csv
/geometry/collimatorProfileId P001
/geometry/enableAirDefect true

/source/energyMode mono
/source/monoEnergy 160 keV

/output/directory results
/output/debug true

/run/initialize
/run/beamOn 1000
```

Expected output:

```text
results/hits_profile_P001_mono_160keV_seed12345_debug.csv
```

### Task 10.2: Create `macros/run_mt.mac`

Multi-thread formal run test macro:

```text
/run/numberOfThreads 8
/run/randomSeed 12345

/geometry/collimatorProfileFile data/collimator_profiles.csv
/geometry/collimatorProfileId P001
/geometry/enableAirDefect true

/source/energyMode mono
/source/monoEnergy 160 keV

/output/directory results
/output/debug false

/run/initialize
/run/beamOn 100000
```

Expected output:

```text
results/hits_profile_P001_mono_160keV_seed12345.csv
```

### Task 10.3: Create `macros/vis.mac`

Visualization macro should support checking:

- PMMA phantom
- optional air defect
- two pentagonal tungsten jaws
- detector helper plane
- source position
- small number of gamma tracks

### Task 10.4: Create placeholder collimator profile data

Create `data/collimator_profiles.csv` containing placeholder `P001`:

```csv
profile_id,jaw_id,vertex_id,x_mm,z_mm
P001,jaw_0,0,50,-28
P001,jaw_0,1,105,-28
P001,jaw_0,2,106,-24
P001,jaw_0,3,105,-20
P001,jaw_0,4,50,-20
P001,jaw_1,0,108,-24
P001,jaw_1,1,109,-28
P001,jaw_1,2,164,-28
P001,jaw_1,3,164,-20
P001,jaw_1,4,109,-20
```

Clearly state that this is placeholder geometry and not a real collimator profile.

### Task 10.5: Create sample spectrum data

Create `data/spectrum.csv` with a small valid example.

The file is only a placeholder for testing spectrum mode unless a real spectrum is later provided.

### Task 10.6: Update README

README must include:

1. project overview
2. software environment
3. build commands
4. single-thread run command
5. multi-thread run command
6. visualization run command
7. macro command summary
8. collimator profile CSV format
9. spectrum CSV format
10. output CSV fields
11. debug vs compact mode
12. placeholder profile warning
13. first-version limitations

### Task 10.7: Add acceptance checklist

Document checks for:

- geometry visualization
- single-thread debug run
- multi-thread compact run
- invalid profile handling
- CSV header correctness
- temp file cleanup behavior

## Done when

- `./BackscatterSim macros/run.mac` produces the expected debug CSV.
- `./BackscatterSim macros/run_mt.mac` produces the expected compact CSV.
- `macros/vis.mac` supports geometry and track visualization.
- README commands match actual project behavior.
- Placeholder data files are present.
- Acceptance checklist matches the project specification.

## Do

- Keep macros aligned with `spec.md`.
- Keep README factual and command-oriented.
- Clearly mark placeholder data as placeholder.
- Include exact build and run commands.
- Include expected output file names.

## Do not

- Do not add post-processing Python analysis scripts.
- Do not add image reconstruction.
- Do not add real detector material response.
- Do not add profile batch scanning.
- Do not add first-version features not present in `spec.md`.
- Do not claim placeholder profile represents real collimator geometry.

## Suggested Codex prompt

```text
Read spec.md, architecture.md, and milestones.md.
Implement Milestone 10 only: Macros, README alignment, and acceptance tests.
Create run.mac, run_mt.mac, vis.mac, placeholder collimator_profiles.csv, sample spectrum.csv, and update README with build/run instructions, macro commands, CSV schemas, debug/compact distinction, and first-version limitations.
Do not add post-processing scripts, image reconstruction, detector material response, or profile batch scanning.
After implementation, summarize files changed and list the acceptance tests to run.
```

---

# Deferred work

The following items are explicitly outside the first implementation sequence.

Codex must not implement these unless a future milestone or updated `spec.md` explicitly requests them.

## Deferred simulation features

- Image reconstruction
- Real detector material response
- Detector energy deposition scoring
- Source collimator modeling
- Source position macro commands
- Detector boundary macro commands
- Full scatter trajectory output
- Automatic scanning over all collimator profiles
- Real collimator profile generation logic

## Deferred data and analysis features

- Real measured spectrum file
- Real collimator profile coordinates
- Python post-processing scripts
- Multiple-scatter ratio plots
- Energy distribution plots
- Detector x-distribution plots
- Profile comparison plots
- Conference-paper figure generation

## Deferred engineering features

- Unit test framework
- CI configuration
- Containerized build environment
- Performance benchmarking
- Large-scale batch run manager
- Metadata database for simulation campaigns

---

# Suggested overall Codex workflow

Use this workflow after all planning files are present:

```text
Read spec.md, architecture.md, and milestones.md.
Do not write code yet.
Summarize the implementation order from milestones.md and identify any ambiguity that blocks Milestone 0.
```

Then proceed milestone by milestone:

```text
Read spec.md, architecture.md, and milestones.md.
Implement Milestone 0 only.
Do not implement Milestone 1 or later.
After implementation, summarize changed files, how to build, and what remains deferred.
```

After each milestone:

```text
Review the previous implementation against milestones.md.
Check whether it implemented anything beyond the requested milestone.
If yes, identify the extra changes and suggest whether to revert them.
Do not write new code unless asked.
```

