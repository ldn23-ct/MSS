#ifndef SPECTRUM_SAMPLER_HH
#define SPECTRUM_SAMPLER_HH

#include <string>
#include <vector>

class SpectrumSampler {
  public:
    SpectrumSampler() = default;

    void Load(const std::string& filePath);
    double SampleEnergyKeV() const;
    const std::string& LoadedFilePath() const;

  private:
    std::string loadedFilePath_;
    std::vector<double> energiesKeV_;
    std::vector<double> cumulativeWeights_;
};

#endif
