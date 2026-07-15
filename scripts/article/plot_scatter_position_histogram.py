#!/usr/bin/env python3
"""Build a condition-level scatter-position histogram from cleaned article data.

Purpose
-------
The script reads ``events_clean.csv`` files produced by ``clean_events.py`` and
histograms one of the six scatter-position fields: first/last scatter on the
x/y/z axis.  Events from the requested S1/S2/S3 channels are pooled into one
histogram.  All matching input files are summed at the condition level.  Counts
are reported for all valid scatters, single scatters (k1), and multiple
scatters (ms); seeds are retained only as provenance.

Inputs
------
``--input-root`` is searched recursively for ``events_clean.csv`` and adjacent
``metadata.yaml`` files.  The CSV must contain ``slit_id``,
``scatter_count_total``, and the selected coordinate field.  Metadata supplies
the phantom ID, primary count, and condition snapshot.  Both raw run metadata
and ``merged_article_batches: true`` condition metadata are accepted.  Scatter
count 0 is invalid for this analysis and is excluded.

Bins use ``[left, right)`` intervals, except that the final bin includes its
right edge.  ``--start-mm`` and ``--bin-width-mm`` are required.  ``--end-mm``
is optional; without it, the maximum selected coordinate is rounded upward to
a complete bin.

Outputs
-------
The output directory receives ``scatter_position_histogram.csv`` (one row per
bin), ``scatter_position_histogram.png`` (condition-count bar chart), and
``analysis_manifest.yaml`` (inputs, provenance, exclusions, bin rules, and output
paths).  Input event files are never modified.

Example
-------
::

    conda run -n data python scripts/article/plot_scatter_position_histogram.py \
      --input-root results/article/test_E1_P0_P5_E460_grid_x0_y0/cleaned \
      --phantom-id P0 --scatter-point first --axis z --slits S2 \
      --start-mm 0 --bin-width-mm 2 \
      --output-dir results/article/test_E1_P0_P5_E460_grid_x0_y0/first_scatter_z_P0
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as error:  # pragma: no cover - exercised by CLI users.
    raise RuntimeError(
        "scatter-position analysis requires PyYAML. "
        "Run `conda activate data` or use `conda run -n data python ...`."
    ) from error


ALLOWED_SLITS = ("S1", "S2", "S3")
HISTOGRAM_CSV_NAME = "scatter_position_histogram.csv"
HISTOGRAM_PNG_NAME = "scatter_position_histogram.png"
MANIFEST_NAME = "analysis_manifest.yaml"
CSV_FIELDS = (
    "condition_id",
    "phantom_id",
    "scatter_point",
    "axis",
    "selected_slits",
    "bin_index",
    "bin_left_mm",
    "bin_right_mm",
    "bin_center_mm",
    "count_total",
    "count_k1",
    "count_ms",
    "n_primary_total",
)


@dataclass(frozen=True)
class RunInfo:
    """Resolved input files and normalized condition-level provenance."""

    events_path: Path
    metadata_path: Path
    phantom_id: str
    seeds: tuple[int, ...]
    n_primary: int
    condition_id: str
    condition_signature: dict[str, Any]


@dataclass(frozen=True)
class BinSpec:
    """Uniform histogram bounds in millimetres."""

    start_mm: float
    end_mm: float
    width_mm: float
    bin_count: int
    range_source: str


def read_yaml(path: Path) -> dict[str, Any]:
    """Read a YAML mapping or raise when the document is not a mapping."""

    with path.open("r", encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"metadata root must be a map: {path}")
    return value


def nested(mapping: dict[str, Any], *keys: str, default: Any = None) -> Any:
    value: Any = mapping
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


def coordinate_field(scatter_point: str, axis: str) -> str:
    """Return the CSV coordinate field for a first/last and x/y/z selection."""

    if scatter_point not in {"first", "last"}:
        raise ValueError("scatter_point must be first or last")
    if axis not in {"x", "y", "z"}:
        raise ValueError("axis must be x, y, or z")
    return f"{scatter_point}_scatter_{axis}"


def parse_slits(text: str) -> tuple[str, ...]:
    """Parse a comma-separated, duplicate-free subset of S1/S2/S3."""

    values = tuple(part.strip().upper() for part in text.split(",") if part.strip())
    if not values:
        raise ValueError("at least one slit must be selected")
    if len(set(values)) != len(values):
        raise ValueError("selected slits must not contain duplicates")
    unknown = [value for value in values if value not in ALLOWED_SLITS]
    if unknown:
        raise ValueError("unknown slit(s): " + ", ".join(unknown))
    return values


def discover_event_files(input_root: Path, events_name: str) -> list[Path]:
    """Recursively discover cleaned event files, or accept one named file."""

    if input_root.is_file():
        if input_root.name != events_name:
            raise ValueError(f"input file must be named {events_name}: {input_root}")
        return [input_root.resolve()]
    if not input_root.is_dir():
        raise FileNotFoundError(f"input root does not exist: {input_root}")
    return sorted(path.resolve() for path in input_root.rglob(events_name) if path.is_file())


def metadata_value(
    metadata: dict[str, Any],
    top_level_key: str,
    condition_key: str,
    metadata_path: Path,
) -> Any:
    """Resolve equivalent raw/merged metadata fields and reject disagreement."""

    top_level = metadata.get(top_level_key)
    condition_value = nested(metadata, "condition", condition_key)
    if top_level is not None and condition_value is not None and top_level != condition_value:
        raise ValueError(
            f"metadata {top_level_key} and condition.{condition_key} disagree: {metadata_path}"
        )
    return top_level if top_level is not None else condition_value


def metadata_seeds(metadata: dict[str, Any], metadata_path: Path) -> tuple[int, ...]:
    """Return raw or merged seed values for provenance only."""

    if metadata.get("merged_article_batches") is True:
        values = nested(metadata, "merge", "seeds", default=[])
        if not isinstance(values, list):
            raise ValueError(f"metadata merge.seeds must be a list: {metadata_path}")
    elif metadata.get("random_seed") is None:
        values = []
    else:
        values = [metadata.get("random_seed")]
    try:
        return tuple(int(value) for value in values)
    except (TypeError, ValueError) as error:
        raise ValueError(f"metadata seeds must be integers: {metadata_path}") from error


def metadata_condition_signature(
    metadata: dict[str, Any], phantom_id: str, metadata_path: Path
) -> dict[str, Any]:
    """Build a normalized physical-condition snapshot for compatibility checks."""

    return {
        "phantom_id": phantom_id,
        "vehicle_geometry_file": metadata_value(
            metadata, "vehicle_geometry_file", "geometry_file", metadata_path
        ),
        "model_type": metadata.get("model_type"),
        "selected_target_component": metadata.get("selected_target_component"),
        "abnormal_material": metadata.get("abnormal_material"),
        "pose": metadata_value(metadata, "pose_id", "pose", metadata_path),
        "head_offset_x_mm": metadata_value(
            metadata, "head_offset_x_mm", "head_offset_x_mm", metadata_path
        ),
        "head_offset_y_mm": metadata_value(
            metadata, "head_offset_y_mm", "head_offset_y_mm", metadata_path
        ),
        "experiment": nested(metadata, "condition", "experiment"),
        "defect_depth_id": nested(metadata, "condition", "defect_depth_id"),
        "source": metadata.get("source"),
        "collimator": metadata.get("collimator"),
        "detector": metadata.get("detector"),
        "physics": metadata.get("physics"),
    }


def condition_id_from_metadata(metadata: dict[str, Any], phantom_id: str) -> str:
    merged_condition_id = str(nested(metadata, "condition", "condition_id", default="") or "")
    if merged_condition_id:
        return merged_condition_id
    case_id = str(metadata.get("case_id", metadata.get("run_id", phantom_id)) or "")
    if case_id:
        return re.sub(r"_seed-?\d+$", "", case_id)
    energy = nested(metadata, "source", "mono_energy_keV", default="unknown")
    pose = metadata.get("pose_id") or nested(metadata, "condition", "pose", default="unknown_pose")
    return f"{phantom_id}_E{energy}_{pose}"


def run_info_for(event_file: Path, metadata_name: str) -> RunInfo:
    """Read and validate provenance for one cleaned event file."""

    metadata_path = event_file.parent / metadata_name
    if not metadata_path.is_file():
        raise FileNotFoundError(f"metadata file not found beside events file: {metadata_path}")
    metadata = read_yaml(metadata_path)
    phantom_id = str(
        metadata_value(metadata, "vehicle_model_id", "phantom_id", metadata_path) or ""
    )
    if not phantom_id:
        raise ValueError(
            "metadata vehicle_model_id or condition.phantom_id is required: "
            f"{metadata_path}"
        )
    try:
        n_primary = int(metadata["n_primary"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"metadata n_primary must be an integer: {metadata_path}") from error
    if n_primary <= 0:
        raise ValueError(f"metadata n_primary must be positive: {metadata_path}")
    return RunInfo(
        events_path=event_file,
        metadata_path=metadata_path,
        phantom_id=phantom_id,
        seeds=metadata_seeds(metadata, metadata_path),
        n_primary=n_primary,
        condition_id=condition_id_from_metadata(metadata, phantom_id),
        condition_signature=metadata_condition_signature(metadata, phantom_id, metadata_path),
    )


def select_runs(
    input_root: Path,
    phantom_id: str,
    events_name: str = "events_clean.csv",
    metadata_name: str = "metadata.yaml",
) -> list[RunInfo]:
    """Select one phantom and enforce one compatible physical condition."""

    event_files = discover_event_files(input_root, events_name)
    if not event_files:
        raise FileNotFoundError(f"no {events_name} files found under {input_root}")
    runs = [run_info_for(path, metadata_name) for path in event_files]
    selected = sorted(
        (run for run in runs if run.phantom_id == phantom_id), key=lambda run: run.events_path
    )
    if not selected:
        raise ValueError(f"no runs found for phantom_id={phantom_id}")

    first = selected[0]
    for run in selected[1:]:
        if run.condition_signature != first.condition_signature:
            raise ValueError(
                "selected runs do not share one physical condition: "
                f"{first.metadata_path} versus {run.metadata_path}"
            )
        if run.condition_id != first.condition_id:
            raise ValueError(
                f"selected runs have different condition IDs: {first.condition_id} and {run.condition_id}"
            )
    return selected


def parse_non_negative_integer(value: Any, source: Path, row_number: int) -> int:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"scatter_count_total must be a non-negative integer in {source} row {row_number}: {value!r}"
        ) from error
    if not math.isfinite(numeric) or numeric < 0.0 or not numeric.is_integer():
        raise ValueError(
            f"scatter_count_total must be a non-negative integer in {source} row {row_number}: {value!r}"
        )
    return int(numeric)


def scan_maximum(run: RunInfo, field: str, selected_slits: tuple[str, ...], start_mm: float) -> float | None:
    """Return the largest valid selected coordinate at or above the start."""

    maximum: float | None = None
    with run.events_path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"events CSV has no header: {run.events_path}")
        missing = sorted({"slit_id", "scatter_count_total", field}.difference(reader.fieldnames))
        if missing:
            raise ValueError(f"events CSV is missing required columns {missing}: {run.events_path}")
        for row_number, row in enumerate(reader, start=2):
            slit_id = str(row.get("slit_id", "")).strip()
            if slit_id not in ALLOWED_SLITS:
                raise ValueError(
                    f"slit_id must be one of {ALLOWED_SLITS} in {run.events_path} "
                    f"row {row_number}: {slit_id!r}"
                )
            scatter_count = parse_non_negative_integer(
                row.get("scatter_count_total"), run.events_path, row_number
            )
            # A zero-scatter detector hit has no valid scattering source for this histogram.
            if slit_id not in selected_slits or scatter_count == 0:
                continue
            try:
                coordinate = float(row.get(field, ""))
            except (TypeError, ValueError):
                continue
            if math.isfinite(coordinate) and coordinate >= start_mm:
                maximum = coordinate if maximum is None else max(maximum, coordinate)
    return maximum


def make_bin_spec(
    runs: list[RunInfo],
    field: str,
    selected_slits: tuple[str, ...],
    start_mm: float,
    bin_width_mm: float,
    end_mm: float | None,
) -> BinSpec:
    """Validate bounds and construct a uniform bin specification."""

    if not math.isfinite(start_mm):
        raise ValueError("start_mm must be finite")
    if not math.isfinite(bin_width_mm) or bin_width_mm <= 0.0:
        raise ValueError("bin_width_mm must be finite and > 0")
    if end_mm is not None:
        if not math.isfinite(end_mm) or end_mm <= start_mm:
            raise ValueError("end_mm must be finite and greater than start_mm")
        span = end_mm - start_mm
        bin_count = int(math.ceil(span / bin_width_mm))
        # An explicit end is authoritative; the final bin may therefore be narrower.
        return BinSpec(start_mm, end_mm, bin_width_mm, bin_count, "explicit_end_mm")

    maxima = [scan_maximum(run, field, selected_slits, start_mm) for run in runs]
    finite_maxima = [value for value in maxima if value is not None]
    if not finite_maxima:
        raise ValueError("no valid selected coordinates are available at or above start_mm")
    observed_max = max(finite_maxima)
    bin_count = max(1, int(math.ceil((observed_max - start_mm) / bin_width_mm)))
    # Rounding upward gives stable shared edges across all compatible inputs.
    auto_end = start_mm + bin_count * bin_width_mm
    return BinSpec(start_mm, auto_end, bin_width_mm, bin_count, "observed_max_aligned")


def bin_run(
    run: RunInfo,
    field: str,
    selected_slits: tuple[str, ...],
    spec: BinSpec,
) -> dict[str, Any]:
    """Count one input file into the shared bins and return exclusion details."""

    counts = [0] * spec.bin_count
    k1_counts = [0] * spec.bin_count
    ms_counts = [0] * spec.bin_count
    zero_scatter_excluded = 0
    nonfinite_excluded = 0
    underflow = 0
    overflow = 0
    with run.events_path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"events CSV has no header: {run.events_path}")
        missing = sorted({"slit_id", "scatter_count_total", field}.difference(reader.fieldnames))
        if missing:
            raise ValueError(f"events CSV is missing required columns {missing}: {run.events_path}")
        for row_number, row in enumerate(reader, start=2):
            slit_id = str(row.get("slit_id", "")).strip()
            if slit_id not in ALLOWED_SLITS:
                raise ValueError(
                    f"slit_id must be one of {ALLOWED_SLITS} in {run.events_path} "
                    f"row {row_number}: {slit_id!r}"
                )
            scatter_count = parse_non_negative_integer(
                row.get("scatter_count_total"), run.events_path, row_number
            )
            if slit_id not in selected_slits:
                continue
            if scatter_count == 0:
                zero_scatter_excluded += 1
                continue
            try:
                coordinate = float(row.get(field, ""))
            except (TypeError, ValueError):
                nonfinite_excluded += 1
                continue
            if not math.isfinite(coordinate):
                nonfinite_excluded += 1
            elif coordinate < spec.start_mm:
                underflow += 1
            elif coordinate > spec.end_mm:
                overflow += 1
            else:
                # The global right edge belongs to the final bin; all internal right edges
                # naturally belong to the following bin through floor division.
                if math.isclose(coordinate, spec.end_mm, rel_tol=0.0, abs_tol=1.0e-12):
                    bin_index = spec.bin_count - 1
                else:
                    bin_index = int(math.floor((coordinate - spec.start_mm) / spec.width_mm))
                    if bin_index >= spec.bin_count:
                        overflow += 1
                        continue
                counts[bin_index] += 1
                if scatter_count == 1:
                    k1_counts[bin_index] += 1
                else:
                    ms_counts[bin_index] += 1
    if any(total != k1 + ms for total, k1, ms in zip(counts, k1_counts, ms_counts)):
        raise RuntimeError(f"internal count invariant failed for {run.events_path}")
    return {
        "run": run,
        "counts": counts,
        "k1_counts": k1_counts,
        "ms_counts": ms_counts,
        "zero_scatter_excluded": zero_scatter_excluded,
        "nonfinite_coordinate_excluded": nonfinite_excluded,
        "underflow": underflow,
        "overflow": overflow,
        "binned_count": sum(counts),
        "binned_k1_count": sum(k1_counts),
        "binned_ms_count": sum(ms_counts),
    }


def build_analysis(
    input_root: Path,
    phantom_id: str,
    scatter_point: str,
    axis: str,
    selected_slits: tuple[str, ...],
    start_mm: float,
    bin_width_mm: float,
    end_mm: float | None = None,
    events_name: str = "events_clean.csv",
    metadata_name: str = "metadata.yaml",
) -> dict[str, Any]:
    """Aggregate compatible input files and return histogram rows plus provenance."""

    field = coordinate_field(scatter_point, axis)
    runs = select_runs(input_root, phantom_id, events_name, metadata_name)
    spec = make_bin_spec(runs, field, selected_slits, start_mm, bin_width_mm, end_mm)
    run_results = [bin_run(run, field, selected_slits, spec) for run in runs]
    n_primary_total = sum(run.n_primary for run in runs)
    rows: list[dict[str, Any]] = []
    for bin_index in range(spec.bin_count):
        count_total = sum(result["counts"][bin_index] for result in run_results)
        count_k1 = sum(result["k1_counts"][bin_index] for result in run_results)
        count_ms = sum(result["ms_counts"][bin_index] for result in run_results)
        if count_total != count_k1 + count_ms:
            raise RuntimeError(f"internal count invariant failed for bin {bin_index}")
        left = spec.start_mm + bin_index * spec.width_mm
        right = spec.end_mm if bin_index == spec.bin_count - 1 else left + spec.width_mm
        rows.append(
            {
                "condition_id": runs[0].condition_id,
                "phantom_id": phantom_id,
                "scatter_point": scatter_point,
                "axis": axis,
                "selected_slits": ",".join(selected_slits),
                "bin_index": bin_index,
                "bin_left_mm": left,
                "bin_right_mm": right,
                "bin_center_mm": (left + right) * 0.5,
                "count_total": count_total,
                "count_k1": count_k1,
                "count_ms": count_ms,
                "n_primary_total": n_primary_total,
            }
        )
    return {
        "input_root": input_root.resolve(),
        "phantom_id": phantom_id,
        "scatter_point": scatter_point,
        "axis": axis,
        "coordinate_field": field,
        "selected_slits": list(selected_slits),
        "condition_id": runs[0].condition_id,
        "bin_spec": spec,
        "runs": runs,
        "run_results": run_results,
        "rows": rows,
        "input_file_count": len(runs),
        "n_primary_total": n_primary_total,
    }


def format_csv_value(value: Any) -> Any:
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        return f"{value:.12g}"
    return value


def write_histogram_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write the merged per-bin table."""

    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: format_csv_value(row[field]) for field in CSV_FIELDS})


def write_histogram_plot(path: Path, analysis: dict[str, Any]) -> None:
    """Render condition-level bin counts as a non-interactive PNG bar chart."""

    try:
        os.environ.setdefault("MPLCONFIGDIR", "/tmp/mss_matplotlib")
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as error:  # pragma: no cover - environment-specific.
        raise RuntimeError(
            "scatter-position plotting requires matplotlib. "
            "Run `conda activate data` or use `conda run -n data python ...`."
        ) from error

    rows = analysis["rows"]
    centers = [row["bin_center_mm"] for row in rows]
    counts = [row["count_total"] for row in rows]
    widths = [row["bin_right_mm"] - row["bin_left_mm"] for row in rows]
    fig, ax = plt.subplots(figsize=(11.0, 6.2), constrained_layout=True)
    ax.bar(centers, counts, width=[width * 0.92 for width in widths], align="center")
    ax.set_xlabel(f"{analysis['coordinate_field']} (mm)")
    ax.set_ylabel("Count")
    ax.set_title(
        f"{analysis['phantom_id']} {analysis['coordinate_field']} | "
        f"slits={','.join(analysis['selected_slits'])}"
    )
    ax.grid(axis="y", alpha=0.25)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def to_builtin(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, BinSpec):
        return {
            "start_mm": value.start_mm,
            "end_mm": value.end_mm,
            "width_mm": value.width_mm,
            "bin_count": value.bin_count,
            "range_source": value.range_source,
            "interval_rule": "[left,right), final bin includes end_mm",
        }
    if isinstance(value, dict):
        return {str(key): to_builtin(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_builtin(item) for item in value]
    if isinstance(value, float) and math.isnan(value):
        return "NaN"
    return value


def write_manifest(path: Path, analysis: dict[str, Any], csv_path: Path, plot_path: Path) -> None:
    """Write condition-level aggregation and input provenance."""

    input_records = []
    for result in analysis["run_results"]:
        run = result["run"]
        input_records.append(
            {
                "seeds": run.seeds,
                "n_primary": run.n_primary,
                "events_file": run.events_path,
                "metadata_file": run.metadata_path,
                "binned_count": result["binned_count"],
                "binned_k1_count": result["binned_k1_count"],
                "binned_ms_count": result["binned_ms_count"],
                "zero_scatter_excluded": result["zero_scatter_excluded"],
                "nonfinite_coordinate_excluded": result["nonfinite_coordinate_excluded"],
                "underflow": result["underflow"],
                "overflow": result["overflow"],
            }
        )
    manifest = {
        "script": Path(__file__).as_posix(),
        "input_root": analysis["input_root"],
        "condition_id": analysis["condition_id"],
        "phantom_id": analysis["phantom_id"],
        "scatter_point": analysis["scatter_point"],
        "axis": analysis["axis"],
        "coordinate_field": analysis["coordinate_field"],
        "selected_slits": analysis["selected_slits"],
        "binning": analysis["bin_spec"],
        "count_classes": {
            "total": "scatter_count_total >= 1",
            "k1": "scatter_count_total == 1",
            "ms": "scatter_count_total >= 2",
            "invariant": "total = k1 + ms",
        },
        "aggregation": {
            "mode": "condition_total",
            "input_file_count": analysis["input_file_count"],
            "n_primary_total": analysis["n_primary_total"],
            "count_channels": ["total", "k1", "ms"],
            "rule": "sum counts from all compatible input files",
            "seed_role": "provenance only",
        },
        "inputs": input_records,
        "outputs": {"histogram_csv": csv_path, "histogram_png": plot_path},
    }
    with path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(to_builtin(manifest), stream, sort_keys=False, allow_unicode=False, width=100)


def ensure_output_dir(path: Path, overwrite: bool) -> None:
    """Create the output directory and protect existing analysis products."""

    owned = [path / HISTOGRAM_CSV_NAME, path / HISTOGRAM_PNG_NAME, path / MANIFEST_NAME]
    existing = [item for item in owned if item.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"analysis output already exists; use --overwrite: {existing[0]}")
    path.mkdir(parents=True, exist_ok=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--phantom-id", required=True)
    parser.add_argument("--scatter-point", choices=("first", "last"), required=True)
    parser.add_argument("--axis", choices=("x", "y", "z"), required=True)
    parser.add_argument("--slits", default="S1,S2,S3")
    parser.add_argument("--start-mm", type=float, required=True)
    parser.add_argument("--bin-width-mm", type=float, required=True)
    parser.add_argument("--end-mm", type=float)
    parser.add_argument("--events-name", default="events_clean.csv")
    parser.add_argument("--metadata-name", default="metadata.yaml")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    selected_slits = parse_slits(args.slits)
    ensure_output_dir(args.output_dir, args.overwrite)
    analysis = build_analysis(
        args.input_root,
        args.phantom_id,
        args.scatter_point,
        args.axis,
        selected_slits,
        args.start_mm,
        args.bin_width_mm,
        args.end_mm,
        args.events_name,
        args.metadata_name,
    )
    csv_path = args.output_dir / HISTOGRAM_CSV_NAME
    plot_path = args.output_dir / HISTOGRAM_PNG_NAME
    manifest_path = args.output_dir / MANIFEST_NAME
    write_histogram_csv(csv_path, analysis["rows"])
    write_histogram_plot(plot_path, analysis)
    write_manifest(manifest_path, analysis, csv_path, plot_path)
    print(f"processed {analysis['input_file_count']} compatible input file(s)")
    print(f"histogram: {csv_path}")
    print(f"plot: {plot_path}")
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
