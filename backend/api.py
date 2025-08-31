import os
import uuid
import json
import asyncio
import pika
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_openai import ChatOpenAI
from qdrant_client import QdrantClient
from langchain_qdrant import QdrantVectorStore
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate

# Load environment variables
load_dotenv()

# Validate required environment variables
required_vars = [
    "GOOGLE_API_KEY",
    "QDRANT_HOST",
    "RABBITMQ_HOST"
]

missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}. Please check your .env file.")

# Initialize FastAPI app
app = FastAPI()

# Configure CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request models
class ChatRequest(BaseModel):
    doc_id: str
    query: str
    conversation_id: str = None  # Optional conversation ID for context tracking

class UploadResponse(BaseModel):
    doc_id: str

# In-memory storage for conversation history (in production, use Redis or database)
conversation_history = {}

# Create temporary directory for uploads
os.makedirs("/tmp/uploads", exist_ok=True)

@app.post("/upload", response_model=UploadResponse)
async def upload_pdf(file: UploadFile):
    """
    Upload a PDF file and enqueue it for processing
    """
    try:
        # Generate unique document ID
        doc_id = str(uuid.uuid4())
        
        # Validate file type
        if not file.content_type or "pdf" not in file.content_type.lower():
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        
        # Save file to temporary location
        file_path = f"/tmp/uploads/{doc_id}.pdf"
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Connect to RabbitMQ and publish job
        rabbitmq_host = os.getenv("RABBITMQ_HOST", "localhost")
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=rabbitmq_host)
        )
        channel = connection.channel()
        
        # Declare queue (ensure it exists)
        channel.queue_declare(queue='pdf_processing_queue', durable=True)
        
        # Create job message
        job_data = {
            "doc_id": doc_id,
            "file_path": file_path
        }
        
        # Publish message to queue
        channel.basic_publish(
            exchange='',
            routing_key='pdf_processing_queue',
            body=json.dumps(job_data),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Make message persistent
            )
        )
        
        # Close connection
        connection.close()
        
        # Return document ID immediately
        return UploadResponse(doc_id=doc_id)
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")



@app.post("/chat")
async def chat_with_pdf(request: ChatRequest):
    """
    Chat with a processed PDF document using RAG
    """
    try:
        # Validate input
        if not request.doc_id or not request.query:
            raise HTTPException(status_code=400, detail="Document ID and query are required")
            
        # Initialize conversation ID if not provided
        conversation_id = request.conversation_id or str(uuid.uuid4())
        
        # Initialize Google Generative AI embeddings
        embeddings = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001",
            google_api_key=os.getenv("GOOGLE_API_KEY")
        )
        
        
        
        # Initialize Qdrant client
        qdrant_client = QdrantClient(host=os.getenv("QDRANT_HOST"), port=6333)
        
        # Check if collection exists
        try:
            qdrant_client.get_collection(request.doc_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Document collection not found. Processing may still be ongoing.")
        
        # Create Qdrant vector store
        qdrant = QdrantVectorStore(
            client=qdrant_client,
            collection_name=request.doc_id,
            embedding=embeddings
        )
        
        # Create retriever
        retriever = qdrant.as_retriever(search_kwargs={"k": 5})  # Retrieve top 5 relevant chunks
        
        # Initialize LLM with Google Generative AI
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite",
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0.3,
            max_tokens=500  # Limit response length
        )
        
        # Get conversation history
        history = conversation_history.get(conversation_id, [])
        
        # Create enhanced prompt template with conversation history
        if history:
            system_prompt = (
                "You are an assistant for question-answering tasks. "
                "Use the following pieces of retrieved context to answer "
                "the question. If you don't know the answer, say that you "
                "don't know. Use three sentences maximum and keep the "
                "answer concise. Always refer to the context when answering."
                "\n\n"
                "Conversation History:\n{history}\n\n"
                "Retrieved Context:\n{context}"
            )
        else:
            system_prompt = (
                "You are an assistant for question-answering tasks. "
                "Use the following pieces of retrieved context to answer "
                "the question. If you don't know the answer, say that you "
                "don't know. Use three sentences maximum and keep the "
                "answer concise. Always refer to the context when answering."
                "\n\n"
                "{context}"
            )
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}"),
        ])
        
        # Format conversation history for the prompt
        formatted_history = "\n".join([f"Human: {msg['query']}\nAssistant: {msg['response']}" for msg in history[-3:]])  # Last 3 exchanges
        
        # Create RAG chain
        question_answer_chain = create_stuff_documents_chain(llm, prompt)
        rag_chain = create_retrieval_chain(retriever, question_answer_chain)
        
        # Invoke the chain with conversation context
        response = rag_chain.invoke({
            "input": request.query,
            "history": formatted_history
        })
        
        # Store conversation history
        conversation_history[conversation_id] = history + [{
            "query": request.query,
            "response": response["answer"]
        }]
        
        return {
            "answer": response["answer"], 
            "doc_id": request.doc_id,
            "conversation_id": conversation_id
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")

@app.get("/sse/document-status/{doc_id}")
async def document_status_stream(doc_id: str):
    """
    Server-Sent Events endpoint for document processing status
    """
    async def event_generator():
        while True:
            try:
                # Initialize Qdrant client
                qdrant_client = QdrantClient(host=os.getenv("QDRANT_HOST"), port=6333)
                
                # Check if collection exists
                qdrant_client.get_collection(doc_id)
                
                # Document found - send processed event
                yield f"data: {json.dumps({'status': 'processed', 'doc_id': doc_id})}\n\n"
                break  # Exit the loop when document is processed
                
            except Exception:
                # Document not ready - send processing event
                yield f"data: {json.dumps({'status': 'processing', 'doc_id': doc_id})}\n\n"
                await asyncio.sleep(2)  # Check every 2 seconds
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)