#include "cgnr.hpp"
#include <iostream>
#include <limits>
#include <stdexcept>

using namespace reconstruction;
void check(bool ok, const char* message) {
    if (!ok) throw std::runtime_error(message);
}
template <typename F> void invalid(F function) {
    try { function(); }
    catch (const std::invalid_argument&) { return; }
    throw std::runtime_error("Entrada inválida aceita.");
}
void verify(const Matrix& h, const Vector& g, const Vector& expected) {
    const Matrix original_h = h;
    const Vector original_g = g;
    const auto result = cgnr(h, g);
    check(result.converged, "Não convergiu no sistema conhecido.");
    check(result.solution.isApprox(expected, 1e-10), "Solução incorreta.");
    check(result.iterations <= 10, "Excedeu 10 iterações.");
    check(result.residual_history.size() == static_cast<std::size_t>(result.iterations + 1),
          "Histórico inconsistente.");
    check(std::abs(result.residual_norm - (g - h * result.solution).norm()) < 1e-10,
          "Norma final incorreta.");
    check(std::abs(result.normal_residual_norm
          - (h.transpose() * (g - h * result.solution)).norm()) < 1e-10,
          "Norma normal final incorreta.");
    check(h == original_h && g == original_g, "Entradas modificadas.");
}

int main() {
    try {
        const Matrix identity = Matrix::Identity(3, 3);
        Vector x(3); x << 1, 2, 3;
        verify(identity, x, x);
        check(cgnr(identity, x).iterations == 1, "Identidade deve exigir um passo.");
        Matrix diagonal = x.asDiagonal();
        // Primeiro passo calculado à mão: H=diag(1,2), g=(1,1), alpha=5/17.
        Matrix d(2, 2); d << 1, 0, 0, 2;
        Vector first_step(2); first_step << 5.0/17, 10.0/17;
        verify(d, Vector::Ones(2), first_step);
        const auto stopped = cgnr(d, Vector::Ones(2));
        check(stopped.iterations == 1 && stopped.error.has_value()
              && *stopped.error < -1e-4 && stopped.residual_norm > 0.1,
              "Deve parar pela diferença assinada, mesmo com resíduo não nulo.");
        check(std::abs(*stopped.error - (stopped.residual_history[1]
              - stopped.residual_history[0])) < 1e-15, "Erro não segue o enunciado.");
        Matrix rectangular(3, 2); rectangular << 1, 0, 0, 1, 1, 1;
        Vector pair(2); pair << 2, 3;
        Vector rectangular_step(2); rectangular_step << 791.0/338, 904.0/338;
        verify(rectangular, rectangular * pair, rectangular_step);
        Vector mean(1); mean << 2;
        verify(Matrix::Ones(3, 1), x, mean); // Mínimos quadrados: resíduo não nulo.
        Matrix rank_deficient(2, 2); rank_deficient << 1, 1, 2, 2;
        verify(rank_deficient, rank_deficient * Vector::Ones(2), Vector::Ones(2));
        Matrix wide(2, 3); wide << 1, 0, 0, 0, 1, 0;
        Vector minimum_norm(3); minimum_norm << 2, 3, 0;
        verify(wide, pair, minimum_norm);

        auto zero = cgnr(identity, Vector::Zero(3));
        check(zero.converged && zero.iterations == 0 && zero.solution.isZero(),
              "Sinal zero deve encerrar na inicialização.");
        zero = cgnr(Matrix::Zero(3, 2), x);
        check(!zero.converged && zero.iterations == 0 && !zero.error.has_value()
              && zero.stop_reason == "numerical_breakdown",
              "Direção zero não deve fingir que o critério de erro foi atingido.");

        for (int limit : {1, 10}) {
            const auto limited = cgnr(diagonal, Vector::Ones(3), 1e-4, limit);
            check(limited.iterations <= limit && limited.iterations == 1,
                  "Parada pelo erro deve preceder o limite.");
        }

        const double inf = std::numeric_limits<double>::infinity();
        const double nan = std::numeric_limits<double>::quiet_NaN();
        invalid([&] { cgnr(Matrix(0, 3), Vector(0)); });
        invalid([&] { cgnr(Matrix(3, 0), x); });
        invalid([&] { cgnr(identity, Vector::Ones(2)); });
        invalid([&] { cgnr(Matrix::Constant(3, 3, nan), x); });
        invalid([&] { cgnr(identity, Vector::Constant(3, inf)); });
        for (double t : {0.0, -1.0, inf, nan})
            invalid([&] { cgnr(identity, x, t); });
        for (int limit : {0, -1, 11, 100})
            invalid([&] { cgnr(identity, x, 1e-8, limit); });

        // Valores finitos que causam overflow/underflow em produtos internos.
        for (double scale : {1e100, 1e-100, 1e200}) {
            const auto failed = cgnr(scale * identity, x);
            check(!failed.converged && failed.stop_reason == "numerical_breakdown",
                  "Instabilidade não identificada.");
            check(failed.solution.allFinite() && failed.iterations == 0,
                  "Falha não preservou o último estado válido.");
        }
        // Escala pequena representável não deve ser rejeitada por epsilon fixo.
        verify(1e-20 * identity, 1e-20 * x, x);
        std::cout << "CGNR: soluções conhecidas, limites e instabilidades OK\n";
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
