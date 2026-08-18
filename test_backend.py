#!/usr/bin/env python3
"""
Test script for Command Center Backend API
"""
import requests
import json

def test_health_endpoint():
    """Test the health check endpoint"""
    url = "http://localhost:8000/api/health"
    try:
        response = requests.get(url)
        print(f"Health Check Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error calling health endpoint: {e}")
        return False

def test_query_endpoint():
    """Test the query endpoint with a sample SPM question"""
    url = "http://localhost:8000/api/query"
    payload = {
        "query": "How to handle G3 RMS decision upload failures?",
        "team_id": "spm-team",
        "confidence_threshold": 5,
        "max_results": 10
    }
    try:
        response = requests.post(url, json=payload)
        print(f"\nQuery Status Code: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Query: {result.get('query')}")
            print(f"Total Results: {result.get('total_results')}")
            print(f"Execution Time: {result.get('execution_time_ms')} ms")
            if 'results' in result and len(result['results']) > 0:
                print("\nSample Result:")
                for i, doc in enumerate(result['results'][:2]):
                    print(f"  Document {i+1}:")
                    print(f"    Title: {doc.get('title')}")
                    print(f"    Score: {doc.get('score')}")
                    print(f"    Confidence: {doc.get('confidence_level')}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error calling query endpoint: {e}")
        return False

if __name__ == "__main__":
    print("Testing Command Center Backend API...\n")
    
    health_ok = test_health_endpoint()
    query_ok = test_query_endpoint()
    
    print("\n" + "="*50)
    if health_ok and query_ok:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed")
        if not health_ok:
            print("  - Health endpoint failed")
        if not query_ok:
            print("  - Query endpoint failed")
