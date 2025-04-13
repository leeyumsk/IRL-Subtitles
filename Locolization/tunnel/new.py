import requests
import socket
import threading
import time
import sys

def fetch_and_forward_audio(client_socket):
    """
    Fetches audio from ESP32 and forwards only the raw audio bytes to ODAS
    """
    # ESP32 endpoint
    esp32_url = "http://192.168.4.254/ach1"
    
    try:
        print("Connecting to ESP32 stream...")
        response = requests.get(esp32_url, stream=True)
        
        if response.status_code == 200:
            print("Successfully connected to ESP32 stream")
            print(f"Content-Type: {response.headers.get('Content-Type', 'unknown')}")
            
            # Forward the raw audio bytes to ODAS
            try:
                chunks_sent = 0
                for chunk in response.iter_content(chunk_size=4096):
                    if chunk:
                        # Send only the raw audio bytes to ODAS
                        client_socket.sendall(chunk)
                        chunks_sent += 1
                        if chunks_sent % 100 == 0:
                            print(f"Sent {chunks_sent} chunks to ODAS")
            except socket.error as e:
                print(f"Error while sending data to ODAS: {e}")
            finally:
                print("ODAS client disconnected")
                client_socket.close()
        else:
            print(f"Failed to connect to ESP32: HTTP {response.status_code}")
            client_socket.close()
            
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to ESP32: {e}")
        client_socket.close()

def start_raw_audio_server():
    """
    Starts a server that accepts connections from ODAS and forwards raw audio
    """
    # Update this to match your ODAS config
    server_host = '127.0.0.1'  # Listen on all interfaces
    server_port = 1001       # Match the port in your ODAS config
    
    # Create server socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind((server_host, server_port))
        server_socket.listen(1)  # Only need to accept one connection from ODAS
        print(f"Raw audio server listening on {server_host}:{server_port}")
        print("Waiting for ODAS to connect...")
        
        while True:
            # Wait for ODAS to connect
            client_socket, client_address = server_socket.accept()
            print(f"ODAS connected from {client_address}")
            
            # Handle ODAS connection in a new thread
            client_thread = threading.Thread(
                target=fetch_and_forward_audio,
                args=(client_socket,)
            )
            client_thread.daemon = True
            client_thread.start()
            
    except socket.error as e:
        print(f"Server socket error: {e}")
    except KeyboardInterrupt:
        print("Server shutting down...")
    finally:
        server_socket.close()
        print("Server closed")

def connect_to_odas():
    """
    Alternative approach: Connect to ODAS directly instead of waiting for it
    """
    odas_host = '172.28.16.1'  # Use the IP from your ODAS config
    odas_port = 1001           # Use the port from your ODAS config
    
    print(f"Attempting to connect to ODAS at {odas_host}:{odas_port}...")
    
    # Create socket to connect to ODAS
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    retry_count = 0
    max_retries = 5
    retry_delay = 2  # seconds
    
    while retry_count < max_retries:
        try:
            retry_count += 1
            print(f"Attempt {retry_count}: Connecting to ODAS...")
            client_socket.connect((odas_host, odas_port))
            print("Connected to ODAS successfully!")
            
            # Start fetching and forwarding audio
            fetch_and_forward_audio(client_socket)
            break
            
        except socket.error as e:
            print(f"Attempt {retry_count}: Failed to connect to ODAS: {e}")
            if retry_count < max_retries:
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print("Max retry attempts reached. Please check if ODAS is running.")

if __name__ == "__main__":
    print("Starting ESP32 to ODAS raw audio bridge")
    print("This script connects to ESP32 HTTP audio stream")
    
    # Uncomment one of these based on your setup:
    
    # If ODAS is expected to connect to this script:
    start_raw_audio_server()
    
    # If this script should connect to ODAS:
    # connect_to_odas()