import json
import logging
import os
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_DOCUMENTS = [
    {
        "id": "doc101", "title": "Exploring Artificial Intelligence in Modern Healthcare",
        "abstract": "This paper discusses the impact of AI on diagnostics and treatment, highlighting machine learning advancements.",
        "keywords": ["ai", "healthcare", "diagnostics", "machine learning", "treatment"]
    },
    {
        "id": "doc102", "title": "The Future of Renewable Energy Sources",
        "abstract": "A comprehensive review of solar, wind, and geothermal energy technologies and their potential.",
        "keywords": ["renewable energy", "solar", "wind", "geothermal", "sustainability"]
    },
    {
        "id": "doc103", "title": "Quantum Computing: A New Paradigm",
        "abstract": "This article introduces the fundamental concepts of quantum computing and its applications.",
        "keywords": ["quantum computing", "qubits", "algorithms", "cryptography"]
    },
    {
        "id": "doc104", "title": "Advanced Machine Learning Techniques for NLP",
        "abstract": "Deep learning models and transformers are revolutionizing Natural Language Processing.",
        "keywords": ["machine learning", "nlp", "deep learning", "transformers", "ai"]
    }
]

class DocumentManager:
    def __init__(self, document_store_file: str = "documents.json", initial_documents: Optional[List[Dict[str, Any]]] = None):
        self.document_store_file = document_store_file
        self.document_store: List[Dict[str, Any]] = []
        self.next_doc_id_counter = 200 # Initial counter for generating new document IDs
        self._load_documents(initial_documents)

    def _load_documents(self, initial_documents: Optional[List[Dict[str, Any]]] = None) -> None:
        """Loads documents from the JSON file or initializes with default/initial documents."""
        try:
            with open(self.document_store_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content:
                    raise ValueError("File is empty")
                self.document_store = json.loads(content)
            logger.info(f"Loaded document store from {self.document_store_file}")
            
            # Update next_doc_id_counter based on loaded documents
            # This ensures new IDs don't clash if documents.json was manually edited with higher IDs
            if self.document_store:
                max_id = 0
                for doc in self.document_store:
                    doc_id_str = doc.get("id", "")
                    if doc_id_str.startswith("doc") and doc_id_str[3:].isdigit():
                        numeric_part = int(doc_id_str[3:])
                        if numeric_part > max_id:
                            max_id = numeric_part
                self.next_doc_id_counter = max_id + 1 if max_id >= 200 else 200


        except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
            logger.warning(f"{self.document_store_file} not found, empty, or invalid JSON ({e}). Initializing with default documents.")
            self.document_store = initial_documents if initial_documents is not None else DEFAULT_DOCUMENTS
            self._save_documents() # Create the file with current documents

    def _save_documents(self) -> None:
        """Saves the current document store to the JSON file."""
        try:
            logger.debug(f"Attempting to save document store. Full store repr: {repr(self.document_store)}")
            with open(self.document_store_file, 'w', encoding='utf-8') as f:
                json.dump(self.document_store, f, indent=4, ensure_ascii=False) # ensure_ascii=False for better readability if non-ASCII titles
            logger.info(f"Document store successfully saved to {self.document_store_file}")
        except IOError as e:
            logger.error(f"Could not save document store to {self.document_store_file}: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred while saving document store: {e}", exc_info=True)

    def generate_next_doc_id(self) -> str:
        """Generates a new unique document ID."""
        # This simple generation might need refinement if many docs are added and removed,
        # or if specific ID patterns are important.
        # For now, it ensures new IDs are higher than any existing numeric "docXXX" ID.
        doc_id = f"doc{self.next_doc_id_counter}"
        self.next_doc_id_counter += 1
        return doc_id

    def add_document(self, document_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Adds a new document to the store. If 'id' is not in document_data or is not unique,
        a new ID will be generated (though current usage in tools.py generates ID before calling this).
        This method should ensure the document has a unique ID.
        """
        if 'id' not in document_data or not document_data['id']:
            document_data['id'] = self.generate_next_doc_id()
        elif any(doc['id'] == document_data['id'] for doc in self.document_store):
            logger.warning(f"Document with ID {document_data['id']} already exists. Consider generating a new ID.")
            # Optionally, generate a new ID or raise an error. For now, we'll allow overwrite if ID matches.
            # However, the current tool implementations generate ID first, so this path is less likely.
            # To strictly prevent overwrites on add, check and raise error or re-generate ID.
            # For now, let's assume ID is pre-generated and unique by the caller.
        
        # If an existing document with the same ID is found, update it. Otherwise, append.
        # This makes `add_document` behave like an "upsert".
        # The original server code appended directly. Let's stick to append for now,
        # assuming callers manage ID uniqueness. If not, this should be an upsert or throw error.
        # For now, let's assume IDs are unique as generated by tools.
        
        existing_doc_index = next((index for (index, d) in enumerate(self.document_store) if d["id"] == document_data["id"]), None)
        if existing_doc_index is not None:
            logger.warning(f"Document with ID {document_data['id']} already exists. Updating it.")
            self.document_store[existing_doc_index] = document_data
        else:
            self.document_store.append(document_data)

        self._save_documents()
        return document_data

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a document by its ID."""
        for doc in self.document_store:
            if doc.get("id") == doc_id:
                return doc
        return None

    def list_documents(self) -> List[Dict[str, Any]]:
        """Returns a copy of all documents in the store."""
        return list(self.document_store) # Return a copy

    def search_documents(self, query_str: str, max_results: int = 3) -> List[Dict[str, Any]]:
        """Searches documents based on a query string."""
        if not query_str:
            return []
        
        query_lower = query_str.lower()
        found_documents = []
        for doc in self.document_store:
            match = False
            if query_lower in doc.get("title", "").lower():
                match = True
            elif query_lower in doc.get("abstract", "").lower():
                match = True
            elif any(query_lower in keyword.lower() for keyword in doc.get("keywords", [])):
                match = True
            
            if match:
                found_documents.append(doc.copy()) # Return copies of matching documents
            
            if len(found_documents) >= max_results:
                break
        
        return found_documents

# Example usage (for testing or if this file is run directly)
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    # Test with a temporary file
    test_file = "test_documents.json"
    if os.path.exists(test_file):
        os.remove(test_file)

    manager = DocumentManager(document_store_file=test_file)
    
    print("Initial documents:")
    for d in manager.list_documents():
        print(f"- {d['id']}: {d['title']}")

    new_id = manager.generate_next_doc_id()
    print(f"\nGenerated next ID: {new_id}")

    doc_to_add = {
        "id": new_id, # Pre-generate ID as tools.py does
        "title": "Test Document Alpha",
        "abstract": "This is a test document added dynamically.",
        "keywords": ["test", "dynamic"]
    }
    manager.add_document(doc_to_add)
    print(f"\nAdded document: {doc_to_add['title']}")

    print("\nDocuments after adding:")
    for d in manager.list_documents():
        print(f"- {d['id']}: {d['title']}")

    retrieved_doc = manager.get_document(new_id)
    print(f"\nRetrieved document {new_id}: {retrieved_doc['title'] if retrieved_doc else 'Not found'}")

    search_results = manager.search_documents("Test Document")
    print("\nSearch results for 'Test Document':")
    for d in search_results:
        print(f"- {d['id']}: {d['title']}")

    # Clean up the test file
    if os.path.exists(test_file):
        os.remove(test_file)
    logger.info("DocumentManager test finished.")

pass
