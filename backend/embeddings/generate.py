from sentence_transformers import SentenceTransformer
import warnings
warnings.filterwarnings("ignore")

# Using the fast mini LM model - produces 384 dimensional embeddings
model = SentenceTransformer('all-MiniLM-L6-v2')

def get_embeddings(texts):
    """
    Returns a list of vectors for the given text chunks.
    """
    embeddings = model.encode(texts, show_progress_bar=False)
    return embeddings.tolist()

def get_query_embedding(query):
     return model.encode(query, show_progress_bar=False).tolist()
