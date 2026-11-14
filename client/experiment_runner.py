"""Execução reproduzível de um plano nos servidores Python e C++."""

from client.signal_preparation import prepare_entry


class PartialSubmissionError(RuntimeError):
    """Falha de envio com histórico das requisições já aceitas."""

    def __init__(self, message, submissions):
        super().__init__(message)
        self.submissions = submissions


def submit_plan_to_servers(
    plan,
    python_client,
    cpp_client,
    *,
    client_id="cliente-01",
    max_iterations=10,
    tolerance=1e-8,
):
    """Envia os mesmos sinais e parâmetros aos dois servidores.

    Se ocorrer uma falha, PartialSubmissionError preserva o histórico
    das requisições confirmadas até aquele momento.
    """
    sequence = plan.get("sequence")

    if not isinstance(sequence, list) or not sequence:
        raise ValueError("o plano precisa conter uma sequência não vazia")

    model_ids = {entry["model_id"] for entry in sequence}
    expected_rows = {}

    for model_id in sorted(model_ids):
        python_model = python_client.get_model(model_id)
        cpp_model = cpp_client.get_model(model_id)

        python_rows = python_model.get("rows")
        cpp_rows = cpp_model.get("rows")

        if type(python_rows) is not int or python_rows <= 0:
            raise ValueError(f"dimensão inválida no servidor python: {model_id}")

        if python_rows != cpp_rows:
            raise ValueError(
                f"modelos incompatíveis: {model_id} "
                f"(python={python_rows}, cpp={cpp_rows})"
            )

        for field in ("columns", "image_shape", "version", "checksum_sha256"):
            left = python_model.get(field)
            right = cpp_model.get(field)

            if left is not None and right is not None and left != right:
                raise ValueError(
                    f"modelos incompatíveis em {field}: {model_id}"
                )

        expected_rows[model_id] = python_rows

    # valida toda a sequência antes de iniciar os envios
    prepared = []

    for entry in sequence:
        signal = prepare_entry(entry)
        model_id = entry["model_id"]

        if signal.size != expected_rows[model_id]:
            raise ValueError(
                f"sinal {entry['signal_id']} incompatível com "
                f"o modelo {model_id}: esperado "
                f"{expected_rows[model_id]}, recebido {signal.size}"
            )

        prepared.append((entry, signal.tolist()))

    submissions = []

    for entry, signal in prepared:
        signal_id = f"{entry['signal_id']}-{entry['position']:03d}"

        record = {
            "position": entry["position"],
            "model_id": entry["model_id"],
            "signal_id": signal_id,
            "gain": entry["gain"],
            "python_request_id": None,
            "cpp_request_id": None,
        }

        try:
            record["python_request_id"] = python_client.submit_signal(
                client_id,
                signal_id,
                entry["model_id"],
                signal,
                max_iterations=max_iterations,
                tolerance=tolerance,
            )

            record["cpp_request_id"] = cpp_client.submit_signal(
                client_id,
                signal_id,
                entry["model_id"],
                signal,
                max_iterations=max_iterations,
                tolerance=tolerance,
            )
        except Exception as exc:
            submissions.append(record)
            raise PartialSubmissionError(
                f"falha ao enviar sinal {signal_id}; "
                "consulte o histórico parcial",
                submissions,
            ) from exc

        submissions.append(record)

    return submissions
