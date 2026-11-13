#pragma once

#include <Eigen/Core>

namespace reconstruction {
using Matrix = Eigen::MatrixXd;
using Vector = Eigen::VectorXd;

// Entradas reais, finitas e não vazias. Dimensões incompatíveis ou valores
// inválidos lançam std::invalid_argument. As entradas não são modificadas.
Matrix multiply_matrices(const Matrix& m, const Matrix& n);
Matrix multiply_scalar_matrix(double a, const Matrix& m);
Vector multiply_matrix_vector(const Matrix& m, const Vector& a);
Vector multiply_vector_matrix(const Vector& a, const Matrix& m);
}  // namespace reconstruction
