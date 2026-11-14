#include "cgnr.hpp"

#include <httplib.h>
#include <nlohmann/json.hpp>

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdlib>
#include <ctime>
#include <deque>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <map>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <utility>
#include <vector>
#include <cmath>

namespace fs = std::filesystem;
using json = nlohmann::json;
using reconstruction::Matrix;
using reconstruction::Vector;

namespace {

std::string utc_now() {
    const auto now = std::chrono::system_clock::now();
    const std::time_t timestamp = std::chrono::system_clock::to_time_t(now);
    std::tm utc{};
#ifdef _WIN32
    gmtime_s(&utc, &timestamp);
#else
    gmtime_r(&timestamp, &utc);
#endif
    const auto milliseconds = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()).count() % 1000;
    std::ostringstream out;
    out << std::put_time(&utc, "%Y-%m-%dT%H:%M:%S") << '.'
        << std::setw(3) << std::setfill('0') << milliseconds << 'Z';
    return out.str();
}

void respond(httplib::Response& res, int status, const json& body) {
    res.status = status;
    res.set_content(body.dump(), "application/json; charset=utf-8");
}

void error(httplib::Response& res, int status, const char* code, const char* message) {
    respond(res, status, {{"error", {{"code", code}, {"message", message}}}});
}

bool valid_identifier(const json& value) {
    return value.is_string() && !value.get<std::string>().empty()
        && value.get<std::string>().find_first_not_of(" \t\n\r") != std::string::npos;
}

// Não inclui linhas em branco, cabeçalho, NaN, infinito nem CSV irregular.
std::vector<double> parse_csv_row(const std::string& line) {
    std::vector<double> values;
    std::stringstream stream(line);
    std::string token;
    while (std::getline(stream, token, ',')) {
        std::size_t position = 0;
        double value = 0;
        try {
            value = std::stod(token, &position);
        } catch (const std::exception&) {
            throw std::runtime_error("CSV contém valor não numérico: " + token);
        }
        if (position != token.size()) {
            // Espaços ao final são tolerados, outros caracteres não.
            if (token.find_first_not_of(" \t\r\n", position) != std::string::npos)
                throw std::runtime_error("CSV contém conteúdo inesperado: " + token);
        }
        if (!std::isfinite(value))
            throw std::runtime_error("CSV contém valor não finito");
        values.push_back(value);
    }
    if (values.empty() || (!line.empty() && line.back() == ','))
        throw std::runtime_error("CSV contém linha vazia ou coluna sem valor");
    return values;
}

Matrix load_csv(const fs::path& path) {
    // Duas passagens evitam duplicar toda a matriz em memória durante a carga.
    std::ifstream input(path);
    if (!input) throw std::runtime_error("Não foi possível abrir matriz: " + path.string());
    std::string line;
    std::size_t rows = 0;
    std::size_t columns = 0;
    while (std::getline(input, line)) {
        if (line.empty()) throw std::runtime_error("CSV contém linha vazia");
        const auto row = parse_csv_row(line);
        if (columns == 0) columns = row.size();
        if (row.size() != columns) throw std::runtime_error("CSV contém linhas com larguras diferentes");
        ++rows;
    }
    if (rows == 0 || columns == 0)
        throw std::runtime_error("Matriz vazia: " + path.string());
    if (rows > static_cast<std::size_t>(std::numeric_limits<Eigen::Index>::max())
        || columns > static_cast<std::size_t>(std::numeric_limits<Eigen::Index>::max()))
        throw std::runtime_error("Dimensões da matriz excedem o limite da biblioteca");
    Matrix matrix(static_cast<Eigen::Index>(rows), static_cast<Eigen::Index>(columns));
    input.clear();
    input.seekg(0);
    for (std::size_t i = 0; i < rows; ++i) {
        if (!std::getline(input, line)) throw std::runtime_error("CSV foi alterado durante a carga");
        const auto row = parse_csv_row(line);
        if (row.size() != columns) throw std::runtime_error("CSV foi alterado durante a carga");
        for (std::size_t j = 0; j < columns; ++j)
            matrix(static_cast<Eigen::Index>(i), static_cast<Eigen::Index>(j)) = row[j];
    }
    return matrix;
}

struct Model {
    std::string id;
    std::string version;
    int image_rows = 0;
    int image_columns = 0;
    Matrix matrix;

    json metadata() const {
        return {{"model_id", id}, {"rows", matrix.rows()}, {"columns", matrix.cols()},
                {"image_shape", {image_rows, image_columns}}, {"data_type", "float64"},
                {"version", version}, {"checksum_sha256", nullptr}};
    }
};

std::unordered_map<std::string, std::shared_ptr<const Model>> load_models(const fs::path& catalog_path) {
    std::ifstream input(catalog_path);
    if (!input) throw std::runtime_error("Não foi possível abrir o catálogo: " + catalog_path.string());
    const json catalog = json::parse(input);
    if (!catalog.is_object() || !catalog.contains("models") || !catalog.at("models").is_array())
        throw std::runtime_error("Catálogo precisa conter o array 'models'");
    std::unordered_map<std::string, std::shared_ptr<const Model>> models;
    for (const auto& entry : catalog.at("models")) {
        if (!entry.is_object() || !entry.contains("model_id") || !entry.contains("file")
            || !entry.contains("image_shape") || !valid_identifier(entry.at("model_id"))
            || !entry.at("file").is_string() || !entry.at("image_shape").is_array()
            || entry.at("image_shape").size() != 2)
            throw std::runtime_error("Definição de modelo inválida no catálogo");
        const auto& shape = entry.at("image_shape");
        if (!shape[0].is_number_integer() || !shape[1].is_number_integer())
            throw std::runtime_error("image_shape deve conter dois inteiros");
        const int height = shape[0].get<int>();
        const int width = shape[1].get<int>();
        if (height <= 0 || width <= 0)
            throw std::runtime_error("image_shape deve conter valores positivos");
        const std::string id = entry.at("model_id").get<std::string>();
        const std::string filename = entry.at("file").get<std::string>();
        if (filename.empty()) throw std::runtime_error("Caminho da matriz vazio");
        auto model = std::make_shared<Model>();
        model->id = id;
        model->version = entry.value("version", std::string("1.0"));
        model->image_rows = height;
        model->image_columns = width;
        model->matrix = load_csv(catalog_path.parent_path() / filename);
        if (static_cast<std::int64_t>(height) * width != model->matrix.cols())
            throw std::runtime_error("image_shape incompatível com as colunas da matriz " + id);
        if (!models.emplace(id, model).second)
            throw std::runtime_error("model_id duplicado: " + id);
    }
    if (models.empty()) throw std::runtime_error("Catálogo de modelos vazio");
    return models;
}

struct Job {
    std::string id;
    std::string client_id;
    std::string signal_id;
    std::shared_ptr<const Model> model;
    Vector signal;
    int max_iterations = 10;
    double tolerance = 1e-8;
    std::string status = "queued";
    std::string created_at;
    json started_at = nullptr;
    json finished_at = nullptr;
    json result = nullptr;
    json failure = nullptr;
    json execution_time_ms = nullptr;
    json iterations = nullptr;
    json converged = nullptr;
    json stop_reason = nullptr;

    json metrics_json() const {
        return {{"request_id", id}, {"client_id", client_id}, {"signal_id", signal_id},
                {"model_id", model->id}, {"algorithm", "cgnr"}, {"status", status},
                {"created_at", created_at}, {"started_at", started_at},
                {"finished_at", finished_at}, {"execution_time_ms", execution_time_ms},
                {"iterations", iterations}, {"converged", converged},
                {"stop_reason", stop_reason}};
    }

    json status_json() const {
        json response = {{"request_id", id}, {"status", status},
                         {"client_id", client_id}, {"signal_id", signal_id},
                         {"model_id", model->id}, {"algorithm", "cgnr"},
                         {"created_at", created_at}, {"started_at", started_at},
                         {"finished_at", finished_at}};
        if (status == "failed") response["error"] = failure;
        return response;
    }
};

class ReconstructionServer {
public:
    ReconstructionServer(const fs::path& catalog, std::size_t queue_capacity)
        : models_(load_models(catalog)), queue_capacity_(queue_capacity),
          worker_(&ReconstructionServer::work, this) {}

    ~ReconstructionServer() {
        {
            std::lock_guard<std::mutex> guard(mutex_);
            stopping_ = true;
        }
        wake_.notify_all();
        worker_.join();
    }

    void configure_routes(httplib::Server& http) {
        http.Get("/health", [](const httplib::Request&, httplib::Response& res) {
            respond(res, 200, {{"status", "ok"}});
        });
        // Metrics endpoints deliberately omit large reconstructed vectors.
        http.Get("/metrics", [this](const httplib::Request&, httplib::Response& res) {
            std::lock_guard<std::mutex> guard(mutex_);
            respond(res, 200, metrics_snapshot());
        });
        http.Get("/metrics/reconstructions", [this](const httplib::Request&, httplib::Response& res) {
            json records = json::array();
            {
                std::lock_guard<std::mutex> guard(mutex_);
                for (const auto& pair : jobs_) records.push_back(pair.second->metrics_json());
            }
            respond(res, 200, {{"schema_version", 1}, {"implementation", "cpp"},
                               {"reconstructions", std::move(records)}});
        });
        http.Get("/models", [this](const httplib::Request&, httplib::Response& res) {
            json list = json::array();
            for (const auto& item : models_) list.push_back(item.second->metadata());
            respond(res, 200, {{"models", list}});
        });
        http.Get(R"(/models/([^/]+))", [this](const httplib::Request& req, httplib::Response& res) {
            const auto it = models_.find(std::string(req.matches[1]));
            if (it == models_.end()) return error(res, 404, "MODEL_NOT_FOUND", "Modelo inexistente");
            respond(res, 200, it->second->metadata());
        });
        http.Post("/reconstructions", [this](const httplib::Request& req, httplib::Response& res) {
            submit(req, res);
        });
        http.Get(R"(/reconstructions/([^/]+)/result)", [this](const httplib::Request& req, httplib::Response& res) {
            const auto job = find_job(std::string(req.matches[1]));
            if (!job) return error(res, 404, "REQUEST_NOT_FOUND", "Requisição não encontrada");
            json payload;
            {
                std::lock_guard<std::mutex> guard(mutex_);
                if (job->status != "completed")
                    return error(res, 409, "RESULT_NOT_READY", "Resultado indisponível");
                payload = job->result;
            }
            respond(res, 200, payload);
        });
        http.Get(R"(/reconstructions/([^/]+))", [this](const httplib::Request& req, httplib::Response& res) {
            const auto job = find_job(std::string(req.matches[1]));
            if (!job) return error(res, 404, "REQUEST_NOT_FOUND", "Requisição não encontrada");
            std::lock_guard<std::mutex> guard(mutex_);
            respond(res, 200, job->status_json());
        });
        http.set_error_handler([](const httplib::Request&, httplib::Response& res) {
            if (res.body.empty())
                error(res, res.status, "HTTP_ERROR", "Rota inexistente ou requisição rejeitada");
        });
        http.set_payload_max_length(2'000'000);
    }

private:
    // Guarded by mutex_. Time-weighted queue metrics include idle (queue=0).
    void accrue_queue_until(std::chrono::steady_clock::time_point now) {
        const double elapsed_ms = std::chrono::duration<double, std::milli>(
            now - last_queue_update_).count();
        if (elapsed_ms > 0) {
            queue_histogram_ms_[queue_.size()] += elapsed_ms;
            weighted_queue_ms_ += elapsed_ms * static_cast<double>(queue_.size());
        }
        last_queue_update_ = now;
    }

    json metrics_snapshot() {
        const auto now = std::chrono::steady_clock::now();
        accrue_queue_until(now);
        const double uptime_ms = std::chrono::duration<double, std::milli>(now - started_).count();
        // O(1): avoid scanning every retained job on each metrics poll.
        // Detailed histories are listed only by /metrics/reconstructions.
        std::size_t mode = 0;
        double longest_ms = -1.0;
        for (const auto& pair : queue_histogram_ms_) {
            if (pair.second > longest_ms) {
                mode = pair.first;
                longest_ms = pair.second;
            }
        }
        return {{"schema_version", 1}, {"implementation", "cpp"},
                {"timestamp_utc", utc_now()}, {"uptime_ms", uptime_ms},
                {"received_count", jobs_.size()}, {"completed_count", completed_count_},
                {"failed_count", failed_count_}, {"running_count", running_count_},
                {"queue_size", queue_.size()},
                {"queue_mean", uptime_ms > 0 ? weighted_queue_ms_ / uptime_ms : 0.0},
                {"queue_mode", mode},
                {"mean_reconstruction_time_ms",
                    completed_count_ ? json(completed_duration_ms_ / completed_count_) : json(nullptr)}};
    }

    std::shared_ptr<Job> find_job(const std::string& id) {
        std::lock_guard<std::mutex> guard(mutex_);
        const auto it = jobs_.find(id);
        return it == jobs_.end() ? nullptr : it->second;
    }

    void submit(const httplib::Request& req, httplib::Response& res) {
        if (req.body.size() > 2'000'000)
            return error(res, 413, "PAYLOAD_TOO_LARGE", "Payload muito grande");
        if (req.get_header_value("Content-Type").rfind("application/json", 0) != 0)
            return error(res, 415, "UNSUPPORTED_MEDIA_TYPE", "Content-Type deve ser application/json");
        const json body = json::parse(req.body, nullptr, false);
        if (body.is_discarded()) return error(res, 422, "INVALID_JSON", "JSON inválido");
        if (!body.is_object()) return error(res, 422, "INVALID_BODY", "Corpo deve ser objeto JSON");
        const char* required[] = {"client_id", "signal_id", "model_id", "algorithm", "signal", "parameters"};
        for (const auto* key : required)
            if (!body.contains(key)) return error(res, 422, "MISSING_FIELDS", "Campos obrigatórios ausentes");
        if (!valid_identifier(body["client_id"]) || !valid_identifier(body["signal_id"])
            || !valid_identifier(body["model_id"]))
            return error(res, 400, "INVALID_IDENTIFIER", "Identificador inválido");
        const auto it = models_.find(body["model_id"].get<std::string>());
        if (it == models_.end()) return error(res, 404, "MODEL_NOT_FOUND", "Modelo inexistente");
        if (body["algorithm"] != "cgnr")
            return error(res, 400, "INVALID_ALGORITHM", "Algoritmo não suportado");
        const json& params = body["parameters"];
        if (!params.is_object()) return error(res, 422, "INVALID_PARAMETERS", "parameters deve ser objeto");
        if (!params.contains("max_iterations") || !params.contains("tolerance")
            || !params["max_iterations"].is_number_integer() || !params["tolerance"].is_number())
            return error(res, 400, "INVALID_PARAMETERS", "Parâmetros numéricos inválidos");
        // Validar o intervalo antes de converter para int evita estouro em JSON grande.
        const auto& iteration_value = params["max_iterations"];
        if (iteration_value.is_number_unsigned()) {
            if (iteration_value.get<std::uint64_t>() > 10)
                return error(res, 400, "INVALID_PARAMETERS", "Parâmetros numéricos inválidos");
        } else if (iteration_value.get<std::int64_t>() < 1 || iteration_value.get<std::int64_t>() > 10) {
            return error(res, 400, "INVALID_PARAMETERS", "Parâmetros numéricos inválidos");
        }
        const int limit = iteration_value.get<int>();
        const double tolerance = params["tolerance"].get<double>();
        if (limit < 1 || !std::isfinite(tolerance) || tolerance <= 0)
            return error(res, 400, "INVALID_PARAMETERS", "Parâmetros numéricos inválidos");
        const json& values = body["signal"];
        if (!values.is_array() || values.size() != static_cast<std::size_t>(it->second->matrix.rows()))
            return error(res, 400, "INVALID_SIGNAL_DIMENSION", "Dimensão ou valores do sinal inválidos");
        Vector signal(it->second->matrix.rows());
        for (std::size_t index = 0; index < values.size(); ++index) {
            if (!values[index].is_number())
                return error(res, 400, "INVALID_SIGNAL_DIMENSION", "Sinal deve conter números finitos");
            const double number = values[index].get<double>();
            if (!std::isfinite(number))
                return error(res, 400, "INVALID_SIGNAL_DIMENSION", "Sinal deve conter números finitos");
            signal(static_cast<Eigen::Index>(index)) = number;
        }
        auto job = std::make_shared<Job>();
        job->client_id = body["client_id"].get<std::string>();
        job->signal_id = body["signal_id"].get<std::string>();
        job->model = it->second;
        job->signal = std::move(signal);
        job->max_iterations = limit;
        job->tolerance = tolerance;
        job->created_at = utc_now();
        const auto stamp = std::chrono::system_clock::now().time_since_epoch().count();
        job->id = "req-" + std::to_string(stamp) + "-" + std::to_string(next_id_.fetch_add(1));
        {
            std::lock_guard<std::mutex> guard(mutex_);
            if (queue_.size() >= queue_capacity_)
                return error(res, 503, "QUEUE_FULL", "Fila temporariamente cheia");
            accrue_queue_until(std::chrono::steady_clock::now());
            jobs_.emplace(job->id, job);
            queue_.push_back(job);
        }
        wake_.notify_one();
        respond(res, 202, {{"request_id", job->id}, {"status", "queued"},
                           {"status_url", "/reconstructions/" + job->id}});
    }

    void work() {
        while (true) {
            std::shared_ptr<Job> job;
            {
                std::unique_lock<std::mutex> guard(mutex_);
                wake_.wait(guard, [&] { return stopping_ || !queue_.empty(); });
                if (stopping_ && queue_.empty()) return;
                accrue_queue_until(std::chrono::steady_clock::now());
                job = queue_.front();
                queue_.pop_front();
                job->status = "running";
                ++running_count_;
                job->started_at = utc_now();
            }
            // Apenas em builds de teste: mantém o worker ocupado sem segurar
            // mutex_, permitindo observar estados queued/running e fila cheia.
            // Remover o arquivo libera a execução; não depende de duração do CGNR.
#ifdef TASK13_TEST_HOOKS
            if (const char* gate = std::getenv("TASK13_TEST_GATE_FILE")) {
                if (*gate != '\0') {
                    while (fs::exists(gate))
                        std::this_thread::sleep_for(std::chrono::milliseconds(5));
                }
            }
#endif
            const auto start = std::chrono::steady_clock::now();
            try {
                const auto result = reconstruction::cgnr(
                    job->model->matrix, job->signal, job->tolerance, job->max_iterations);
                if (!result.solution.allFinite() || !std::isfinite(result.residual_norm)
                    || !std::isfinite(result.normal_residual_norm)
                    || result.stop_reason == "numerical_breakdown")
                    throw std::runtime_error("Falha numérica durante o CGNR");
                const double duration = std::chrono::duration<double, std::milli>(
                    std::chrono::steady_clock::now() - start).count();
                json vector = json::array();
                for (Eigen::Index index = 0; index < result.solution.size(); ++index)
                    vector.push_back(result.solution[index]);
                json payload = {
                    {"request_id", job->id}, {"status", "completed"},
                    {"result", {{"vector", std::move(vector)},
                                {"shape", {job->model->image_rows, job->model->image_columns}}}},
                    {"metadata", {
                        {"client_id", job->client_id}, {"signal_id", job->signal_id},
                        {"model_id", job->model->id}, {"model_version", job->model->version},
                        {"algorithm", "cgnr"}, {"implementation", "cpp"},
                        {"iterations", result.iterations}, {"converged", result.converged},
                        {"stop_reason", result.stop_reason},
                        {"residual_norm", result.residual_norm},
                        {"normal_residual_norm", result.normal_residual_norm},
                        {"execution_time_ms", duration},
                        {"parameters", {{"max_iterations", job->max_iterations}, {"tolerance", job->tolerance}}},
                        {"created_at", job->created_at}, {"started_at", job->started_at},
                        {"finished_at", utc_now()}
                    }}
                };
                std::lock_guard<std::mutex> guard(mutex_);
                job->finished_at = payload["metadata"]["finished_at"];
                job->execution_time_ms = duration;
                job->iterations = result.iterations;
                job->converged = result.converged;
                job->stop_reason = result.stop_reason;
                job->result = std::move(payload);
                job->status = "completed";
                --running_count_;
                ++completed_count_;
                completed_duration_ms_ += duration;
            } catch (const std::exception&) {
                std::lock_guard<std::mutex> guard(mutex_);
                job->finished_at = utc_now();
                job->execution_time_ms = std::chrono::duration<double, std::milli>(
                    std::chrono::steady_clock::now() - start).count();
                job->stop_reason = "reconstruction_failed";
                job->failure = {{"code", "RECONSTRUCTION_FAILED"},
                                {"message", "Erro ao executar a reconstrução"}};
                job->status = "failed";
                --running_count_;
                ++failed_count_;
            }
        }
    }

    const std::unordered_map<std::string, std::shared_ptr<const Model>> models_;
    const std::size_t queue_capacity_;
    // Metrics use a monotonic clock, never the system clock for durations.
    const std::chrono::steady_clock::time_point started_{std::chrono::steady_clock::now()};
    std::chrono::steady_clock::time_point last_queue_update_{started_};
    double weighted_queue_ms_ = 0.0;
    std::map<std::size_t, double> queue_histogram_ms_;
    // Updated on state transitions under mutex_; never scan retained jobs.
    std::size_t completed_count_ = 0;
    std::size_t failed_count_ = 0;
    std::size_t running_count_ = 0;
    double completed_duration_ms_ = 0.0;
    std::mutex mutex_;
    std::condition_variable wake_;
    std::deque<std::shared_ptr<Job>> queue_;
    std::unordered_map<std::string, std::shared_ptr<Job>> jobs_;
    std::atomic<std::uint64_t> next_id_{0};
    bool stopping_ = false;
    std::thread worker_;
};

int parse_port(const std::string& argument) {
    std::size_t used = 0;
    const long port = std::stol(argument, &used);
    if (used != argument.size() || port < 1 || port > 65535)
        throw std::invalid_argument("Porta deve estar entre 1 e 65535");
    return static_cast<int>(port);
}

}  // namespace

int main(int argc, char** argv) {
    std::string host = "127.0.0.1";
    std::string catalog = "models/catalog.json";
    int port = 8080;
    std::size_t queue_capacity = 64;
    try {
        for (int i = 1; i < argc; ++i) {
            const std::string arg(argv[i]);
            if (arg == "--help") {
                std::cout << "Uso: reconstruction_server [--host IP] [--port PORTA]"
                          << " [--catalog ARQUIVO] [--queue-capacity N]\n";
                return 0;
            }
            if (i + 1 >= argc) throw std::invalid_argument("Argumento sem valor: " + arg);
            const std::string value(argv[++i]);
            if (arg == "--host") host = value;
            else if (arg == "--port") port = parse_port(value);
            else if (arg == "--catalog") catalog = value;
            else if (arg == "--queue-capacity") {
                std::size_t used = 0;
                const auto count = std::stoull(value, &used);
                if (used != value.size() || count == 0 || count > 100000)
                    throw std::invalid_argument("Capacidade da fila inválida");
                queue_capacity = static_cast<std::size_t>(count);
            } else throw std::invalid_argument("Opção desconhecida: " + arg);
        }
        ReconstructionServer reconstruction(catalog, queue_capacity);
        httplib::Server http;
        reconstruction.configure_routes(http);
        std::cout << "Servidor C++ em http://" << host << ':' << port << std::endl;
        if (!http.listen(host, port)) {
            std::cerr << "Não foi possível abrir a porta " << port << '\n';
            return 1;
        }
    } catch (const std::exception& ex) {
        std::cerr << "Erro: " << ex.what() << '\n';
        return 1;
    }
}
