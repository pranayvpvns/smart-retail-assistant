# Smart Retail Assistant

Smart Retail Assistant is an advanced web application and backend system tailored for retail analytics, forecasting, anomaly detection, and AI-driven conversational capabilities.

## Features

- **AI-Powered Chat Assistant**: Leverage natural language processing with LangChain and OpenAI to query retail data, get insights, and interact with your digital assistant.
- **Predictive Analytics & Forecasting**: Utilize ML models (Prophet, Scikit-Learn) to forecast sales and predict retail trends.
- **Anomaly Detection**: Automatically detect irregular patterns in sales or inventory.
- **Data Pipelines**: Built with PySpark for scalable data processing.
- **Vector Database Integration**: Uses ChromaDB for semantic search and retrieval-augmented generation (RAG) capabilities.
- **Power BI Dashboard**: A comprehensive Power BI template (`pranay6765.pbix`) is included for advanced visualization.

## Architecture

- **Frontend**: A custom HTML/CSS/JS dashboard interface.
- **Backend**: Flask REST API providing various endpoints:
  - `/auth` - Authentication and user management
  - `/data` & `/datasets` - Data ingestion and management
  - `/forecast` - Time-series forecasting
  - `/anomaly` - Anomaly detection
  - `/chat` - AI assistant interactions
  - `/dashboard`, `/products`, `/orders`, `/pipeline` - Retail business logic
- **Database**: MongoDB for persistent data storage.
- **Containerization**: Docker support for the backend service.

## Project Structure

```
smart_assisstant/
├── backend/          # Flask application, routing, and API logic
├── data/             # Raw and processed datasets
├── data_pipeline/    # Data engineering and transformation scripts (PySpark)
├── db/               # Database connection and models (MongoDB)
├── frontend/         # Frontend web application (HTML, CSS, JS)
├── ml/               # Machine learning models, training scripts
├── requirements.txt  # Python dependencies
├── Dockerfile        # Backend containerization (in backend/)
├── pranay6765.pbix   # Power BI Dashboard file
└── ...
```

## Prerequisites

- Python 3.11+
- MongoDB
- Java (for PySpark capabilities)
- OpenAI API Key (for the chat assistant)
- Docker (optional, for containerized execution)

## Installation and Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd smart_assisstant
```

### 2. Set up the Environment

Create a virtual environment and install the required dependencies:

```bash
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`
pip install -r requirements.txt
```

### 3. Environment Variables

Create a `.env` file based on `.env.example` in the root directory and populate it with your specific configurations (e.g., MongoDB URI, OpenAI API key, Secret keys).

### 4. Run the Backend

You can run the Flask backend directly:

```bash
python backend/app/main.py
```
The server will start on `http://127.0.0.1:5000`.

### 5. Run with Docker (Alternative)

To build and run the backend using Docker:

```bash
cd backend
docker build -t smart-retail-backend .
docker run -p 5000:5000 smart-retail-backend
```

## API Endpoints Overview

- `GET /` : Health check and API status
- `GET /health` : Detailed system and database connection health check

_Refer to the `backend/app/routes/` directory for detailed request/response schemas for each module._

## Documentation

For further information, please refer to the included document:
- `SMART_RETAIL_ASSISTANT_DOCUMENTATION.docx`
