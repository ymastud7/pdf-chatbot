import os
import json
import uuid
import pika
from dotenv import load_dotenv
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

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

def process_pdf(ch, method, properties, body):
    """
    Callback function to process PDF files when a message is received from RabbitMQ
    """
    try:
        # Parse the job message
        job_data = json.loads(body)
        doc_id = job_data["doc_id"]
        file_path = job_data["file_path"]
        
        print(f"Processing document {doc_id} from {file_path}")
        
        # Validate file exists
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Initialize Google Generative AI embeddings
        embeddings = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001",
            google_api_key=os.getenv("GOOGLE_API_KEY")
        )
        
        
        # Load and split the PDF document
        loader = PyMuPDFLoader(file_path)
        documents = loader.load()
        
        # Split documents into chunks with improved parameters
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,  # Reduced chunk size for more focused retrieval
            chunk_overlap=100,  # Reduced overlap
            length_function=len,
            is_separator_regex=False,
        )
        chunks = text_splitter.split_documents(documents)
        
        # Initialize Qdrant client
        qdrant_client = QdrantClient(host=os.getenv("QDRANT_HOST"), port=6333)
        
        # Get embedding dimension
        sample_embedding = embeddings.embed_query("test")
        embedding_dim = len(sample_embedding)
        
        # Create collection if it doesn't exist
        collection_name = doc_id
        try:
            qdrant_client.get_collection(collection_name)
        except Exception as e:
            print(f"Collection {collection_name} not found, creating new one. Error: {e}")
            qdrant_client.recreate_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=embedding_dim,  # Use actual embedding dimension
                    distance=Distance.COSINE
                )
            )
        
        # Embed and store document chunks
        for i, chunk in enumerate(chunks):
            # Generate embedding for the chunk
            embedding = embeddings.embed_query(chunk.page_content)
            
            # Create point for Qdrant
            point = PointStruct(
                id=i,
                vector=embedding,
                payload={
                    "page_content": chunk.page_content,
                    "source": chunk.metadata.get("source", ""),
                    "page": chunk.metadata.get("page", 0)
                }
            )
            
            # Upload to Qdrant
            qdrant_client.upsert(
                collection_name=collection_name,
                points=[point]
            )
        
        print(f"Processing complete for document {doc_id}")
        
        # Acknowledge the message
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
    except FileNotFoundError as e:
        print(f"File error processing document: {str(e)}")
        # Reject the message without requeue to avoid infinite loop
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except Exception as e:
        print(f"Error processing document: {str(e)}")
        # Reject the message and requeue it
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

def main():
    """
    Main function to connect to RabbitMQ and start consuming messages
    """
    # Establish connection to RabbitMQ
    rabbitmq_host = os.getenv("RABBITMQ_HOST", "localhost")
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(host=rabbitmq_host)
    )
    channel = connection.channel()
    
    # Declare the queue
    channel.queue_declare(queue='pdf_processing_queue', durable=True)
    
    # Set up consumer
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(
        queue='pdf_processing_queue',
        on_message_callback=process_pdf
    )
    
    print("Worker waiting for PDF processing jobs. To exit press CTRL+C")
    channel.start_consuming()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Worker stopped")