import uuid
from typing import Optional
class Document:
    def __init__(self, page_content: str, metadata: dict, id: Optional[str] = None):
        self.page_content = page_content
        self.metadata = metadata
        self.id = id or str(uuid.uuid4())

    def __repr__(self):
        return f"Document(source={self.metadata.get('source_file', 'N/A')}, length={len(self.page_content)})"
