import requests

def download_audio(url, filename):
    """Downloads audio from a URL and saves it as a file."""

    response = requests.get(url)

    if response.status_code == 200:
        with open(filename, 'wb') as f:
            f.write(response.content)
        print(f"Audio file downloaded: {filename}")
    else:
        print(f"Failed to download audio: {response.status_code}")

# Example usage
url = "http://192.168.4.1"
filename = "audio.mp3"
download_audio(url, filename)