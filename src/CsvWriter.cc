#include "CsvWriter.hh"

#include "EventAction.hh"

#include "G4Exception.hh"
#include "G4SystemOfUnits.hh"

#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <string>

namespace {

constexpr const char* kCompactHeader =
    "initial_energy,det_x,det_y,det_energy,scatter_count_total,"
    "compton_count,rayleigh_count,is_multiple_scatter,first_scatter_x,"
    "first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,"
    "last_scatter_z";

constexpr const char* kDebugHeader =
    "event_id,track_id,parent_id,det_z,det_dir_x,det_dir_y,det_dir_z,"
    "initial_energy,initial_dir_x,initial_dir_y,initial_dir_z,"
    "det_x,det_y,det_energy,scatter_count_total,"
    "compton_count,rayleigh_count,is_multiple_scatter,first_scatter_x,"
    "first_scatter_y,first_scatter_z,last_scatter_x,last_scatter_y,"
    "last_scatter_z";

void ReportCsvError(const std::string& message)
{
    G4Exception("CsvWriter", "MSSCsv001", FatalException, message.c_str());
}

std::string FormatNumber(double value)
{
    if (!std::isfinite(value)) {
        return "NaN";
    }

    std::ostringstream stream;
    stream << std::setprecision(12) << value;
    return stream.str();
}

std::string FormatPosition(double value)
{
    return FormatNumber(value / mm);
}

} // namespace

CsvWriter::~CsvWriter()
{
    Close();
}

void CsvWriter::Open(const std::string& filePath, bool debugOutput)
{
    Close();

    debugOutput_ = debugOutput;
    output_.open(filePath);
    if (!output_.is_open()) {
        ReportCsvError("Failed to open CSV output file '" + filePath + "'.");
    }

    output_ << (debugOutput_ ? kDebugHeader : kCompactHeader) << '\n';
    if (!output_) {
        ReportCsvError("Failed to write CSV header to '" + filePath + "'.");
    }
}

void CsvWriter::WriteRow(const EventRecord& record)
{
    if (!output_.is_open()) {
        ReportCsvError("CSV writer is not open.");
    }

    const auto& scatter = record.scatter;
    const auto& hit = record.hit;
    const bool isMultipleScatter = scatter.IsMultipleScatter();

    if (debugOutput_) {
        output_ << record.event_id << ','
                << record.track_id << ','
                << record.parent_id << ','
                << FormatNumber(hit.det_z) << ','
                << FormatNumber(hit.det_dir.x()) << ','
                << FormatNumber(hit.det_dir.y()) << ','
                << FormatNumber(hit.det_dir.z()) << ',';
    }

    output_ << FormatNumber(record.initial_energy_keV) << ',';

    if (debugOutput_) {
        output_ << FormatNumber(record.initial_dir.x()) << ','
                << FormatNumber(record.initial_dir.y()) << ','
                << FormatNumber(record.initial_dir.z()) << ',';
    }

    output_ << FormatNumber(hit.det_x) << ','
            << FormatNumber(hit.det_y) << ','
            << FormatNumber(hit.det_energy_keV) << ','
            << scatter.scatter_count_total << ','
            << scatter.compton_count << ','
            << scatter.rayleigh_count << ','
            << (isMultipleScatter ? 1 : 0) << ','
            << FormatPosition(scatter.first_scatter_pos.x()) << ','
            << FormatPosition(scatter.first_scatter_pos.y()) << ','
            << FormatPosition(scatter.first_scatter_pos.z()) << ','
            << FormatPosition(scatter.last_scatter_pos.x()) << ','
            << FormatPosition(scatter.last_scatter_pos.y()) << ','
            << FormatPosition(scatter.last_scatter_pos.z()) << '\n';

    if (!output_) {
        ReportCsvError("Failed to write CSV row.");
    }
}

void CsvWriter::Close()
{
    if (output_.is_open()) {
        output_.close();
    }
}

bool CsvWriter::IsOpen() const
{
    return output_.is_open();
}

const char* CsvWriter::Header(bool debugOutput)
{
    return debugOutput ? kDebugHeader : kCompactHeader;
}

void CsvWriter::MergeFiles(const std::vector<std::string>& inputFilePaths,
                           const std::string& outputFilePath,
                           bool debugOutput,
                           bool deleteInputFiles)
{
    if (inputFilePaths.empty()) {
        ReportCsvError("No temporary CSV files were provided for merge.");
    }

    std::ofstream output(outputFilePath);
    if (!output.is_open()) {
        ReportCsvError("Failed to open merged CSV output file '"
                       + outputFilePath + "'.");
    }

    const std::string expectedHeader = Header(debugOutput);
    output << expectedHeader << '\n';
    if (!output) {
        ReportCsvError("Failed to write merged CSV header to '"
                       + outputFilePath + "'.");
    }

    for (const auto& inputFilePath : inputFilePaths) {
        std::ifstream input(inputFilePath);
        if (!input.is_open()) {
            ReportCsvError("Failed to open temporary CSV file '"
                           + inputFilePath + "' for merge.");
        }

        std::string line;
        if (!std::getline(input, line)) {
            ReportCsvError("Temporary CSV file '" + inputFilePath
                           + "' is empty.");
        }
        if (line != expectedHeader) {
            ReportCsvError("Temporary CSV file '" + inputFilePath
                           + "' has an unexpected header.");
        }

        while (std::getline(input, line)) {
            output << line << '\n';
            if (!output) {
                ReportCsvError("Failed while writing merged CSV output file '"
                               + outputFilePath + "'.");
            }
        }

        if (input.bad()) {
            ReportCsvError("Failed while reading temporary CSV file '"
                           + inputFilePath + "'.");
        }
    }

    output.close();
    if (!output) {
        ReportCsvError("Failed to close merged CSV output file '"
                       + outputFilePath + "'.");
    }

    if (!deleteInputFiles) {
        return;
    }

    for (const auto& inputFilePath : inputFilePaths) {
        std::error_code error;
        const bool removed = std::filesystem::remove(inputFilePath, error);
        if (error || !removed) {
            ReportCsvError("Failed to delete temporary CSV file '"
                           + inputFilePath + "'.");
        }
    }
}
