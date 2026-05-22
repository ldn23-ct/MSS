#ifndef SIMULATION_CONFIG_HH
#define SIMULATION_CONFIG_HH

#include <array>
#include <optional>
#include <string>
#include <vector>

struct RunConfig {
    long random_seed = 12345;
    int number_of_threads = 1;
    long n_primary_per_pose = 10000;
    bool debug = false;
};

struct VehicleRunConfig {
    std::string geometry_file;
    std::string model_type;
    std::optional<std::string> selected_target_component;
    std::string abnormal_material = "G4_POLYETHYLENE";
};

struct PoseRawConfig {
    std::string mode;
    std::vector<int> list_head_offset_x_mm;
    std::vector<int> list_head_offset_y_mm;
    std::vector<int> grid_x_offsets_mm;
    std::vector<int> grid_y_offsets_mm;
};

struct SourceConfig {
    std::string particle;
    std::string energy_mode;
    double mono_energy_keV = 160.0;
    std::string spectrum_file;
    std::array<double, 3> source_pos_zero_mm = {0.0, 0.0, 0.0};
    double incident_theta_deg = 45.0;
    double focal_spot_diameter_mm = 5.0;
};

struct CollimatorConfig {
    bool enable = true;
    std::string profile_file;
    std::string profile_id;
    double jaw_extrusion_length_y_mm = 120.0;
};

struct DetectorConfig {
    double detector_z_zero_mm = 0.0;
    std::array<double, 2> detector_x_range_zero_mm = {0.0, 0.0};
    std::array<double, 2> detector_y_range_zero_mm = {0.0, 0.0};
    std::string accept_direction;
};

struct PhysicsConfig {
    std::string physics_list;
    double production_cut_mm = 0.1;
};

struct OutputConfig {
    std::string output_directory;
    std::string events_csv_name;
    std::string metadata_yaml_name;
    std::string thread_tmp_directory;
    std::string existing_run_policy = "fail";
};

struct WorldConfig {
    std::array<double, 3> center_mm = {0.0, 0.0, 0.0};
    std::array<double, 3> size_mm = {4000.0, 4000.0, 4000.0};
    std::string material = "G4_AIR";
};

struct SimulationConfig {
    std::string configFilePath;
    int schema_version = 2;
    RunConfig run;
    VehicleRunConfig vehicle;
    PoseRawConfig pose;
    SourceConfig source;
    CollimatorConfig collimator;
    DetectorConfig detector;
    PhysicsConfig physics;
    OutputConfig output;
    WorldConfig world;

    void ValidateConfigPathOnly() const;
    void Validate() const;
};

#endif
