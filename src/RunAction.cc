#include "RunAction.hh"

#include "CsvWriter.hh"
#include "SimulationConfig.hh"

#ifdef G4MULTITHREADED
#include "G4MTRunManager.hh"
#include "G4Threading.hh"
#endif
#include "G4Exception.hh"
#include "G4RunManager.hh"
#include "Randomize.hh"

#include <cmath>
#include <filesystem>
#include <iomanip>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace {

void ReportRunError(const std::string& message)
{
    G4Exception("RunAction", "MSSRun001", FatalException, message.c_str());
}

bool IsConfigOwnerThread()
{
#ifdef G4MULTITHREADED
    return G4Threading::IsMasterThread();
#else
    return true;
#endif
}

int GetWorkerThreadId()
{
#ifdef G4MULTITHREADED
    const int threadId = G4Threading::G4GetThreadId();
    if (threadId < 0) {
        ReportRunError("Worker thread ID is not available.");
    }
    return threadId;
#else
    return 0;
#endif
}

std::string FormatEnergyForFileName(double energy_keV)
{
    if (!std::isfinite(energy_keV) || energy_keV <= 0.0) {
        ReportRunError("monoEnergy must be positive and finite.");
    }

    std::ostringstream stream;
    stream << std::setprecision(12) << energy_keV;
    return stream.str();
}

std::string BuildOutputBaseName(const SimulationConfig& config,
                                bool debugOutput)
{
    std::ostringstream fileName;
    fileName << "hits_profile_" << config.collimatorProfileId << '_';
    if (config.energyMode == "mono") {
        fileName << "mono_" << FormatEnergyForFileName(config.monoEnergy_keV)
                 << "keV_seed" << config.randomSeed;
    } else if (config.energyMode == "spectrum") {
        fileName << "spectrum_seed" << config.randomSeed;
    } else {
        ReportRunError("energyMode must be either 'mono' or 'spectrum'.");
    }

    if (debugOutput) {
        fileName << "_debug";
    }

    return fileName.str();
}

std::filesystem::path BuildOutputFilePath(const SimulationConfig& config,
                                          bool debugOutput)
{
    return std::filesystem::path(config.outputDirectory)
           / (BuildOutputBaseName(config, debugOutput) + ".csv");
}

std::filesystem::path BuildTempDirectoryPath(const SimulationConfig& config)
{
    return std::filesystem::path(config.outputDirectory) / "tmp";
}

std::filesystem::path BuildTempFilePath(const SimulationConfig& config,
                                        bool debugOutput,
                                        int threadId)
{
    std::ostringstream fileName;
    fileName << BuildOutputBaseName(config, debugOutput)
             << "_thread" << threadId << ".csv";
    return BuildTempDirectoryPath(config) / fileName.str();
}

void EnsureDirectory(const std::filesystem::path& directory,
                     const std::string& description)
{
    try {
        if (std::filesystem::exists(directory)) {
            if (!std::filesystem::is_directory(directory)) {
                ReportRunError(description + " path '" + directory.string()
                               + "' exists but is not a directory.");
            }
            return;
        }

        if (!std::filesystem::create_directories(directory)) {
            ReportRunError("Failed to create " + description + " directory '"
                           + directory.string() + "'.");
        }
    } catch (const std::filesystem::filesystem_error& error) {
        ReportRunError("Failed to prepare " + description + " directory '"
                       + directory.string() + "': " + error.what());
    }
}

std::vector<std::string> BuildTempFilePaths(const SimulationConfig& config,
                                            bool debugOutput)
{
    std::vector<std::string> paths;
    paths.reserve(static_cast<std::size_t>(config.numberOfThreads));
    for (int threadId = 0; threadId < config.numberOfThreads; ++threadId) {
        paths.push_back(BuildTempFilePath(config, debugOutput, threadId).string());
    }
    return paths;
}

} // namespace

RunAction::RunAction(std::shared_ptr<SimulationConfig> config,
                     std::shared_ptr<CsvWriter> csvWriter)
    : config_(std::move(config)),
      csvWriter_(std::move(csvWriter))
{
}

void RunAction::BeginOfRunAction(const G4Run*)
{
    if (config_ == nullptr) {
        ReportRunError("SimulationConfig is not available.");
    }

    if (IsConfigOwnerThread()) {
        config_->numberOfThreads = GetEffectiveNumberOfThreads();
        config_->Validate();

        G4Random::setTheSeed(config_->randomSeed);

        EnsureDirectory(std::filesystem::path(config_->outputDirectory),
                        "output");

        if (config_->numberOfThreads > 1) {
            EnsureDirectory(BuildTempDirectoryPath(*config_),
                            "temporary output");
        }
    }

    if (csvWriter_ != nullptr) {
        config_->Validate();
        const bool debugOutput = config_->ResolveDebugOutput();
        const auto outputPath =
            config_->numberOfThreads > 1
                ? BuildTempFilePath(*config_, debugOutput, GetWorkerThreadId())
                : BuildOutputFilePath(*config_, debugOutput);
        csvWriter_->Open(outputPath.string(), debugOutput);
    }
}

void RunAction::EndOfRunAction(const G4Run*)
{
    if (csvWriter_ != nullptr) {
        csvWriter_->Close();
    }

    if (config_ != nullptr && IsConfigOwnerThread()
        && config_->numberOfThreads > 1) {
        const bool debugOutput = config_->ResolveDebugOutput();
        const auto outputPath = BuildOutputFilePath(*config_, debugOutput);
        const auto tempFilePaths = BuildTempFilePaths(*config_, debugOutput);
        CsvWriter::MergeFiles(tempFilePaths,
                              outputPath.string(),
                              debugOutput,
                              !debugOutput);
    }
}

int RunAction::GetEffectiveNumberOfThreads() const
{
#ifdef G4MULTITHREADED
    auto* runManager = G4RunManager::GetRunManager();
    auto* mtRunManager = dynamic_cast<G4MTRunManager*>(runManager);
    if (mtRunManager != nullptr && mtRunManager->GetNumberOfThreads() > 0) {
        return mtRunManager->GetNumberOfThreads();
    }

    if (runManager != nullptr) {
        return 1;
    }
#else
    if (G4RunManager::GetRunManager() != nullptr) {
        return 1;
    }
#endif

    if (config_ != nullptr && config_->numberOfThreads > 0) {
        return config_->numberOfThreads;
    }

    return 1;
}
