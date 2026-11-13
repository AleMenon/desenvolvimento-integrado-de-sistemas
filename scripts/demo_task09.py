"""Demonstração de troca de sinal e resultado usando o servidor HTTP simulado."""

from client.reconstruction_client import CommunicationError, ReconstructionClient


def main():
    client = ReconstructionClient("http://127.0.0.1:8765", timeout=5)
    try:
        print("Health:", client.health())
        print("Modelos:", client.list_models())
        result = client.reconstruct(
            client_id="cliente-01", signal_id="sinal-01", model_id="mock_3",
            signal=[0.1, 0.2, 0.3], max_iterations=10, tolerance=1e-8,
            poll_interval=0.1,
        )
        print("Resposta do servidor:", result)
    except CommunicationError as exc:
        raise SystemExit(f"Erro de comunicação: {exc}") from exc


if __name__ == "__main__":
    main()
