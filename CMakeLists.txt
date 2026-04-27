cmake_minimum_required(VERSION 3.16)

project(MSS VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(Geant4 REQUIRED)
include(${Geant4_USE_FILE})

add_executable(MSS
    main.cc
    src/ActionInitialization.cc
    src/CollimatorBuilder.cc
    src/CollimatorProfileReader.cc
    src/CsvWriter.cc
    src/DetectorConstruction.cc
    src/EventAction.cc
    src/PhysicsList.cc
    src/PrimaryGeneratorAction.cc
    src/RunAction.cc
    src/SpectrumSampler.cc
    src/SteppingAction.cc
)

target_include_directories(MSS PRIVATE include)
target_link_libraries(MSS PRIVATE ${Geant4_LIBRARIES})
