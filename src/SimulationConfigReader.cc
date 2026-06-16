#include "SimulationConfigReader.hh"

#include <cctype>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <yaml-cpp/yaml.h>

namespace {

std::string FieldPath(const std::string& parentPath, const std::string& key)
{
    if (parentPath.empty()) {
        return key;
    }
    return parentPath + "." + key;
}

YAML::Node RequireField(const YAML::Node& parent, const std::string& key, const std::string& parentPath)
{
    if (!parent.IsMap()) {
        throw std::runtime_error(parentPath + " must be a YAML map");
    }

    const YAML::Node node = parent[key];
    if (!node) {
        throw std::runtime_error("missing required field: " + FieldPath(parentPath, key));
    }
    return node;
}

YAML::Node RequireMap(const YAML::Node& parent, const std::string& key, const std::string& parentPath)
{
    const YAML::Node node = RequireField(parent, key, parentPath);
    if (!node.IsMap()) {
        throw std::runtime_error(FieldPath(parentPath, key) + " must be a YAML map");
    }
    return node;
}

template <typename T>
T ReadScalar(const YAML::Node& parent, const std::string& key, const std::string& parentPath)
{
    const YAML::Node node = RequireField(parent, key, parentPath);
    const std::string path = FieldPath(parentPath, key);
    if (!node.IsScalar()) {
        throw std::runtime_error(path + " must be a scalar value");
    }

    try {
        return node.as<T>();
    } catch (const YAML::Exception& error) {
        throw std::runtime_error(path + " has invalid type or value: " + std::string(error.what()));
    }
}

std::optional<std::string> ReadNullableString(
    const YAML::Node& parent,
    const std::string& key,
    const std::string& parentPath)
{
    const YAML::Node node = RequireField(parent, key, parentPath);
    const std::string path = FieldPath(parentPath, key);
    if (node.IsNull()) {
        return std::nullopt;
    }
    if (!node.IsScalar()) {
        throw std::runtime_error(path + " must be a string or null");
    }

    try {
        return node.as<std::string>();
    } catch (const YAML::Exception& error) {
        throw std::runtime_error(path + " has invalid type or value: " + std::string(error.what()));
    }
}


bool IsStrictIntegerText(const std::string& value)
{
    if (value.empty()) {
        return false;
    }

    std::size_t index = 0;
    if (value[index] == '-') {
        ++index;
        if (index == value.size()) {
            return false;
        }
    }

    for (; index < value.size(); ++index) {
        if (!std::isdigit(static_cast<unsigned char>(value[index]))) {
            return false;
        }
    }
    return true;
}

int ParseStrictInt(const YAML::Node& node, const std::string& path)
{
    const std::string text = node.Scalar();
    if (!IsStrictIntegerText(text)) {
        throw std::runtime_error(path + " contains a non-integer value");
    }

    try {
        const long long value = std::stoll(text);
        if (value < std::numeric_limits<int>::min() || value > std::numeric_limits<int>::max()) {
            throw std::runtime_error(path + " contains an integer outside int range");
        }
        return static_cast<int>(value);
    } catch (const std::invalid_argument&) {
        throw std::runtime_error(path + " contains a non-integer value");
    } catch (const std::out_of_range&) {
        throw std::runtime_error(path + " contains an integer outside int range");
    }
}

template <std::size_t N>
std::array<double, N> ReadDoubleArray(
    const YAML::Node& parent,
    const std::string& key,
    const std::string& parentPath)
{
    const YAML::Node node = RequireField(parent, key, parentPath);
    const std::string path = FieldPath(parentPath, key);
    if (!node.IsSequence() || node.size() != N) {
        std::ostringstream message;
        message << path << " must be an array with " << N << " values";
        throw std::runtime_error(message.str());
    }

    std::array<double, N> values = {};
    for (std::size_t i = 0; i < N; ++i) {
        if (!node[i].IsScalar()) {
            throw std::runtime_error(path + " contains a non-scalar value");
        }
        try {
            values[i] = node[i].as<double>();
        } catch (const YAML::Exception& error) {
            throw std::runtime_error(path + " contains an invalid numeric value: " + std::string(error.what()));
        }
    }
    return values;
}

std::vector<int> ReadIntVector(const YAML::Node& parent, const std::string& key, const std::string& parentPath)
{
    const YAML::Node node = RequireField(parent, key, parentPath);
    const std::string path = FieldPath(parentPath, key);
    if (!node.IsSequence()) {
        throw std::runtime_error(path + " must be an integer array");
    }

    std::vector<int> values;
    values.reserve(node.size());
    for (std::size_t i = 0; i < node.size(); ++i) {
        if (!node[i].IsScalar()) {
            throw std::runtime_error(path + " contains a non-scalar value");
        }
        values.push_back(ParseStrictInt(node[i], path));
    }
    return values;
}

}  // namespace

SimulationConfig SimulationConfigReader::ReadPathOnly(const std::string& configFilePath) const
{
    SimulationConfig config;
    config.configFilePath = configFilePath;
    config.ValidateConfigPathOnly();
    return config;
}

SimulationConfig SimulationConfigReader::Read(const std::string& configFilePath) const
{
    SimulationConfig config = ReadPathOnly(configFilePath);

    YAML::Node root;
    try {
        root = YAML::LoadFile(configFilePath);
    } catch (const YAML::Exception& error) {
        throw std::runtime_error("failed to read YAML config " + configFilePath + ": " + std::string(error.what()));
    }
    if (!root.IsMap()) {
        throw std::runtime_error("YAML config root must be a map: " + configFilePath);
    }

    config.schema_version = ReadScalar<int>(root, "schema_version", "");

    const YAML::Node run = RequireMap(root, "run", "");
    config.run.random_seed = ReadScalar<long>(run, "random_seed", "run");
    config.run.number_of_threads = ReadScalar<int>(run, "number_of_threads", "run");
    config.run.n_primary_per_pose = ReadScalar<long>(run, "n_primary_per_pose", "run");
    config.run.debug = ReadScalar<bool>(run, "debug", "run");

    const YAML::Node vehicle = RequireMap(root, "vehicle", "");
    config.vehicle.geometry_file = ReadScalar<std::string>(vehicle, "geometry_file", "vehicle");
    config.vehicle.model_type = ReadScalar<std::string>(vehicle, "model_type", "vehicle");
    config.vehicle.selected_target_component = ReadNullableString(vehicle, "selected_target_component", "vehicle");
    config.vehicle.abnormal_material =
        ReadNullableString(vehicle, "abnormal_material", "vehicle").value_or("");

    const YAML::Node pose = RequireMap(root, "pose", "");
    config.pose.mode = ReadScalar<std::string>(pose, "mode", "pose");

    const YAML::Node poseList = RequireMap(pose, "list", "pose");
    config.pose.list_head_offset_x_mm = ReadIntVector(poseList, "head_offset_x_mm", "pose.list");
    config.pose.list_head_offset_y_mm = ReadIntVector(poseList, "head_offset_y_mm", "pose.list");

    const YAML::Node poseGrid = RequireMap(pose, "grid", "pose");
    config.pose.grid_x_offsets_mm = ReadIntVector(poseGrid, "x_offsets_mm", "pose.grid");
    config.pose.grid_y_offsets_mm = ReadIntVector(poseGrid, "y_offsets_mm", "pose.grid");

    const YAML::Node source = RequireMap(root, "source", "");
    config.source.particle = ReadScalar<std::string>(source, "particle", "source");
    config.source.energy_mode = ReadScalar<std::string>(source, "energy_mode", "source");
    config.source.mono_energy_keV = ReadScalar<double>(source, "mono_energy_keV", "source");
    config.source.spectrum_file = ReadScalar<std::string>(source, "spectrum_file", "source");
    config.source.source_pos_zero_mm = ReadDoubleArray<3>(source, "source_pos_zero_mm", "source");
    config.source.incident_theta_deg = ReadScalar<double>(source, "incident_theta_deg", "source");
    config.source.focal_spot_diameter_mm = ReadScalar<double>(source, "focal_spot_diameter_mm", "source");

    const YAML::Node collimator = RequireMap(root, "collimator", "");
    config.collimator.enable = ReadScalar<bool>(collimator, "enable", "collimator");
    config.collimator.profile_file = ReadScalar<std::string>(collimator, "profile_file", "collimator");
    config.collimator.profile_id = ReadScalar<std::string>(collimator, "profile_id", "collimator");
    config.collimator.jaw_extrusion_length_y_mm =
        ReadScalar<double>(collimator, "jaw_extrusion_length_y_mm", "collimator");

    const YAML::Node detector = RequireMap(root, "detector", "");
    config.detector.detector_z_zero_mm = ReadScalar<double>(detector, "detector_z_zero_mm", "detector");
    config.detector.detector_x_range_zero_mm =
        ReadDoubleArray<2>(detector, "detector_x_range_zero_mm", "detector");
    config.detector.detector_y_range_zero_mm =
        ReadDoubleArray<2>(detector, "detector_y_range_zero_mm", "detector");
    config.detector.accept_direction = ReadScalar<std::string>(detector, "accept_direction", "detector");

    const YAML::Node physics = RequireMap(root, "physics", "");
    config.physics.physics_list = ReadScalar<std::string>(physics, "physics_list", "physics");
    config.physics.production_cut_mm = ReadScalar<double>(physics, "production_cut_mm", "physics");

    const YAML::Node output = RequireMap(root, "output", "");
    config.output.output_directory = ReadScalar<std::string>(output, "output_directory", "output");
    config.output.events_csv_name = ReadScalar<std::string>(output, "events_csv_name", "output");
    config.output.metadata_yaml_name = ReadScalar<std::string>(output, "metadata_yaml_name", "output");
    config.output.thread_tmp_directory = ReadScalar<std::string>(output, "thread_tmp_directory", "output");
    if (const YAML::Node existingRunPolicy = output["existing_run_policy"]) {
        if (!existingRunPolicy.IsScalar()) {
            throw std::runtime_error("output.existing_run_policy must be a scalar value");
        }
        try {
            config.output.existing_run_policy = existingRunPolicy.as<std::string>();
        } catch (const YAML::Exception& error) {
            throw std::runtime_error(
                "output.existing_run_policy has invalid type or value: " + std::string(error.what()));
        }
    }

    if (const YAML::Node diagnostics = root["diagnostics"]) {
        if (!diagnostics.IsMap()) {
            throw std::runtime_error("diagnostics must be a YAML map");
        }
        config.diagnostics.configured = true;
        config.diagnostics.case_id = ReadScalar<std::string>(diagnostics, "case_id", "diagnostics");

        const YAML::Node phaseSpace = RequireMap(diagnostics, "phase_space", "diagnostics");
        config.diagnostics.phase_space.enable =
            ReadScalar<bool>(phaseSpace, "enable", "diagnostics.phase_space");
        config.diagnostics.phase_space.csv_name =
            ReadScalar<std::string>(phaseSpace, "csv_name", "diagnostics.phase_space");
    }

    config.Validate();
    return config;
}
