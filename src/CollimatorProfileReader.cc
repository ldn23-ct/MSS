#include "CollimatorProfileReader.hh"

#include "G4Exception.hh"

#include <array>
#include <cerrno>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace {

constexpr double kGeometryTolerance = 1.0e-12;

void ReportProfileError(const std::string& message)
{
    G4Exception("CollimatorProfileReader",
                "MSSProfile001",
                FatalException,
                message.c_str());
}

std::string Trim(const std::string& value)
{
    const auto begin = value.find_first_not_of(" \t\r\n");
    if (begin == std::string::npos) {
        return "";
    }

    const auto end = value.find_last_not_of(" \t\r\n");
    return value.substr(begin, end - begin + 1);
}

std::vector<std::string> SplitCsvLine(const std::string& line)
{
    std::vector<std::string> fields;
    std::stringstream stream(line);
    std::string field;

    while (std::getline(stream, field, ',')) {
        fields.push_back(Trim(field));
    }

    if (!line.empty() && line.back() == ',') {
        fields.emplace_back();
    }

    return fields;
}

std::map<std::string, std::size_t> BuildHeaderIndex(
    const std::vector<std::string>& header)
{
    std::map<std::string, std::size_t> index;
    for (std::size_t i = 0; i < header.size(); ++i) {
        if (!header[i].empty()) {
            index[header[i]] = i;
        }
    }

    const std::array<const char*, 5> requiredColumns = {
        "profile_id", "jaw_id", "vertex_id", "x_mm", "z_mm"};

    for (const char* column : requiredColumns) {
        if (index.find(column) == index.end()) {
            ReportProfileError(std::string("Missing required column '") + column
                               + "'.");
        }
    }

    return index;
}

std::string RequiredField(const std::vector<std::string>& fields,
                          const std::map<std::string, std::size_t>& headerIndex,
                          const std::string& column,
                          int lineNumber)
{
    const auto found = headerIndex.find(column);
    if (found == headerIndex.end() || found->second >= fields.size()) {
        ReportProfileError("Missing required field '" + column + "' on line "
                           + std::to_string(lineNumber) + ".");
    }

    const std::string value = Trim(fields[found->second]);
    if (value.empty()) {
        ReportProfileError("Empty required field '" + column + "' on line "
                           + std::to_string(lineNumber) + ".");
    }

    return value;
}

int ParseVertexId(const std::string& text, int lineNumber)
{
    char* end = nullptr;
    errno = 0;
    const long parsed = std::strtol(text.c_str(), &end, 10);
    if (errno != 0 || end == text.c_str() || *end != '\0') {
        ReportProfileError("vertex_id must be an integer on line "
                           + std::to_string(lineNumber) + ".");
    }

    if (parsed < 0 || parsed > 4) {
        ReportProfileError("vertex_id must be in 0..4 on line "
                           + std::to_string(lineNumber) + ".");
    }

    return static_cast<int>(parsed);
}

double ParseFiniteDouble(const std::string& text,
                         const std::string& column,
                         int lineNumber)
{
    char* end = nullptr;
    errno = 0;
    const double parsed = std::strtod(text.c_str(), &end);
    if (errno != 0 || end == text.c_str() || *end != '\0') {
        ReportProfileError(column + " must be numeric on line "
                           + std::to_string(lineNumber) + ".");
    }

    if (!std::isfinite(parsed)) {
        ReportProfileError(column + " must be finite on line "
                           + std::to_string(lineNumber) + ".");
    }

    return parsed;
}

double Cross(const XZPoint& a, const XZPoint& b, const XZPoint& c)
{
    const double ab_x = b.x_mm - a.x_mm;
    const double ab_z = b.z_mm - a.z_mm;
    const double bc_x = c.x_mm - b.x_mm;
    const double bc_z = c.z_mm - b.z_mm;
    return ab_x * bc_z - ab_z * bc_x;
}

double SignedArea(const std::array<XZPoint, 5>& vertices)
{
    double areaTwice = 0.0;
    for (std::size_t i = 0; i < vertices.size(); ++i) {
        const auto& current = vertices[i];
        const auto& next = vertices[(i + 1) % vertices.size()];
        areaTwice += current.x_mm * next.z_mm - next.x_mm * current.z_mm;
    }

    return 0.5 * areaTwice;
}

void ValidateConvexPentagon(const PentagonJawProfile& jaw)
{
    const double area = SignedArea(jaw.vertices);
    if (std::abs(area) <= kGeometryTolerance) {
        ReportProfileError("Jaw '" + jaw.jaw_id + "' has zero polygon area.");
    }

    int expectedSign = 0;
    for (std::size_t i = 0; i < jaw.vertices.size(); ++i) {
        const double cross = Cross(jaw.vertices[i],
                                   jaw.vertices[(i + 1) % jaw.vertices.size()],
                                   jaw.vertices[(i + 2) % jaw.vertices.size()]);

        if (std::abs(cross) <= kGeometryTolerance) {
            ReportProfileError("Jaw '" + jaw.jaw_id
                               + "' is not a strictly convex pentagon.");
        }

        const int sign = cross > 0.0 ? 1 : -1;
        if (expectedSign == 0) {
            expectedSign = sign;
        } else if (sign != expectedSign) {
            ReportProfileError("Jaw '" + jaw.jaw_id
                               + "' is not a convex pentagon.");
        }
    }
}

struct JawAccumulator {
    PentagonJawProfile profile;
    std::array<bool, 5> seen = {false, false, false, false, false};
    int count = 0;
};

void StoreVertex(JawAccumulator& jaw,
                 int vertexId,
                 const XZPoint& point,
                 int lineNumber)
{
    if (jaw.seen[vertexId]) {
        ReportProfileError("Duplicate vertex_id " + std::to_string(vertexId)
                           + " for jaw '" + jaw.profile.jaw_id + "' on line "
                           + std::to_string(lineNumber) + ".");
    }

    jaw.profile.vertices[vertexId] = point;
    jaw.seen[vertexId] = true;
    ++jaw.count;
}

void ValidateCompleteJaw(const JawAccumulator& jaw)
{
    if (jaw.count != 5) {
        ReportProfileError("Jaw '" + jaw.profile.jaw_id
                           + "' must contain exactly 5 vertices.");
    }

    for (std::size_t vertexId = 0; vertexId < jaw.seen.size(); ++vertexId) {
        if (!jaw.seen[vertexId]) {
            ReportProfileError("Jaw '" + jaw.profile.jaw_id
                               + "' is missing vertex_id "
                               + std::to_string(vertexId) + ".");
        }
    }

    ValidateConvexPentagon(jaw.profile);
}

} // namespace

CollimatorProfile CollimatorProfileReader::ReadProfile(
    const std::string& filePath,
    const std::string& profileId) const
{
    if (filePath.empty()) {
        ReportProfileError("Collimator profile file path must not be empty.");
    }

    if (profileId.empty()) {
        ReportProfileError("Collimator profile ID must not be empty.");
    }

    std::ifstream input(filePath);
    if (!input.is_open()) {
        ReportProfileError("Failed to open collimator profile file '"
                           + filePath + "'.");
    }

    std::string line;
    if (!std::getline(input, line)) {
        ReportProfileError("Collimator profile file '" + filePath
                           + "' is empty.");
    }

    const auto headerIndex = BuildHeaderIndex(SplitCsvLine(line));

    JawAccumulator jaw0;
    jaw0.profile.jaw_id = "jaw_0";
    JawAccumulator jaw1;
    jaw1.profile.jaw_id = "jaw_1";

    bool foundProfile = false;
    int lineNumber = 1;
    while (std::getline(input, line)) {
        ++lineNumber;
        if (Trim(line).empty()) {
            continue;
        }

        const auto fields = SplitCsvLine(line);
        const std::string rowProfileId =
            RequiredField(fields, headerIndex, "profile_id", lineNumber);
        if (rowProfileId != profileId) {
            continue;
        }

        foundProfile = true;
        const std::string jawId =
            RequiredField(fields, headerIndex, "jaw_id", lineNumber);
        const std::string vertexText =
            RequiredField(fields, headerIndex, "vertex_id", lineNumber);
        const std::string xText =
            RequiredField(fields, headerIndex, "x_mm", lineNumber);
        const std::string zText =
            RequiredField(fields, headerIndex, "z_mm", lineNumber);

        const int vertexId = ParseVertexId(vertexText, lineNumber);
        const XZPoint point = {
            ParseFiniteDouble(xText, "x_mm", lineNumber),
            ParseFiniteDouble(zText, "z_mm", lineNumber)};

        if (jawId == "jaw_0") {
            StoreVertex(jaw0, vertexId, point, lineNumber);
        } else if (jawId == "jaw_1") {
            StoreVertex(jaw1, vertexId, point, lineNumber);
        } else {
            ReportProfileError("Invalid jaw_id '" + jawId + "' on line "
                               + std::to_string(lineNumber)
                               + "; expected jaw_0 or jaw_1.");
        }
    }

    if (!foundProfile) {
        ReportProfileError("Profile ID '" + profileId
                           + "' was not found in '" + filePath + "'.");
    }

    ValidateCompleteJaw(jaw0);
    ValidateCompleteJaw(jaw1);

    CollimatorProfile profile;
    profile.profile_id = profileId;
    profile.jaw0 = jaw0.profile;
    profile.jaw1 = jaw1.profile;
    return profile;
}
