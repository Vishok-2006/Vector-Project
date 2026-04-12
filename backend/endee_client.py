import os
from endee import Endee, Precision

ENDEE_HOST = os.getenv("ENDEE_HOST", "localhost")
ENDEE_PORT = os.getenv("ENDEE_PORT", "8080")
ENDEE_URL = f"http://{ENDEE_HOST}:{ENDEE_PORT}/api/v1"
INDEX_NAME = "pdf_rag_index"
VECTOR_DIMENSION = 384

client = Endee()
client.set_base_url(ENDEE_URL)

def get_or_create_index():
    try:
         return client.get_index(name=INDEX_NAME)
    except Exception:
         client.create_index(
             name=INDEX_NAME,
             dimension=VECTOR_DIMENSION,
             space_type="cosine",
             precision=Precision.FLOAT32
         )
         return client.get_index(name=INDEX_NAME)

def upsert_vectors(chunks, embeddings):
    """
    chunks: list of dicts {id, text, metadata:{filename, page}}
    embeddings: list of vectors (float arrays)
    """
    index = get_or_create_index()
    records = []
    
    for chunk, emb in zip(chunks, embeddings):
         records.append({
             "id": chunk["id"],
             "vector": emb,
             "meta": {
                 "text": chunk["text"],
                 "filename": chunk["metadata"]["filename"],
                 "page": chunk["metadata"].get("page", 0)
             },
             "filter": {
                 "filename": chunk["metadata"]["filename"]
             }
         })
         
    # Upsert in batches of 500
    for i in range(0, len(records), 500):
         index.upsert(records[i:i+500])

def search_similar(query_vector, top_k=5):
    index = get_or_create_index()
    results = index.query(
        vector=query_vector,
        top_k=top_k,
        ef=128,
        include_vectors=False
    )
    return results
