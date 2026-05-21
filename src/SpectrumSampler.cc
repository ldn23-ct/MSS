#include "SpectrumSampler.hh"

#include <stdexcept>

void SpectrumSampler::Load(const std::string& filePath)
{
    loadedFilePath_ = filePath;
}

double SpectrumSampler::SampleEnergyKeV() const
{
    throw std::runtime_error("SpectrumSampler sampling is deferred beyond M0");
}

const std::string& SpectrumSampler::LoadedFilePath() const
{
    return loadedFilePath_;
}
