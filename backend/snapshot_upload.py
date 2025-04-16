import requests
import json
import time

# Configuration
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
SNAPSHOT_FILENAME = "my_collection-1903078838920009-2025-04-14-05-26-09.snapshot"
TARGET_COLLECTION_NAME = "restored_collection_name"

def main():
    # Step 1: Delete the collection if it exists
    print(f"Checking if collection '{TARGET_COLLECTION_NAME}' exists...")
    response = requests.get(f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections")
    
    if response.status_code == 200:
        # Parse the response carefully and debug its structure
        response_data = response.json()
        print(f"Got collections response: {json.dumps(response_data, indent=2)[:200]}...")
        
        # Correctly extract collection names based on the actual API response format
        if 'result' in response_data:
            collections = response_data['result']
            
            # Handle different possible formats of the collections list
            collection_names = []
            if isinstance(collections, list):
                # Try to extract names carefully
                for c in collections:
                    if isinstance(c, dict) and 'name' in c:
                        collection_names.append(c['name'])
                    elif isinstance(c, str):
                        collection_names.append(c)
            
            print(f"Found collections: {collection_names}")
            
            if TARGET_COLLECTION_NAME in collection_names:
                print(f"Collection '{TARGET_COLLECTION_NAME}' exists, deleting it...")
                delete_response = requests.delete(
                    f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{TARGET_COLLECTION_NAME}"
                )
                print(f"Delete response: {delete_response.status_code}")
                if delete_response.status_code >= 400:
                    print(f"Error deleting collection: {delete_response.text}")
                    return
                time.sleep(2)  # Give the server time to process the deletion
        else:
            print("Response doesn't contain 'result' key. Full response:")
            print(json.dumps(response_data, indent=2))
    else:
        print(f"Error getting collections: {response.status_code}, {response.text}")
    
    # Step 2: Create a new collection (we'll use a basic vector configuration)
    print(f"\nCreating collection '{TARGET_COLLECTION_NAME}'...")
    create_payload = {
        "vectors": {
            "size": 1536,  # Common size for embeddings, adjust if needed
            "distance": "Cosine"
        }
    }
    
    create_response = requests.put(
        f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{TARGET_COLLECTION_NAME}",
        json=create_payload
    )
    
    print(f"Create response status: {create_response.status_code}")
    print(f"Create response: {create_response.text}")
    
    if create_response.status_code >= 400:
        print(f"Error creating collection: {create_response.text}")
        return
    
    print(f"Collection created successfully.")
    time.sleep(2)  # Give the server time to fully create the collection
    
    # Step 3: Attempt recovery with different URL formats
    url_formats = [
        f"file:///qdrant/snapshots/{SNAPSHOT_FILENAME}",
        f"/qdrant/snapshots/{SNAPSHOT_FILENAME}",
        SNAPSHOT_FILENAME,
        f"snapshots/{SNAPSHOT_FILENAME}"
    ]
    
    for url_format in url_formats:
        print(f"\nAttempting recovery with location: {url_format}")
        recovery_payload = {
            "location": url_format
        }
        
        recovery_url = f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{TARGET_COLLECTION_NAME}/snapshots/recover"
        recovery_response = requests.put(recovery_url, json=recovery_payload)
        
        print(f"Response status: {recovery_response.status_code}")
        print(f"Response: {recovery_response.text}")
        
        if recovery_response.status_code < 400:
            print("\nRecovery initiated successfully!")
            print("Waiting for collection to be ready...")
            
            # Wait and check collection status
            time.sleep(5)
            check_response = requests.get(
                f"http://{QDRANT_HOST}:{QDRANT_PORT}/collections/{TARGET_COLLECTION_NAME}"
            )
            
            if check_response.status_code == 200:
                collection_info = check_response.json().get('result', {})
                print(f"Collection info: {json.dumps(collection_info, indent=2)}")
                
                # Try to extract collection status and points count based on the API response format
                status = None
                points_count = 0
                
                if isinstance(collection_info, dict):
                    status = collection_info.get('status')
                    vectors_info = collection_info.get('vectors', {})
                    if isinstance(vectors_info, dict):
                        points_count = vectors_info.get('total_vector_count', 0)
                
                print(f"Collection status: {status}")
                print(f"Points count: {points_count}")
                
                if points_count > 0:
                    print("\nSUCCESS! Collection restored successfully.")
                    return
                else:
                    print("Warning: Collection was created but appears to be empty.")
                    print("It might still be loading, check status again after a few minutes.")
            else:
                print(f"Error checking collection status: {check_response.text}")
            
            # Even if points count is 0, we'll consider this URL format successful
            # since the API accepted it, and break the loop
            break
            
        # If we get here, recovery with this format failed, try the next one
    
    print("\nRecovery attempts complete. If the collection appears empty, wait a few minutes")
    print("and check again as large snapshots may take time to fully restore.")
    print("\nTo check status, run: curl http://localhost:6333/collections/restored_collection_name")

if __name__ == "__main__":
    main()