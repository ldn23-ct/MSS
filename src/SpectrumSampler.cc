#include "SpectrumSampler.hh"

#include "Randomize.hh"

#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

std::string Trim(const std::string& value)
{
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) {
        return "";
    }
    const auto last = value.find_last_not_of(" \t\r\n");
    return value.substr(first, last - first + 1);
}

std::string StripUtf8Bom(std::string value)
{
    if (value.size() >= 3
        && static_cast<unsigned char>(value[0]) == 0xEF
        && static_cast<unsigned char>(value[1]) == 0xBB
        && static_cast<unsigned char>(value[2]) == 0xBF) {
        value.erase(0, 3);
    }
    return value;
}

std::vector<std::string> SplitCsvLine(const std::string& line)
{
    std::vector<std::string> fields;
    std::string field;
    std::istringstream stream(line);
    while (std::getline(stream, field, ',')) {
        fields.push_back(Trim(field));
    }
    if (!line.empty() && line.back() == ',') {
        fields.emplace_back();
    }
    return fields;
}

double ParseFiniteDouble(const std::string& text, const std::string& context)
{
    const std::string trimmed = Trim(text);
    if (trimmed.empty()) {
        throw std::runtime_error(context + " is empty");
    }

    errno = 0;
    char* end = nullptr;
    const double value = std::strtod(trimmed.c_str(), &end);
    if (end == trimmed.c_str() || *end != '\0' || errno == ERANGE || !std::isfinite(value)) {
        throw std::runtime_error(context + " must be a finite numeric value");
    }
    return value;
}

}  // namespace

void SpectrumSampler::Load(const std::string& filePath)
{
    std::ifstream input(filePath);
    if (!input) {
        throw std::runtime_error("failed to open spectrum CSV: " + filePath);
    }

    std::string header;
    if (!std::getline(input, header)) {
        throw std::runtime_error("spectrum CSV is empty: " + filePath);
    }
    header = StripUtf8Bom(Trim(header));
    if (header != "energy_keV,weight") {
        throw std::runtime_error("spectrum CSV header must be energy_keV,weight: " + filePath);
    }

    std::vector<double> energies;
    std::vector<double> cumulativeWeights;
    double totalWeight = 0.0;
    std::string line;
    int lineNumber = 1;
    while (std::getline(input, line)) {
        ++lineNumber;
        if (Trim(line).empty()) {
            continue;
        }

        const auto fields = SplitCsvLine(line);
        if (fields.size() != 2) {
            throw std::runtime_error("spectrum CSV row must have 2 columns at line " + std::to_string(lineNumber));
        }

        const double energy = ParseFiniteDouble(fields[0], "spectrum energy at line " + std::to_string(lineNumber));
        const double weight = ParseFiniteDouble(fields[1], "spectrum weight at line " + std::to_string(lineNumber));
        if (energy <= 0.0) {
            throw std::runtime_error("spectrum energy must be > 0 at line " + std::to_string(lineNumber));
        }
        if (weight < 0.0) {
            throw std::runtime_error("spectrum weight must be >= 0 at line " + std::to_string(lineNumber));
        }
        if (weight > 0.0 && totalWeight > std::numeric_limits<double>::max() - weight) {
            throw std::runtime_error("spectrum cumulative weight overflows double");
        }

        totalWeight += weight;
        energies.push_back(energy);
        cumulativeWeights.push_back(totalWeight);
    }

    if (energies.empty()) {
        throw std::runtime_error("spectrum CSV must contain at least one data row: " + filePath);
    }
    if (totalWeight <= 0.0 || !std::isfinite(totalWeight)) {
        throw std::runtime_error("spectrum CSV weight sum must be finite and > 0: " + filePath);
    }

    loadedFilePath_ = filePath;
    energiesKeV_ = std::move(energies);
    cumulativeWeights_ = std::move(cumulativeWeights);
}

double SpectrumSampler::SampleEnergyKeV() const
{
    if (energiesKeV_.empty() || cumulativeWeights_.empty()) {
        throw std::runtime_error("SpectrumSampler must be loaded before sampling");
    }

    const double totalWeight = cumulativeWeights_.back();
    const double target = G4UniformRand() * totalWeight;
    auto iter = std::upper_bound(cumulativeWeights_.begin(), cumulativeWeights_.end(), target);
    if (iter == cumulativeWeights_.end()) {
        return energiesKeV_.back();
    }

    const auto index = static_cast<std::size_t>(std::distance(cumulativeWeights_.begin(), iter));
    return energiesKeV_[index];
}

const std::string& SpectrumSampler::LoadedFilePath() const
{
    return loadedFilePath_;
}
