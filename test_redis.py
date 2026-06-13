import redis

# Connect to local Valkey
client = redis.Redis(host='127.0.0.1', port=6379, decode_responses=True)

if __name__ == "__main__":
    client.set('key', 'hello')
    print(client.get('key'))  # Outputs: hello