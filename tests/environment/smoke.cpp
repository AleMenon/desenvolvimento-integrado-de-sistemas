#include <Eigen/Dense>
#include <iostream>

int main() {
    Eigen::Matrix2d matrix;

    matrix << 1.0, 2.0,
              3.0, 4.0;

    Eigen::Vector2d vector(1.0, 1.0);

    Eigen::Vector2d result = matrix * vector;

    if (!result.isApprox(Eigen::Vector2d(3.0, 7.0))) {
        std::cerr << "Falha no teste do Eigen.\n";
        return 1;
    }

    std::cout << "Ambiente C++ configurado!\n";
    std::cout << "Resultado: " << result.transpose() << '\n';

    return 0;
}