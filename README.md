# Growtrics Agentic Content Generation Service

A production-ready, cost-conscious, and reliable backend service prototype for generating educational content at scale using a multi-agent system.

---

## 1. Project Architecture Overview

This project is built using **Clean Architecture** principles to separate core business entities and orchestration pipelines from external databases, LLM providers, and FastAPI framework details:

- **`app/domain`**: Pure Python containing core entities, validation schemas (`QuestionItem`, `JudgeRubric`), and repository/provider interfaces.
- **`app/application`**: Handles orchestration. `PipelineOrchestrator` manages agent coordination, structured validations, and circuit-breaking.
- **`app/providers`**: Concrete adapters for LLMs (OpenAI and Gemini gateways) featuring exponential backoff retries.
- **`app/repositories`**: SQLAlchemey implementation for database entities with Write-Ahead Logging (WAL) enabled SQLite.
- **`app/workers`**: Background task worker using an `asyncio.Queue` consumer pool to process generation requests asynchronously.

For in-depth trade-off analyses, cost calculations, and structural design logs, refer to the [Architecture Note](architecture_note.md).

---

## 2. Local Setup and Installation

### Prerequisites
- Python 3.10+ (Built and validated with Python 3.14)
- Virtual Environment tool (`venv` module)

### Setup Steps
1. Navigate to the project root directory.
2. Initialize and activate the virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a `.env` file in the root directory to store your API keys:
   ```env
   OPENAI_API_KEY=your-openai-api-key
   GEMINI_API_KEY=your-gemini-api-key
   ```

---

## 3. Running the Server

Start the FastAPI application locally using Uvicorn:
```bash
python3 -m uvicorn app.main:app --reload --port 8000
```
Once started, the interactive API documentation is available at:
- Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- ReDoc: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 4. API Endpoints

### 1. Submit Content Generation Job
* **Endpoint**: `POST /api/jobs`
* **Headers**:
  * `Content-Type: application/json`
  * `X-Idempotency-Key`: `uuid-or-unique-string` (Optional)
* **Curl Command**:
  ```bash
  curl -X POST http://127.0.0.1:8000/api/jobs \
    -H "Content-Type: application/json" \
    -H "X-Idempotency-Key: test-idempotency-123" \
    -d '{
      "subject": "Secondary school chemistry",
      "difficulty": "Beginner",
      "items_requested": 5
    }'
  ```
* **Response**: `202 Accepted`
  ```json
  {
    "id": "job-uuid",
    "subject": "Secondary school chemistry",
    "difficulty": "Beginner",
    "items_requested": 5,
    "status": "QUEUED",
    "total_cost": 0.0,
    "created_at": "2026-07-09T00:00:00Z",
    "updated_at": "2026-07-09T00:00:00Z"
  }
  ```

### 2. Poll Job Status
* **Endpoint**: `GET /api/jobs/{job_id}`
* **Curl Command**:
  ```bash
  curl http://127.0.0.1:8000/api/jobs/job-uuid
  ```
* **Response**: `200 OK`
  ```json
  {
    "id": "job-uuid",
    "status": "PROCESSING",
    "total_cost": 0.00035,
    "error_message": null,
    "created_at": "2026-07-09T00:00:00Z",
    "updated_at": "2026-07-09T00:00:05Z"
  }
  ```

### 3. Retrieve Completed Results & Metrics
* **Endpoint**: `GET /api/jobs/{job_id}/results`
* **Curl Command**:
  ```bash
  curl http://127.0.0.1:8000/api/jobs/job-uuid/results
  ```
* **Response**: `200 OK`
  Returns the metadata of the job, detailed quality and latency metrics (including P50 and P95), and the list of verified questions.


---

## 5. Verification & Testing

### Run Automated Tests
We have built a test suite featuring database session mocks and a scripted `MockLLMProvider` which lets you run the orchestrator, state transitions, validation, and repair loops locally without incurring API key costs or network overhead:
```bash
pytest
```

### Running the Required Test Cases
To execute the three required evaluation cases and output the results directly in `/test_cases/`, execute:
```bash
python3 generate_test_cases.py
```
This generates:
- `test_cases/chemistry_beginner.json`
- `test_cases/chemistry_advanced.json`
- `test_cases/biology_intermediate.json`
