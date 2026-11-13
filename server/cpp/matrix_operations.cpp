#include "matrix_operations.hpp"

#include <cmath>
#include <stdexcept>

namespace reconstruction {
namespace {
template <typename Derived>
void validate(const Eigen::MatrixBase<Derived>& value) {
    if (value.size() == 0) {
        throw std::invalid_argument("A entrada não pode ser vazia.");
    }
    if (!value.allFinite()) {
        throw std::invalid_argument("A entrada contém NaN ou infinitos.");
    }
}
}  // namespace

Matrix multiply_matrices(const Matrix& m, const Matrix& n) {
    validate(m);
    validate(n);
    if (m.cols() != n.rows()) {
        throw std::invalid_argument("Dimensões incompatíveis para matriz × matriz.");
    }
    return m * n;
}

Matrix multiply_scalar_matrix(double a, const Matrix& m) {
    if (!std::isfinite(a)) {
        throw std::invalid_argument("O escalar deve ser finito.");
    }
    validate(m);
    return a * m;
}

Vector multiply_matrix_vector(const Matrix& m, const Vector& a) {
    validate(m);
    validate(a);
    if (m.cols() != a.size()) {
        throw std::invalid_argument("Dimensões incompatíveis para matriz × vetor.");
    }
    return m * a;
}

Vector multiply_vector_matrix(const Vector& a, const Matrix& m) {
    validate(a);
    validate(m);
    if (a.size() != m.rows()) {
        throw std::invalid_argument("Dimensões incompatíveis para vetor × matriz.");
    }
    // O resultado é um vetor, como no NumPy (sem dimensão de linha extra).
    return m.transpose() * a;
}
}  // namespace reconstruction
