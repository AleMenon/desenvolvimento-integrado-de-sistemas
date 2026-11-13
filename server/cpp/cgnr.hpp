#pragma once

#include "matrix_operations.hpp"
#include <optional>
#include <string>
#include <vector>

namespace reconstruction {
struct CgnrResult {
    Vector solution;
    int iterations = 0;
    bool converged = false;
    std::string stop_reason = "max_iterations";
    double residual_norm = 0;
    double normal_residual_norm = 0;
    std::vector<double> residual_history;
    std::optional<double> error; // Diferença assinada apenas para diagnóstico; não decide a parada.
};

// Inicialização f0=0; parada: ||Hᵀr|| <= tolerance * ||Hᵀr0||.
// Entradas inválidas lançam std::invalid_argument. Limite permitido: 1 a 10.
// Falhas durante o cálculo retornam o último estado válido e numerical_breakdown.
CgnrResult cgnr(const Matrix& h, const Vector& g,
                double tolerance = 1e-8, int max_iterations = 10);
}  // namespace reconstruction
