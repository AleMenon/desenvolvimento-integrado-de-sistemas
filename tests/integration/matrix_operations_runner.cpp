// Adaptador exclusivo dos testes: texto por linhas, sem dependência da API HTTP.
#include "matrix_operations.hpp"
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

using namespace reconstruction;

double read_number() {
    std::string token;
    if (!(std::cin >> token)) throw std::runtime_error("Dados incompletos.");
    std::size_t consumed;
    double value = std::stod(token, &consumed);
    if (consumed != token.size()) throw std::runtime_error("Número inválido.");
    return value;
}

Matrix read_matrix() {
    Eigen::Index rows, cols;
    if (!(std::cin >> rows >> cols) || rows < 0 || cols < 0) {
        throw std::runtime_error("Formato inválido.");
    }
    Matrix m(rows, cols);
    for (Eigen::Index i = 0; i < rows; ++i)
        for (Eigen::Index j = 0; j < cols; ++j) m(i, j) = read_number();
    return m;
}

int main() {
    try {
        std::string operation;
        std::cin >> operation;
        const Matrix m = read_matrix();
        Matrix result;
        if (operation == "scalar") {
            result = multiply_scalar_matrix(read_number(), m);
        } else if (operation == "matrices") {
            result = multiply_matrices(m, read_matrix());
        } else if (operation == "matrix_vector" || operation == "vector_matrix") {
            const Matrix input = read_matrix();
            if (input.cols() != 1) throw std::runtime_error("Esperado vetor coluna.");
            const Vector a = input.col(0);
            if (operation == "matrix_vector") result = multiply_matrix_vector(m, a);
            else result = multiply_vector_matrix(a, m);
        } else {
            throw std::runtime_error("Operação desconhecida.");
        }
        std::cout << result.rows() << ' ' << result.cols() << '\n'
                  << std::setprecision(std::numeric_limits<double>::max_digits10);
        for (Eigen::Index i = 0; i < result.rows(); ++i) {
            for (Eigen::Index j = 0; j < result.cols(); ++j)
                std::cout << result(i, j) << ' ';
            std::cout << '\n';
        }
    } catch (const std::invalid_argument& error) {
        std::cerr << error.what() << '\n';
        return 2;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
