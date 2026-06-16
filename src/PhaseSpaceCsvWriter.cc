#include "PhaseSpaceCsvWriter.hh"

#include "EventRecord.hh"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace {

constexpr const char* kHeader =
    "event_id,hit_id,track_id,parent_id,is_primary_gamma,particle,phase_x_mm,phase_y_mm,"
    "phase_z_mm,dir_x,dir_y,dir_z,kinetic_energy_keV,weight";

std::string FormatDouble(double value)
{
    if (std::isnan(value)) {
        return "NaN";
    }

    std::ostringstream stream;
    stream << std::setprecision(12) << value;
    return stream.str();
}

std::vector<const GammaTrackSummary*> SortedDetectedTracks(const EventRecord& record)
{
    std::vector<const GammaTrackSummary*> tracks;
    for (const auto& item : record.gamma_tracks) {
        if (item.second.hit.detected) {
            tracks.push_back(&item.second);
        }
    }
    std::sort(tracks.begin(), tracks.end(), [](const auto* lhs, const auto* rhs) {
        if (lhs->hit.hit_id != rhs->hit.hit_id) {
            return lhs->hit.hit_id < rhs->hit.hit_id;
        }
        return lhs->track_id < rhs->track_id;
    });
    return tracks;
}

}  // namespace

void PhaseSpaceCsvWriter::Open(const std::string& filePath)
{
    if (isOpen_) {
        throw std::runtime_error("phase-space CSV writer is already open");
    }
    if (filePath.empty()) {
        throw std::runtime_error("phase-space CSV output path must be non-empty");
    }

    output_.open(filePath, std::ios::out | std::ios::trunc);
    if (!output_) {
        throw std::runtime_error("failed to open phase-space CSV output file: " + filePath);
    }
    output_ << Header() << '\n';
    if (!output_) {
        throw std::runtime_error("failed to write phase-space CSV header");
    }
    isOpen_ = true;
}

void PhaseSpaceCsvWriter::WriteRows(const EventRecord& record)
{
    if (!IsOpen()) {
        throw std::runtime_error("phase-space CSV writer is not open");
    }

    for (const auto* track : SortedDetectedTracks(record)) {
        const auto& hit = track->hit;
        output_ << record.event_id << ','
                << hit.hit_id << ','
                << track->track_id << ','
                << track->parent_id << ','
                << (track->is_primary_gamma ? 1 : 0) << ','
                << "gamma" << ','
                << FormatDouble(hit.det_x_mm) << ','
                << FormatDouble(hit.det_y_mm) << ','
                << FormatDouble(hit.det_z_mm) << ','
                << FormatDouble(hit.direction.x()) << ','
                << FormatDouble(hit.direction.y()) << ','
                << FormatDouble(hit.direction.z()) << ','
                << FormatDouble(hit.det_energy_keV) << ','
                << FormatDouble(hit.weight) << '\n';
    }
    if (!output_) {
        throw std::runtime_error("failed while writing phase-space CSV rows");
    }
}

void PhaseSpaceCsvWriter::Close()
{
    if (output_.is_open()) {
        output_.flush();
        if (!output_) {
            throw std::runtime_error("failed to flush phase-space CSV output file");
        }
        output_.close();
    }
    isOpen_ = false;
}

bool PhaseSpaceCsvWriter::IsOpen() const
{
    return isOpen_ && output_.is_open();
}

const char* PhaseSpaceCsvWriter::Header()
{
    return kHeader;
}

void PhaseSpaceCsvWriter::MergeFiles(const std::vector<std::string>& inputFilePaths,
                                     const std::string& outputFilePath,
                                     bool deleteInputFiles)
{
    if (inputFilePaths.empty()) {
        throw std::runtime_error("phase-space CSV merge requires at least one input file");
    }

    std::ofstream output(outputFilePath, std::ios::out | std::ios::trunc);
    if (!output) {
        throw std::runtime_error("failed to open merged phase-space CSV: " + outputFilePath);
    }

    bool wroteHeader = false;
    for (const auto& inputFilePath : inputFilePaths) {
        std::ifstream input(inputFilePath);
        if (!input) {
            throw std::runtime_error("failed to open phase-space thread CSV: " + inputFilePath);
        }

        std::string header;
        if (!std::getline(input, header)) {
            throw std::runtime_error("phase-space thread CSV is empty: " + inputFilePath);
        }
        if (!header.empty() && header.back() == '\r') {
            header.pop_back();
        }
        if (header != Header()) {
            throw std::runtime_error("phase-space thread CSV header mismatch: " + inputFilePath);
        }
        if (!wroteHeader) {
            output << header << '\n';
            wroteHeader = true;
        }

        std::string line;
        while (std::getline(input, line)) {
            output << line << '\n';
        }
        if (!input.eof()) {
            throw std::runtime_error("failed while reading phase-space thread CSV: " + inputFilePath);
        }
    }

    output.flush();
    if (!output) {
        throw std::runtime_error("failed to flush merged phase-space CSV: " + outputFilePath);
    }
    output.close();

    if (deleteInputFiles) {
        for (const auto& inputFilePath : inputFilePaths) {
            std::error_code error;
            if (!std::filesystem::remove(inputFilePath, error)) {
                throw std::runtime_error(
                    "failed to delete phase-space thread CSV: " + inputFilePath
                    + (error ? ": " + error.message() : ""));
            }
        }
    }
}
