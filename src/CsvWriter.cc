#include "CsvWriter.hh"

#include "EventRecord.hh"

void CsvWriter::Open(const std::string&, bool)
{
    isOpen_ = true;
}

void CsvWriter::WriteRow(const EventRecord&) {}

void CsvWriter::Close()
{
    isOpen_ = false;
}

bool CsvWriter::IsOpen() const
{
    return isOpen_;
}

void CsvWriter::MergeFiles(const std::vector<std::string>&,
                           const std::string&,
                           bool,
                           bool)
{
}
