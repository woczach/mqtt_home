import random
import json
def generate_random_vectors(num_vectors=10000, vector_dim=4):
    cities = ["Berlin", "London", "Moscow", "Paris", "New York"]
    data = []

    for i in range(1, num_vectors + 1):
        vector = [round(random.uniform(0, 1), 2) for _ in range(vector_dim)]  # Generate random vector
        payload = {}


        payload["city"] = random.sample(cities, random.randint(1, 3))  # Random cities


        entry = {"id": i, "vector": vector}
        if payload:
            entry["payload"] = payload
        data.append(entry)
    
    return data

# Example usage
random_vectors = generate_random_vectors()
print(json.dumps(random_vectors[:500]))  # Print first 5 entries as a sample