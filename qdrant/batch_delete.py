from qdrant_client import QdrantClient

def delete_vectors_in_batches(collection_name, ids, batch_size=10):

    client = QdrantClient(host="192.168.0.230", port=6333) 
    total_vectors = len(ids)
    print(f"Total vectors to delete: {total_vectors}")

    for start in range(0, total_vectors, batch_size):
        end = min(start + batch_size, total_vectors)
        batch = ids[start:end]
        client.delete(collection_name=collection_name, points_selector=list(batch))
        print(f"Deleted batch {start // batch_size + 1}: {len(batch)} vectors")
    
    print("All batches processed.")


collection_name = "test_collection"
vector_ids = range(1, 500)  

delete_vectors_in_batches(collection_name, vector_ids)