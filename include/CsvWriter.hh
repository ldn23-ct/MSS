#ifndef CSV_WRITER_HH
#define CSV_WRITER_HH

#include <fstream>
#include <string>
#include <vector>

struct EventRecord;

class CsvWriter {
  public:
    CsvWriter() = default;
    ~CsvWriter();

    CsvWriter(const CsvWriter&) = delete;
    CsvWriter& operator=(const CsvWriter&) = delete;

    void Open(const std::string& filePath, bool debugOutput);
    void WriteRow(const EventRecord& record);
    void Close();

    bool IsOpen() const;

    static const char* Header(bool debugOutput);
    static void MergeFiles(const std::vector<std::string>& inputFilePaths,
                           const std::string& outputFilePath,
                           bool debugOutput,
                           bool deleteInputFiles);

  private:
    std::ofstream output_;
    bool debugOutput_ = false;
};

#endif
