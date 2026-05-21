#ifndef SPECTRUM_SAMPLER_HH
#define SPECTRUM_SAMPLER_HH

#include <string>

class SpectrumSampler {
  public:
    SpectrumSampler() = default;

    void Load(const std::string& filePath);
    double SampleEnergyKeV() const;
    const std::string& LoadedFilePath() const;

  private:
    std::string loadedFilePath_;
};

#endif
