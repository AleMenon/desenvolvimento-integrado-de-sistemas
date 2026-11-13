"""Cliente HTTP/JSON para solicitações assíncronas de reconstrução (TASK-09)."""

import math
import time
from urllib.parse import quote

import requests


class CommunicationError(RuntimeError):
    """Erro de rede, protocolo ou processamento remoto."""


class ReconstructionClient:
    def __init__(self, base_url: str, timeout: float = 5.0, session=None):
        if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url deve começar com http:// ou https://")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout deve ser positivo e finito")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session if session is not None else requests.Session()

    def _request(self, method: str, path: str, *, payload=None, expected_status=200) -> dict:
        try:
            response = self.session.request(
                method, f"{self.base_url}{path}", json=payload,
                timeout=self.timeout, headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            if response.status_code != expected_status:
                raise CommunicationError(
                    f"Status HTTP inesperado: {response.status_code}; esperado: {expected_status}"
                )
            data = response.json()
        except requests.Timeout as exc:
            raise CommunicationError("Tempo limite de comunicação excedido") from exc
        except requests.RequestException as exc:
            raise CommunicationError(f"Falha na comunicação HTTP: {exc}") from exc
        except ValueError as exc:
            raise CommunicationError("Servidor retornou JSON inválido") from exc
        if not isinstance(data, dict):
            raise CommunicationError("Resposta JSON deve ser um objeto")
        return data

    @staticmethod
    def _identifier(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} deve ser uma string não vazia")
        return value

    @staticmethod
    def _parameters(max_iterations, tolerance):
        if (isinstance(max_iterations, (bool,)) or not isinstance(max_iterations, int)
                or not 1 <= max_iterations <= 10):
            raise ValueError("max_iterations deve ser inteiro entre 1 e 10")
        if (isinstance(tolerance, bool) or not isinstance(tolerance, (int, float))
                or not math.isfinite(tolerance) or tolerance <= 0):
            raise ValueError("tolerance deve ser positiva e finita")
        return {"max_iterations": max_iterations, "tolerance": float(tolerance)}

    def health(self) -> dict:
        return self._request("GET", "/health")

    def list_models(self) -> dict:
        return self._request("GET", "/models")

    def get_model(self, model_id: str) -> dict:
        model_id = quote(self._identifier(model_id, "model_id"), safe="")
        return self._request("GET", f"/models/{model_id}")

    def submit_signal(
        self, client_id: str, signal_id: str, model_id: str, signal,
        *, max_iterations: int = 10, tolerance: float = 1e-8,
    ) -> str:
        """Envia um sinal e devolve request_id (POST deve retornar HTTP 202)."""
        client_id = self._identifier(client_id, "client_id")
        signal_id = self._identifier(signal_id, "signal_id")
        model_id = self._identifier(model_id, "model_id")
        parameters = self._parameters(max_iterations, tolerance)
        if isinstance(signal, (str, bytes)):
            raise ValueError("signal deve ser um vetor numérico")
        try:
            values = signal.tolist() if hasattr(signal, "tolist") else list(signal)
        except (TypeError, ValueError) as exc:
            raise ValueError("signal deve ser um vetor numérico") from exc
        if not isinstance(values, list) or not values or any(
            isinstance(v, (bool, str, bytes, list, dict))
            or not isinstance(v, (int, float)) or not math.isfinite(v)
            for v in values
        ):
            raise ValueError("signal deve conter números reais finitos")
        payload = {
            "client_id": client_id, "signal_id": signal_id,
            "model_id": model_id, "algorithm": "cgnr",
            "signal": [float(v) for v in values],
            "parameters": parameters,
        }
        data = self._request("POST", "/reconstructions", payload=payload, expected_status=202)
        request_id = data.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            raise CommunicationError("Servidor não retornou request_id")
        if data.get("status") not in {"queued", "running", "completed"}:
            raise CommunicationError("Servidor retornou status inválido na aceitação")
        return request_id

    def get_status(self, request_id: str) -> dict:
        path_id = quote(self._identifier(request_id, "request_id"), safe="")
        data = self._request("GET", f"/reconstructions/{path_id}")
        if data.get("status") not in {"queued", "running", "completed", "failed"}:
            raise CommunicationError("Resposta de status inválida")
        return data

    def get_result(self, request_id: str) -> dict:
        path_id = quote(self._identifier(request_id, "request_id"), safe="")
        data = self._request("GET", f"/reconstructions/{path_id}/result")
        result, metadata = data.get("result"), data.get("metadata")
        if (data.get("request_id") != request_id or data.get("status") != "completed"
                or not isinstance(result, dict) or not isinstance(metadata, dict)):
            raise CommunicationError("Resposta de reconstrução fora do contrato JSON")
        vector, shape = result.get("vector"), result.get("shape")
        if (not isinstance(vector, list) or not isinstance(shape, list)
                or len(shape) != 2 or any(type(s) is not int or s <= 0 for s in shape)
                or len(vector) != shape[0] * shape[1]
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in vector)):
            raise CommunicationError("Vetor ou shape de reconstrução inválido")
        return data

    def reconstruct(
        self, client_id: str, signal_id: str, model_id: str, signal,
        *, max_iterations: int = 10, tolerance: float = 1e-8,
        poll_interval: float = 0.2, max_polls: int = 30,
    ) -> dict:
        """Envia sinal, consulta estado e devolve resultado estruturado."""
        if type(max_polls) is not int or max_polls < 1:
            raise ValueError("max_polls deve ser um inteiro positivo")
        if (isinstance(poll_interval, bool) or not isinstance(poll_interval, (int, float))
                or not math.isfinite(poll_interval) or poll_interval < 0):
            raise ValueError("poll_interval deve ser não negativo e finito")
        request_id = self.submit_signal(
            client_id, signal_id, model_id, signal,
            max_iterations=max_iterations, tolerance=tolerance,
        )
        for attempt in range(max_polls):
            status = self.get_status(request_id)
            state = status["status"]
            if state == "completed":
                return self.get_result(request_id)
            if state == "failed":
                raise CommunicationError(f"Reconstrução falhou: {status.get('error', 'sem detalhes')}")
            if attempt + 1 < max_polls:
                time.sleep(poll_interval)
        raise CommunicationError("Limite de consultas excedido sem resultado")
