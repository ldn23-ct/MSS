#include "CsvWriter.hh"

#include "EventRecord.hh"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace {

constexpr const char* kFormalHeader =
    "event_id,hit_id,track_id,parent_id,is_primary_gamma,gamma_source_type,gamma_source_process,"
    "gamma_source_x,gamma_source_y,gamma_source_z,gamma_source_region_id,det_x,det_y,det_z,"
    "det_energy,scatter_count_total,compton_count,rayleigh_count,first_scatter_x,first_scatter_y,"
    "first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z,first_scatter_region_id,"
    "last_scatter_region_id";

constexpr const char* kDebugHeader =
    "event_id,track_id,parent_id,is_primary_gamma,gamma_source_type,gamma_source_process,"
    "gamma_source_x,gamma_source_y,gamma_source_z,gamma_source_region_id,detected,hit_id,det_x,"
    "det_y,det_z,det_energy,scatter_count_total,compton_count,rayleigh_count,first_scatter_x,"
    "first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,last_scatter_z,"
    "first_scatter_region_id,last_scatter_region_id";

std::string FormatDouble(double value)
{
    if (std::isnan(value)) {
        return "NaN";
    }

    std::ostringstream stream;
    stream << std::setprecision(12) << value;
    return stream.str();
}

std::string FormatBool(bool value)
{
    return value ? "1" : "0";
}

std::string EscapeCsv(const std::string& value)
{
    if (value.find_first_of(",\"\r\n") == std::string::npos) {
        return value;
    }

    std::string escaped = "\"";
    for (const char ch : value) {
        if (ch == '"') {
            escaped += "\"\"";
        } else {
            escaped += ch;
        }
    }
    escaped += '"';
    return escaped;
}

std::vector<const GammaTrackSummary*> SortedTracks(const EventRecord& record)
{
    std::vector<const GammaTrackSummary*> tracks;
    tracks.reserve(record.gamma_tracks.size());
    for (const auto& item : record.gamma_tracks) {
        tracks.push_back(&item.second);
    }
    std::sort(tracks.begin(), tracks.end(), [](const auto* lhs, const auto* rhs) {
        return lhs->track_id < rhs->track_id;
    });
    return tracks;
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

void WriteCommonTrackFields(std::ostream& output, const GammaTrackSummary& track)
{
    output << track.track_id << ','
           << track.parent_id << ','
           << FormatBool(track.is_primary_gamma) << ','
           << EscapeCsv(track.gamma_source_type) << ','
           << EscapeCsv(track.gamma_source_process) << ','
           << FormatDouble(track.gamma_source_pos.x()) << ','
           << FormatDouble(track.gamma_source_pos.y()) << ','
           << FormatDouble(track.gamma_source_pos.z()) << ','
           << EscapeCsv(track.gamma_source_region_id);
}

void WriteHitFields(std::ostream& output, const DetectorHitRecord& hit)
{
    output << hit.hit_id << ','
           << FormatDouble(hit.det_x_mm) << ','
           << FormatDouble(hit.det_y_mm) << ','
           << FormatDouble(hit.det_z_mm) << ','
           << FormatDouble(hit.det_energy_keV);
}

void WriteScatterFields(std::ostream& output, const ScatterSummary& scatter)
{
    output << scatter.scatter_count_total << ','
           << scatter.compton_count << ','
           << scatter.rayleigh_count << ','
           << FormatDouble(scatter.first_scatter_pos.x()) << ','
           << FormatDouble(scatter.first_scatter_pos.y()) << ','
           << FormatDouble(scatter.first_scatter_pos.z()) << ','
           << FormatDouble(scatter.last_scatter_pos.x()) << ','
           << FormatDouble(scatter.last_scatter_pos.y()) << ','
           << FormatDouble(scatter.last_scatter_pos.z()) << ','
           << EscapeCsv(scatter.first_scatter_region_id) << ','
           << EscapeCsv(scatter.last_scatter_region_id);
}

}  // namespace

void CsvWriter::Open(const std::string& filePath, bool debugOutput)
{
    if (isOpen_) {
        throw std::runtime_error("CSV writer is already open");
    }
    if (filePath.empty()) {
        throw std::runtime_error("CSV output path must be non-empty");
    }

    debugOutput_ = debugOutput;
    output_.open(filePath, std::ios::out | std::ios::trunc);
    if (!output_) {
        throw std::runtime_error("failed to open CSV output file: " + filePath);
    }

    isOpen_ = true;
    WriteHeader();
}

void CsvWriter::WriteRow(const EventRecord& record)
{
    if (!isOpen_ || !output_.is_open()) {
        throw std::runtime_error("CSV writer is not open");
    }

    if (debugOutput_) {
        for (const auto* track : SortedTracks(record)) {
            output_ << record.event_id << ',';
            WriteCommonTrackFields(output_, *track);
            output_ << ','
                    << FormatBool(track->hit.detected) << ',';
            WriteHitFields(output_, track->hit);
            output_ << ',';
            WriteScatterFields(output_, track->scatter);
            output_ << '\n';
        }
    } else {
        for (const auto* track : SortedDetectedTracks(record)) {
            output_ << record.event_id << ','
                    << track->hit.hit_id << ',';
            WriteCommonTrackFields(output_, *track);
            output_ << ','
                    << FormatDouble(track->hit.det_x_mm) << ','
                    << FormatDouble(track->hit.det_y_mm) << ','
                    << FormatDouble(track->hit.det_z_mm) << ','
                    << FormatDouble(track->hit.det_energy_keV) << ',';
            WriteScatterFields(output_, track->scatter);
            output_ << '\n';
        }
    }

    if (!output_) {
        throw std::runtime_error("failed while writing CSV rows");
    }
}

void CsvWriter::Close()
{
    if (output_.is_open()) {
        output_.flush();
        if (!output_) {
            throw std::runtime_error("failed to flush CSV output file");
        }
        output_.close();
    }
    isOpen_ = false;
}

bool CsvWriter::IsOpen() const
{
    return isOpen_ && output_.is_open();
}

void CsvWriter::MergeFiles(const std::vector<std::string>&,
                           const std::string&,
                           bool,
                           bool)
{
    throw std::runtime_error("CSV merge is deferred to M15");
}

void CsvWriter::WriteHeader()
{
    output_ << (debugOutput_ ? kDebugHeader : kFormalHeader) << '\n';
    if (!output_) {
        throw std::runtime_error("failed to write CSV header");
    }
}
