#ifndef CSV_WRITER_HH
#define CSV_WRITER_HH

#include <fstream>
#include <string>
#include <vector>

struct EventRecord;

class CsvWriter {
  public:
    CsvWriter() = default;

    void Open(const std::string& filePath, bool debugOutput);
    void WriteRow(const EventRecord& record);
    void Close();
    bool IsOpen() const;

    static void MergeFiles(const std::vector<std::string>& inputFilePaths,
                           const std::string& outputFilePath,
                           bool debugOutput,
                           bool deleteInputFiles);

  private:
    void WriteHeader();

    bool isOpen_ = false;
    bool debugOutput_ = false;
    std::ofstream output_;
};

#endif
