# BackscatterSim Architecture

## 1. Purpose

This document defines the implementation architecture for `BackscatterSim`.

It is intended for Codex-assisted development. It should be read together with `spec.md`.

- `spec.md` defines the simulation requirements and accepted behavior.
- `architecture.md` defines how the code should be organized to satisfy those requirements.
- If there is a conflict, `spec.md` is the source of truth.

This file should not duplicate every physical parameter from `spec.md`. It should clarify module boundaries, ownership, data flow, Geant4 lifecycle, and implementation constraints.

---

## 2. Architectural Principles

### 2.1 Keep physics intent separate from software plumbing

The project is not a general Geant4 framework. It is a focused gamma backscatter simulator.

The code should keep the following concerns separate:

| Concern | Main owner |
|---|---|
| Geometry construction | `DetectorConstruction`, `CollimatorBuilder` |
| External collimator profile parsing | `CollimatorProfileReader` |
| Physics process registration | `PhysicsList` |
| Primary gamma generation | `PrimaryGeneratorAction`, `SpectrumSampler` |
| Per-event scatter summary | `EventAction` |
| Per-step detection and scattering logic | `SteppingAction` |
| CSV output and file merging | `CsvWriter`, `RunAction` |
| Run-level configuration and naming | `RunAction`, messenger/config classes |

No class should become a global container for unrelated state.

---

### 2.2 Use explicit data structures for cross-module information

Avoid passing raw unrelated variables across classes. Use small structs for stable interfaces.

Recommended shared data structures:

```cpp
struct DetectorPlaneConfig {
    double z_mm = -73.0;
    double x_min_mm = 53.0;
    double x_max_mm = 161.0;
    double y_min_mm = -50.0;
    double y_max_mm = 50.0;
};
```

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

```cpp
struct ScatterSummary {
    int scatter_count_total = 0;
    int compton_count = 0;
    int rayleigh_count = 0;

    bool has_scatter = false;
    G4ThreeVector first_scatter_pos;
    G4ThreeVector last_scatter_pos;
};
```

```cpp
struct DetectorHitRecord {
    bool detected = false;

    double det_x = 0.0;
    double det_y = 0.0;
    double det_z = -73.0;
    double det_energy_keV = 0.0;

    G4ThreeVector det_dir;
};
```

```cpp
struct EventRecord {
    int event_id = -1;
    int track_id = 1;
    int parent_id = 0;

    double initial_energy_keV = 0.0;
    ScatterSummary scatter;
    DetectorHitRecord hit;
};
```

These structs may be placed in a small header such as `include/SimulationData.hh` if Codex needs a shared location.

---

## 3. Repository Layout

Target layout:

```text
MSS/
├── AGENTS.md
├── CMakeLists.txt
├── README.md
├── docs/
│   ├── architecture.md
│   ├── decisions.md
│   ├── milestones.md
│   ├── spec.md
├── include/
│   ├── DetectorConstruction.hh
│   ├── PhysicsList.hh
│   ├── PrimaryGeneratorAction.hh
│   ├── RunAction.hh
│   ├── EventAction.hh
│   ├── SteppingAction.hh
│   ├── CollimatorProfileReader.hh
│   ├── CollimatorBuilder.hh
│   ├── SpectrumSampler.hh
│   ├── CsvWriter.hh
│   └── SimulationData.hh
├── src/
│   ├── DetectorConstruction.cc
│   ├── PhysicsList.cc
│   ├── PrimaryGeneratorAction.cc
│   ├── RunAction.cc
│   ├── EventAction.cc
│   ├── SteppingAction.cc
│   ├── CollimatorProfileReader.cc
│   ├── CollimatorBuilder.cc
│   ├── SpectrumSampler.cc
│   └── CsvWriter.cc
├── macros/
│   ├── vis.mac
│   ├── run.mac
│   └── run_mt.mac
├── data/
│   ├── collimator_profiles.csv
│   └── spectrum.csv
└── results/
```

Optional Geant4 glue classes may be added if needed:

```text
include/ActionInitialization.hh
src/ActionInitialization.cc
```

`ActionInitialization` is acceptable if Codex uses the standard Geant4 pattern to register `PrimaryGeneratorAction`, `RunAction`, `EventAction`, and `SteppingAction`.

---

## 4. Runtime Lifecycle

### 4.1 Program startup

Expected startup sequence:

```text
main()
  ├── create G4RunManager via G4RunManagerFactory
  ├── construct shared configuration objects
  ├── register DetectorConstruction
  ├── register PhysicsList
  ├── register ActionInitialization or individual user actions
  ├── load macro file from argv[1]
  └── execute macro commands
```

The program should support both single-thread and multi-thread execution through Geant4 run manager factory.

Do not hard-code a single-thread run manager.

---

### 4.2 Macro command configuration

Macro commands are the primary user interface.

The first version must support:

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

Implementation requirement:

- Macro values should be stored in explicit config fields.
- Geometry-related commands must be applied before `/run/initialize`.
- Output and source configuration must be available before `/run/beamOn`.
- Invalid command values should fail early with a clear Geant4 exception or fatal error.

Recommended config grouping:

```cpp
struct GeometryConfig {
    std::string collimator_profile_file = "data/collimator_profiles.csv";
    std::string collimator_profile_id = "P001";
    bool enable_air_defect = true;
};

struct SourceConfig {
    std::string energy_mode = "mono";
    double mono_energy_keV = 160.0;
    std::string spectrum_file = "data/spectrum.csv";
};

struct OutputConfig {
    std::string output_directory = "results";
    bool debug = false;
};

struct RunConfig {
    long random_seed = 12345;
    int number_of_threads = 1;
};
```

These structs may be combined into one `SimulationConfig` object.

---

### 4.3 Run initialization

At `/run/initialize`:

1. `DetectorConstruction` builds world, PMMA, optional air defect, collimator, and visualization detector plane.
2. `CollimatorProfileReader` reads and validates the selected profile.
3. `CollimatorBuilder` converts the selected profile into Geant4 tungsten geometry.
4. `PhysicsList` registers Livermore EM physics and production cut.
5. Source and output modules should already have valid configuration.

Any invalid geometry or profile input must stop the program before event generation begins.

---

### 4.4 Run begin

At `BeginOfRunAction`:

1. Apply or confirm random seed.
2. Determine effective output mode.
3. Build final output file name.
4. Create output directory and `results/tmp/` if needed.
5. Initialize per-thread CSV writing.

Default output mode:

| Thread mode | Default output mode |
|---|---|
| Single-thread | `debug` |
| Multi-thread | `compact` |

If `/output/debug` is explicitly set, it overrides the default.

---

### 4.5 Event lifecycle

For each event:

```text
BeginOfEventAction
  ├── reset EventRecord
  ├── reset ScatterSummary
  └── reset DetectorHitRecord

GeneratePrimaries
  ├── sample initial gamma energy
  ├── sample target point on z = 0 circular beam spot
  ├── generate primary gamma from source position
  └── store initial energy in EventAction

SteppingAction
  ├── ignore non-primary gamma tracks
  ├── update PMMA Compton/Rayleigh scatter summary
  ├── test detector plane crossing
  └── record detector hit if crossing point lies inside detector bounds

EndOfEventAction
  ├── if primary gamma was detected: write one CSV row
  └── otherwise write nothing
```

Important invariant:

```text
1 event = 1 primary gamma
1 CSV row = 1 detected primary gamma
```

Events not reaching the detector plane are intentionally absent from the CSV.

---

### 4.6 Run end

At `EndOfRunAction`:

1. Close thread-local CSV files.
2. On master, merge worker CSV files.
3. Keep only one header in the final CSV.
4. In compact mode, delete temporary thread CSV files after successful merge.
5. In debug mode, keep temporary thread CSV files after successful merge.
6. If merging fails, preserve temporary files and report an error.

---

## 5. Component Design

## 5.1 `DetectorConstruction`

### Responsibility

Build all Geant4 geometry:

- World volume.
- PMMA phantom.
- Optional air defect.
- Collimator tungsten jaws.
- Visualization helper for detector plane.

### Inputs

- `GeometryConfig`
- `DetectorPlaneConfig`
- `CollimatorProfileReader`
- `CollimatorBuilder`

### Outputs

- Geant4 physical world.
- Accessible detector plane bounds for `SteppingAction`.
- Stable volume names for scatter filtering.

### Required volume naming

Use stable names so step logic can identify PMMA interactions:

```text
WorldLogical
PMMALogical
AirDefectLogical
CollimatorJaw0Logical
CollimatorJaw1Logical
DetectorPlaneVisLogical
```

`SteppingAction` should not rely on visual attributes or placement order.

---

## 5.2 `CollimatorProfileReader`

### Responsibility

Read, filter, validate, and return one collimator profile.

### Input

CSV file:

```csv
profile_id,jaw_id,vertex_id,x_mm,z_mm
```

### Output

```cpp
CollimatorProfile
```

### Validation rules

Fatal errors:

- Requested `profile_id` does not exist.
- Profile does not contain exactly two jaws.
- A jaw does not contain exactly five vertices.
- `vertex_id` is missing, duplicated, or outside `0..4`.
- Coordinate is empty, non-numeric, NaN, or Inf.
- Polygon area is zero.
- Polygon is not convex.

### Boundary

This class validates geometry data but does not create Geant4 solids.

---

## 5.3 `CollimatorBuilder`

### Responsibility

Convert a validated `CollimatorProfile` into Geant4 tungsten geometry.

### Required implementation

- Use `G4ExtrudedSolid`.
- Treat input `x_mm` and `z_mm` as global coordinates.
- Map input `(x_mm, z_mm)` to the local 2D section of `G4ExtrudedSolid`.
- Extrude along local z with half-length `60 mm`.
- Rotate so extrusion corresponds to global y direction.
- Do not add an extra collimator center z offset.

### Boundary

This class should not parse CSV and should not decide which profile ID is used.

---

## 5.4 `PhysicsList`

### Responsibility

Define Geant4 physics processes.

### Required implementation

- Register `G4EmLivermorePhysics`.
- Set global production cut to `0.1 mm`.

### Boundary

This class should not contain geometry, source, output, or event-recording logic.

---

## 5.5 `PrimaryGeneratorAction`

### Responsibility

Generate one primary gamma per event.

### Required behavior

- Particle type: gamma.
- Source position: `(0, 0, -185 mm)`.
- Beam model: cone beam generated by target-plane sampling.
- Target plane: `z = 0 mm`.
- Beam spot: circular disk of radius `1.5 mm`.
- Energy mode: `mono` or `spectrum`.

### Data handoff

After choosing the initial energy, call into `EventAction` or a shared event state interface to store:

```text
initial_energy_keV
```

### Boundary

This class should not write CSV and should not inspect detector crossing.

---

## 5.6 `SpectrumSampler`

### Responsibility

Read and sample a gamma energy spectrum.

### Input

CSV file:

```csv
energy_keV,weight
```

### Required behavior

- Validate positive finite energies.
- Validate non-negative finite weights.
- Reject empty spectra.
- Reject spectra with zero total weight.
- Normalize weights internally.
- Build CDF.
- Sample one energy per event.

### Boundary

This class should not know about Geant4 events, geometry, or output files.

---

## 5.7 `EventAction`

### Responsibility

Own the current event record.

### Required behavior

At event start:

- Reset all scatter counters.
- Reset first and last scatter positions.
- Reset detector hit flag.

During event:

- Provide methods used by `PrimaryGeneratorAction` and `SteppingAction`:

```cpp
void SetInitialEnergy(double energy_keV);
void AddScatter(const std::string& process_name, const G4ThreeVector& pos);
void SetDetectorHit(const DetectorHitRecord& hit);
```

At event end:

- If `hit.detected == true`, write exactly one CSV row.
- If `hit.detected == false`, write nothing.

### Boundary

This class should not determine whether a step is Compton/Rayleigh or whether a detector crossing occurred. That logic belongs in `SteppingAction`.

---

## 5.8 `SteppingAction`

### Responsibility

Inspect each step and update event state.

### Step filter

Only process steps satisfying:

```text
particle == gamma
track_id == 1
parent_id == 0
```

### Scatter detection

A scatter is counted only when:

```text
processName == "compt" || processName == "Rayl"
```

and the interaction is inside PMMA.

Recommended interaction position:

```cpp
step->GetPostStepPoint()->GetPosition()
```

Do not count:

- Photoelectric effect.
- Interactions in tungsten collimator.
- Interactions in air or world.
- Secondary gamma interactions.

### Detector crossing

Detector plane crossing condition:

```text
preStep.z > detector_z
postStep.z <= detector_z
direction.z < 0
```

Crossing point interpolation:

```text
t = (detector_z - pre_z) / (post_z - pre_z)
det_x = pre_x + t * (post_x - pre_x)
det_y = pre_y + t * (post_y - pre_y)
```

Accept hit only if:

```text
53 mm <= det_x <= 161 mm
-50 mm <= det_y <= 50 mm
```

### Multiple crossing protection

After a valid detector hit has been recorded for an event, later crossings in the same event should not create additional CSV rows.

---

## 5.9 `CsvWriter`

### Responsibility

Write CSV rows safely in single-thread and multi-thread runs.

### Required behavior

- Generate correct header for debug or compact mode.
- Open one CSV file per worker thread.
- Never share one `std::ofstream` across worker threads.
- Convert Geant4 units to mm and keV before writing.
- Represent unavailable scatter positions as `NaN`.
- Merge worker files on master at run end.
- Keep one header in final output.

### Compact columns

```csv
initial_energy,det_x,det_y,det_energy,scatter_count_total,compton_count,rayleigh_count,is_multiple_scatter,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z
```

### Debug columns

```csv
event_id,track_id,parent_id,det_z,det_dir_x,det_dir_y,det_dir_z,initial_energy,det_x,det_y,det_energy,scatter_count_total,compton_count,rayleigh_count,is_multiple_scatter,first_scatter_x,first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z
```

---

## 5.10 `RunAction`

### Responsibility

Manage run-level initialization and finalization.

### Required behavior

- Initialize random seed.
- Resolve debug or compact output mode.
- Construct final and temporary output file names.
- Initialize CSV writer at begin of run.
- Trigger CSV merge at end of run.

### Boundary

This class should not perform per-step physics checks and should not parse collimator profile geometry.

---

## 6. Data Flow Summary

```text
Macro commands
  └── SimulationConfig
        ├── DetectorConstruction
        │     ├── CollimatorProfileReader
        │     └── CollimatorBuilder
        ├── PrimaryGeneratorAction
        │     └── SpectrumSampler
        ├── RunAction
        │     └── CsvWriter
        └── SteppingAction
              └── DetectorPlaneConfig
```

Per event:

```text
PrimaryGeneratorAction
  └── initial energy
        ↓
EventAction::EventRecord
        ↑
SteppingAction
  ├── PMMA scatter updates
  └── detector crossing update
        ↓
EndOfEventAction
  └── CsvWriter::WriteRow(EventRecord)
```

---

## 7. Threading Model

### 7.1 Thread ownership

In multi-thread mode:

- Worker threads process events.
- Each worker writes to its own temporary CSV file.
- Master merges files after workers finish.

### 7.2 Shared state rules

Allowed shared read-only state:

- Geometry constants.
- Detector plane bounds.
- Frozen configuration values.

Avoid shared mutable state during event processing.

Disallowed:

- A single global `std::ofstream` used by multiple threads.
- Updating one shared `EventRecord` from multiple threads.
- Accumulating all event records in memory before writing.

---

## 8. Error Handling Policy

Use fail-fast behavior for invalid input or impossible geometry.

Fatal at initialization:

- Missing collimator profile file.
- Missing requested profile ID.
- Invalid jaw count or vertex count.
- Invalid polygon shape.
- Invalid spectrum file when spectrum mode is selected.
- Cannot create output directory.

Fatal at runtime:

- CSV file cannot be opened.
- CSV merge fails.

Non-fatal by design:

- Event does not reach detector.
- Event has zero PMMA scatter but reaches detector.
- Event undergoes photoelectric absorption before detection.

---

## 9. Units and Output Convention

Internal Geant4 values may use Geant4 units.

CSV output convention:

| Quantity | CSV unit |
|---|---|
| Length | mm |
| Energy | keV |

Do not add extra unit suffixes to CSV field names unless `spec.md` is changed.

---

## 10. Implementation Boundaries for Codex

Codex should implement the project incrementally.

Recommended rule:

> Implement one module or one narrow integration step at a time. Compile after each step.

Good Codex tasks:

```text
Read spec.md and architecture.md. Implement only CollimatorProfileReader and its header/source files. Do not modify unrelated files except CMakeLists.txt if needed. Ensure it validates profile_id, jaw count, vertex ids, finite coordinates, polygon area, and convexity.
```

```text
Read spec.md and architecture.md. Implement DetectorConstruction using the existing CollimatorProfileReader and CollimatorBuilder interfaces. Do not implement CSV output in this step.
```

```text
Read spec.md and architecture.md. Implement EventAction and SteppingAction detector crossing logic. Do not change geometry constants unless required by spec.md.
```

Poor Codex tasks:

```text
Build the whole project.
```

```text
Make it work.
```

```text
Implement everything from the spec.
```

These prompts are too broad and make it harder to inspect errors.

---

## 11. First Implementation Pass

The first pass should prioritize a compileable and inspectable project over performance.

Suggested order:

1. CMake skeleton and executable entry point.
2. `PhysicsList`.
3. Config structs and macro messengers.
4. `CollimatorProfileReader`.
5. `CollimatorBuilder`.
6. `DetectorConstruction` with visualization support.
7. `PrimaryGeneratorAction` in mono mode.
8. `EventAction` and `SteppingAction` for detector crossing.
9. `CsvWriter` in single-thread debug mode.
10. Multi-thread per-worker CSV files.
11. Master CSV merge.
12. `SpectrumSampler` and spectrum mode.
13. `vis.mac`, `run.mac`, `run_mt.mac`.
14. README update.

This order is architectural guidance only. `milestones.md` should define acceptance criteria and checkpoints.

---

## 12. Non-Goals for Version 1

The first version must not expand into unrelated features.

Do not implement unless later specified:

- Image reconstruction.
- Real detector material response.
- Detector energy deposition scoring.
- Automatic traversal of all collimator profiles.
- Full scatter trajectory output.
- Macro-controlled source position.
- Macro-controlled detector bounds.
- Real collimator profile generation logic.

---

## 13. Architecture Acceptance Checklist

The implementation is consistent with this architecture if:

- `spec.md` remains the source of truth for physical parameters.
- Geometry construction, profile parsing, event tracking, and CSV output are in separate modules.
- Only primary gamma tracks are recorded.
- PMMA Compton/Rayleigh scatter counts are attached to the current event.
- Detector crossing uses plane interpolation.
- One detected primary gamma produces one CSV row.
- Multi-thread output never shares one stream across workers.
- Compact mode deletes temporary CSV files only after successful merge.
- Debug mode preserves temporary CSV files after successful merge.
- Invalid profile inputs fail before event generation.
