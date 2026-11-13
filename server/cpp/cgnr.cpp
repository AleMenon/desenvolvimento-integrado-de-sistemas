#include "cgnr.hpp"

#include <cmath>
#include <stdexcept>

namespace reconstruction {
CgnrResult cgnr(const Matrix& h, const Vector& g,
                double tolerance, int max_iterations) {
    if (h.rows() == 0 || h.cols() == 0 || g.size() != h.rows())
        throw std::invalid_argument("Dimensões incompatíveis ou vazias em H e g.");
    if (!h.allFinite() || !g.allFinite())
        throw std::invalid_argument("H e g devem conter apenas valores finitos.");
    if (!std::isfinite(tolerance) || tolerance <= 0)
        throw std::invalid_argument("A tolerância deve ser positiva e finita.");
    if (max_iterations < 1 || max_iterations > 10)
        throw std::invalid_argument("O limite de iterações deve estar entre 1 e 10.");

    CgnrResult result;
    result.solution = Vector::Zero(h.cols());
    Vector r = g;
    Vector z = h.transpose() * r;
    Vector p = z;
    const double initial_normal_norm = z.stableNorm();
    const double threshold = tolerance * initial_normal_norm;
    result.residual_history.push_back(r.stableNorm());

    // Recalcula os resíduos verdadeiros, sem depender somente da recorrência.
    auto finish = [&](const std::string& reason) {
        const Vector final_r = g - h * result.solution;
        const Vector final_z = h.transpose() * final_r;
        result.residual_norm = final_r.stableNorm();
        result.normal_residual_norm = final_z.stableNorm();
        result.stop_reason = reason;
        const bool finite = final_r.allFinite() && final_z.allFinite()
            && std::isfinite(result.residual_norm)
            && std::isfinite(result.normal_residual_norm);
        if (!finite) result.stop_reason = "numerical_breakdown";
        result.converged = finite && reason != "numerical_breakdown"
            && result.normal_residual_norm <= threshold;
        if (result.converged) result.stop_reason = "tolerance_reached";
        else if (reason == "tolerance_reached") result.stop_reason = "numerical_breakdown";
        return result;
    };

    if (!z.allFinite() || !std::isfinite(initial_normal_norm)
        || !std::isfinite(result.residual_history.back()))
        return finish("numerical_breakdown");
    if (initial_normal_norm == 0) return finish("tolerance_reached");

    double gamma = z.squaredNorm();
    for (int iteration = 1; iteration <= max_iterations; ++iteration) {
        if (!std::isfinite(gamma) || gamma <= 0)
            return finish("numerical_breakdown");
        const Vector w = h * p;
        const double denominator = w.squaredNorm();
        if (!w.allFinite() || !std::isfinite(denominator) || denominator <= 0)
            return finish("numerical_breakdown");
        const double alpha = gamma / denominator;
        if (!std::isfinite(alpha) || alpha <= 0)
            return finish("numerical_breakdown");

        const Vector next_solution = result.solution + alpha * p;
        const Vector next_r = r - alpha * w;
        const Vector next_z = h.transpose() * next_r;
        const double next_norm = next_r.stableNorm();
        const double next_normal_norm = next_z.stableNorm();
        if (!next_solution.allFinite() || !next_r.allFinite() || !next_z.allFinite()
            || !std::isfinite(next_norm) || !std::isfinite(next_normal_norm))
            return finish("numerical_breakdown");

        result.error = next_norm - result.residual_history.back();
        result.solution = next_solution;
        r = next_r;
        result.iterations = iteration;
        result.residual_history.push_back(next_norm);
        if (next_normal_norm <= threshold)
            return finish("tolerance_reached");
        if (iteration == max_iterations) break;

        const double next_gamma = next_z.squaredNorm();
        if (!std::isfinite(next_gamma) || next_gamma <= 0)
            return finish("numerical_breakdown");
        const double beta = next_gamma / gamma;
        if (!std::isfinite(beta) || beta <= 0)
            return finish("numerical_breakdown");
        p = next_z + beta * p;
        if (!p.allFinite()) return finish("numerical_breakdown");
        gamma = next_gamma;
    }
    return finish("max_iterations");
}
}  // namespace reconstruction
