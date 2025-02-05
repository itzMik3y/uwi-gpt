import os
import re
import subprocess
from typing import Optional, List

# Updated imports per deprecation warnings:
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain.text_splitter import TokenTextSplitter
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.chains import RetrievalQA
from langchain.llms.base import LLM
from langchain.prompts import PromptTemplate


# =============================================================================
# Custom LLM class for Ollama
# =============================================================================
class OllamaLLM(LLM):
    model_name: str = "deepseek-r1:14b"  # Adjust as needed
    temperature: float = 0.0

    @property
    def _llm_type(self) -> str:
        return "ollama"

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        command = ["ollama", "run", self.model_name, "p"]
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8"  # Force UTF-8 encoding to avoid UnicodeDecodeError
        )
        out, err = process.communicate(prompt)
        if err:
            print("Ollama stderr:", err)
        return out

    @property
    def _identifying_params(self):
        return {"model_name": self.model_name, "temperature": self.temperature}


# =============================================================================
# Document Loading and Cleaning
# =============================================================================
def load_and_clean_documents(doc_folder: str):
    """
    Loads PDFs and text files from the folder, cleans the text,
    and attaches simple metadata.
    """
    documents = []
    for filename in os.listdir(doc_folder):
        file_path = os.path.join(doc_folder, filename)

        # Load PDF or text files only
        if filename.lower().endswith('.pdf'):
            loader = PyPDFLoader(file_path)
            docs = loader.load()
        elif filename.lower().endswith('.txt'):
            loader = TextLoader(file_path)
            docs = loader.load()
        else:
            continue  # Skip unsupported file types

        for doc in docs:
            # Clean the page content by removing extra whitespace and unwanted artifacts
            cleaned = re.sub(r'\s+', ' ', doc.page_content).strip()
            doc.page_content = cleaned

            # Attach metadata such as the source filename
            if not doc.metadata:
                doc.metadata = {}
            doc.metadata["source_file"] = filename
            documents.append(doc)
    return documents


# =============================================================================
# Define Prompt Templates
# =============================================================================
# Default prompt template for general questions
default_template = """
You are an AI assistant that answers questions based only on the provided context.

Context:
{context}

Question: {question}

Answer:
"""

default_prompt = PromptTemplate(
    input_variables=["context", "question"],
    template=default_template
)

# Custom prompt template for credit-related questions
credit_template = """
You are an AI assistant that answers questions based only on the provided context from a faculty handbook.
The context contains details about credit requirements for a BSc in Computer Science.
Please follow these steps:
1. Identify the number of credits required at Level 1.
2. Identify the number of credits required at Levels 2/3.
3. Identify the foundation course details (note that one foundation course gives 6 credits instead of 3, e.g., FOUN 1019).
4. Sum these values appropriately. If there are two possibilities (for example, one option yields 93 credits total and another yields 96), provide both totals.
5. Answer clearly with the final credit total(s).

Context:
{context}

Question: {question}

Answer:
"""

credit_prompt = PromptTemplate(
    input_variables=["context", "question"],
    template=credit_template
)


def is_credit_question(query: str) -> bool:
    """Return True if the query appears to be credit-related."""
    keywords = ["credit", "graduate", "BSc", "degree", "study"]
    return any(keyword.lower() in query.lower() for keyword in keywords)


# =============================================================================
# Main Execution
# =============================================================================
def main():
    # 1. Document Loading and Cleaning
    doc_folder = "./docs"  # Folder containing your documents (e.g., your faculty handbook)
    print("Loading and cleaning documents...")
    documents = load_and_clean_documents(doc_folder)
    print(f"Loaded {len(documents)} documents.")

    # 2. Document Splitting using a token-based splitter
    # Set a target of ~512 tokens per chunk with 50 token overlap.
    text_splitter = TokenTextSplitter(chunk_size=512, chunk_overlap=50)
    docs = text_splitter.split_documents(documents)
    print(f"Created {len(docs)} document chunks.")

    # 3. Build the Vector Store with Embeddings (Chroma)
    embedding_model = SentenceTransformerEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )
    vector_store = Chroma.from_documents(
        docs,
        embedding=embedding_model,
        persist_directory="./chroma_db"
    )
    # Use a higher 'k' to capture enough context
    retriever = vector_store.as_retriever(search_kwargs={"k": 10})

    # 4. Set Up the QA Chain with Conditional Prompt Selection
    llm = OllamaLLM(model_name="deepseek-r1:14b", temperature=0.0)
    query = "What level 1 courses do i have to do in computer science?"

    if is_credit_question(query):
        chosen_prompt = credit_prompt
        print("Using custom credit prompt.")
    else:
        chosen_prompt = default_prompt
        print("Using default prompt.")

    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",  # This chain concatenates retrieved chunks into one prompt.
        retriever=retriever,
        return_source_documents=False,
        chain_type_kwargs={"prompt": chosen_prompt}
    )

    # 5. Query the Chain
    print(f"\nQuery: {query}\n")
    answer = qa_chain.invoke(query)
    print("Answer (using local Ollama model):\n", answer)


if __name__ == "__main__":
    main()
