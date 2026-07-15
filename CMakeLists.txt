cmake_minimum_required(VERSION 3.16)

project(MSS VERSION 0.2.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(Geant4 REQUIRED ui_all vis_all)
include(${Geant4_USE_FILE})

find_package(yaml-cpp REQUIRED)
if(TARGET yaml-cpp::yaml-cpp)
    set(MSS_YAML_CPP_TARGET yaml-cpp::yaml-cpp)
elseif(TARGET yaml-cpp)
    set(MSS_YAML_CPP_TARGET yaml-cpp)
elseif(YAML_CPP_LIBRARIES)
    set(MSS_YAML_CPP_TARGET ${YAML_CPP_LIBRARIES})
else()
    message(FATAL_ERROR "yaml-cpp was found, but no link target or library variable is available.")
endif()

add_executable(MSS
    main.cc
    src/ActionInitialization.cc
    src/CsvWriter.cc
    src/DetectorConstruction.cc
    src/EventAction.cc
    src/ImagingHeadConstruction.cc
    src/MaterialManager.cc
    src/MetadataWriter.cc
    src/PhysicsList.cc
    src/PoseRunController.cc
    src/PrimaryGeneratorAction.cc
    src/RegionRegistry.cc
    src/RegionResolver.cc
    src/RunAction.cc
    src/RunIdBuilder.cc
    src/ScanPoseManager.cc
    src/SimulationConfig.cc
    src/SimulationConfigReader.cc
    src/SimulationMessenger.cc
    src/SlitCollimatorBuilder.cc
    src/SlitCollimatorProfileReader.cc
    src/SourceModel.cc
    src/SpectrumSampler.cc
    src/SteppingAction.cc
    src/VehicleROIConfig.cc
    src/VehicleROIConfigReader.cc
    src/VehicleROIConstruction.cc
    src/VirtualDetectorPlane.cc
    src/VisualizationController.cc
)

target_include_directories(MSS PRIVATE include)
target_link_libraries(MSS PRIVATE ${Geant4_LIBRARIES} ${MSS_YAML_CPP_TARGET})

include(CTest)
if(BUILD_TESTING)
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
    add_test(
        NAME core_experiment_contract_unit
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_SOURCE_DIR}/tests/test_core_experiment_contract.py
    )
    set_tests_properties(core_experiment_contract_unit PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

    add_test(
        NAME experiment_queue_unit
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_SOURCE_DIR}/tests/test_experiment_queue.py
    )
    set_tests_properties(experiment_queue_unit PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

    add_test(
        NAME source_response_config_unit
        COMMAND ${Python3_EXECUTABLE} ${CMAKE_SOURCE_DIR}/tests/test_source_response_experiment_configs.py
    )
    set_tests_properties(source_response_config_unit PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

endif()
