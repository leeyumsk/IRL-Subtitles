import requests
import socket
import threading
import time
import sys

def fetch_and_forward_audio():
    """
    Fetches audio from ESP32 and forwards raw audio bytes to ODAS via localhost socket
    """
    # ESP32 endpoint
    esp32_url = "http://192.168.4.254/ach1"
    
    # ODAS socket configuration (localhost)
    odas_host = '172.28.16.1'
    odas_port = 12346  # Make sure this matches the port in your ODAS config
    
    # Connect to ODAS with retry
    odas_socket = None
    connected = False
    retry_count = 0
    
    while not connected:
        try:
            # Create socket connection to ODAS
            odas_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            odas_socket.connect((odas_host, odas_port))
            connected = True
            print(f"Successfully connected to ODAS at {odas_host}:{odas_port}")
        except socket.error as e:
            retry_count += 1
            print(f"Attempt {retry_count}: Failed to connect to ODAS: {e}")
            print("Retrying in 3 seconds...")
            # Close socket if it was created
            if odas_socket:
                odas_socket.close()
            time.sleep(3)
    
    try:
        # Connect to ESP32 stream
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
                        # Send raw audio bytes to ODAS via localhost socket
                        odas_socket.sendall(chunk)
                        chunks_sent += 1
                        if chunks_sent % 100 == 0:
                            print(f"Sent {chunks_sent} chunks to ODAS")
            except socket.error as e:
                print(f"Error while sending data to ODAS: {e}")
            finally:
                print("Closing connection to ODAS")
                if odas_socket:
                    odas_socket.close()
        else:
            print(f"Failed to connect to ESP32: HTTP {response.status_code}")
            if odas_socket:
                odas_socket.close()
            
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to ESP32: {e}")
    except KeyboardInterrupt:
        print("Stream forwarding interrupted")
    finally:
        try:
            if odas_socket:
                odas_socket.close()
        except:
            pass

def main():
    print("Starting ESP32 to ODAS raw audio bridge")
    print("This script connects to ESP32 HTTP audio stream")
    print("and forwards raw audio bytes to ODAS via localhost socket")
    
    try:
        # Start the audio forwarding process
        fetch_and_forward_audio()
    except KeyboardInterrupt:
        print("Program terminated by user")

if __name__ == "__main__":
    main()