#include "SlitCollimatorProfileReader.hh"

void SlitCollimatorProfileReader::SetSourceFileForM0(const std::string& filePath)
{
    sourceFile_ = filePath;
}

const std::string& SlitCollimatorProfileReader::SourceFileForM0() const
{
    return sourceFile_;
}
