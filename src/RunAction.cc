#include "RunAction.hh"

#include "G4Threading.hh"

#include <filesystem>
#include <stdexcept>
#include <string>
#include <utility>

namespace fs = std::filesystem;

namespace {

bool DirectoryIsNonEmpty(const fs::path& directory)
{
    return fs::directory_iterator(directory) != fs::directory_iterator();
}

}  // namespace

RunAction::RunAction(SimulationConfig config,
                     VehicleROIConfig vehicleROI,
                     ScanPose pose,
                     OutputRole role)
    : configured_(true),
      role_(role),
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

    if (role_ == OutputRole::Master) {
        PrepareRunOutputDirectory();
        return;
    }

    EnsureTmpDirectory();
    writer_.Open(TempCsvPath(CurrentThreadId()), config_.run.debug);
}

void RunAction::EndOfRunAction(const G4Run*)
{
    if (writer_.IsOpen()) {
        writer_.Close();
    }

    if (!configured_ || role_ == OutputRole::Worker) {
        return;
    }

    MergeThreadCsvFiles();
    metadataWriter_.Write(MetadataPath(), config_, vehicleROI_, pose_, BuildRunId(), OutputCsvName());
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

std::string RunAction::FinalCsvPath() const
{
    return (fs::path(RunDirectory()) / OutputCsvName()).string();
}

std::string RunAction::MetadataPath() const
{
    return (fs::path(RunDirectory()) / config_.output.metadata_yaml_name).string();
}

std::string RunAction::RunDirectory() const
{
    return (fs::path(config_.output.output_directory) / BuildRunId()).string();
}

std::string RunAction::TmpDirectory() const
{
    return (fs::path(RunDirectory()) / config_.output.thread_tmp_directory).string();
}

std::string RunAction::TempCsvName(int threadId) const
{
    const std::string prefix = config_.run.debug ? "events_debug_thread" : "events_thread";
    return prefix + std::to_string(threadId) + ".csv";
}

std::string RunAction::TempCsvPath(int threadId) const
{
    return (fs::path(TmpDirectory()) / TempCsvName(threadId)).string();
}

std::vector<std::string> RunAction::ExpectedTempCsvPaths() const
{
    const int threadCount = (config_.run.number_of_threads > 1) ? config_.run.number_of_threads : 1;
    std::vector<std::string> paths;
    paths.reserve(static_cast<std::size_t>(threadCount));
    for (int threadId = 0; threadId < threadCount; ++threadId) {
        paths.push_back(TempCsvPath(threadId));
    }
    return paths;
}

int RunAction::CurrentThreadId() const
{
    if (role_ == OutputRole::Serial) {
        return 0;
    }

    const int threadId = G4Threading::G4GetThreadId();
    if (threadId < 0) {
        throw std::runtime_error("worker RunAction received invalid Geant4 thread id");
    }
    return threadId;
}

void RunAction::PrepareRunOutputDirectory() const
{
    const fs::path baseDir(config_.output.output_directory);
    const fs::path runDir(RunDirectory());

    std::error_code ec;
    fs::create_directories(baseDir, ec);
    if (ec) {
        throw std::runtime_error("failed to create output directory: " + baseDir.string() + ": " + ec.message());
    }

    if (fs::exists(runDir)) {
        if (!fs::is_directory(runDir)) {
            throw std::runtime_error("run output path exists but is not a directory: " + runDir.string());
        }
        if (DirectoryIsNonEmpty(runDir)) {
            throw std::runtime_error("run output directory already exists and is non-empty: " + runDir.string());
        }
    } else {
        fs::create_directories(runDir, ec);
        if (ec) {
            throw std::runtime_error("failed to create run output directory: " + runDir.string() + ": " + ec.message());
        }
    }

    EnsureTmpDirectory();
}

void RunAction::EnsureTmpDirectory() const
{
    const fs::path tmpDir(TmpDirectory());
    std::error_code ec;
    fs::create_directories(tmpDir, ec);
    if (ec) {
        throw std::runtime_error("failed to create thread temporary CSV directory: "
                                 + tmpDir.string() + ": " + ec.message());
    }
    if (!fs::is_directory(tmpDir)) {
        throw std::runtime_error("thread temporary CSV path exists but is not a directory: " + tmpDir.string());
    }
}

void RunAction::MergeThreadCsvFiles()
{
    const bool deleteInputFiles = !config_.run.debug;
    CsvWriter::MergeFiles(ExpectedTempCsvPaths(), FinalCsvPath(), config_.run.debug, deleteInputFiles);
}
