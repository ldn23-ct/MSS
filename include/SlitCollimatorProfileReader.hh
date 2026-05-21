#ifndef SLIT_COLLIMATOR_PROFILE_READER_HH
#define SLIT_COLLIMATOR_PROFILE_READER_HH

#include <string>

class SlitCollimatorProfileReader {
  public:
    SlitCollimatorProfileReader() = default;
    void SetSourceFileForM0(const std::string& filePath);
    const std::string& SourceFileForM0() const;

  private:
    std::string sourceFile_;
};

#endif
