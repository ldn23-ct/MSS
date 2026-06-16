#ifndef PHASE_SPACE_CSV_WRITER_HH
#define PHASE_SPACE_CSV_WRITER_HH

#include <fstream>
#include <string>
#include <vector>

struct EventRecord;

class PhaseSpaceCsvWriter {
  public:
    PhaseSpaceCsvWriter() = default;

    void Open(const std::string& filePath);
    void WriteRows(const EventRecord& record);
    void Close();
    bool IsOpen() const;

    static const char* Header();
    static void MergeFiles(const std::vector<std::string>& inputFilePaths,
                           const std::string& outputFilePath,
                           bool deleteInputFiles);

  private:
    bool isOpen_ = false;
    std::ofstream output_;
};

#endif
