#include "SlitCollimatorProfileReader.hh"

#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct HeaderColumns {
    int profile_id = -1;
    int jaw_id = -1;
    int vertex_id = -1;
    int x_mm = -1;
    int y_mm = -1;
    int z_mm = -1;
    int count = 0;
};

struct VertexRow {
    int vertex_id = 0;
    double x_mm = 0.0;
    double z_mm = 0.0;
    bool has_y_mm = false;
    double y_mm = 0.0;
};

struct JawRows {
    std::string jaw_id;
    std::vector<VertexRow> vertices;
};

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

void RequireNonEmpty(const std::string& value, const std::string& field, int lineNumber)
{
    if (value.empty()) {
        throw std::runtime_error(field + " must be non-empty at line " + std::to_string(lineNumber));
    }
}

double ParseFiniteDouble(const std::string& text, const std::string& field, int lineNumber)
{
    RequireNonEmpty(text, field, lineNumber);

    errno = 0;
    char* end = nullptr;
    const double value = std::strtod(text.c_str(), &end);
    if (end == text.c_str() || *end != '\0' || errno == ERANGE || !std::isfinite(value)) {
        throw std::runtime_error(field + " must be a finite numeric value at line " + std::to_string(lineNumber));
    }
    return value;
}

int ParseStrictNonNegativeInt(const std::string& text, const std::string& field, int lineNumber)
{
    RequireNonEmpty(text, field, lineNumber);
    for (const char c : text) {
        if (c < '0' || c > '9') {
            throw std::runtime_error(field + " must be a non-negative integer at line " + std::to_string(lineNumber));
        }
    }

    try {
        const long long value = std::stoll(text);
        if (value > std::numeric_limits<int>::max()) {
            throw std::runtime_error(field + " is outside int range at line " + std::to_string(lineNumber));
        }
        return static_cast<int>(value);
    } catch (const std::invalid_argument&) {
        throw std::runtime_error(field + " must be a non-negative integer at line " + std::to_string(lineNumber));
    } catch (const std::out_of_range&) {
        throw std::runtime_error(field + " is outside int range at line " + std::to_string(lineNumber));
    }
}

int ParseJawIndex(const std::string& jawId)
{
    constexpr const char* kPrefix = "jaw_";
    const std::string prefix(kPrefix);
    if (jawId.size() <= prefix.size() || jawId.compare(0, prefix.size(), prefix) != 0) {
        throw std::runtime_error("jaw_id must have form jaw_<index>: " + jawId);
    }

    const std::string indexText = jawId.substr(prefix.size());
    for (const char c : indexText) {
        if (c < '0' || c > '9') {
            throw std::runtime_error("jaw_id must have a non-negative integer suffix: " + jawId);
        }
    }
    if (indexText.size() > 1 && indexText.front() == '0') {
        throw std::runtime_error("jaw_id must not use leading zeroes: " + jawId);
    }

    try {
        const long long value = std::stoll(indexText);
        if (value > std::numeric_limits<int>::max()) {
            throw std::runtime_error("jaw_id index is outside int range: " + jawId);
        }
        return static_cast<int>(value);
    } catch (const std::invalid_argument&) {
        throw std::runtime_error("jaw_id must have a non-negative integer suffix: " + jawId);
    } catch (const std::out_of_range&) {
        throw std::runtime_error("jaw_id index is outside int range: " + jawId);
    }
}

HeaderColumns ParseHeader(const std::string& rawHeader, const std::string& filePath)
{
    const auto fields = SplitCsvLine(StripUtf8Bom(rawHeader));
    if (fields.empty()) {
        throw std::runtime_error("collimator profile CSV header is empty: " + filePath);
    }

    HeaderColumns columns;
    columns.count = static_cast<int>(fields.size());
    std::set<std::string> seen;
    for (int i = 0; i < columns.count; ++i) {
        const std::string field = fields[static_cast<std::size_t>(i)];
        if (field.empty()) {
            throw std::runtime_error("collimator profile CSV header contains an empty column: " + filePath);
        }
        if (!seen.insert(field).second) {
            throw std::runtime_error("collimator profile CSV header contains duplicate column: " + field);
        }

        if (field == "profile_id") {
            columns.profile_id = i;
        } else if (field == "jaw_id") {
            columns.jaw_id = i;
        } else if (field == "vertex_id") {
            columns.vertex_id = i;
        } else if (field == "x_mm") {
            columns.x_mm = i;
        } else if (field == "y_mm") {
            columns.y_mm = i;
        } else if (field == "z_mm") {
            columns.z_mm = i;
        } else {
            throw std::runtime_error("collimator profile CSV header contains unknown column: " + field);
        }
    }

    if (columns.profile_id < 0 || columns.jaw_id < 0 || columns.vertex_id < 0
        || columns.x_mm < 0 || columns.z_mm < 0) {
        throw std::runtime_error(
            "collimator profile CSV header must contain profile_id,jaw_id,vertex_id,x_mm,z_mm: " + filePath);
    }
    return columns;
}

std::string RequiredField(
    const std::vector<std::string>& fields,
    int index,
    const std::string& fieldName,
    int lineNumber)
{
    if (index < 0 || static_cast<std::size_t>(index) >= fields.size()) {
        throw std::runtime_error(fieldName + " is missing at line " + std::to_string(lineNumber));
    }
    const std::string value = fields[static_cast<std::size_t>(index)];
    RequireNonEmpty(value, fieldName, lineNumber);
    return value;
}

VertexRow BuildVertexRow(const std::vector<std::string>& fields, const HeaderColumns& columns, int lineNumber)
{
    VertexRow row;
    row.vertex_id = ParseStrictNonNegativeInt(
        RequiredField(fields, columns.vertex_id, "vertex_id", lineNumber),
        "vertex_id",
        lineNumber);
    row.x_mm = ParseFiniteDouble(RequiredField(fields, columns.x_mm, "x_mm", lineNumber), "x_mm", lineNumber);
    row.z_mm = ParseFiniteDouble(RequiredField(fields, columns.z_mm, "z_mm", lineNumber), "z_mm", lineNumber);
    if (columns.y_mm >= 0) {
        row.has_y_mm = true;
        row.y_mm = ParseFiniteDouble(RequiredField(fields, columns.y_mm, "y_mm", lineNumber), "y_mm", lineNumber);
    }
    return row;
}

double Cross(const XZPoint& origin, const XZPoint& lhs, const XZPoint& rhs)
{
    const double ax = lhs.x_mm - origin.x_mm;
    const double az = lhs.z_mm - origin.z_mm;
    const double bx = rhs.x_mm - origin.x_mm;
    const double bz = rhs.z_mm - origin.z_mm;
    return ax * bz - az * bx;
}

double SignedAreaTwice(const std::vector<XZPoint>& vertices)
{
    double areaTwice = 0.0;
    for (std::size_t i = 0; i < vertices.size(); ++i) {
        const auto& current = vertices[i];
        const auto& next = vertices[(i + 1) % vertices.size()];
        areaTwice += current.x_mm * next.z_mm - next.x_mm * current.z_mm;
    }
    return areaTwice;
}

void ValidatePolygon(const SlitJawProfile& jaw)
{
    if (jaw.vertices.size() < 3) {
        throw std::runtime_error(jaw.jaw_id + " must contain at least 3 vertices");
    }

    constexpr double kTolerance = 1.0e-9;
    const double areaTwice = SignedAreaTwice(jaw.vertices);
    if (std::abs(areaTwice) <= kTolerance) {
        throw std::runtime_error(jaw.jaw_id + " polygon area must be non-zero");
    }

    int expectedSign = 0;
    for (std::size_t i = 0; i < jaw.vertices.size(); ++i) {
        const auto& previous = jaw.vertices[(i + jaw.vertices.size() - 1) % jaw.vertices.size()];
        const auto& current = jaw.vertices[i];
        const auto& next = jaw.vertices[(i + 1) % jaw.vertices.size()];
        const double cross = Cross(current, next, previous);
        if (std::abs(cross) <= kTolerance) {
            throw std::runtime_error(jaw.jaw_id + " polygon contains consecutive collinear vertices");
        }
        const int sign = cross > 0.0 ? 1 : -1;
        if (expectedSign == 0) {
            expectedSign = sign;
        } else if (sign != expectedSign) {
            throw std::runtime_error(jaw.jaw_id + " polygon must be convex");
        }
    }
}

SlitJawProfile BuildJawProfile(const JawRows& rows)
{
    SlitJawProfile jaw;
    jaw.jaw_id = rows.jaw_id;
    if (rows.vertices.size() < 3) {
        throw std::runtime_error(jaw.jaw_id + " must contain at least 3 vertices");
    }

    std::map<int, VertexRow> byVertexId;
    bool hasY = false;
    double yZeroMm = 0.0;
    for (const auto& row : rows.vertices) {
        if (!byVertexId.emplace(row.vertex_id, row).second) {
            throw std::runtime_error(jaw.jaw_id + " contains duplicate vertex_id " + std::to_string(row.vertex_id));
        }
        if (row.has_y_mm) {
            if (!hasY) {
                hasY = true;
                yZeroMm = row.y_mm;
            } else if (std::abs(yZeroMm - row.y_mm) > 1.0e-9) {
                throw std::runtime_error(jaw.jaw_id + " has inconsistent y_mm values");
            }
        }
    }

    for (int expectedVertex = 0; expectedVertex < static_cast<int>(byVertexId.size()); ++expectedVertex) {
        const auto found = byVertexId.find(expectedVertex);
        if (found == byVertexId.end()) {
            throw std::runtime_error(jaw.jaw_id + " vertex_id must be continuous from 0");
        }
        jaw.vertices.push_back(XZPoint{found->second.x_mm, found->second.z_mm});
    }
    jaw.y_zero_mm = hasY ? yZeroMm : 0.0;

    ValidatePolygon(jaw);
    return jaw;
}

}  // namespace

SlitCollimatorProfile SlitCollimatorProfileReader::ReadProfile(
    const std::string& filePath,
    const std::string& profileId) const
{
    if (filePath.empty()) {
        throw std::runtime_error("collimator profile file path must be non-empty");
    }
    if (profileId.empty()) {
        throw std::runtime_error("collimator profile_id must be non-empty");
    }

    std::ifstream input(filePath);
    if (!input) {
        throw std::runtime_error("failed to open collimator profile CSV: " + filePath);
    }

    std::string headerLine;
    if (!std::getline(input, headerLine)) {
        throw std::runtime_error("collimator profile CSV is empty: " + filePath);
    }
    const HeaderColumns columns = ParseHeader(headerLine, filePath);

    std::map<int, JawRows> rowsByJawIndex;
    bool foundProfile = false;
    std::string line;
    int lineNumber = 1;
    while (std::getline(input, line)) {
        ++lineNumber;
        if (Trim(line).empty()) {
            continue;
        }

        const auto fields = SplitCsvLine(line);
        if (static_cast<int>(fields.size()) != columns.count) {
            throw std::runtime_error("collimator profile CSV row has wrong column count at line "
                                     + std::to_string(lineNumber));
        }

        const std::string rowProfileId = RequiredField(fields, columns.profile_id, "profile_id", lineNumber);
        if (rowProfileId != profileId) {
            continue;
        }
        foundProfile = true;

        const std::string jawId = RequiredField(fields, columns.jaw_id, "jaw_id", lineNumber);
        const int jawIndex = ParseJawIndex(jawId);
        auto& jawRows = rowsByJawIndex[jawIndex];
        if (jawRows.jaw_id.empty()) {
            jawRows.jaw_id = jawId;
        } else if (jawRows.jaw_id != jawId) {
            throw std::runtime_error("multiple jaw_id values map to the same jaw index: " + jawId);
        }

        jawRows.vertices.push_back(BuildVertexRow(fields, columns, lineNumber));
    }

    if (!foundProfile) {
        throw std::runtime_error("collimator profile_id not found: " + profileId);
    }
    if (rowsByJawIndex.empty()) {
        throw std::runtime_error("collimator profile must contain at least one jaw: " + profileId);
    }

    SlitCollimatorProfile profile;
    profile.profile_id = profileId;
    for (int expectedJaw = 0; expectedJaw < static_cast<int>(rowsByJawIndex.size()); ++expectedJaw) {
        const auto found = rowsByJawIndex.find(expectedJaw);
        if (found == rowsByJawIndex.end()) {
            throw std::runtime_error("jaw_id must be continuous from jaw_0 in profile: " + profileId);
        }
        profile.jaws.push_back(BuildJawProfile(found->second));
    }

    return profile;
}
