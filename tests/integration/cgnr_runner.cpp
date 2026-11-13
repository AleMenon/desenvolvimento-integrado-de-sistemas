// Adaptador de teste: matriz por linhas, sinal, tolerância e limite via stdin.
#include "cgnr.hpp"
#include <iostream>
#include <iomanip>
#include <stdexcept>
int main() {
    try {
        int rows, cols, limit;
        double tolerance;
        if (!(std::cin >> rows >> cols >> tolerance >> limit) || rows <= 0 || cols <= 0)
            throw std::runtime_error("Cabeçalho inválido");
        reconstruction::Matrix h(rows, cols);
        reconstruction::Vector g(rows);
        for (int i=0; i<rows; ++i)
            for (int j=0; j<cols; ++j)
                if (!(std::cin >> h(i,j))) throw std::runtime_error("Matriz incompleta");
        for (int i=0; i<rows; ++i)
            if (!(std::cin >> g(i))) throw std::runtime_error("Sinal incompleto");
        const auto r = reconstruction::cgnr(h, g, tolerance, limit);
        std::cout << std::setprecision(17) << r.iterations << ' ' << r.converged << ' '
                  << r.residual_norm << ' ' << r.normal_residual_norm << '\n';
        std::cout << r.solution.transpose() << '\n';
        for (double v : r.residual_history) std::cout << v << ' ';
        std::cout << '\n';
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n'; return 1;
    }
}
