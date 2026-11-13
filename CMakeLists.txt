cmake_minimum_required(VERSION 3.18)

project(
    desenvolvimento_integrado_de_sistemas
    VERSION 0.1.0
    LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(BLA_VENDOR OpenBLAS)

# Eigen 5 mantém o nome do pacote Eigen3, mas não aceita pedidos de versão 3.x.
find_package(Eigen3 REQUIRED NO_MODULE)
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

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
add_library(matrix_operations server/cpp/matrix_operations.cpp)
target_include_directories(matrix_operations PUBLIC server/cpp)
target_link_libraries(matrix_operations PUBLIC Eigen3::Eigen BLAS::BLAS)
target_compile_definitions(matrix_operations PUBLIC EIGEN_USE_BLAS)

add_library(cgnr server/cpp/cgnr.cpp)
target_link_libraries(cgnr PUBLIC matrix_operations)

include(CTest)
if(BUILD_TESTING)
    add_executable(test_cgnr tests/unit/test_cgnr.cpp)
    target_link_libraries(test_cgnr PRIVATE cgnr)
    add_test(NAME cgnr_cpp COMMAND test_cgnr)
    add_test(NAME environment_cpp COMMAND environment_check)
    add_executable(matrix_operations_runner tests/integration/matrix_operations_runner.cpp)
    target_link_libraries(matrix_operations_runner PRIVATE matrix_operations)
    # Python é necessário somente para a comparação opcional via pytest.
endif()
