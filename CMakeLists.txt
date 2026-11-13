cmake_minimum_required(VERSION 3.16)

project(
    desenvolvimento_integrado_de_sistemas
    VERSION 0.1.0
    LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(BLA_VENDOR OpenBLAS)

find_package(Eigen3 3.3 REQUIRED NO_MODULE)
find_package(BLAS REQUIRED)

add_executable(
    environment_check
    tests/environment/smoke.cpp
)

target_link_libraries(
    environment_check
    PRIVATE
    Eigen3::Eigen
    BLAS::BLAS
)

target_compile_definitions(
    environment_check
    PRIVATE EIGEN_USE_BLAS
)