#include "RunAction.hh"

#include <filesystem>
#include <stdexcept>
#include <utility>

namespace fs = std::filesystem;

RunAction::RunAction(SimulationConfig config, VehicleROIConfig vehicleROI, ScanPose pose)
    : configured_(true),
      config_(std::move(config)),
      vehicleROI_(std::move(vehicleROI)),
      pose_(std::move(pose))
{
}

void RunAction::BeginOfRunAction(const G4Run*)
{
    if (!configured_) {
        return;
    }
    if (config_.run.number_of_threads != 1) {
        throw std::runtime_error("M13 CSV output supports single-thread runs only; multi-thread merge is deferred to M15");
    }

    PrepareOutputDirectory();
    writer_.Open(OutputCsvPath(), config_.run.debug);
}

void RunAction::EndOfRunAction(const G4Run*)
{
    if (writer_.IsOpen()) {
        writer_.Close();
    }

    if (configured_) {
        metadataWriter_.Write(MetadataPath(), config_, vehicleROI_, pose_, BuildRunId(), OutputCsvName());
    }
}

CsvWriter* RunAction::Writer()
{
    return &writer_;
}

std::string RunAction::BuildRunId() const
{
    return pose_.pose_id + "_" + config_.vehicle.model_type + "_seed" + std::to_string(pose_.random_seed);
}

std::string RunAction::OutputCsvName() const
{
    if (config_.run.debug) {
        return "events_debug.csv";
    }
    return config_.output.events_csv_name;
}

std::string RunAction::OutputCsvPath() const
{
    return (fs::path(config_.output.output_directory) / BuildRunId() / OutputCsvName()).string();
}

std::string RunAction::MetadataPath() const
{
    return (fs::path(config_.output.output_directory) / BuildRunId() / config_.output.metadata_yaml_name).string();
}

void RunAction::PrepareOutputDirectory() const
{
    const fs::path baseDir(config_.output.output_directory);
    const fs::path runDir = baseDir / BuildRunId();

    std::error_code ec;
    fs::create_directories(baseDir, ec);
    if (ec) {
        throw std::runtime_error("failed to create output directory: " + baseDir.string() + ": " + ec.message());
    }

    if (fs::exists(runDir)) {
        if (!fs::is_directory(runDir)) {
            throw std::runtime_error("run output path exists but is not a directory: " + runDir.string());
        }
        if (fs::directory_iterator(runDir) != fs::directory_iterator()) {
            throw std::runtime_error("run output directory already exists and is non-empty: " + runDir.string());
        }
        return;
    }

    fs::create_directories(runDir, ec);
    if (ec) {
        throw std::runtime_error("failed to create run output directory: " + runDir.string() + ": " + ec.message());
    }
}
