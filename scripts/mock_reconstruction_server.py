"""Servidor HTTP de TESTE. Apenas ecoa sinais: NÃO executa CGNR."""

import argparse
import json
import math
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from urllib.parse import unquote


MODELS = {
    "mock_3": {
        "model_id": "mock_3", "rows": 3, "columns": 3,
        "image_shape": [1, 3], "data_type": "float64",
        "version": "mock", "checksum_sha256": None,
    }
}


class Handler(BaseHTTPRequestHandler):
    jobs = {}
    lock = Lock()

    def send_json(self, status, data):
        body = json.dumps(data, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def error(self, http_status, code, message):
        return self.send_json(http_status, {"error": {"code": code, "message": message}})

    def do_GET(self):
        if self.path == "/health":
            return self.send_json(200, {"status": "ok"})
        if self.path == "/models":
            return self.send_json(200, {"models": list(MODELS.values())})
        parts = self.path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "models":
            model = MODELS.get(unquote(parts[1]))
            return self.send_json(200, model) if model else self.error(404, "MODEL_NOT_FOUND", "Modelo inexistente")
        if len(parts) in (2, 3) and parts[0] == "reconstructions":
            with self.lock:
                job = self.jobs.get(unquote(parts[1]))
            if job is None:
                return self.error(404, "REQUEST_NOT_FOUND", "Requisição não encontrada")
            if len(parts) == 2:
                return self.send_json(200, job["status"])
            if parts[2] == "result":
                if job["status"]["status"] != "completed":
                    return self.error(409, "RESULT_NOT_READY", "Resultado indisponível")
                return self.send_json(200, job["result"])
        return self.error(404, "ROUTE_NOT_FOUND", "Rota não encontrada")

    def do_POST(self):
        if self.path != "/reconstructions":
            return self.error(404, "ROUTE_NOT_FOUND", "Rota não encontrada")
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2_000_000:
                return self.error(413, "PAYLOAD_TOO_LARGE", "Payload vazio ou muito grande")
            data = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            return self.error(422, "INVALID_JSON", "JSON inválido")
        if not isinstance(data, dict):
            return self.error(422, "INVALID_BODY", "Corpo deve ser objeto JSON")
        required = ("client_id", "signal_id", "model_id", "algorithm", "signal", "parameters")
        if any(field not in data for field in required):
            return self.error(422, "MISSING_FIELDS", "Campos obrigatórios ausentes")
        if any(not isinstance(data[field], str) or not data[field].strip() for field in ("client_id", "signal_id", "model_id")):
            return self.error(400, "INVALID_IDENTIFIER", "Identificador inválido")
        model = MODELS.get(data["model_id"])
        if not model:
            return self.error(404, "MODEL_NOT_FOUND", "Modelo inexistente")
        if data["algorithm"] != "cgnr":
            return self.error(400, "INVALID_ALGORITHM", "Algoritmo não suportado")
        params = data["parameters"]
        if not isinstance(params, dict):
            return self.error(422, "INVALID_PARAMETERS", "parameters deve ser objeto")
        limit, tolerance = params.get("max_iterations"), params.get("tolerance")
        if (type(limit) is not int or not 1 <= limit <= 10
                or isinstance(tolerance, bool) or not isinstance(tolerance, (int, float))
                or not math.isfinite(tolerance) or tolerance <= 0):
            return self.error(400, "INVALID_PARAMETERS", "Parâmetros numéricos inválidos")
        values = data["signal"]
        if (not isinstance(values, list) or len(values) != model["rows"]
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values)):
            return self.error(400, "INVALID_SIGNAL_DIMENSION", "Dimensão ou valores do sinal inválidos")

        request_id = str(uuid.uuid4())
        created = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        status = {
            "request_id": request_id, "status": "completed",
            "client_id": data["client_id"], "signal_id": data["signal_id"],
            "model_id": data["model_id"], "algorithm": "cgnr",
            "created_at": created, "started_at": created, "finished_at": created,
        }
        result = {
            "request_id": request_id, "status": "completed",
            "result": {"vector": [float(v) for v in values], "shape": model["image_shape"]},
            "metadata": {
                "client_id": data["client_id"], "signal_id": data["signal_id"],
                "model_id": data["model_id"], "algorithm": "cgnr",
                "implementation": "mock", "iterations": 0,
                "converged": False, "stop_reason": "mock_echo",
                "residual_norm": None, "execution_time_ms": 0.0,
                "parameters": params,
            },
        }
        with self.lock:
            self.jobs[request_id] = {"status": status, "result": result}
        return self.send_json(202, {
            "request_id": request_id, "status": "queued",
            "status_url": f"/reconstructions/{request_id}",
        })


def serve(host="127.0.0.1", port=8765):
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Servidor MOCK em http://{host}:{httpd.server_port}", flush=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    serve(port=args.port)
