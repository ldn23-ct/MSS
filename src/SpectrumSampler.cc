#include "SpectrumSampler.hh"

#include "G4Exception.hh"
#include "Randomize.hh"

#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace {

void ReportSpectrumError(const std::string& message)
{
    G4Exception("SpectrumSampler",
                "MSSSpectrum001",
                FatalException,
                message.c_str());
}

std::string Trim(const std::string& value)
{
    std::string text = value;
    const std::string utf8Bom = "\xEF\xBB\xBF";
    if (text.rfind(utf8Bom, 0) == 0) {
        text.erase(0, utf8Bom.size());
    }

    const auto begin = text.find_first_not_of(" \t\r\n");
    if (begin == std::string::npos) {
        return "";
    }

    const auto end = text.find_last_not_of(" \t\r\n");
    return text.substr(begin, end - begin + 1);
}

std::vector<std::string> SplitCsvLine(const std::string& line)
{
    std::vector<std::string> fields;
    std::stringstream stream(line);
    std::string field;

    while (std::getline(stream, field, ',')) {
        fields.push_back(Trim(field));
    }

    if (!line.empty() && line.back() == ',') {
        fields.emplace_back();
    }

    return fields;
}

std::map<std::string, std::size_t> BuildHeaderIndex(
    const std::vector<std::string>& header)
{
    std::map<std::string, std::size_t> index;
    for (std::size_t i = 0; i < header.size(); ++i) {
        if (!header[i].empty()) {
            index[header[i]] = i;
        }
    }

    if (index.find("energy_keV") == index.end()) {
        ReportSpectrumError("Missing required column 'energy_keV'.");
    }
    if (index.find("weight") == index.end()) {
        ReportSpectrumError("Missing required column 'weight'.");
    }

    return index;
}

std::string RequiredField(const std::vector<std::string>& fields,
                          const std::map<std::string, std::size_t>& headerIndex,
                          const std::string& column,
                          int lineNumber)
{
    const auto found = headerIndex.find(column);
    if (found == headerIndex.end() || found->second >= fields.size()) {
        ReportSpectrumError("Missing required field '" + column + "' on line "
                            + std::to_string(lineNumber) + ".");
    }

    const std::string value = Trim(fields[found->second]);
    if (value.empty()) {
        ReportSpectrumError("Empty required field '" + column + "' on line "
                            + std::to_string(lineNumber) + ".");
    }

    return value;
}

double ParseFiniteDouble(const std::string& text,
                         const std::string& column,
                         int lineNumber)
{
    char* end = nullptr;
    errno = 0;
    const double parsed = std::strtod(text.c_str(), &end);
    if (errno != 0 || end == text.c_str() || *end != '\0') {
        ReportSpectrumError(column + " must be numeric on line "
                            + std::to_string(lineNumber) + ".");
    }

    if (!std::isfinite(parsed)) {
        ReportSpectrumError(column + " must be finite on line "
                            + std::to_string(lineNumber) + ".");
    }

    return parsed;
}

} // namespace

void SpectrumSampler::Load(const std::string& filePath)
{
    if (filePath.empty()) {
        ReportSpectrumError("Spectrum file path must not be empty.");
    }

    std::ifstream input(filePath);
    if (!input.is_open()) {
        ReportSpectrumError("Failed to open spectrum file '" + filePath + "'.");
    }

    std::string line;
    if (!std::getline(input, line)) {
        ReportSpectrumError("Spectrum file '" + filePath + "' is empty.");
    }

    const auto headerIndex = BuildHeaderIndex(SplitCsvLine(line));

    std::vector<double> energies;
    std::vector<double> weights;
    double totalWeight = 0.0;

    int lineNumber = 1;
    while (std::getline(input, line)) {
        ++lineNumber;
        if (Trim(line).empty()) {
            continue;
        }

        const auto fields = SplitCsvLine(line);
        const double energy =
            ParseFiniteDouble(
                RequiredField(fields, headerIndex, "energy_keV", lineNumber),
                "energy_keV",
                lineNumber);
        const double weight =
            ParseFiniteDouble(
                RequiredField(fields, headerIndex, "weight", lineNumber),
                "weight",
                lineNumber);

        if (energy <= 0.0) {
            ReportSpectrumError("energy_keV must be positive on line "
                                + std::to_string(lineNumber) + ".");
        }
        if (weight < 0.0) {
            ReportSpectrumError("weight must be non-negative on line "
                                + std::to_string(lineNumber) + ".");
        }

        energies.push_back(energy);
        weights.push_back(weight);
        totalWeight += weight;
    }

    if (energies.empty()) {
        ReportSpectrumError("Spectrum file '" + filePath
                            + "' contains no data rows.");
    }
    if (!std::isfinite(totalWeight) || totalWeight <= 0.0) {
        ReportSpectrumError("Spectrum total weight must be positive and finite.");
    }

    std::vector<double> cdf;
    cdf.reserve(weights.size());
    double cumulative = 0.0;
    for (const double weight : weights) {
        cumulative += weight / totalWeight;
        cdf.push_back(cumulative);
    }
    cdf.back() = 1.0;

    loadedFilePath_ = filePath;
    energies_keV_ = std::move(energies);
    cdf_ = std::move(cdf);
}

double SpectrumSampler::SampleEnergyKeV() const
{
    if (energies_keV_.empty() || cdf_.empty()) {
        ReportSpectrumError("SpectrumSampler has not loaded a spectrum.");
    }

    const double sample = G4UniformRand();
    const auto found = std::lower_bound(cdf_.begin(), cdf_.end(), sample);
    if (found == cdf_.end()) {
        return energies_keV_.back();
    }

    const auto index = static_cast<std::size_t>(found - cdf_.begin());
    return energies_keV_[index];
}

const std::string& SpectrumSampler::LoadedFilePath() const
{
    return loadedFilePath_;
}
