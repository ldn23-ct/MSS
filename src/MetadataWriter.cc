#include "MetadataWriter.hh"

#include <array>
#include <fstream>
#include <optional>
#include <sstream>
#include <stdexcept>

namespace {

std::string BoolText(bool value)
{
    return value ? "true" : "false";
}

std::string NullableText(const std::optional<std::string>& value)
{
    if (!value || value->empty()) {
        return "null";
    }
    return *value;
}

template <typename T, std::size_t N>
std::string ArrayText(const std::array<T, N>& values)
{
    std::ostringstream stream;
    stream << '[';
    for (std::size_t i = 0; i < N; ++i) {
        if (i > 0) {
            stream << ", ";
        }
        stream << values[i];
    }
    stream << ']';
    return stream.str();
}

const BoxComponentConfig* FindComponent(const VehicleROIConfig& vehicleROI, const std::string& name)
{
    for (const auto& component : vehicleROI.components) {
        if (component.name == name) {
            return &component;
        }
    }
    return nullptr;
}

std::string AbnormalTargetType(const SimulationConfig& config, const VehicleROIConfig& vehicleROI)
{
    if (config.vehicle.model_type != "abnormal" || !config.vehicle.selected_target_component) {
        return "none";
    }

    const auto* component = FindComponent(vehicleROI, *config.vehicle.selected_target_component);
    if (component == nullptr || component->role.empty()) {
        return "none";
    }
    return component->role;
}

std::string AbnormalTargetRegion(const SimulationConfig& config)
{
    if (config.vehicle.model_type == "abnormal" && config.vehicle.selected_target_component) {
        return "target";
    }
    return "none";
}

}  // namespace

void MetadataWriter::Write(const std::string& filePath,
                           const SimulationConfig& config,
                           const VehicleROIConfig& vehicleROI,
                           const ScanPose& pose,
                           const std::string& runId,
                           const std::string& outputCsvName) const
{
    if (filePath.empty()) {
        throw std::runtime_error("metadata output path must be non-empty");
    }

    std::ofstream output(filePath, std::ios::out | std::ios::trunc);
    if (!output) {
        throw std::runtime_error("failed to open metadata output file: " + filePath);
    }

    output << "run_id: " << runId << '\n';
    output << "output_csv: " << outputCsvName << '\n';
    output << '\n';
    output << "model_type: " << config.vehicle.model_type << '\n';
    output << "vehicle_model_id: " << vehicleROI.vehicle_model_id << '\n';
    output << "vehicle_geometry_file: " << config.vehicle.geometry_file << '\n';
    output << "selected_target_component: " << NullableText(config.vehicle.selected_target_component) << '\n';
    output << "abnormal_target_type: " << AbnormalTargetType(config, vehicleROI) << '\n';
    output << "abnormal_target_region: " << AbnormalTargetRegion(config) << '\n';
    output << '\n';
    output << "pose_id: " << pose.pose_id << '\n';
    output << "pose_index: " << pose.pose_index << '\n';
    output << "head_offset_x_mm: " << pose.head_offset_x_mm << '\n';
    output << "head_offset_y_mm: " << pose.head_offset_y_mm << '\n';
    output << '\n';
    output << "n_primary: " << config.run.n_primary_per_pose << '\n';
    output << "base_random_seed: " << config.run.random_seed << '\n';
    output << "random_seed: " << pose.random_seed << '\n';
    output << "number_of_threads: " << config.run.number_of_threads << '\n';
    output << "debug: " << BoolText(config.run.debug) << '\n';
    output << '\n';
    output << "source:\n";
    output << "  particle: " << config.source.particle << '\n';
    output << "  energy_mode: " << config.source.energy_mode << '\n';
    output << "  mono_energy_keV: " << config.source.mono_energy_keV << '\n';
    output << "  spectrum_file: " << config.source.spectrum_file << '\n';
    output << "  incident_theta_deg: " << config.source.incident_theta_deg << '\n';
    output << "  focal_spot_diameter_mm: " << config.source.focal_spot_diameter_mm << '\n';
    output << "  source_pos_zero_mm: " << ArrayText(config.source.source_pos_zero_mm) << '\n';
    output << '\n';
    output << "collimator:\n";
    output << "  enable: " << BoolText(config.collimator.enable) << '\n';
    output << "  profile_file: " << config.collimator.profile_file << '\n';
    output << "  profile_id: " << config.collimator.profile_id << '\n';
    output << "  jaw_extrusion_length_y_mm: " << config.collimator.jaw_extrusion_length_y_mm << '\n';
    output << '\n';
    output << "detector:\n";
    output << "  detector_z_zero_mm: " << config.detector.detector_z_zero_mm << '\n';
    output << "  detector_x_range_zero_mm: " << ArrayText(config.detector.detector_x_range_zero_mm) << '\n';
    output << "  detector_y_range_zero_mm: " << ArrayText(config.detector.detector_y_range_zero_mm) << '\n';
    output << "  accept_direction: " << config.detector.accept_direction << '\n';
    output << '\n';
    output << "physics:\n";
    output << "  physics_list: " << config.physics.physics_list << '\n';
    output << "  production_cut_mm: " << config.physics.production_cut_mm << '\n';
    output << '\n';
    output << "world:\n";
    output << "  shape: box\n";
    output << "  center_mm: " << ArrayText(config.world.center_mm) << '\n';
    output << "  size_mm: " << ArrayText(config.world.size_mm) << '\n';
    output << "  material: " << config.world.material << '\n';
    output << '\n';
    output << "output_policy:\n";
    output << "  existing_run_policy: " << config.output.existing_run_policy << '\n';
    output << '\n';
    output << "notes: M14 run-level metadata\n";

    output.flush();
    if (!output) {
        throw std::runtime_error("failed while writing metadata output file: " + filePath);
    }
}
