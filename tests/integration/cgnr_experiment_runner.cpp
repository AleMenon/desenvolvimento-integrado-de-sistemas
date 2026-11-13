// TASK-08: runner experimental. Formato binário documentado em export_task08_binary.py.
// Mede SOMENTE o CGNR, excluindo carregamento e gravação.
#include "cgnr.hpp"
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

namespace {
std::uint64_t read_u64(std::ifstream& stream) {
    // O projeto é executado em x86_64 little-endian; bytes explícitos mantêm portabilidade.
    unsigned char bytes[8]{};
    if (!stream.read(reinterpret_cast<char*>(bytes), 8))
        throw std::runtime_error("Cabeçalho binário incompleto");
    std::uint64_t result = 0;
    for (int i = 0; i < 8; ++i) result |= std::uint64_t(bytes[i]) << (8 * i);
    return result;
}
void ensure_end(std::ifstream& stream) {
    if (stream.peek() != std::char_traits<char>::eof())
        throw std::runtime_error("Arquivo binário contém dados excedentes");
}
reconstruction::Matrix read_matrix(const std::string& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("Matriz não encontrada: " + path);
    auto rows = read_u64(input), columns = read_u64(input);
    if (!rows || !columns || rows > static_cast<std::uint64_t>(std::numeric_limits<Eigen::Index>::max()) ||
        columns > static_cast<std::uint64_t>(std::numeric_limits<Eigen::Index>::max()) ||
        rows > std::numeric_limits<std::uint64_t>::max() / columns / sizeof(double))
        throw std::runtime_error("Dimensões inválidas ou excesso de tamanho");
    reconstruction::Matrix matrix(static_cast<Eigen::Index>(rows), static_cast<Eigen::Index>(columns));
    const auto count = static_cast<std::streamsize>(rows * columns * sizeof(double));
    if (!input.read(reinterpret_cast<char*>(matrix.data()), count))
        throw std::runtime_error("Matriz binária incompleta");
    ensure_end(input);
    return matrix;
}
reconstruction::Vector read_signal(const std::string& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("Sinal não encontrado: " + path);
    auto count = read_u64(input);
    if (!count || count > static_cast<std::uint64_t>(std::numeric_limits<Eigen::Index>::max()) ||
        count > static_cast<std::uint64_t>(std::numeric_limits<std::streamsize>::max()) / sizeof(double))
        throw std::runtime_error("Tamanho inválido do sinal");
    reconstruction::Vector signal(static_cast<Eigen::Index>(count));
    if (!input.read(reinterpret_cast<char*>(signal.data()), static_cast<std::streamsize>(count * sizeof(double))))
        throw std::runtime_error("Sinal binário incompleto");
    ensure_end(input);
    return signal;
}
void write_number(std::ostream& out, double value) {
    if (std::isfinite(value)) out << value;
    else out << "null"; // JSON proíbe NaN/Infinity.
}
}
int main(int argc, char** argv) {
    try {
        if (argc != 5) {
            std::cerr << "Uso: cgnr_experiment_runner H.bin g.bin solution.csv metrics.json\n";
            return 2;
        }
        auto matrix = read_matrix(argv[1]);
        auto signal = read_signal(argv[2]);
        if (signal.size() != matrix.rows()) throw std::runtime_error("Dimensão do sinal incompatível");
        const auto start = std::chrono::steady_clock::now();
        const auto result = reconstruction::cgnr(matrix, signal, 1e-8, 10);
        const auto finish = std::chrono::steady_clock::now();
        const double elapsed = std::chrono::duration<double>(finish - start).count();
        std::ofstream vector_out(argv[3]);
        if (!vector_out) throw std::runtime_error("Não foi possível gravar a solução");
        vector_out << std::setprecision(17);
        for (Eigen::Index i = 0; i < result.solution.size(); ++i) vector_out << result.solution[i] << '\n';
        vector_out.close();
        if (!vector_out) throw std::runtime_error("Erro gravando solução");
        std::ofstream json(argv[4]);
        if (!json) throw std::runtime_error("Não foi possível gravar metadados");
        json << std::setprecision(17) << "{\n"
             << "  \"rows\": " << matrix.rows() << ",\n"
             << "  \"columns\": " << matrix.cols() << ",\n"
             << "  \"iterations\": " << result.iterations << ",\n"
             << "  \"converged\": " << (result.converged ? "true" : "false") << ",\n"
             << "  \"stop_reason\": \"" << result.stop_reason << "\",\n"
             << "  \"residual_norm\": ";
        write_number(json, result.residual_norm);
        json << ",\n  \"normal_residual_norm\": ";
        write_number(json, result.normal_residual_norm);
        json << ",\n  \"elapsed_seconds\": " << elapsed << ",\n  \"residual_history\": [";
        for (std::size_t i = 0; i < result.residual_history.size(); ++i) {
            if (i) json << ", ";
            write_number(json, result.residual_history[i]);
        }
        json << "]\n}\n";
        json.close();
        if (!json) throw std::runtime_error("Erro gravando metadados");
        std::cout << "CGNR C++: " << result.iterations << " iterações; converged=" << result.converged
                  << "; tempo CGNR=" << elapsed << "s\n";
    } catch (const std::exception& error) {
        std::cerr << "Erro: " << error.what() << '\n';
        return 1;
    }
}
