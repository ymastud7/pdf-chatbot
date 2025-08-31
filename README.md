# PDF Chatbot Application

A full-stack PDF chatbot application that allows users to upload PDF documents and ask questions about their content using Retrieval-Augmented Generation (RAG).

## Architecture

- **Frontend**: Next.js with React
- **Backend API**: Python with FastAPI
- **Background Worker**: Python script with RabbitMQ
- **Vector Database**: Qdrant
- **LLM**: Google Gemini 2.5 Flash Lite via Google AI Studio
- **Embeddings**: Google Gemini Embeddings via Google AI Studio
- **PDF Processing**: PyMuPDF (fitz) for efficient PDF text extraction

## Features

- Asynchronous document processing using message queues
- Efficient vector storage and retrieval
- Real-time processing status updates
- Responsive chat interface
- Error handling and user feedback

## Prerequisites

- Docker and Docker Compose
- Python 3.8+
- Node.js 16+
- API keys for:
  - [Google AI Studio](https://ai.google.dev/) (for LLM and embeddings)

## Setup Instructions

1. **Start infrastructure services**:
   ```bash
   docker-compose up -d
   ```

2. **Install backend dependencies**:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

3. **Configure environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

4. **Start the FastAPI server**:
   ```bash
   python api.py
   ```

5. **Start the worker process**:
   ```bash
   python worker.py
   ```

6. **Install frontend dependencies**:
   ```bash
   cd frontend
   npm install
   ```

7. **Start the Next.js frontend**:
   ```bash
   npm run dev
   ```

## Usage

1. Open your browser to http://localhost:3000
2. Upload a PDF document
3. Wait for processing to complete (check console logs)
4. Ask questions about your document

## API Endpoints

- `POST /upload` - Upload a PDF file
- `GET /sse/document-status/{doc_id}` - Server-Sent Events for document processing status
- `POST /chat` - Chat with a processed PDF document

## Development

### Project Structure
```
/pdf-chatbot
|-- /backend
|   |-- api.py             # FastAPI server
|   |-- worker.py          # RabbitMQ worker
|   |-- requirements.txt
|   |-- .env
|
|-- /frontend
|   |-- /app
|   |   |-- page.js        # Main Next.js component
|   |   |-- globals.css
|   |-- package.json
|
|-- docker-compose.yml
```

### Adding New Features

1. Backend changes should be made in `api.py` or `worker.py`
2. Frontend changes should be made in the `frontend/app` directory
3. Update dependencies in `requirements.txt` or `package.json` as needed

## Understanding the System

To better understand how the PDF chatbot works, including the vectors, chunks, and thought process:

1. The system uses Retrieval-Augmented Generation (RAG) to answer questions about PDF documents
2. Documents are split into chunks and converted to vector embeddings
3. These vectors are stored in Qdrant for efficient similarity search
4. When a user asks a question, it's converted to a vector and similar document chunks are retrieved
5. The retrieved context is sent to the LLM along with the question to generate a context-aware response

For implementation details, see the code in `api.py` and `worker.py`.

## Troubleshooting

- Make sure all Docker services are running: `docker-compose ps`
- Check that environment variables are set correctly
- Ensure RabbitMQ and Qdrant are accessible at their default ports
- Check the console logs for error messages

