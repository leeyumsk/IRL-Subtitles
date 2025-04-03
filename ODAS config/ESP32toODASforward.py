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
    # Listen on all interfaces
    server_host = '192.168.4.2'
    # Use port 9001 as specified in your config
    server_port = 9001
    
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

if __name__ == "__main__":
    print("Starting ESP32 to ODAS raw audio bridge")
    print("This script connects to ESP32 HTTP audio stream")
    print("and forwards raw audio bytes to ODAS when it connects")
    start_raw_audio_server()